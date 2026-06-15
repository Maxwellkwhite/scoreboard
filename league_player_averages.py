"""Qualified MLB player league stat pools via pybaseball (daily JSON cache)."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pybaseball import batting_stats_bref, pitching_stats_bref

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "league_player_averages"
_BUILD_WAIT_SECONDS = 180
_BUILD_POLL_SECONDS = 0.5
_MEMORY_TTL_SECONDS = 3600

_BREF_BATTING_MAP = {
    "BA": "avg",
    "OBP": "onBasePct",
    "SLG": "slugAvg",
    "OPS": "OPS",
    "R": "runs",
    "H": "hits",
    "2B": "doubles",
    "3B": "triples",
    "HR": "homeRuns",
    "RBI": "RBIs",
    "BB": "walks",
    "SO": "strikeouts",
    "SB": "stolenBases",
    "AB": "atBats",
    "PA": "plateAppearances",
}

_BREF_PITCHING_MAP = {
    "ERA": "ERA",
    "WHIP": "WHIP",
    "IP": "innings",
    "W": "wins",
    "L": "losses",
    "SV": "saves",
    "SO": "strikeouts",
    "BB": "walks",
    "H": "hits",
    "ER": "earnedRuns",
    "HR": "homeRuns",
    "SO9": "strikeoutsPerNineInnings",
}

_FANGRAPHS_BATTING_MAP = {
    "AVG": "avg",
    "OBP": "onBasePct",
    "SLG": "slugAvg",
    "OPS": "OPS",
    "R": "runs",
    "H": "hits",
    "2B": "doubles",
    "3B": "triples",
    "HR": "homeRuns",
    "RBI": "RBIs",
    "BB": "walks",
    "SO": "strikeouts",
    "SB": "stolenBases",
    "AB": "atBats",
    "PA": "plateAppearances",
}

_FANGRAPHS_PITCHING_MAP = {
    "ERA": "ERA",
    "WHIP": "WHIP",
    "IP": "innings",
    "W": "wins",
    "L": "losses",
    "SV": "saves",
    "SO": "strikeouts",
    "BB": "walks",
    "H": "hits",
    "ER": "earnedRuns",
    "HR": "homeRuns",
    "K/9": "strikeoutsPerNineInnings",
}

_memory_cache: dict[str, tuple[float, dict[str, dict[str, list[float]]]]] = {}
_batting_bref_cache: dict[int, pd.DataFrame] = {}
_pitching_bref_cache: dict[int, pd.DataFrame] = {}


def _parse_number(value: Any) -> float | None:
    from team_stats import _parse_number as parse_number

    return parse_number(value)


def _ip_to_outs(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if "." in text:
        whole, fraction = text.split(".", 1)
        outs = int(whole or 0) * 3
        if fraction:
            outs += int(fraction[0])
        return float(outs)
    return float(text) * 3.0


def _filter_bref_mlb_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "Lev" not in frame.columns:
        return frame
    return frame[frame["Lev"].astype(str).str.startswith("Maj")].copy()


def _get_batting_bref_season(year: int) -> pd.DataFrame:
    cached = _batting_bref_cache.get(year)
    if cached is not None:
        return cached
    frame = batting_stats_bref(year)
    _batting_bref_cache[year] = frame
    return frame


def _get_pitching_bref_season(year: int) -> pd.DataFrame:
    cached = _pitching_bref_cache.get(year)
    if cached is not None:
        return cached
    frame = pitching_stats_bref(year)
    _pitching_bref_cache[year] = frame
    return frame


def _estimate_team_games_played(
    batting_frame: pd.DataFrame,
    pitching_frame: pd.DataFrame,
    season_year: int,
) -> int:
    games = 0
    for frame in (batting_frame, pitching_frame):
        if frame is None or frame.empty or "G" not in frame.columns:
            continue
        max_games = pd.to_numeric(frame["G"], errors="coerce").max()
        if pd.notna(max_games):
            games = max(games, int(max_games))
    if games > 0:
        return games
    today = date.today()
    if season_year < today.year:
        return 162
    if season_year > today.year:
        return 1
    opening_day = date(season_year, 3, 28)
    if today < opening_day:
        return 1
    days_elapsed = (today - opening_day).days
    return max(1, min(162, round(days_elapsed * 162 / 185)))


def _qualifying_thresholds(games: int) -> tuple[int, float]:
    qual_pa = max(1, round(502 * games / 162))
    qual_ip = max(1.0, round(162 * games / 162 * 10) / 10)
    return qual_pa, qual_ip


def _frame_league_stats(
    frame: pd.DataFrame,
    column_map: dict[str, str],
) -> dict[str, list[float]]:
    league_stats: dict[str, list[float]] = {}
    for column, stat_name in column_map.items():
        if column not in frame.columns:
            continue
        values: list[float] = []
        for raw_value in frame[column]:
            number = _parse_number(raw_value)
            if number is not None:
                values.append(number)
        if values:
            league_stats[stat_name] = values
    return league_stats


def _filter_qualified_batting(frame: pd.DataFrame, qual_pa: int) -> pd.DataFrame:
    if frame.empty or "PA" not in frame.columns:
        return frame
    pa = pd.to_numeric(frame["PA"], errors="coerce")
    return frame[pa >= qual_pa].copy()


def _filter_qualified_pitching(frame: pd.DataFrame, qual_ip: float) -> pd.DataFrame:
    if frame.empty or "IP" not in frame.columns:
        return frame
    min_outs = qual_ip * 3.0
    mask = frame["IP"].apply(lambda value: _ip_to_outs(value) >= min_outs)
    return frame[mask].copy()


def _build_from_fangraphs(season_year: int) -> dict[str, dict[str, list[float]]]:
    from pybaseball import batting_stats, pitching_stats

    batting_frame = batting_stats(season_year, qual=1)
    pitching_frame = pitching_stats(season_year, season_year, qual=1)
    return {
        "batting": _frame_league_stats(batting_frame, _FANGRAPHS_BATTING_MAP),
        "pitching": _frame_league_stats(pitching_frame, _FANGRAPHS_PITCHING_MAP),
    }


def _build_from_bref(season_year: int) -> dict[str, dict[str, list[float]]]:
    batting_frame = _filter_bref_mlb_frame(_get_batting_bref_season(season_year))
    pitching_frame = _filter_bref_mlb_frame(_get_pitching_bref_season(season_year))
    games = _estimate_team_games_played(batting_frame, pitching_frame, season_year)
    qual_pa, qual_ip = _qualifying_thresholds(games)
    batting_frame = _filter_qualified_batting(batting_frame, qual_pa)
    pitching_frame = _filter_qualified_pitching(pitching_frame, qual_ip)
    return {
        "batting": _frame_league_stats(batting_frame, _BREF_BATTING_MAP),
        "pitching": _frame_league_stats(pitching_frame, _BREF_PITCHING_MAP),
        "_meta": {
            "source": "baseball_reference",
            "qual_pa": qual_pa,
            "qual_ip": qual_ip,
            "games": games,
        },
    }


def _build_league_stats(season_year: int) -> dict[str, Any]:
    try:
        stats = _build_from_fangraphs(season_year)
        if stats.get("batting") or stats.get("pitching"):
            stats["_meta"] = {"source": "fangraphs", "qual": 1}
            return stats
    except Exception:
        pass
    return _build_from_bref(season_year)


def _cache_file_path(season_year: int, cache_date: str) -> Path:
    return _DATA_DIR / str(season_year) / f"{cache_date}.json"


def _lock_file_path(season_year: int, cache_date: str) -> Path:
    return _DATA_DIR / str(season_year) / f"{cache_date}.lock"


def _payload_has_data(payload: dict[str, Any]) -> bool:
    batting = payload.get("batting") or {}
    pitching = payload.get("pitching") or {}
    batting_count = len((batting.get("avg") or batting.get("OPS") or []))
    pitching_count = len((pitching.get("ERA") or pitching.get("WHIP") or []))
    return batting_count > 0 or pitching_count > 0


def _payload_from_league_stats(
    season_year: int,
    cache_date: str,
    league_stats: dict[str, Any],
) -> dict[str, Any]:
    meta = league_stats.pop("_meta", {})
    return {
        "date": cache_date,
        "season_year": season_year,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "batting": league_stats.get("batting") or {},
        "pitching": league_stats.get("pitching") or {},
    }


def _league_stats_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, list[float]]]:
    return {
        "batting": {
            stat: [float(value) for value in values]
            for stat, values in (payload.get("batting") or {}).items()
        },
        "pitching": {
            stat: [float(value) for value in values]
            for stat, values in (payload.get("pitching") or {}).items()
        },
    }


def _load_payload_from_disk(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to read league cache %s: %s", path, exc)
        return None
    if not _payload_has_data(payload):
        logger.warning("League cache %s is empty; rebuilding", path)
        return None
    return payload


def _save_payload(payload: dict[str, Any]) -> None:
    season_year = payload["season_year"]
    cache_date = payload["date"]
    path = _cache_file_path(season_year, cache_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    encoded = json.dumps(payload, separators=(",", ":"))
    tmp_path.write_text(encoded, encoding="utf-8")
    os.replace(tmp_path, path)
    logger.info("Wrote league player cache to %s (%d bytes)", path, len(encoded))


def _wait_for_cache_file(path: Path, lock_path: Path) -> dict[str, Any] | None:
    deadline = time.time() + _BUILD_WAIT_SECONDS
    while time.time() < deadline:
        payload = _load_payload_from_disk(path)
        if payload is not None:
            return payload
        if not lock_path.exists():
            return None
        time.sleep(_BUILD_POLL_SECONDS)
    payload = _load_payload_from_disk(path)
    if payload is not None:
        return payload
    logger.warning("Timed out waiting for league cache build at %s", path)
    return None


def _try_acquire_build_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
        lock_file.write(
            json.dumps({
                "pid": os.getpid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        )
    return True


def _build_and_save_league_cache(
    season_year: int,
    cache_date: str,
    *,
    path: Path,
    lock_path: Path,
) -> dict[str, dict[str, list[float]]]:
    if not _try_acquire_build_lock(lock_path):
        payload = _wait_for_cache_file(path, lock_path)
        if payload is not None:
            return _league_stats_from_payload(payload)
        raise RuntimeError(f"Another worker is building league cache at {path}")

    try:
        logger.info("Building league player cache for %s season %s", cache_date, season_year)
        built = _build_league_stats(season_year)
        payload = _payload_from_league_stats(season_year, cache_date, built)
        if not _payload_has_data(payload):
            raise RuntimeError("League stats build returned no qualified player data")
        _save_payload(payload)
        return _league_stats_from_payload(payload)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def warm_league_cache_for_today(season_year: int | None = None) -> bool:
    """Build today's league cache file if missing (safe to call on app startup)."""
    year = season_year or date.today().year
    result = get_league_player_stats_by_category(year)
    has_data = bool((result.get("batting") or {}) or (result.get("pitching") or {}))
    if has_data:
        logger.info("League cache ready for season %s", year)
    else:
        logger.warning("League cache warm-up produced no data for season %s", year)
    return has_data


def get_league_player_stats_by_category(
    season_year: int,
    *,
    cache_date: str | None = None,
) -> dict[str, dict[str, list[float]]]:
    """Qualified MLB player distributions for stat-bar comparisons (cached per day)."""
    cache_date = cache_date or date.today().isoformat()
    mem_key = f"{season_year}:{cache_date}"
    cached = _memory_cache.get(mem_key)
    now = time.time()
    if cached and now - cached[0] < _MEMORY_TTL_SECONDS:
        return cached[1]

    path = _cache_file_path(season_year, cache_date)
    lock_path = _lock_file_path(season_year, cache_date)

    payload = _load_payload_from_disk(path)
    if payload is not None:
        result = _league_stats_from_payload(payload)
        _memory_cache[mem_key] = (now, result)
        return result

    if lock_path.exists():
        payload = _wait_for_cache_file(path, lock_path)
        if payload is not None:
            result = _league_stats_from_payload(payload)
            _memory_cache[mem_key] = (time.time(), result)
            return result

    try:
        result = _build_and_save_league_cache(
            season_year,
            cache_date,
            path=path,
            lock_path=lock_path,
        )
    except Exception:
        logger.exception(
            "Failed to build league player cache for season %s on %s",
            season_year,
            cache_date,
        )
        return {"batting": {}, "pitching": {}}

    _memory_cache[mem_key] = (time.time(), result)
    return result
