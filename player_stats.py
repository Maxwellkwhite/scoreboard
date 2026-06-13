"""Player season/career stats via pybaseball (Baseball Reference)."""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date
from typing import Any

import warnings

import pandas as pd
import requests
from pybaseball import (
    bwar_bat,
    bwar_pitch,
    cache,
    get_splits,
    pitching_stats_bref,
    playerid_lookup,
    statcast_batter_pitch_arsenal,
    statcast_pitcher_arsenal_stats,
    statcast_pitcher_pitch_arsenal,
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
ESPN_ATHLETE_STATS_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}/stats"
)
_PITCHER_MIX_METRICS = (
    ("velo", "Velo", "mph", 105.0),
    ("spin", "Spin", "rpm", 3200.0),
    ("whiff", "Whiff%", "%", 100.0),
    ("k", "K%", "%", 100.0),
    ("put_away", "Put Away%", "%", 100.0),
    ("xwoba", "xwOBA", "", 0.600),
)
_BATTER_MIX_METRICS = (
    ("whiff", "Whiff%", "%", 100.0),
    ("ba", "BA", "", 0.500),
    ("slg", "SLG", "", 1.000),
    ("xwoba", "xwOBA", "", 0.600),
    ("hard_hit", "HardHit%", "%", 100.0),
)
_BATTING_SPLIT_REGULAR = (
    ("Platoon Splits", ("vs RHP", "vs LHP")),
    ("Home or Away", ("Home", "Away")),
    ("Months", None),
)
_BATTING_SPLIT_ADVANCED = (
    ("Leverage", None),
    ("Clutch Stats", None),
    ("Hit Trajectory", None),
)
_PITCHING_SPLIT_REGULAR_MAIN = (
    ("Platoon Splits", ("vs RHB", "vs LHB")),
)
_PITCHING_SPLIT_REGULAR_LEVEL = (
    ("Home or Away -- Game-Level", ("Home", "Away")),
    ("Months -- Game-Level", None),
)
_PITCHING_SPLIT_ADVANCED_MAIN = (
    ("Leverage", None),
    ("Clutch Stats", None),
)
_PITCHING_SPLIT_ADVANCED_LEVEL = (
    ("Run Support -- Game-Level", None),
    ("Days of Rest -- Game-Level", None),
)
_BATTING_SPLIT_REGULAR_COLUMNS = ("PA", "AB", "H", "HR", "RBI", "BB", "SO", "BA", "OBP", "SLG", "OPS")
_BATTING_SPLIT_ADVANCED_COLUMNS = ("PA", "AB", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "BA", "OBP", "SLG", "OPS", "BAbip", "tOPS+")
_PITCHING_SPLIT_OPPONENT_COLUMNS = ("PA", "H", "HR", "BB", "SO", "BA", "OBP", "SLG", "OPS", "BAbip")
_PITCHING_SPLIT_LEVEL_REGULAR_COLUMNS = ("ERA", "IP", "WHIP", "SO", "BB", "H", "HR", "SO9")
_PITCHING_SPLIT_LEVEL_ADVANCED_COLUMNS = ("ERA", "IP", "WHIP", "SO", "BB", "BF", "SO9", "SO/W", "W", "L")
_POSTSEASON_FALLBACK_LABELS = {
    "batting": (
        "GP", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "HBP", "K",
        "SB", "CS", "AVG", "OBP", "SLG", "OPS",
    ),
    "pitching": (
        "GP", "GS", "W", "L", "W%", "WAR", "ERA", "WHIP", "IP", "K", "BB",
        "K/BB", "H", "R", "ER", "SV", "HLD", "BLSV",
    ),
}
_CAREER_OPS_PLUS_LG_OBP = 0.328
_CAREER_OPS_PLUS_LG_SLG = 0.411
_CACHE_TTL_SECONDS = 3600
_bwar_bat_df: pd.DataFrame | None = None
_bwar_bat_loaded_at: float = 0.0
_bwar_pitch_df: pd.DataFrame | None = None
_bwar_pitch_loaded_at: float = 0.0
_player_lookup_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_stats_table_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_stat_panels_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
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
        "mlbam_id": int(row.get("key_mlbam")) if pd.notna(row.get("key_mlbam")) else None,
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

    season_splits = None
    try:
        season_splits = _normalize_splits_df(get_splits(bbref_id, year=year))
    except Exception:
        season_splits = None
    season_row = (
        _split_row(season_splits, season_year=year, career=False)
        if season_splits is not None
        else None
    )
    career_row = _split_row(batting_splits, season_year=year, career=True)
    if season_row is None and career_row is None:
        return None

    resolved_year = year
    if season_row is not None and season_splits is not None:
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
    cache_key = f"{player_name.lower()}:{year}:{'pitch' if pitching else 'bat'}:v2"
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
                return None
            result = _fetch_batting_stats_table(
                player_name,
                bbref_id=player_record["bbref_id"],
                year=year,
            )
        _stats_table_cache[cache_key] = (now, result)
        return result
    except Exception:
        return None


def _format_espn_value(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    text = str(value).strip()
    if not text or text in {"—", "--", "-"}:
        return "—"
    return text


def _empty_stats_table(labels: list[str] | tuple[str, ...], season_year: int) -> dict[str, Any]:
    return {
        "season_year": str(season_year),
        "columns": [
            {"label": label, "season": "—", "career": "—"}
            for label in labels
        ],
    }


def _parse_espn_category_table(
    category: dict[str, Any],
    *,
    season_year: int,
    require_data: bool = True,
) -> dict[str, Any] | None:
    labels = category.get("labels") or []
    if not labels:
        return None

    season_row: dict[str, str] = {}
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if str(year) == str(season_year):
            season_row = dict(zip(labels, stat.get("stats") or []))
            break

    career_row = dict(zip(labels, category.get("totals") or []))
    columns: list[dict[str, str]] = []
    for label in labels:
        columns.append({
            "label": label,
            "season": _format_espn_value(season_row.get(label)),
            "career": _format_espn_value(career_row.get(label)),
        })

    if require_data and not any(col["season"] != "—" or col["career"] != "—" for col in columns):
        return None

    return {
        "season_year": str(season_year),
        "columns": columns,
    }


_ADVANCED_ESPN_CATEGORIES = {
    "batting": {
        "regular": "advanced-batting",
        "postseason": "postseason-batting",
    },
    "pitching": {
        "regular": "expanded-pitching",
        "postseason": "postseason-pitching",
    },
}


def _espn_advanced_table(
    categories: dict[str, Any],
    *,
    kind: str,
    view: str,
    season_year: int,
) -> dict[str, Any]:
    category_name = _ADVANCED_ESPN_CATEGORIES[kind][view]
    category = categories.get(category_name)
    table: dict[str, Any] | None = None
    if category:
        table = _parse_espn_category_table(
            category,
            season_year=season_year,
            require_data=view != "postseason",
        )
    if not table and view == "postseason":
        labels = (category or {}).get("labels") or _POSTSEASON_FALLBACK_LABELS[kind]
        table = _empty_stats_table(labels, season_year)
    if not table:
        labels = (category or {}).get("labels") or _POSTSEASON_FALLBACK_LABELS[kind]
        table = _empty_stats_table(labels, season_year)
    return table


def _pitch_arsenal_wide_value(
    wide_row: pd.Series | None,
    pitch_type: str,
    stat: str,
) -> Any:
    if wide_row is None:
        return None
    key = f"{pitch_type.lower()}_{stat}"
    if key not in wide_row.index:
        return None
    return wide_row.get(key)


def _pitch_mix_numeric(value: Any) -> float | None:
    number = _parse_number(value)
    return number


def _fetch_pitch_mix_panel(
    *,
    mlbam_id: int | None,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    label = "Pitch Mix" if pitching else "vs Pitches"
    empty: dict[str, Any] = {
        "id": "pitch_mix",
        "label": label,
        "panel_kind": "pitch_mix",
        "pitching": pitching,
        "season_year": str(season_year),
        "pitches": [],
        "metrics": [],
    }
    if not mlbam_id:
        return empty

    pitches: list[dict[str, Any]] = []
    try:
        if pitching:
            stats = statcast_pitcher_arsenal_stats(season_year, minPA=1)
            player_rows = stats[stats["player_id"] == mlbam_id].copy()
            if player_rows.empty:
                return empty

            velo_df = statcast_pitcher_pitch_arsenal(season_year, minP=1, arsenal_type="avg_speed")
            spin_df = statcast_pitcher_pitch_arsenal(season_year, minP=1, arsenal_type="avg_spin")
            velo_row = velo_df[velo_df["pitcher"] == mlbam_id]
            spin_row = spin_df[spin_df["pitcher"] == mlbam_id]
            velo_series = velo_row.iloc[0] if not velo_row.empty else None
            spin_series = spin_row.iloc[0] if not spin_row.empty else None

            player_rows = player_rows.sort_values("pitch_usage", ascending=False)
            for _, row in player_rows.iterrows():
                pitch_count = _parse_number(row.get("pitches"))
                if not pitch_count:
                    continue
                pitch_type = str(row.get("pitch_type") or "")
                pitches.append({
                    "label": str(row.get("pitch_name") or pitch_type),
                    "pitch_type": pitch_type,
                    "usage": _pitch_mix_numeric(row.get("pitch_usage")),
                    "velo": _pitch_mix_numeric(
                        _pitch_arsenal_wide_value(velo_series, pitch_type, "avg_speed")
                    ),
                    "spin": _pitch_mix_numeric(
                        _pitch_arsenal_wide_value(spin_series, pitch_type, "avg_spin")
                    ),
                    "whiff": _pitch_mix_numeric(row.get("whiff_percent")),
                    "k": _pitch_mix_numeric(row.get("k_percent")),
                    "put_away": _pitch_mix_numeric(row.get("put_away")),
                    "xwoba": _pitch_mix_numeric(row.get("est_woba")),
                })
            metrics = [
                {"id": key, "label": label, "unit": unit, "max": max_val}
                for key, label, unit, max_val in _PITCHER_MIX_METRICS
            ]
        else:
            stats = statcast_batter_pitch_arsenal(season_year, minPA=1)
            player_rows = stats[stats["player_id"] == mlbam_id].copy()
            if player_rows.empty:
                return empty

            player_rows = player_rows.sort_values("pitch_usage", ascending=False)
            for _, row in player_rows.iterrows():
                pitch_count = _parse_number(row.get("pitches"))
                if not pitch_count:
                    continue
                pitch_type = str(row.get("pitch_type") or "")
                pitches.append({
                    "label": str(row.get("pitch_name") or pitch_type),
                    "pitch_type": pitch_type,
                    "usage": _pitch_mix_numeric(row.get("pitch_usage")),
                    "whiff": _pitch_mix_numeric(row.get("whiff_percent")),
                    "ba": _pitch_mix_numeric(row.get("ba")),
                    "slg": _pitch_mix_numeric(row.get("slg")),
                    "xwoba": _pitch_mix_numeric(row.get("est_woba")),
                    "hard_hit": _pitch_mix_numeric(row.get("hard_hit_percent")),
                })
            metrics = [
                {"id": key, "label": label, "unit": unit, "max": max_val}
                for key, label, unit, max_val in _BATTER_MIX_METRICS
            ]
    except Exception:
        return empty

    if not pitches:
        return empty

    return {
        "id": "pitch_mix",
        "label": label,
        "panel_kind": "pitch_mix",
        "pitching": pitching,
        "season_year": str(season_year),
        "pitches": pitches,
        "metrics": metrics,
    }


def _split_cell_value(label: str, value: Any) -> str:
    if label in {"BA", "OBP", "SLG", "OPS", "BAbip"}:
        return _format_rate(value)
    if label == "ERA":
        number = _parse_number(value)
        return "—" if number is None else f"{number:.2f}"
    if label == "WHIP":
        number = _parse_number(value)
        return "—" if number is None else f"{number:.2f}"
    if label in {"SO9", "SO/W"}:
        number = _parse_number(value)
        return "—" if number is None else f"{number:.1f}"
    if label == "tOPS+":
        number = _parse_number(value)
        return "—" if number is None else str(round(number))
    if label == "IP":
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return str(value).strip()
    return _format_count(value)


def _split_group_table(
    frame: pd.DataFrame,
    *,
    split_type: str,
    row_names: tuple[str, ...] | None,
    columns: tuple[str, ...],
) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None
    if split_type not in frame.index.get_level_values("Split Type"):
        return None

    section = frame.loc[split_type]
    if section.empty:
        return None

    available_columns = [col for col in columns if col in section.columns]
    if not available_columns:
        return None

    rows: list[dict[str, Any]] = []
    names = list(row_names) if row_names else list(section.index)
    for name in names:
        if name not in section.index:
            continue
        row = section.loc[name]
        rows.append({
            "label": str(name),
            "cells": [
                {"label": col, "value": _split_cell_value(col, row.get(col))}
                for col in available_columns
            ],
        })

    if not rows and row_names is None:
        for name, row in section.iterrows():
            rows.append({
                "label": str(name),
                "cells": [
                    {"label": col, "value": _split_cell_value(col, row.get(col))}
                    for col in available_columns
                ],
            })

    if not rows:
        return None

    return {
        "title": split_type.replace(" -- Game-Level", ""),
        "columns": available_columns,
        "rows": rows,
    }


def _build_split_view(
    main_splits: pd.DataFrame | None,
    level_splits: pd.DataFrame | None,
    *,
    main_specs: tuple[tuple[str, tuple[str, ...] | None], ...] = (),
    level_specs: tuple[tuple[str, tuple[str, ...] | None], ...] = (),
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for split_type, row_names in main_specs:
        if main_splits is None:
            continue
        group = _split_group_table(
            main_splits,
            split_type=split_type,
            row_names=row_names,
            columns=columns,
        )
        if group:
            groups.append(group)
    for split_type, row_names in level_specs:
        if level_splits is None:
            continue
        group = _split_group_table(
            level_splits,
            split_type=split_type,
            row_names=row_names,
            columns=columns,
        )
        if group:
            groups.append(group)
    return groups


def _fetch_splits_panels(
    bbref_id: str,
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    empty_view = {"id": "regular", "label": "Regular", "groups": []}
    empty_advanced = {"id": "advanced", "label": "Advanced", "groups": []}
    try:
        result = get_splits(bbref_id, season_year, pitching_splits=pitching)
        if pitching:
            main_splits = _normalize_splits_df(result)
            level_splits = result[1] if isinstance(result, tuple) and len(result) > 1 else None
        else:
            main_splits = _normalize_splits_df(result)
            level_splits = None
    except Exception:
        return {
            "id": "splits",
            "label": "Splits",
            "panel_kind": "toggle_splits",
            "default_view": "regular",
            "views": [empty_view, empty_advanced],
        }

    if pitching:
        regular_groups = _build_split_view(
            main_splits,
            None,
            main_specs=_PITCHING_SPLIT_REGULAR_MAIN,
            columns=_PITCHING_SPLIT_OPPONENT_COLUMNS,
        )
        regular_groups.extend(
            _build_split_view(
                None,
                level_splits,
                level_specs=_PITCHING_SPLIT_REGULAR_LEVEL,
                columns=_PITCHING_SPLIT_LEVEL_REGULAR_COLUMNS,
            )
        )
        advanced_groups = _build_split_view(
            main_splits,
            None,
            main_specs=_PITCHING_SPLIT_ADVANCED_MAIN,
            columns=_PITCHING_SPLIT_OPPONENT_COLUMNS,
        )
        advanced_groups.extend(
            _build_split_view(
                None,
                level_splits,
                level_specs=_PITCHING_SPLIT_ADVANCED_LEVEL,
                columns=_PITCHING_SPLIT_LEVEL_ADVANCED_COLUMNS,
            )
        )
    else:
        regular_groups = _build_split_view(
            main_splits,
            None,
            main_specs=_BATTING_SPLIT_REGULAR,
            columns=_BATTING_SPLIT_REGULAR_COLUMNS,
        )
        advanced_groups = _build_split_view(
            main_splits,
            None,
            main_specs=_BATTING_SPLIT_ADVANCED,
            columns=_BATTING_SPLIT_ADVANCED_COLUMNS,
        )

    return {
        "id": "splits",
        "label": "Splits",
        "panel_kind": "toggle_splits",
        "default_view": "regular",
        "views": [
            {"id": "regular", "label": "Regular", "groups": regular_groups},
            {"id": "advanced", "label": "Advanced", "groups": advanced_groups},
        ],
    }


def fetch_player_stat_panels(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> list[dict[str, Any]]:
    if not player_id:
        return []

    year = None
    if season_year is not None:
        try:
            year = int(season_year)
        except (TypeError, ValueError):
            year = date.today().year
    if year is None:
        year = date.today().year

    kind = "pitching" if is_pitcher_position(position) else "batting"
    pitching = kind == "pitching"
    cache_key = f"{player_id}:{year}:{kind}:v4"
    cached = _stat_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    categories: dict[str, Any] = {}
    try:
        response = requests.get(
            ESPN_ATHLETE_STATS_URL.format(player_id=player_id),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        categories = {
            category.get("name"): category
            for category in payload.get("categories") or []
            if category.get("name")
        }
    except requests.RequestException:
        pass

    player_record = _lookup_player_record(player_name) if player_name else None
    bbref_id = (player_record or {}).get("bbref_id")
    mlbam_id = (player_record or {}).get("mlbam_id")

    advanced_panel = {
        "id": "advanced",
        "label": "Advanced",
        "panel_kind": "toggle_table",
        "default_view": "regular",
        "views": [
            {
                "id": "regular",
                "label": "Regular Season",
                "stats_table": _espn_advanced_table(
                    categories, kind=kind, view="regular", season_year=year,
                ),
            },
            {
                "id": "postseason",
                "label": "Postseason",
                "stats_table": _espn_advanced_table(
                    categories, kind=kind, view="postseason", season_year=year,
                ),
            },
        ],
    }

    pitch_mix_panel = _fetch_pitch_mix_panel(
        mlbam_id=mlbam_id,
        pitching=pitching,
        season_year=year,
    )

    splits_panel = (
        _fetch_splits_panels(bbref_id, pitching=pitching, season_year=year)
        if bbref_id
        else {
            "id": "splits",
            "label": "Splits",
            "panel_kind": "toggle_splits",
            "default_view": "regular",
            "views": [
                {"id": "regular", "label": "Regular", "groups": []},
                {"id": "advanced", "label": "Advanced", "groups": []},
            ],
        }
    )

    panels = [advanced_panel, pitch_mix_panel, splits_panel]
    _stat_panels_cache[cache_key] = (now, panels)
    return panels
