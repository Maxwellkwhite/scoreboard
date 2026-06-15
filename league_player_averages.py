"""Qualified MLB player league stat pools via pybaseball (daily JSON cache)."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pybaseball import batting_stats_bref, pitching_stats_bref

_DATA_DIR = Path(__file__).resolve().parent / "data" / "league_player_averages"

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


def _save_payload(payload: dict[str, Any]) -> None:
    season_year = payload["season_year"]
    cache_date = payload["date"]
    path = _cache_file_path(season_year, cache_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


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
    if cached and now - cached[0] < 3600:
        return cached[1]

    path = _cache_file_path(season_year, cache_date)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result = _league_stats_from_payload(payload)
            _memory_cache[mem_key] = (now, result)
            return result
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    built = _build_league_stats(season_year)
    payload = _payload_from_league_stats(season_year, cache_date, built)
    try:
        _save_payload(payload)
    except OSError:
        pass

    result = _league_stats_from_payload(payload)
    _memory_cache[mem_key] = (now, result)
    return result
