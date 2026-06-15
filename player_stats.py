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
    statcast_batter,
    statcast_batter_expected_stats,
    statcast_batter_exitvelo_barrels,
    statcast_batter_percentile_ranks,
    statcast_pitcher_arsenal_stats,
    statcast_pitcher_exitvelo_barrels,
    statcast_pitcher_expected_stats,
    statcast_pitcher_percentile_ranks,
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
_SPRAY_EVENT_LABELS = {
    "single": "Single",
    "double": "Double",
    "triple": "Triple",
    "home_run": "Home Run",
    "out": "Out",
}
_SPRAY_BB_TYPE_LABELS = {
    "ground_ball": "Ground Ball",
    "line_drive": "Line Drive",
    "fly_ball": "Fly Ball",
    "popup": "Popup",
}
_SPRAY_BB_TYPE_ORDER = ("ground_ball", "line_drive", "fly_ball", "popup")
_SPRAY_TYPE_METRICS = (
    ("ev", "Exit Velo", "mph", 115.0),
    ("launch_angle", "Launch Angle", "°", 45.0),
    ("distance", "Distance", "ft", 450.0),
    ("xwoba", "xwOBA", "", 0.600),
    ("hard_hit", "Hard Hit%", "%", 100.0),
)
_PERCENTILE_MIN_YEAR = 2015
_BATTER_PERCENTILE_GROUPS = (
    ("Expected Stats", (
        ("xwoba", "xwOBA"),
        ("xba", "xBA"),
        ("xslg", "xSLG"),
        ("xiso", "xISO"),
        ("xobp", "xOBP"),
    )),
    ("Bat-to-Ball Skills", (
        ("bat_speed", "Bat Speed"),
        ("squared_up_rate", "Squared Up%"),
        ("swing_length", "Swing Length"),
    )),
    ("Contact", (
        ("exit_velocity", "Avg Exit Velo"),
        ("max_ev", "Max Exit Velo"),
        ("hard_hit_percent", "Hard Hit%"),
        ("brl_percent", "Barrel%"),
        ("brl", "Barrels"),
    )),
    ("Plate Discipline", (
        ("k_percent", "K%"),
        ("bb_percent", "BB%"),
        ("whiff_percent", "Whiff%"),
        ("chase_percent", "Chase%"),
    )),
    ("Running & Defense", (
        ("sprint_speed", "Sprint Speed"),
        ("arm_strength", "Arm Strength"),
        ("oaa", "Outs Above Avg"),
    )),
)
_PITCHER_PERCENTILE_GROUPS = (
    ("Expected Stats", (
        ("xera", "xERA"),
        ("xwoba", "xwOBA Allowed"),
        ("xba", "xBA Allowed"),
        ("xslg", "xSLG Allowed"),
        ("xiso", "xISO Allowed"),
        ("xobp", "xOBP Allowed"),
    )),
    ("Contact Allowed", (
        ("exit_velocity", "Avg Exit Velo"),
        ("max_ev", "Max Exit Velo"),
        ("hard_hit_percent", "Hard Hit%"),
        ("brl_percent", "Barrel%"),
        ("brl", "Barrels"),
    )),
    ("Plate Discipline", (
        ("k_percent", "K%"),
        ("bb_percent", "BB%"),
        ("whiff_percent", "Whiff%"),
        ("chase_percent", "Chase%"),
    )),
    ("Pitch Arsenal", (
        ("fb_velocity", "Fastball Velo"),
        ("fb_spin", "Fastball Spin"),
        ("curve_spin", "Curve Spin"),
    )),
)
_SAVANT_DISCIPLINE_URL = (
    "https://baseballsavant.mlb.com/leaderboard/custom"
    "?year={year}&type={player_type}&filter=&min=0"
    "&selections=player_id%2Ck_percent%2Cbb_percent%2Cwhiff_percent%2Cchase_percent"
    "&csv=true"
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
_espn_categories_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_player_core_panels_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_player_visual_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_player_percentile_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_player_splits_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_bbref_splits_cache: dict[str, tuple[float, pd.DataFrame | None]] = {}
_batter_percentile_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_pitcher_percentile_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_discipline_table_cache: dict[tuple[int, str], tuple[float, pd.DataFrame | None]] = {}
_bat_tracking_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_sprint_speed_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
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


def _cached_get_splits(
    bbref_id: str,
    *,
    year: int | None = None,
    pitching_splits: bool = False,
) -> pd.DataFrame | None:
    kind = "pitch" if pitching_splits else "bat"
    cache_key = f"{bbref_id}:{kind}:{year if year is not None else 'career'}"
    cached = _bbref_splits_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        if year is None:
            result = get_splits(bbref_id, pitching_splits=pitching_splits)
        else:
            result = get_splits(bbref_id, year, pitching_splits=pitching_splits)
    except Exception:
        frame = None
    else:
        frame = _normalize_splits_df(result)

    _bbref_splits_cache[cache_key] = (now, frame)
    return frame


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
    batting_splits = _cached_get_splits(bbref_id)
    if batting_splits is None:
        return None

    season_splits = _cached_get_splits(bbref_id, year=year)
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
    cache_key = f"{player_name.lower()}:{year}:{'pitch' if pitching else 'bat'}:v4"
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


_PLAYER_BATTING_ESPN_MAP = {
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
}

_PLAYER_PITCHING_ESPN_MAP = {
    "ERA": "ERA",
    "WHIP": "WHIP",
    "IP": "innings",
    "W": "wins",
    "L": "losses",
    "SV": "saves",
    "K": "strikeouts",
    "SO": "strikeouts",
    "BB": "walks",
    "H": "hits",
    "ER": "earnedRuns",
    "HR": "homeRuns",
}


def _espn_row_to_stats(
    row: dict[str, str],
    mapping: dict[str, str],
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for espn_label, stat_name in mapping.items():
        value = row.get(espn_label)
        if value is not None and str(value).strip() not in {"", "—", "--", "-"}:
            stats[stat_name] = value
    return stats


def _parse_player_batting_stats(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, Any]:
    from team_stats import _espn_category_season_row

    batting_row = _espn_category_season_row(
        categories.get("career-batting"),
        season_year,
    )
    expanded_row = _espn_category_season_row(
        categories.get("expanded-batting"),
        season_year,
    )
    stats = _espn_row_to_stats(batting_row, _PLAYER_BATTING_ESPN_MAP)
    if expanded_row.get("PA") is not None:
        stats["plateAppearances"] = expanded_row["PA"]
    return stats


def _parse_player_pitching_stats(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, Any]:
    from team_stats import _espn_category_season_row

    pitching_row = _espn_category_season_row(
        categories.get("pitching"),
        season_year,
    )
    expanded_row = _espn_category_season_row(
        categories.get("expanded-pitching"),
        season_year,
    )
    opponent_row = _espn_category_season_row(
        categories.get("opponent-batting"),
        season_year,
    )
    stats = _espn_row_to_stats(pitching_row, _PLAYER_PITCHING_ESPN_MAP)
    if expanded_row.get("K/9") is not None:
        stats["strikeoutsPerNineInnings"] = expanded_row["K/9"]
    if expanded_row.get("QS") is not None:
        stats["qualityStarts"] = expanded_row["QS"]
    if opponent_row.get("OBA") is not None:
        stats["opponentAvg"] = opponent_row["OBA"]
    return stats


def _build_player_stats_panel(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any] | None:
    from league_player_averages import get_league_player_stats_by_category
    from team_stats import (
        _BATTING_DETAIL_SPECS,
        _PITCHING_DETAIL_SPECS,
        _build_stat_metrics,
    )

    league_stats = get_league_player_stats_by_category(season_year)
    views: list[dict[str, Any]] = []
    if pitching:
        player_pitching = _parse_player_pitching_stats(categories, season_year=season_year)
        pitching_metrics = _build_stat_metrics(
            player_pitching,
            _PITCHING_DETAIL_SPECS,
            category="pitching",
            league_stats=league_stats.get("pitching") or {},
        )
        if pitching_metrics:
            views.append({
                "id": "pitching",
                "label": "Pitching",
                "metrics": pitching_metrics,
            })
    else:
        player_batting = _parse_player_batting_stats(categories, season_year=season_year)
        batting_metrics = _build_stat_metrics(
            player_batting,
            _BATTING_DETAIL_SPECS,
            category="batting",
            league_stats=league_stats.get("batting") or {},
        )
        if batting_metrics:
            views.append({
                "id": "batting",
                "label": "Batting",
                "metrics": batting_metrics,
            })

    if not views:
        return None

    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": views[0]["id"],
        "season_year": str(season_year),
        "views": views,
    }


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


def _statcast_season_range(season_year: int) -> tuple[str, str]:
    today = date.today()
    start = f"{season_year}-03-01"
    if season_year >= today.year:
        end = today.isoformat()
    else:
        end = f"{season_year}-11-30"
    return start, end


def _spray_event_category(event: str) -> str:
    if event in {"single", "double", "triple", "home_run"}:
        return event
    return "out"


def _series_mean(values: pd.Series) -> float | None:
    numbers = [_parse_number(value) for value in values]
    valid = [number for number in numbers if number is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 1)


def _hard_hit_rate(values: pd.Series) -> float | None:
    numbers = [_parse_number(value) for value in values]
    valid = [number for number in numbers if number is not None]
    if not valid:
        return None
    hard = sum(1 for number in valid if number >= 95)
    return round(hard / len(valid) * 100, 1)


def _barrel_rate(values: pd.Series) -> float | None:
    numbers = [_parse_number(value) for value in values]
    valid = [number for number in numbers if number is not None]
    if not valid:
        return None
    barrels = sum(1 for number in valid if number == 6)
    return round(barrels / len(valid) * 100, 1)


def _spray_type_stats(group: pd.DataFrame) -> dict[str, float | None]:
    return {
        "ev": _series_mean(group.get("launch_speed", pd.Series(dtype=float))),
        "launch_angle": _series_mean(group.get("launch_angle", pd.Series(dtype=float))),
        "distance": _series_mean(group.get("hit_distance_sc", pd.Series(dtype=float))),
        "xwoba": _round_rate_mean(group.get("estimated_woba_using_speedangle", pd.Series(dtype=float))),
        "hard_hit": _hard_hit_rate(group.get("launch_speed", pd.Series(dtype=float))),
    }


def _round_rate_mean(values: pd.Series) -> float | None:
    numbers = [_parse_number(value) for value in values]
    valid = [number for number in numbers if number is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 3)


def _fetch_pitch_mix_panel(
    *,
    mlbam_id: int | None,
    season_year: int,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "id": "pitch_mix",
        "label": "Pitch Mix",
        "panel_kind": "pitch_mix",
        "pitching": True,
        "season_year": str(season_year),
        "pitches": [],
        "metrics": [],
    }
    if not mlbam_id:
        return empty

    pitches: list[dict[str, Any]] = []
    try:
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
    except Exception:
        return empty

    if not pitches:
        return empty

    metrics = [
        {"id": key, "label": label, "unit": unit, "max": max_val}
        for key, label, unit, max_val in _PITCHER_MIX_METRICS
    ]
    return {
        "id": "pitch_mix",
        "label": "Pitch Mix",
        "panel_kind": "pitch_mix",
        "pitching": True,
        "season_year": str(season_year),
        "pitches": pitches,
        "metrics": metrics,
    }


def _fetch_spray_chart_panel(
    *,
    mlbam_id: int | None,
    season_year: int,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "id": "spray_chart",
        "label": "Batting Metrics",
        "panel_kind": "spray_chart",
        "season_year": str(season_year),
        "summary": {},
        "legend": [],
        "types": [],
        "metrics": [],
        "points": [],
    }
    if not mlbam_id:
        return empty

    try:
        start_dt, end_dt = _statcast_season_range(season_year)
        df = statcast_batter(start_dt, end_dt, mlbam_id)
        if df is None or df.empty:
            return empty

        sub = df[
            df["events"].notna()
            & df["hc_x"].notna()
            & df["hc_y"].notna()
        ].copy()
        if sub.empty:
            return empty

        total = len(sub)
        counts: dict[str, int] = {"single": 0, "double": 0, "triple": 0, "home_run": 0, "out": 0}
        points: list[dict[str, Any]] = []

        for _, row in sub.iterrows():
            raw_event = str(row.get("events") or "")
            category = _spray_event_category(raw_event)
            counts[category] = counts.get(category, 0) + 1

            bb_type = str(row.get("bb_type") or "")
            launch_speed = _parse_number(row.get("launch_speed"))
            launch_angle = _parse_number(row.get("launch_angle"))
            distance = _parse_number(row.get("hit_distance_sc"))
            xwoba = _parse_number(row.get("estimated_woba_using_speedangle"))

            points.append({
                "x": round(float(row["hc_x"]), 2),
                "y": round(float(row["hc_y"]), 2),
                "event": category,
                "event_label": _SPRAY_EVENT_LABELS.get(category, category),
                "bb_type": bb_type,
                "bb_type_label": _SPRAY_BB_TYPE_LABELS.get(bb_type, bb_type),
                "launch_speed": launch_speed,
                "launch_angle": launch_angle,
                "distance": distance,
                "xwoba": xwoba,
            })

        legend_order = ("home_run", "triple", "double", "single", "out")
        legend = [
            {
                "event": event,
                "label": _SPRAY_EVENT_LABELS[event],
                "count": counts.get(event, 0),
            }
            for event in legend_order
            if counts.get(event, 0)
        ]

        hits = counts["single"] + counts["double"] + counts["triple"] + counts["home_run"]
        non_hr_hits = hits - counts["home_run"]
        hr_count = counts["home_run"]
        babip = (
            round(non_hr_hits / (total - hr_count), 3)
            if total > hr_count
            else None
        )

        bb_type_counts = sub["bb_type"].value_counts() if "bb_type" in sub.columns else pd.Series(dtype=int)
        types: list[dict[str, Any]] = []
        for bb_type in _SPRAY_BB_TYPE_ORDER:
            count = int(bb_type_counts.get(bb_type, 0))
            if not count:
                continue
            group = sub[sub["bb_type"] == bb_type]
            type_stats = _spray_type_stats(group)
            types.append({
                "label": _SPRAY_BB_TYPE_LABELS[bb_type],
                "bb_type": bb_type,
                "usage": round(count / total * 100, 1),
                "count": count,
                **type_stats,
            })

        metrics = [
            {"id": key, "label": label, "unit": unit, "max": max_val}
            for key, label, unit, max_val in _SPRAY_TYPE_METRICS
        ]

        return {
            "id": "spray_chart",
            "label": "Batting Metrics",
            "panel_kind": "spray_chart",
            "season_year": str(season_year),
            "summary": {
                "total": total,
                "hits": hits,
                "home_runs": counts["home_run"],
                "outs": counts["out"],
                "avg_ev": _series_mean(sub.get("launch_speed", pd.Series(dtype=float))),
                "avg_launch_angle": _series_mean(sub.get("launch_angle", pd.Series(dtype=float))),
                "avg_distance": _series_mean(sub.get("hit_distance_sc", pd.Series(dtype=float))),
                "avg_xwoba": _round_rate_mean(
                    sub.get("estimated_woba_using_speedangle", pd.Series(dtype=float))
                ),
                "hard_hit_pct": _hard_hit_rate(sub.get("launch_speed", pd.Series(dtype=float))),
                "barrel_pct": _barrel_rate(sub.get("launch_speed_angle", pd.Series(dtype=float))),
                "babip": babip,
            },
            "legend": legend,
            "types": types,
            "metrics": metrics,
            "points": points,
        }
    except Exception:
        return empty


def _get_batter_percentile_table(season_year: int) -> pd.DataFrame | None:
    cached = _batter_percentile_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        table = statcast_batter_percentile_ranks(season_year)
        if table is None or table.empty:
            result = None
        else:
            result = table
    except Exception:
        result = None
    _batter_percentile_table_cache[season_year] = (now, result)
    return result


def _get_pitcher_percentile_table(season_year: int) -> pd.DataFrame | None:
    cached = _pitcher_percentile_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        table = statcast_pitcher_percentile_ranks(season_year)
        if table is None or table.empty:
            result = None
        else:
            result = table
    except Exception:
        result = None
    _pitcher_percentile_table_cache[season_year] = (now, result)
    return result


def _get_discipline_table(season_year: int, player_type: str) -> pd.DataFrame | None:
    cache_key = (season_year, player_type)
    cached = _discipline_table_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            _SAVANT_DISCIPLINE_URL.format(year=season_year, player_type=player_type),
            timeout=20,
        )
        response.raise_for_status()
        table = pd.read_csv(pd.io.common.StringIO(response.text))
        result = table if not table.empty else None
    except Exception:
        result = None
    _discipline_table_cache[cache_key] = (now, result)
    return result


def _get_bat_tracking_table(season_year: int) -> pd.DataFrame | None:
    cached = _bat_tracking_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            f"https://baseballsavant.mlb.com/leaderboard/bat-tracking?year={season_year}&csv=true",
            timeout=20,
        )
        response.raise_for_status()
        table = pd.read_csv(pd.io.common.StringIO(response.text))
        result = table if not table.empty else None
    except Exception:
        result = None
    _bat_tracking_table_cache[season_year] = (now, result)
    return result


def _get_sprint_speed_table(season_year: int) -> pd.DataFrame | None:
    cached = _sprint_speed_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            f"https://baseballsavant.mlb.com/leaderboard/sprint_speed?year={season_year}&csv=true",
            timeout=20,
        )
        response.raise_for_status()
        table = pd.read_csv(pd.io.common.StringIO(response.text))
        result = table if not table.empty else None
    except Exception:
        result = None
    _sprint_speed_table_cache[season_year] = (now, result)
    return result


def _weighted_pitcher_arsenal_rates(
    rows: pd.DataFrame,
    column: str,
) -> float | None:
    if rows.empty or column not in rows.columns:
        return None
    pitches = rows["pitches"].apply(_parse_number)
    values = rows[column].apply(_parse_number)
    valid = [
        (pitch_count, value)
        for pitch_count, value in zip(pitches, values, strict=False)
        if pitch_count and value is not None
    ]
    if not valid:
        return None
    total_pitches = sum(pitch_count for pitch_count, _ in valid)
    if not total_pitches:
        return None
    return sum(pitch_count * value for pitch_count, value in valid) / total_pitches


def _format_unqualified_percentile_stat(metric_id: str, value: float | int) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    if metric_id in {"xera"}:
        return f"{number:.2f}"
    if metric_id in {
        "xwoba", "xba", "xslg", "xiso", "xobp",
    }:
        return f"{number:.3f}"
    if metric_id in {
        "hard_hit_percent", "brl_percent", "k_percent", "bb_percent",
        "whiff_percent", "chase_percent", "squared_up_rate",
    }:
        return f"{number:.1f}%"
    if metric_id in {"exit_velocity", "max_ev", "fb_velocity", "sprint_speed", "arm_strength"}:
        return f"{number:.1f}"
    if metric_id in {"fb_spin", "curve_spin"}:
        return f"{round(number):,}"
    if metric_id in {"brl", "oaa"}:
        return str(round(number))
    if metric_id in {"bat_speed"}:
        return f"{number:.1f}"
    if metric_id in {"swing_length"}:
        return f"{number:.1f}"
    return str(round(number, 1))


def _fetch_pitcher_raw_statcast_values(
    mlbam_id: int,
    season_year: int,
) -> dict[str, float | int]:
    values: dict[str, float | int] = {}

    try:
        expected = statcast_pitcher_expected_stats(season_year, minPA=0)
        row = expected[expected["player_id"] == mlbam_id]
        if not row.empty:
            record = row.iloc[0]
            for metric_id, column in (
                ("xera", "xera"),
                ("xwoba", "est_woba"),
                ("xba", "est_ba"),
                ("xslg", "est_slg"),
            ):
                parsed = _parse_number(record.get(column))
                if parsed is not None:
                    values[metric_id] = parsed
            est_ba = _parse_number(record.get("est_ba"))
            est_slg = _parse_number(record.get("est_slg"))
            if est_ba is not None and est_slg is not None:
                values["xiso"] = est_slg - est_ba
    except Exception:
        pass

    try:
        contact = statcast_pitcher_exitvelo_barrels(season_year, minBBE=0)
        row = contact[contact["player_id"] == mlbam_id]
        if not row.empty:
            record = row.iloc[0]
            for metric_id, column in (
                ("exit_velocity", "avg_hit_speed"),
                ("max_ev", "max_hit_speed"),
                ("brl_percent", "brl_percent"),
                ("brl", "barrels"),
            ):
                parsed = _parse_number(record.get(column))
                if parsed is not None:
                    values[metric_id] = parsed
            hard_hit = _parse_number(record.get("ev95percent"))
            if hard_hit is not None:
                values["hard_hit_percent"] = hard_hit
    except Exception:
        pass

    try:
        discipline = _get_discipline_table(season_year, "pitcher")
        if discipline is not None:
            row = discipline[discipline["player_id"] == mlbam_id]
            if not row.empty:
                record = row.iloc[0]
                for metric_id, column in (
                    ("k_percent", "k_percent"),
                    ("bb_percent", "bb_percent"),
                    ("whiff_percent", "whiff_percent"),
                    ("chase_percent", "chase_percent"),
                ):
                    parsed = _parse_number(record.get(column))
                    if parsed is not None:
                        values[metric_id] = parsed
    except Exception:
        pass

    try:
        arsenal = statcast_pitcher_arsenal_stats(season_year, minPA=1)
        rows = arsenal[arsenal["player_id"] == mlbam_id]
        if not rows.empty:
            for metric_id, column in (
                ("k_percent", "k_percent"),
                ("whiff_percent", "whiff_percent"),
                ("hard_hit_percent", "hard_hit_percent"),
            ):
                if metric_id not in values:
                    parsed = _weighted_pitcher_arsenal_rates(rows, column)
                    if parsed is not None:
                        values[metric_id] = parsed
    except Exception:
        pass

    try:
        velo_df = statcast_pitcher_pitch_arsenal(season_year, minP=1, arsenal_type="avg_speed")
        spin_df = statcast_pitcher_pitch_arsenal(season_year, minP=1, arsenal_type="avg_spin")
        velo_row = velo_df[velo_df["pitcher"] == mlbam_id]
        spin_row = spin_df[spin_df["pitcher"] == mlbam_id]
        if not velo_row.empty:
            ff_velo = _parse_number(velo_row.iloc[0].get("ff_avg_speed"))
            if ff_velo is not None:
                values["fb_velocity"] = ff_velo
        if not spin_row.empty:
            ff_spin = _parse_number(spin_row.iloc[0].get("ff_avg_spin"))
            curve_spin = _parse_number(spin_row.iloc[0].get("cu_avg_spin"))
            if ff_spin is not None:
                values["fb_spin"] = ff_spin
            if curve_spin is not None:
                values["curve_spin"] = curve_spin
    except Exception:
        pass

    return values


def _fetch_batter_raw_statcast_values(
    mlbam_id: int,
    season_year: int,
) -> dict[str, float | int]:
    values: dict[str, float | int] = {}

    try:
        expected = statcast_batter_expected_stats(season_year, minPA=0)
        row = expected[expected["player_id"] == mlbam_id]
        if not row.empty:
            record = row.iloc[0]
            for metric_id, column in (
                ("xwoba", "est_woba"),
                ("xba", "est_ba"),
                ("xslg", "est_slg"),
            ):
                parsed = _parse_number(record.get(column))
                if parsed is not None:
                    values[metric_id] = parsed
            est_ba = _parse_number(record.get("est_ba"))
            est_slg = _parse_number(record.get("est_slg"))
            if est_ba is not None and est_slg is not None:
                values["xiso"] = est_slg - est_ba
    except Exception:
        pass

    try:
        contact = statcast_batter_exitvelo_barrels(season_year, minBBE=0)
        row = contact[contact["player_id"] == mlbam_id]
        if not row.empty:
            record = row.iloc[0]
            for metric_id, column in (
                ("exit_velocity", "avg_hit_speed"),
                ("max_ev", "max_hit_speed"),
                ("brl_percent", "brl_percent"),
                ("brl", "barrels"),
            ):
                parsed = _parse_number(record.get(column))
                if parsed is not None:
                    values[metric_id] = parsed
            hard_hit = _parse_number(record.get("ev95percent"))
            if hard_hit is not None:
                values["hard_hit_percent"] = hard_hit
    except Exception:
        pass

    try:
        discipline = _get_discipline_table(season_year, "batter")
        if discipline is not None:
            row = discipline[discipline["player_id"] == mlbam_id]
            if not row.empty:
                record = row.iloc[0]
                for metric_id, column in (
                    ("k_percent", "k_percent"),
                    ("bb_percent", "bb_percent"),
                    ("whiff_percent", "whiff_percent"),
                    ("chase_percent", "chase_percent"),
                ):
                    parsed = _parse_number(record.get(column))
                    if parsed is not None:
                        values[metric_id] = parsed
    except Exception:
        pass

    try:
        tracking = _get_bat_tracking_table(season_year)
        if tracking is not None and "id" in tracking.columns:
            row = tracking[tracking["id"] == mlbam_id]
            if not row.empty:
                record = row.iloc[0]
                bat_speed = _parse_number(record.get("avg_bat_speed"))
                swing_length = _parse_number(record.get("swing_length"))
                squared_up = _parse_number(record.get("squared_up_per_swing"))
                if bat_speed is not None:
                    values["bat_speed"] = bat_speed
                if swing_length is not None:
                    values["swing_length"] = swing_length
                if squared_up is not None:
                    values["squared_up_rate"] = squared_up * 100
    except Exception:
        pass

    try:
        sprint = _get_sprint_speed_table(season_year)
        if sprint is not None:
            row = sprint[sprint["player_id"] == mlbam_id]
            if not row.empty:
                sprint_speed = _parse_number(row.iloc[0].get("sprint_speed"))
                if sprint_speed is not None:
                    values["sprint_speed"] = sprint_speed
    except Exception:
        pass

    return values


def _build_percentile_groups(
    row: pd.Series,
    group_specs: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_title, metric_specs in group_specs:
        metrics: list[dict[str, Any]] = []
        for metric_id, label in metric_specs:
            if metric_id not in row.index:
                continue
            value = _parse_number(row.get(metric_id))
            if value is None:
                continue
            metrics.append({
                "id": metric_id,
                "label": label,
                "value": round(value),
            })
        if metrics:
            groups.append({"title": group_title, "metrics": metrics})
    return groups


def _build_unqualified_percentile_groups(
    raw_values: dict[str, float | int],
    group_specs: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_title, metric_specs in group_specs:
        metrics: list[dict[str, Any]] = []
        for metric_id, label in metric_specs:
            if metric_id not in raw_values:
                continue
            value = raw_values[metric_id]
            if value is None:
                continue
            metrics.append({
                "id": metric_id,
                "label": label,
                "display": _format_unqualified_percentile_stat(metric_id, value),
            })
        if metrics:
            groups.append({"title": group_title, "metrics": metrics})
    return groups


def _empty_percentile_panel(season_year: int) -> dict[str, Any]:
    return {
        "id": "percentile_ranks",
        "label": "Percentile Rankings",
        "panel_kind": "percentile_ranks",
        "season_year": str(season_year),
        "qualified": False,
        "groups": [],
    }


def _qualified_percentile_panel(
    season_year: int,
    *,
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_empty_percentile_panel(season_year),
        "qualified": True,
        "groups": groups,
    }


def _unqualified_percentile_panel(
    season_year: int,
    *,
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_empty_percentile_panel(season_year),
        "qualified": False,
        "groups": groups,
    }


def _fetch_batter_percentile_panel(
    *,
    mlbam_id: int | None,
    season_year: int,
) -> dict[str, Any]:
    empty = _empty_percentile_panel(season_year)
    if not mlbam_id:
        return empty

    table = _get_batter_percentile_table(season_year)
    if table is not None and not table.empty:
        player_rows = table[table["player_id"] == mlbam_id]
        if not player_rows.empty:
            groups = _build_percentile_groups(player_rows.iloc[0], _BATTER_PERCENTILE_GROUPS)
            if groups:
                return _qualified_percentile_panel(season_year, groups=groups)

    raw_values = _fetch_batter_raw_statcast_values(mlbam_id, season_year)
    groups = _build_unqualified_percentile_groups(raw_values, _BATTER_PERCENTILE_GROUPS)
    if groups:
        return _unqualified_percentile_panel(season_year, groups=groups)
    return empty


def _fetch_pitcher_percentile_panel(
    *,
    mlbam_id: int | None,
    season_year: int,
) -> dict[str, Any]:
    empty = _empty_percentile_panel(season_year)
    if not mlbam_id:
        return empty

    table = _get_pitcher_percentile_table(season_year)
    if table is not None and not table.empty:
        player_rows = table[table["player_id"] == mlbam_id]
        if not player_rows.empty:
            groups = _build_percentile_groups(player_rows.iloc[0], _PITCHER_PERCENTILE_GROUPS)
            if groups:
                return _qualified_percentile_panel(season_year, groups=groups)

    raw_values = _fetch_pitcher_raw_statcast_values(mlbam_id, season_year)
    groups = _build_unqualified_percentile_groups(raw_values, _PITCHER_PERCENTILE_GROUPS)
    if groups:
        return _unqualified_percentile_panel(season_year, groups=groups)
    return empty


def _percentile_available_years(debut_year: int | None) -> list[str]:
    end_year = date.today().year
    start_year = max(_PERCENTILE_MIN_YEAR, int(debut_year) if debut_year else _PERCENTILE_MIN_YEAR)
    return [str(y) for y in range(end_year, start_year - 1, -1)]


def _attach_percentile_year_options(
    panel: dict[str, Any],
    *,
    debut_year: int | None,
) -> dict[str, Any]:
    panel["available_years"] = _percentile_available_years(debut_year)
    return panel


def fetch_batter_percentile_panel(
    player_name: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any]:
    year = season_year if season_year is not None else date.today().year
    record = _lookup_player_record(player_name) if player_name else None
    mlbam_id = (record or {}).get("mlbam_id")
    debut_year = (record or {}).get("debut_year")
    panel = _fetch_batter_percentile_panel(mlbam_id=mlbam_id, season_year=year)
    return _attach_percentile_year_options(panel, debut_year=debut_year)


def fetch_pitcher_percentile_panel(
    player_name: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any]:
    year = season_year if season_year is not None else date.today().year
    record = _lookup_player_record(player_name) if player_name else None
    mlbam_id = (record or {}).get("mlbam_id")
    debut_year = (record or {}).get("debut_year")
    panel = _fetch_pitcher_percentile_panel(mlbam_id=mlbam_id, season_year=year)
    return _attach_percentile_year_options(panel, debut_year=debut_year)


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


def _resolve_panel_year(season_year: str | int | None) -> int:
    if season_year is not None:
        try:
            return int(season_year)
        except (TypeError, ValueError):
            pass
    return date.today().year


def _fetch_espn_stat_categories(player_id: str) -> dict[str, Any]:
    cached = _espn_categories_cache.get(player_id)
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

    _espn_categories_cache[player_id] = (now, categories)
    return categories


def _empty_player_stats_panel(*, pitching: bool, season_year: int) -> dict[str, Any]:
    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": "pitching" if pitching else "batting",
        "season_year": str(season_year),
        "views": [{
            "id": "pitching" if pitching else "batting",
            "label": "Pitching" if pitching else "Batting",
            "metrics": [],
        }],
    }


def _empty_splits_panel() -> dict[str, Any]:
    return {
        "id": "splits",
        "label": "Splits",
        "panel_kind": "toggle_splits",
        "default_view": "regular",
        "views": [
            {"id": "regular", "label": "Regular", "groups": []},
            {"id": "advanced", "label": "Advanced", "groups": []},
        ],
    }


def fetch_player_core_stat_panels(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> list[dict[str, Any]]:
    if not player_id:
        return []

    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:core:v1"
    cached = _player_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    categories = _fetch_espn_stat_categories(player_id)
    player_stats_panel = _build_player_stats_panel(
        categories,
        pitching=pitching,
        season_year=year,
    ) or _empty_player_stats_panel(pitching=pitching, season_year=year)
    panels = [player_stats_panel]
    _player_core_panels_cache[cache_key] = (now, panels)
    return panels


def fetch_player_visual_stat_panel(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any] | None:
    if not player_id:
        return None

    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:visual:v1"
    cached = _player_visual_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    player_record = _lookup_player_record(player_name) if player_name else None
    mlbam_id = (player_record or {}).get("mlbam_id")
    panel = (
        _fetch_pitch_mix_panel(mlbam_id=mlbam_id, season_year=year)
        if pitching
        else _fetch_spray_chart_panel(mlbam_id=mlbam_id, season_year=year)
    )
    _player_visual_panel_cache[cache_key] = (now, panel)
    return panel


def fetch_player_percentile_stat_panel(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any] | None:
    if not player_id:
        return None

    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:percentile:v1"
    cached = _player_percentile_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    player_record = _lookup_player_record(player_name) if player_name else None
    mlbam_id = (player_record or {}).get("mlbam_id")
    if pitching:
        panel = _attach_percentile_year_options(
            _fetch_pitcher_percentile_panel(mlbam_id=mlbam_id, season_year=year),
            debut_year=(player_record or {}).get("debut_year"),
        )
    else:
        panel = _attach_percentile_year_options(
            _fetch_batter_percentile_panel(mlbam_id=mlbam_id, season_year=year),
            debut_year=(player_record or {}).get("debut_year"),
        )
    _player_percentile_panel_cache[cache_key] = (now, panel)
    return panel


def fetch_player_splits_stat_panel(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any] | None:
    if not player_id:
        return None

    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:splits:v1"
    cached = _player_splits_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    player_record = _lookup_player_record(player_name) if player_name else None
    bbref_id = (player_record or {}).get("bbref_id")
    panel = (
        _fetch_splits_panels(bbref_id, pitching=pitching, season_year=year)
        if bbref_id
        else _empty_splits_panel()
    )
    _player_splits_panel_cache[cache_key] = (now, panel)
    return panel


def fetch_player_stat_panels(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> list[dict[str, Any]]:
    if not player_id:
        return []

    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:all:v17"
    cached = _stat_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panels: list[dict[str, Any]] = []
    panels.extend(fetch_player_core_stat_panels(
        player_id,
        player_name=player_name,
        position=position,
        season_year=year,
    ))
    visual_panel = fetch_player_visual_stat_panel(
        player_id,
        player_name=player_name,
        position=position,
        season_year=year,
    )
    if visual_panel:
        panels.append(visual_panel)
    percentile_panel = fetch_player_percentile_stat_panel(
        player_id,
        player_name=player_name,
        position=position,
        season_year=year,
    )
    if percentile_panel:
        panels.append(percentile_panel)
    splits_panel = fetch_player_splits_stat_panel(
        player_id,
        player_name=player_name,
        position=position,
        season_year=year,
    )
    if splits_panel:
        panels.append(splits_panel)
    _stat_panels_cache[cache_key] = (now, panels)
    return panels
