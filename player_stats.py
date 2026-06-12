"""Player season/career stats via pybaseball (Baseball Reference)."""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date
from typing import Any

import warnings

import pandas as pd
from pybaseball import (
    bwar_bat,
    bwar_pitch,
    cache,
    get_splits,
    pitching_stats_bref,
    playerid_lookup,
)
from pybaseball.playerid_lookup import get_closest_names, get_lookup_table

cache.enable()
warnings.filterwarnings("ignore", category=UserWarning, module="pybaseball.split_stats")

_BATTING_COLUMNS = (
    ("AB", "AB"),
    ("H", "H"),
    ("HR", "HR"),
    ("BA", "BA"),
    ("R", "R"),
    ("RBI", "RBI"),
    ("SB", "SB"),
    ("OBP", "OBP"),
    ("SLG", "SLG"),
    ("OPS", "OPS"),
    ("OPS+", "OPS+"),
    ("WAR", "WAR"),
)
_PITCHING_COLUMNS = (
    ("W", "W"),
    ("L", "L"),
    ("ERA", "ERA"),
    ("G", "G"),
    ("GS", "GS"),
    ("SV", "SV"),
    ("IP", "IP"),
    ("SO", "SO"),
    ("WHIP", "WHIP"),
    ("WAR", "WAR"),
)
_PITCHER_POSITIONS = frozenset({"P", "SP", "RP", "CP", "CL", "LR", "MR", "SU"})
_CAREER_OPS_PLUS_LG_OBP = 0.328
_CAREER_OPS_PLUS_LG_SLG = 0.411
_CACHE_TTL_SECONDS = 3600
_bwar_bat_df: pd.DataFrame | None = None
_bwar_bat_loaded_at: float = 0.0
_bwar_pitch_df: pd.DataFrame | None = None
_bwar_pitch_loaded_at: float = 0.0
_player_lookup_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_stats_table_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_pitching_bref_season_cache: dict[int, pd.DataFrame] = {}


def _fold_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _playerid_matches(last_name: str, first_name: str) -> pd.DataFrame:
    try:
        matches = playerid_lookup(last_name, first_name)
        if matches is not None and not matches.empty:
            return matches
    except Exception:
        pass

    try:
        folded_last = _fold_name(last_name)
        folded_first = _fold_name(first_name)
        if folded_last != last_name.casefold() or folded_first != first_name.casefold():
            matches = playerid_lookup(folded_last, folded_first)
            if matches is not None and not matches.empty:
                return matches
    except Exception:
        pass

    try:
        closest = get_closest_names(last_name.lower(), first_name.lower(), get_lookup_table())
        if closest is not None and not closest.empty:
            return closest.head(1)
    except Exception:
        pass

    return pd.DataFrame()


def _parse_player_name(name: str) -> tuple[str, str]:
    parts = name.strip().split()
    if not parts:
        return "", ""
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    while len(parts) > 1 and parts[-1].lower().rstrip(".") in suffixes:
        parts.pop()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], parts[0]


def is_pitcher_position(position: str | None) -> bool:
    if not position:
        return False
    pos = position.strip().upper()
    return pos in _PITCHER_POSITIONS


def _lookup_player_record(player_name: str) -> dict[str, Any] | None:
    cached = _player_lookup_cache.get(player_name)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    last_name, first_name = _parse_player_name(player_name)
    if not last_name:
        _player_lookup_cache[player_name] = (now, None)
        return None

    matches = _playerid_matches(last_name, first_name)
    if matches.empty:
        _player_lookup_cache[player_name] = (now, None)
        return None

    row = matches.iloc[0]
    debut = row.get("mlb_played_first")
    last_played = row.get("mlb_played_last")
    record = {
        "bbref_id": str(row.get("key_bbref") or "").strip() or None,
        "debut_year": int(debut) if pd.notna(debut) else None,
        "last_year": int(last_played) if pd.notna(last_played) else date.today().year,
    }
    if not record["bbref_id"]:
        record = None
    _player_lookup_cache[player_name] = (now, record)
    return record


def _normalize_splits_df(result: Any) -> pd.DataFrame | None:
    if isinstance(result, tuple):
        result = result[0]
    if result is None or not isinstance(result, pd.DataFrame) or result.empty:
        return None
    return result


def _get_pitching_bref_season(year: int) -> pd.DataFrame:
    cached = _pitching_bref_season_cache.get(year)
    if cached is not None:
        return cached
    frame = pitching_stats_bref(year)
    _pitching_bref_season_cache[year] = frame
    return frame


def _pitching_bref_row(player_name: str, year: int) -> pd.Series | None:
    frame = _get_pitching_bref_season(year)
    rows = frame[frame["Name"] == player_name]
    if rows.empty:
        rows = frame[frame["Name"].str.casefold() == player_name.casefold()]
    if rows.empty:
        return None
    return rows.iloc[0]


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


def _outs_to_ip(outs: float) -> str:
    if outs <= 0:
        return "0"
    whole_innings = int(outs // 3)
    partial_outs = int(outs % 3)
    if partial_outs:
        return f"{whole_innings}.{partial_outs}"
    return str(whole_innings)


def _pitching_career_totals(
    player_name: str,
    *,
    debut_year: int | None,
    last_year: int,
) -> dict[str, Any]:
    if debut_year is None:
        debut_year = max(1995, last_year - 25)
    start_year = debut_year
    totals = {
        "G": 0.0,
        "GS": 0.0,
        "W": 0.0,
        "L": 0.0,
        "SV": 0.0,
        "SO": 0.0,
        "H": 0.0,
        "BB": 0.0,
        "ER": 0.0,
        "ip_outs": 0.0,
    }
    found = False
    for year in range(start_year, last_year + 1):
        row = _pitching_bref_row(player_name, year)
        if row is None:
            continue
        found = True
        for key in ("G", "GS", "W", "L", "SV", "SO", "H", "BB", "ER"):
            totals[key] += _parse_number(row.get(key)) or 0.0
        totals["ip_outs"] += _ip_to_outs(row.get("IP"))

    if not found:
        return {}

    innings = totals["ip_outs"] / 3.0
    era = (totals["ER"] / innings * 9) if innings > 0 else None
    whip = ((totals["H"] + totals["BB"]) / innings) if innings > 0 else None
    return {
        "G": totals["G"],
        "GS": totals["GS"],
        "W": totals["W"],
        "L": totals["L"],
        "SV": totals["SV"],
        "SO": totals["SO"],
        "IP": _outs_to_ip(totals["ip_outs"]),
        "ERA": era,
        "WHIP": whip,
    }


def _load_bwar_bat() -> pd.DataFrame:
    global _bwar_bat_df, _bwar_bat_loaded_at
    now = time.time()
    if _bwar_bat_df is not None and now - _bwar_bat_loaded_at < _CACHE_TTL_SECONDS:
        return _bwar_bat_df
    _bwar_bat_df = bwar_bat()
    _bwar_bat_loaded_at = now
    return _bwar_bat_df


def _load_bwar_pitch() -> pd.DataFrame:
    global _bwar_pitch_df, _bwar_pitch_loaded_at
    now = time.time()
    if _bwar_pitch_df is not None and now - _bwar_pitch_loaded_at < _CACHE_TTL_SECONDS:
        return _bwar_pitch_df
    _bwar_pitch_df = bwar_pitch()
    _bwar_pitch_loaded_at = now
    return _bwar_pitch_df


def _parse_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in {"—", "--", "-"}:
        return None
    try:
        if text.startswith("."):
            return float(f"0{text}")
        return float(text)
    except ValueError:
        return None


def _format_rate(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    return f"{number:.3f}".lstrip("0")


def _format_count(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}"


def _format_war(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    rounded = round(number, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def _format_stat(label: str, value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if label in {"BA", "OBP", "SLG", "OPS"}:
        return _format_rate(value)
    if label == "ERA":
        number = _parse_number(value)
        return "—" if number is None else f"{number:.2f}"
    if label == "WHIP":
        number = _parse_number(value)
        return "—" if number is None else f"{number:.2f}"
    if label == "WAR":
        return _format_war(value)
    if label == "OPS+":
        number = _parse_number(value)
        return "—" if number is None else str(round(number))
    if label == "IP":
        number = _parse_number(value)
        return "—" if number is None else str(value).strip()
    return _format_count(value)


def _compute_career_ops_plus(obp: Any, slg: Any) -> str | None:
    obp_value = _parse_number(obp)
    slg_value = _parse_number(slg)
    if obp_value is None or slg_value is None:
        return None
    ops_plus = 100 * (
        obp_value / _CAREER_OPS_PLUS_LG_OBP
        + slg_value / _CAREER_OPS_PLUS_LG_SLG
        - 1
    )
    return str(round(ops_plus))


def _split_row(
    splits: pd.DataFrame,
    *,
    season_year: int | None,
    career: bool,
) -> pd.Series | None:
    if splits is None or splits.empty:
        return None

    if career:
        key = ("Season Totals", "Career Totals")
        return splits.loc[key] if key in splits.index else None

    if season_year is not None:
        key = ("Season Totals", f"{season_year} Totals")
        if key in splits.index:
            return splits.loc[key]

    latest_key = None
    latest_year = -1
    for split_type, split_name in splits.index:
        if split_type != "Season Totals":
            continue
        match = re.fullmatch(r"(\d{4}) Totals", str(split_name))
        if not match:
            continue
        year = int(match.group(1))
        if year > latest_year:
            latest_year = year
            latest_key = (split_type, split_name)
    return splits.loc[latest_key] if latest_key else None


def _war_for_player(
    player_name: str,
    *,
    season_year: int | None,
    pitching: bool,
) -> tuple[str | None, str | None]:
    frame = _load_bwar_pitch() if pitching else _load_bwar_bat()
    rows = frame[frame["name_common"] == player_name]
    if rows.empty:
        last_name, first_name = _parse_player_name(player_name)
        if first_name:
            rows = frame[
                frame["name_common"].str.contains(last_name, case=False, na=False)
                & frame["name_common"].str.contains(first_name, case=False, na=False)
            ]
    if rows.empty:
        return None, None

    career_total = rows["WAR"].sum()
    season_value = None
    if season_year is not None:
        season_rows = rows[rows["year_ID"] == season_year]
        if not season_rows.empty:
            season_value = float(season_rows["WAR"].sum())

    return (
        _format_war(season_value) if season_value is not None else None,
        _format_war(career_total),
    )


def _stat_value(row: pd.Series | None, key: str) -> Any:
    if row is None:
        return None
    if key in row.index:
        return row.get(key)
    return None


def _build_row_values(
    row: pd.Series | None,
    *,
    war_value: str | None,
    pitching: bool,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if war_value is not None:
        values["WAR"] = war_value

    if pitching:
        if row is None:
            return values
        if isinstance(row, pd.Series):
            for key in ("W", "L", "ERA", "G", "GS", "SV", "IP", "SO", "WHIP"):
                values[key] = row.get(key)
        elif isinstance(row, dict):
            for key in ("W", "L", "ERA", "G", "GS", "SV", "IP", "SO", "WHIP"):
                values[key] = row.get(key)
        return values

    for key in ("AB", "H", "HR", "R", "RBI", "SB", "OBP", "SLG", "OPS"):
        values[key] = _stat_value(row, key)
    values["BA"] = _stat_value(row, "BA")
    return values


def _build_stats_table_result(
    *,
    season_year: int,
    columns: tuple[tuple[str, str], ...],
    season_values: dict[str, Any],
    career_values: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    table_columns: list[dict[str, str]] = []
    for _, label in columns:
        table_columns.append({
            "label": label,
            "season": _format_stat(label, season_values.get(label)),
            "career": _format_stat(label, career_values.get(label)),
        })
    return {
        "kind": kind,
        "title": "Summary",
        "season_year": str(season_year),
        "columns": table_columns,
    }


def _fetch_batting_stats_table(
    player_name: str,
    *,
    bbref_id: str,
    year: int,
) -> dict[str, Any] | None:
    batting_splits = _normalize_splits_df(get_splits(bbref_id))
    if batting_splits is None:
        return None

    season_splits = _normalize_splits_df(get_splits(bbref_id, year=year))
    if season_splits is None:
        return None

    season_row = _split_row(season_splits, season_year=year, career=False)
    career_row = _split_row(batting_splits, season_year=year, career=True)
    if season_row is None and career_row is None:
        return None

    resolved_year = year
    if season_row is not None:
        for split_type, split_name in season_splits.index:
            if split_type != "Season Totals":
                continue
            match = re.fullmatch(r"(\d{4}) Totals", str(split_name))
            if match and season_row.name == (split_type, split_name):
                resolved_year = int(match.group(1))
                break

    season_war, career_war = _war_for_player(
        player_name,
        season_year=resolved_year,
        pitching=False,
    )
    season_values = _build_row_values(season_row, war_value=season_war, pitching=False)
    career_values = _build_row_values(career_row, war_value=career_war, pitching=False)

    if career_row is not None:
        career_values["OPS+"] = _compute_career_ops_plus(
            career_row.get("OBP"),
            career_row.get("SLG"),
        )
    season_values["OPS+"] = _stat_value(season_row, "sOPS+")

    return _build_stats_table_result(
        season_year=resolved_year,
        columns=_BATTING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="batting",
    )


def _fetch_pitching_stats_table(
    player_name: str,
    *,
    player_record: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    season_row = _pitching_bref_row(player_name, year)
    career_row = _pitching_career_totals(
        player_name,
        debut_year=player_record.get("debut_year"),
        last_year=max(year, player_record.get("last_year") or year),
    )
    if season_row is None and not career_row:
        return None

    resolved_year = year
    season_war, career_war = _war_for_player(
        player_name,
        season_year=resolved_year,
        pitching=True,
    )
    season_values = _build_row_values(season_row, war_value=season_war, pitching=True)
    career_values = _build_row_values(career_row, war_value=career_war, pitching=True)

    return _build_stats_table_result(
        season_year=resolved_year,
        columns=_PITCHING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="pitching",
    )


def fetch_player_stats_table(
    player_name: str,
    season_year: str | int | None = None,
    *,
    position: str | None = None,
) -> dict[str, Any] | None:
    if not player_name:
        return None

    year = None
    if season_year is not None:
        try:
            year = int(season_year)
        except (TypeError, ValueError):
            year = date.today().year
    if year is None:
        year = date.today().year

    pitching = is_pitcher_position(position)
    cache_key = f"{player_name.lower()}:{year}:{'pitch' if pitching else 'bat'}"
    cached = _stats_table_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    player_record = _lookup_player_record(player_name)

    try:
        if pitching:
            if not player_record:
                player_record = {
                    "bbref_id": None,
                    "debut_year": None,
                    "last_year": year,
                }
            result = _fetch_pitching_stats_table(
                player_name,
                player_record=player_record,
                year=year,
            )
        else:
            if not player_record or not player_record.get("bbref_id"):
                _stats_table_cache[cache_key] = (now, None)
                return None
            result = _fetch_batting_stats_table(
                player_name,
                bbref_id=player_record["bbref_id"],
                year=year,
            )
        _stats_table_cache[cache_key] = (now, result)
        return result
    except Exception:
        _stats_table_cache[cache_key] = (now, None)
        return None
