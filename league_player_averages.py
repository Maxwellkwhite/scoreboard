"""League-average stat pools for player and team comparison bars (JSON cache files)."""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "league_player_averages"
_MASTER_CACHE_PATH = _DATA_DIR / "league_player_averages.json"
_MASTER_LOCK_PATH = _DATA_DIR / "league_player_averages.lock"
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
    from pybaseball import batting_stats_bref

    frame = batting_stats_bref(year)
    _batting_bref_cache[year] = frame
    return frame


def _get_pitching_bref_season(year: int) -> pd.DataFrame:
    cached = _pitching_bref_cache.get(year)
    if cached is not None:
        return cached
    from pybaseball import pitching_stats_bref

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


def _empty_store() -> dict[str, Any]:
    return {"seasons": {}}


def _load_store() -> dict[str, Any]:
    if not _MASTER_CACHE_PATH.is_file():
        return _empty_store()
    try:
        store = json.loads(_MASTER_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to read league cache %s: %s", _MASTER_CACHE_PATH, exc)
        return _empty_store()
    if not isinstance(store.get("seasons"), dict):
        return _empty_store()
    return store


def _save_store(store: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _MASTER_CACHE_PATH.with_suffix(".json.tmp")
    encoded = json.dumps(store, separators=(",", ":"))
    tmp_path.write_text(encoded, encoding="utf-8")
    os.replace(tmp_path, _MASTER_CACHE_PATH)
    logger.info("Wrote league player cache to %s (%d bytes)", _MASTER_CACHE_PATH, len(encoded))


def _season_needs_refresh(entry: dict[str, Any] | None) -> bool:
    return entry is None or not _payload_has_data(entry)


def _import_legacy_season(season_year: int) -> dict[str, Any] | None:
    """One-time import from old per-year daily JSON files, if present."""
    year_dir = _DATA_DIR / str(season_year)
    if not year_dir.is_dir():
        return None
    candidates = sorted(
        (
            path
            for path in year_dir.glob("*.json")
            if not path.name.endswith(".tmp")
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            continue
        if _payload_has_data(payload):
            logger.info("Imported legacy league cache for %s from %s", season_year, path)
            return payload
    return None


def _try_acquire_build_lock() -> bool:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(_MASTER_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
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


def _release_build_lock() -> None:
    try:
        _MASTER_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _wait_for_store_season(season_year: int) -> dict[str, Any] | None:
    deadline = time.time() + _BUILD_WAIT_SECONDS
    key = str(season_year)
    while time.time() < deadline:
        entry = (_load_store().get("seasons") or {}).get(key)
        if entry is not None and _payload_has_data(entry):
            return entry
        if not _MASTER_LOCK_PATH.exists():
            return None
        time.sleep(_BUILD_POLL_SECONDS)
    entry = (_load_store().get("seasons") or {}).get(key)
    if entry is not None and _payload_has_data(entry):
        return entry
    logger.warning(
        "Timed out waiting for league cache season %s in %s",
        season_year,
        _MASTER_CACHE_PATH,
    )
    return None


def _build_season_entry(season_year: int, cache_date: str) -> dict[str, Any]:
    logger.info("Building league player cache for season %s", season_year)
    built = _build_league_stats(season_year)
    payload = _payload_from_league_stats(season_year, cache_date, built)
    if not _payload_has_data(payload):
        raise RuntimeError("League stats build returned no qualified player data")
    return payload


def _ensure_season_entry(
    season_year: int,
    cache_date: str,
    *,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    key = str(season_year)
    store = _load_store()
    seasons = store.setdefault("seasons", {})
    entry = seasons.get(key)

    if not force_rebuild and not _season_needs_refresh(entry):
        return entry

    if not force_rebuild and entry is None:
        legacy = _import_legacy_season(season_year)
        if legacy is not None:
            seasons[key] = legacy
            _save_store(store)
            return legacy

    if not _try_acquire_build_lock():
        waited = _wait_for_store_season(season_year)
        if waited is not None:
            return waited
        raise RuntimeError(f"Another worker is building league cache at {_MASTER_CACHE_PATH}")

    try:
        store = _load_store()
        seasons = store.setdefault("seasons", {})
        entry = seasons.get(key)
        if not force_rebuild and not _season_needs_refresh(entry):
            return entry

        if not force_rebuild and entry is None:
            legacy = _import_legacy_season(season_year)
            if legacy is not None:
                seasons[key] = legacy
                _save_store(store)
                return legacy

        entry = _build_season_entry(season_year, cache_date)
        seasons[key] = entry
        _save_store(store)
        return entry
    finally:
        _release_build_lock()


def _read_season_entry(season_year: int) -> dict[str, Any] | None:
    """Return a cached player season entry without triggering a build."""
    key = str(season_year)
    entry = (_load_store().get("seasons") or {}).get(key)
    if entry is None or not _payload_has_data(entry):
        return None
    return entry


def _read_best_season_entry(
    season_year: int,
    store: dict[str, Any],
    *,
    has_data: Any,
) -> dict[str, Any] | None:
    """Prefer the requested season; otherwise use the newest cached season with data."""
    key = str(season_year)
    entry = (store.get("seasons") or {}).get(key)
    if entry is not None and has_data(entry):
        return entry

    best_entry: dict[str, Any] | None = None
    best_year: int | None = None
    for year_key, payload in (store.get("seasons") or {}).items():
        if not has_data(payload):
            continue
        try:
            year_num = int(year_key)
        except (TypeError, ValueError):
            continue
        if best_year is None or year_num > best_year:
            best_year = year_num
            best_entry = payload
    return best_entry


def warm_league_caches(season_year: int | None = None) -> bool:
    """Rebuild league comparison caches on every app startup."""
    year = season_year or date.today().year
    player = get_league_player_stats_by_category(
        year,
        allow_build=True,
        force_rebuild=True,
    )
    team = get_league_team_stats_by_category(
        year,
        allow_build=True,
        force_rebuild=True,
    )
    player_ok = bool((player.get("batting") or {}) or (player.get("pitching") or {}))
    team_ok = any((team.get(category) or {}) for category in ("batting", "pitching", "fielding"))
    if player_ok and team_ok:
        logger.info("League caches ready for season %s", year)
    else:
        logger.warning(
            "League cache warm-up incomplete for season %s (player=%s team=%s)",
            year,
            player_ok,
            team_ok,
        )
    return player_ok and team_ok


def warm_league_cache_for_today(season_year: int | None = None) -> bool:
    return warm_league_caches(season_year)


def get_league_player_stats_by_category(
    season_year: int,
    *,
    cache_date: str | None = None,
    allow_build: bool = False,
    force_rebuild: bool = False,
) -> dict[str, dict[str, list[float]]]:
    """Qualified MLB player distributions for stat-bar comparisons.

    Cached in data/league_player_averages/league_player_averages.json.
    Startup always rebuilds the current season; web requests read the cached file
    and use the most recent season entry available (date on the entry is ignored).
    """
    cache_date = cache_date or date.today().isoformat()
    mem_key = str(season_year)
    cached = _memory_cache.get(mem_key)
    now = time.time()
    if cached and now - cached[0] < _MEMORY_TTL_SECONDS:
        return cached[1]

    try:
        if allow_build:
            entry = _ensure_season_entry(
                season_year,
                cache_date,
                force_rebuild=force_rebuild,
            )
        else:
            entry = _read_best_season_entry(
                season_year,
                _load_store(),
                has_data=_payload_has_data,
            )
            if entry is None:
                return {"batting": {}, "pitching": {}}
        result = _league_stats_from_payload(entry)
    except Exception:
        logger.exception(
            "Failed to load league player cache for season %s",
            season_year,
        )
        return {"batting": {}, "pitching": {}}

    _memory_cache[mem_key] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Team league averages (ESPN, 30-team pools for team stat bars)
# ---------------------------------------------------------------------------

_TEAM_DATA_DIR = Path(__file__).resolve().parent / "data" / "league_team_averages"
_TEAM_MASTER_CACHE_PATH = _TEAM_DATA_DIR / "league_team_averages.json"
_TEAM_MASTER_LOCK_PATH = _TEAM_DATA_DIR / "league_team_averages.lock"

_team_memory_cache: dict[str, tuple[float, dict[str, dict[str, list[float]]]]] = {}


def _team_payload_has_data(payload: dict[str, Any]) -> bool:
    for category in ("batting", "pitching", "fielding"):
        bucket = payload.get(category) or {}
        for values in bucket.values():
            if values:
                return True
    return False


def _team_payload_from_league_stats(
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
        "fielding": league_stats.get("fielding") or {},
    }


def _team_league_stats_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, list[float]]]:
    result: dict[str, dict[str, list[float]]] = {}
    for category in ("batting", "pitching", "fielding"):
        result[category] = {
            stat: [float(value) for value in values]
            for stat, values in (payload.get(category) or {}).items()
        }
    return result


def _team_empty_store() -> dict[str, Any]:
    return {"seasons": {}}


def _team_load_store() -> dict[str, Any]:
    if not _TEAM_MASTER_CACHE_PATH.is_file():
        return _team_empty_store()
    try:
        store = json.loads(_TEAM_MASTER_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to read team league cache %s: %s", _TEAM_MASTER_CACHE_PATH, exc)
        return _team_empty_store()
    if not isinstance(store.get("seasons"), dict):
        return _team_empty_store()
    return store


def _team_save_store(store: dict[str, Any]) -> None:
    _TEAM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _TEAM_MASTER_CACHE_PATH.with_suffix(".json.tmp")
    encoded = json.dumps(store, separators=(",", ":"))
    tmp_path.write_text(encoded, encoding="utf-8")
    os.replace(tmp_path, _TEAM_MASTER_CACHE_PATH)
    logger.info("Wrote team league cache to %s (%d bytes)", _TEAM_MASTER_CACHE_PATH, len(encoded))


def _team_season_needs_refresh(entry: dict[str, Any] | None) -> bool:
    return entry is None or not _team_payload_has_data(entry)


def _team_try_acquire_build_lock() -> bool:
    _TEAM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(_TEAM_MASTER_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
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


def _team_release_build_lock() -> None:
    try:
        _TEAM_MASTER_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _team_wait_for_store_season(season_year: int) -> dict[str, Any] | None:
    deadline = time.time() + _BUILD_WAIT_SECONDS
    key = str(season_year)
    while time.time() < deadline:
        entry = (_team_load_store().get("seasons") or {}).get(key)
        if entry is not None and _team_payload_has_data(entry):
            return entry
        if not _TEAM_MASTER_LOCK_PATH.exists():
            return None
        time.sleep(_BUILD_POLL_SECONDS)
    entry = (_team_load_store().get("seasons") or {}).get(key)
    if entry is not None and _team_payload_has_data(entry):
        return entry
    logger.warning(
        "Timed out waiting for team league cache season %s in %s",
        season_year,
        _TEAM_MASTER_CACHE_PATH,
    )
    return None


def _build_team_league_stats(season_year: int) -> dict[str, Any]:
    from team_stats import _fetch_team_statistics, _get_mlb_team_ids, _parse_number

    league_stats: dict[str, dict[str, list[float]]] = {
        "batting": {},
        "pitching": {},
        "fielding": {},
    }
    team_ids = _get_mlb_team_ids()
    team_count = 0
    if team_ids:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(_fetch_team_statistics, team_id): team_id
                for team_id in team_ids
            }
            for future in as_completed(futures):
                try:
                    stats_by_category = future.result()
                except Exception:
                    continue
                team_count += 1
                for category_name, category_stats in stats_by_category.items():
                    bucket = league_stats.setdefault(category_name, {})
                    for stat_name, raw_value in category_stats.items():
                        number = _parse_number(raw_value)
                        if number is None:
                            continue
                        bucket.setdefault(stat_name, []).append(number)

    league_stats["_meta"] = {
        "source": "espn",
        "season_year": season_year,
        "team_count": team_count,
    }
    return league_stats


def _team_build_season_entry(season_year: int, cache_date: str) -> dict[str, Any]:
    logger.info("Building team league cache for season %s", season_year)
    built = _build_team_league_stats(season_year)
    payload = _team_payload_from_league_stats(season_year, cache_date, built)
    if not _team_payload_has_data(payload):
        raise RuntimeError("Team league stats build returned no data")
    return payload


def _team_ensure_season_entry(
    season_year: int,
    cache_date: str,
    *,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    key = str(season_year)
    store = _team_load_store()
    seasons = store.setdefault("seasons", {})
    entry = seasons.get(key)

    if not force_rebuild and not _team_season_needs_refresh(entry):
        return entry

    if not _team_try_acquire_build_lock():
        waited = _team_wait_for_store_season(season_year)
        if waited is not None:
            return waited
        raise RuntimeError(f"Another worker is building team league cache at {_TEAM_MASTER_CACHE_PATH}")

    try:
        store = _team_load_store()
        seasons = store.setdefault("seasons", {})
        entry = seasons.get(key)
        if not force_rebuild and not _team_season_needs_refresh(entry):
            return entry

        entry = _team_build_season_entry(season_year, cache_date)
        seasons[key] = entry
        _team_save_store(store)
        return entry
    finally:
        _team_release_build_lock()


def get_league_team_stats_by_category(
    season_year: int,
    *,
    cache_date: str | None = None,
    allow_build: bool = False,
    force_rebuild: bool = False,
) -> dict[str, dict[str, list[float]]]:
    """All-30-team ESPN stat distributions for team stat-bar comparisons."""
    cache_date = cache_date or date.today().isoformat()
    mem_key = f"team:{season_year}"
    cached = _team_memory_cache.get(mem_key)
    now = time.time()
    if cached and now - cached[0] < _MEMORY_TTL_SECONDS:
        return cached[1]

    empty = {"batting": {}, "pitching": {}, "fielding": {}}
    try:
        if allow_build:
            entry = _team_ensure_season_entry(
                season_year,
                cache_date,
                force_rebuild=force_rebuild,
            )
        else:
            entry = _read_best_season_entry(
                season_year,
                _team_load_store(),
                has_data=_team_payload_has_data,
            )
            if entry is None:
                return empty
        result = _team_league_stats_from_payload(entry)
    except Exception:
        logger.exception(
            "Failed to load team league cache for season %s",
            season_year,
        )
        return empty

    _team_memory_cache[mem_key] = (time.time(), result)
    return result


def warm_league_team_cache_for_today(season_year: int | None = None) -> bool:
    return warm_league_caches(season_year)
