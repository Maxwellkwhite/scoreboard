"""MLB team league stat pools via ESPN (single JSON cache file)."""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "league_team_averages"
_MASTER_CACHE_PATH = _DATA_DIR / "league_team_averages.json"
_MASTER_LOCK_PATH = _DATA_DIR / "league_team_averages.lock"
_BUILD_WAIT_SECONDS = 180
_BUILD_POLL_SECONDS = 0.5
_MEMORY_TTL_SECONDS = 3600

_memory_cache: dict[str, tuple[float, dict[str, dict[str, list[float]]]]] = {}


def _payload_has_data(payload: dict[str, Any]) -> bool:
    for category in ("batting", "pitching", "fielding"):
        bucket = payload.get(category) or {}
        for values in bucket.values():
            if values:
                return True
    return False


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
        "fielding": league_stats.get("fielding") or {},
    }


def _league_stats_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, list[float]]]:
    result: dict[str, dict[str, list[float]]] = {}
    for category in ("batting", "pitching", "fielding"):
        result[category] = {
            stat: [float(value) for value in values]
            for stat, values in (payload.get(category) or {}).items()
        }
    return result


def _empty_store() -> dict[str, Any]:
    return {"seasons": {}}


def _load_store() -> dict[str, Any]:
    if not _MASTER_CACHE_PATH.is_file():
        return _empty_store()
    try:
        store = json.loads(_MASTER_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to read team league cache %s: %s", _MASTER_CACHE_PATH, exc)
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
    logger.info("Wrote team league cache to %s (%d bytes)", _MASTER_CACHE_PATH, len(encoded))


def _season_needs_refresh(season_year: int, entry: dict[str, Any] | None, cache_date: str) -> bool:
    if entry is None or not _payload_has_data(entry):
        return True
    if season_year < date.today().year:
        return False
    if season_year > date.today().year:
        return False
    return entry.get("date") != cache_date


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


def _wait_for_store_season(season_year: int, cache_date: str) -> dict[str, Any] | None:
    deadline = time.time() + _BUILD_WAIT_SECONDS
    key = str(season_year)
    while time.time() < deadline:
        entry = (_load_store().get("seasons") or {}).get(key)
        if entry is not None and _payload_has_data(entry):
            if not _season_needs_refresh(season_year, entry, cache_date):
                return entry
        if not _MASTER_LOCK_PATH.exists():
            return None
        time.sleep(_BUILD_POLL_SECONDS)
    entry = (_load_store().get("seasons") or {}).get(key)
    if entry is not None and _payload_has_data(entry):
        if not _season_needs_refresh(season_year, entry, cache_date):
            return entry
    logger.warning(
        "Timed out waiting for team league cache season %s in %s",
        season_year,
        _MASTER_CACHE_PATH,
    )
    return None


def _build_league_stats(season_year: int) -> dict[str, Any]:
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


def _build_season_entry(season_year: int, cache_date: str) -> dict[str, Any]:
    logger.info("Building team league cache for season %s", season_year)
    built = _build_league_stats(season_year)
    payload = _payload_from_league_stats(season_year, cache_date, built)
    if not _payload_has_data(payload):
        raise RuntimeError("Team league stats build returned no data")
    return payload


def _ensure_season_entry(season_year: int, cache_date: str) -> dict[str, Any]:
    key = str(season_year)
    store = _load_store()
    seasons = store.setdefault("seasons", {})
    entry = seasons.get(key)

    if not _season_needs_refresh(season_year, entry, cache_date):
        return entry

    if not _try_acquire_build_lock():
        waited = _wait_for_store_season(season_year, cache_date)
        if waited is not None:
            return waited
        raise RuntimeError(f"Another worker is building team league cache at {_MASTER_CACHE_PATH}")

    try:
        store = _load_store()
        seasons = store.setdefault("seasons", {})
        entry = seasons.get(key)
        if not _season_needs_refresh(season_year, entry, cache_date):
            return entry

        entry = _build_season_entry(season_year, cache_date)
        seasons[key] = entry
        _save_store(store)
        return entry
    finally:
        _release_build_lock()


def _read_season_entry(season_year: int, cache_date: str) -> dict[str, Any] | None:
    """Return a cached season entry without triggering an ESPN build."""
    key = str(season_year)
    entry = (_load_store().get("seasons") or {}).get(key)
    if entry is None or not _payload_has_data(entry):
        return None
    if _season_needs_refresh(season_year, entry, cache_date):
        return None
    return entry


def warm_league_team_cache_for_today(season_year: int | None = None) -> bool:
    """Refresh the current season in the master cache if today's data is missing."""
    year = season_year or date.today().year
    result = get_league_team_stats_by_category(year, allow_build=True)
    has_data = any((result.get(category) or {}) for category in ("batting", "pitching", "fielding"))
    if has_data:
        logger.info("Team league cache ready for season %s", year)
    else:
        logger.warning("Team league cache warm-up produced no data for season %s", year)
    return has_data


def get_league_team_stats_by_category(
    season_year: int,
    *,
    cache_date: str | None = None,
    allow_build: bool = False,
) -> dict[str, dict[str, list[float]]]:
    """All-30-team ESPN stat distributions for team stat-bar comparisons.

    All seasons live in data/league_team_averages/league_team_averages.json.
    The current calendar year is refreshed once per day; older seasons are built
    only when missing and then kept permanently.

    Web requests should use the default ``allow_build=False`` and rely on the app
    startup warm-up (or a pre-built JSON file). Only background warm-up/build
    jobs should pass ``allow_build=True``.
    """
    cache_date = cache_date or date.today().isoformat()
    mem_key = (
        f"{season_year}:{cache_date}"
        if season_year == date.today().year
        else str(season_year)
    )
    cached = _memory_cache.get(mem_key)
    now = time.time()
    if cached and now - cached[0] < _MEMORY_TTL_SECONDS:
        return cached[1]

    empty = {"batting": {}, "pitching": {}, "fielding": {}}
    try:
        if allow_build:
            entry = _ensure_season_entry(season_year, cache_date)
        else:
            entry = _read_season_entry(season_year, cache_date)
            if entry is None:
                return empty
        result = _league_stats_from_payload(entry)
    except Exception:
        logger.exception(
            "Failed to load team league cache for season %s",
            season_year,
        )
        return empty

    _memory_cache[mem_key] = (time.time(), result)
    return result
