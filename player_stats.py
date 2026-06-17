"""Player season/career stats via pybaseball with source fallbacks."""

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
_SPRAY_BB_TYPE_LABELS = {
    "ground_ball": "Ground Ball",
    "line_drive": "Line Drive",
    "fly_ball": "Fly Ball",
    "popup": "Popup",
}
_SPRAY_BB_TYPE_RATE_COLUMNS = (
    ("ground_ball", "gb_rate"),
    ("line_drive", "ld_rate"),
    ("fly_ball", "fb_rate"),
    ("popup", "pu_rate"),
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
_SAVANT_BATTED_BALL_URL = (
    "https://baseballsavant.mlb.com/leaderboard/batted-ball?year={year}&min=0&csv=true"
)
_SAVANT_PLAYER_PAGE_URL = (
    "https://baseballsavant.mlb.com/savant-player/{player_id}"
    "?stats=statcast-r-{kind}-mlb"
)
_savant_career_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
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
_batted_ball_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_exitvelo_batter_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_expected_batter_table_cache: dict[int, tuple[float, pd.DataFrame | None]] = {}
_pitching_bref_season_cache: dict[int, pd.DataFrame] = {}
_ESPN_SEASON_PITCHING_CATEGORY = "pitching"
_ESPN_SEASON_BATTING_CATEGORY = "career-batting"
_ESPN_TO_PITCHING_COLUMN = {
    "G": "GP",
    "SO": "K",
}
_ESPN_TO_BATTING_COLUMN = {
    "BA": "AVG",
    "G": "GP",
}
_CAREER_LOG_BATTING_TABLE_COLUMNS = (
    "G", "AB", "BA", "OBP", "SLG", "OPS", "HR", "RBI", "SB", "OPS+",
)
_CAREER_LOG_PITCHING_TABLE_COLUMNS = (
    "G", "GS", "W", "L", "ERA", "IP", "SO", "WHIP", "WAR",
)
_CAREER_LOG_HEADER_LABELS = {
    "BA": "AVG",
}
_SAVANT_BATTING_LEAGUE_KEYS = {
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
_SAVANT_PITCHING_LEAGUE_KEYS = {
    "ERA": "ERA",
    "WHIP": "WHIP",
    "W": "wins",
    "L": "losses",
    "SO": "strikeouts",
    "BB": "walks",
    "H": "hits",
    "ER": "earnedRuns",
    "HR": "homeRuns",
    "IP": "innings",
}
_espn_team_abbr_cache: dict[str, str] = {}


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
        "fangraphs_id": int(row.get("key_fangraphs")) if pd.notna(row.get("key_fangraphs")) else None,
        "debut_year": int(debut) if pd.notna(debut) else None,
        "last_year": int(last_played) if pd.notna(last_played) else date.today().year,
    }
    if not any((record["bbref_id"], record["mlbam_id"], record["fangraphs_id"])):
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


def _load_bwar_bat() -> pd.DataFrame | None:
    global _bwar_bat_df, _bwar_bat_loaded_at
    now = time.time()
    if _bwar_bat_df is not None and now - _bwar_bat_loaded_at < _CACHE_TTL_SECONDS:
        return _bwar_bat_df
    try:
        _bwar_bat_df = bwar_bat()
        _bwar_bat_loaded_at = now
        return _bwar_bat_df
    except Exception:
        return None


def _load_bwar_pitch() -> pd.DataFrame | None:
    global _bwar_pitch_df, _bwar_pitch_loaded_at
    now = time.time()
    if _bwar_pitch_df is not None and now - _bwar_pitch_loaded_at < _CACHE_TTL_SECONDS:
        return _bwar_pitch_df
    try:
        import io

        from pybaseball.datasources.bref import BRefSession

        response = BRefSession().get("http://www.baseball-reference.com/data/war_daily_pitch.txt")
        text = response.content.decode("utf-8", errors="replace")
        if text.lstrip().startswith("<"):
            return None
        frame = pd.read_csv(io.StringIO(text))
        cols_to_keep = [
            "name_common", "mlb_ID", "player_ID", "year_ID", "team_ID", "stint_ID", "lg_ID",
            "G", "GS", "RA", "xRA", "BIP", "BIP_perc", "salary", "ERA_plus", "WAR_rep", "WAA",
            "WAA_adj", "WAR",
        ]
        _bwar_pitch_df = frame[cols_to_keep]
        _bwar_pitch_loaded_at = now
        return _bwar_pitch_df
    except Exception:
        return None


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
    if frame is None or frame.empty:
        return None, None
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


def _column_specs_for_kind(kind: str) -> tuple[tuple[str, str], ...]:
    return _PITCHING_COLUMNS if kind == "pitching" else _BATTING_COLUMNS


def _values_from_espn_row(
    labels: list[str],
    stats: list[Any],
    column_labels: list[str],
    *,
    pitching: bool,
) -> dict[str, Any]:
    source = dict(zip(labels, stats))
    alias_map = _ESPN_TO_PITCHING_COLUMN if pitching else _ESPN_TO_BATTING_COLUMN
    values: dict[str, Any] = {}
    for label in column_labels:
        source_key = alias_map.get(label, label)
        if source_key in source:
            values[label] = source[source_key]
        elif label in source:
            values[label] = source[label]
    return values


_MULTI_TEAM_LABEL = "Multiple teams"


def _espn_stat_source(labels: list[str], stats: list[Any]) -> dict[str, Any]:
    return dict(zip(labels, stats))


def _merge_espn_pitching_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
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
    war_values: list[float] = []
    for source in sources:
        totals["G"] += _parse_number(source.get("GP")) or 0.0
        totals["GS"] += _parse_number(source.get("GS")) or 0.0
        totals["W"] += _parse_number(source.get("W")) or 0.0
        totals["L"] += _parse_number(source.get("L")) or 0.0
        totals["SV"] += _parse_number(source.get("SV")) or 0.0
        totals["SO"] += _parse_number(source.get("K")) or 0.0
        totals["H"] += _parse_number(source.get("H")) or 0.0
        totals["BB"] += _parse_number(source.get("BB")) or 0.0
        totals["ER"] += _parse_number(source.get("ER")) or 0.0
        totals["ip_outs"] += _ip_to_outs(source.get("IP"))
        war = _parse_number(source.get("WAR"))
        if war is not None:
            war_values.append(war)

    innings = totals["ip_outs"] / 3.0
    era = (totals["ER"] / innings * 9) if innings > 0 else None
    whip = ((totals["H"] + totals["BB"]) / innings) if innings > 0 else None
    war_total = sum(war_values) if war_values else None

    return {
        "GP": _format_count(totals["G"]),
        "GS": _format_count(totals["GS"]),
        "W": _format_count(totals["W"]),
        "L": _format_count(totals["L"]),
        "SV": _format_count(totals["SV"]),
        "K": _format_count(totals["SO"]),
        "IP": _outs_to_ip(totals["ip_outs"]),
        "ERA": "—" if era is None else f"{era:.2f}",
        "WHIP": "—" if whip is None else f"{whip:.2f}",
        "WAR": _format_war(war_total) if war_total is not None else "—",
    }


def _merge_espn_batting_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "GP": 0.0,
        "AB": 0.0,
        "R": 0.0,
        "H": 0.0,
        "2B": 0.0,
        "3B": 0.0,
        "HR": 0.0,
        "RBI": 0.0,
        "BB": 0.0,
        "HBP": 0.0,
        "SO": 0.0,
        "SB": 0.0,
        "CS": 0.0,
    }
    war_values: list[float] = []
    for source in sources:
        totals["GP"] += _parse_number(source.get("GP")) or 0.0
        totals["AB"] += _parse_number(source.get("AB")) or 0.0
        totals["R"] += _parse_number(source.get("R")) or 0.0
        totals["H"] += _parse_number(source.get("H")) or 0.0
        totals["2B"] += _parse_number(source.get("2B")) or 0.0
        totals["3B"] += _parse_number(source.get("3B")) or 0.0
        totals["HR"] += _parse_number(source.get("HR")) or 0.0
        totals["RBI"] += _parse_number(source.get("RBI")) or 0.0
        totals["BB"] += _parse_number(source.get("BB")) or 0.0
        totals["HBP"] += _parse_number(source.get("HBP")) or 0.0
        totals["SO"] += _parse_number(source.get("SO")) or 0.0
        totals["SB"] += _parse_number(source.get("SB")) or 0.0
        totals["CS"] += _parse_number(source.get("CS")) or 0.0
        war = _parse_number(source.get("WAR"))
        if war is not None:
            war_values.append(war)

    ab = totals["AB"]
    hits = totals["H"]
    singles = hits - totals["2B"] - totals["3B"] - totals["HR"]
    total_bases = singles + (2 * totals["2B"]) + (3 * totals["3B"]) + (4 * totals["HR"])
    avg = (hits / ab) if ab > 0 else None
    obp_den = ab + totals["BB"] + totals["HBP"]
    obp = ((hits + totals["BB"] + totals["HBP"]) / obp_den) if obp_den > 0 else None
    slg = (total_bases / ab) if ab > 0 else None
    ops = (obp + slg) if obp is not None and slg is not None else None
    war_total = sum(war_values) if war_values else None

    return {
        "GP": _format_count(totals["GP"]),
        "AB": _format_count(totals["AB"]),
        "R": _format_count(totals["R"]),
        "H": _format_count(totals["H"]),
        "2B": _format_count(totals["2B"]),
        "3B": _format_count(totals["3B"]),
        "HR": _format_count(totals["HR"]),
        "RBI": _format_count(totals["RBI"]),
        "BB": _format_count(totals["BB"]),
        "HBP": _format_count(totals["HBP"]),
        "SO": _format_count(totals["SO"]),
        "SB": _format_count(totals["SB"]),
        "CS": _format_count(totals["CS"]),
        "AVG": _format_rate(avg) if avg is not None else "—",
        "OBP": _format_rate(obp) if obp is not None else "—",
        "SLG": _format_rate(slg) if slg is not None else "—",
        "OPS": _format_rate(ops) if ops is not None else "—",
        "WAR": _format_war(war_total) if war_total is not None else "—",
    }


def _collapse_espn_year_statistics(
    stats: list[dict[str, Any]],
    *,
    labels: list[str],
    column_labels: list[str],
    pitching: bool,
) -> dict[str, Any] | None:
    usable: list[dict[str, Any]] = []
    for stat in stats:
        values = _values_from_espn_row(
            labels,
            stat.get("stats") or [],
            column_labels,
            pitching=pitching,
        )
        if any(value not in (None, "", "--", "-", "—") for value in values.values()):
            usable.append(stat)
    if not usable:
        return None

    total_rows = [stat for stat in usable if not stat.get("teamId")]
    team_rows = [stat for stat in usable if stat.get("teamId")]

    if total_rows:
        chosen_stats = total_rows[0].get("stats") or []
    elif len(team_rows) == 1:
        chosen_stats = team_rows[0].get("stats") or []
    elif len(team_rows) > 1:
        sources = [
            _espn_stat_source(labels, stat.get("stats") or [])
            for stat in team_rows
        ]
        merged = (
            _merge_espn_pitching_sources(sources)
            if pitching
            else _merge_espn_batting_sources(sources)
        )
        chosen_stats = [merged.get(label) for label in labels]
    else:
        chosen_stats = usable[0].get("stats") or []

    return _values_from_espn_row(
        labels,
        chosen_stats,
        column_labels,
        pitching=pitching,
    )


def _all_season_rows_from_espn(
    categories: dict[str, Any],
    *,
    pitching: bool,
    column_labels: list[str],
) -> list[tuple[int, dict[str, Any]]]:
    category_name = (
        _ESPN_SEASON_PITCHING_CATEGORY if pitching else _ESPN_SEASON_BATTING_CATEGORY
    )
    category = categories.get(category_name) or {}
    labels = category.get("labels") or []
    if not labels:
        return []

    by_year: dict[int, list[dict[str, Any]]] = {}
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if year is None:
            continue
        by_year.setdefault(int(year), []).append(stat)

    rows: list[tuple[int, dict[str, Any]]] = []
    for year in sorted(by_year.keys(), reverse=True):
        values = _collapse_espn_year_statistics(
            by_year[year],
            labels=labels,
            column_labels=column_labels,
            pitching=pitching,
        )
        if values:
            rows.append((year, values))
    return rows


def _all_season_rows_from_bref_pitching(
    player_name: str,
    *,
    debut_year: int,
    last_year: int,
) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    for year in range(last_year, debut_year - 1, -1):
        row = _pitching_bref_row(player_name, year)
        if row is None:
            continue
        values = _build_row_values(row, war_value=None, pitching=True)
        rows.append((year, values))
    return rows


def _all_season_rows_from_bref_batting(
    bbref_id: str,
    *,
    column_labels: list[str],
) -> list[tuple[int, dict[str, Any]]]:
    splits = _cached_get_splits(bbref_id)
    if splits is None or splits.empty:
        return []

    rows: list[tuple[int, dict[str, Any]]] = []
    for split_type, split_name in splits.index:
        if split_type != "Season Totals":
            continue
        match = re.fullmatch(r"(\d{4}) Totals", str(split_name))
        if not match:
            continue
        year = int(match.group(1))
        row = splits.loc[(split_type, split_name)]
        values = _build_row_values(row, war_value=None, pitching=False)
        if "OPS+" in column_labels:
            values["OPS+"] = _stat_value(row, "sOPS+")
        rows.append((year, values))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows


def _career_values_from_table_columns(table: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in table.get("columns") or []:
        label = column.get("label")
        if not label:
            continue
        career_value = column.get("career")
        values[label] = None if career_value in (None, "—") else career_value
    return values


def _bref_season_ops_plus(bbref_id: str, year: int) -> Any:
    season_splits = _cached_get_splits(bbref_id, year=year)
    if season_splits is None or season_splits.empty:
        return None
    key = ("Season Totals", f"{year} Totals")
    if key not in season_splits.index:
        return None
    return _stat_value(season_splits.loc[key], "sOPS+")


def _enrich_season_rows_ops_plus(
    season_rows: list[tuple[int, dict[str, Any]]],
    *,
    player_record: dict[str, Any] | None,
    pitching: bool,
) -> list[tuple[int, dict[str, Any]]]:
    if pitching or not player_record or not player_record.get("bbref_id"):
        return season_rows

    bbref_id = player_record["bbref_id"]
    enriched: list[tuple[int, dict[str, Any]]] = []
    for year, values in season_rows:
        row_values = dict(values)
        ops_plus = row_values.get("OPS+")
        if ops_plus in (None, "", "--", "-", "—") or _parse_number(ops_plus) is None:
            bref_ops_plus = _bref_season_ops_plus(bbref_id, year)
            if bref_ops_plus is not None:
                row_values["OPS+"] = bref_ops_plus
        enriched.append((year, row_values))
    return enriched


def _enrich_season_rows_war(
    season_rows: list[tuple[int, dict[str, Any]]],
    *,
    player_name: str,
    pitching: bool,
    player_record: dict[str, Any] | None,
    espn_categories: dict[str, Any] | None,
) -> list[tuple[int, dict[str, Any]]]:
    enriched: list[tuple[int, dict[str, Any]]] = []
    for year, values in season_rows:
        row_values = dict(values)
        if _normalize_war_value(row_values.get("WAR")) is None:
            season_war, _ = _resolve_war_for_player(
                player_name,
                season_year=year,
                pitching=pitching,
                player_record=player_record,
                espn_categories=espn_categories,
            )
            if season_war is not None:
                row_values["WAR"] = season_war
        enriched.append((year, row_values))
    return enriched


def _expand_stats_table_seasons(
    table: dict[str, Any],
    *,
    player_name: str,
    player_record: dict[str, Any] | None,
    pitching: bool,
    year: int,
    espn_categories: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = table.get("kind") or ("pitching" if pitching else "batting")
    columns = _column_specs_for_kind(kind)
    column_labels = [label for _, label in columns]

    season_rows: list[tuple[int, dict[str, Any]]] = []
    if espn_categories:
        season_rows = _all_season_rows_from_espn(
            espn_categories,
            pitching=pitching,
            column_labels=column_labels,
        )

    if not season_rows and player_record:
        if pitching:
            debut_year = player_record.get("debut_year") or max(1995, year - 25)
            last_year = max(year, player_record.get("last_year") or year)
            season_rows = _all_season_rows_from_bref_pitching(
                player_name,
                debut_year=debut_year,
                last_year=last_year,
            )
        elif player_record.get("bbref_id"):
            season_rows = _all_season_rows_from_bref_batting(
                player_record["bbref_id"],
                column_labels=column_labels,
            )

    if not season_rows:
        return table

    season_rows = _enrich_season_rows_war(
        season_rows,
        player_name=player_name,
        pitching=pitching,
        player_record=player_record,
        espn_categories=espn_categories,
    )
    season_rows = _enrich_season_rows_ops_plus(
        season_rows,
        player_record=player_record,
        pitching=pitching,
    )

    career_values = _career_values_from_table_columns(table)
    season_values = dict(
        next((values for season_year, values in season_rows if season_year == year), season_rows[0][1])
    )
    return _build_stats_table_result(
        season_year=year,
        columns=columns,
        season_values=season_values,
        career_values=career_values,
        kind=kind,
        season_rows=season_rows,
    )


def _build_stats_table_result(
    *,
    season_year: int,
    columns: tuple[tuple[str, str], ...],
    season_values: dict[str, Any],
    career_values: dict[str, Any],
    kind: str,
    season_rows: list[tuple[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    table_columns: list[dict[str, str]] = []
    for _, label in columns:
        table_columns.append({
            "label": label,
            "season": _format_stat(label, season_values.get(label)),
            "career": _format_stat(label, career_values.get(label)),
        })

    row_source = season_rows or [(season_year, season_values)]
    formatted_rows: list[dict[str, Any]] = []
    for row_year, row_values in row_source:
        formatted_rows.append({
            "label": str(row_year),
            "row_kind": "season",
            "cells": {
                label: _format_stat(label, row_values.get(label))
                for _, label in columns
            },
        })
    formatted_rows.append({
        "label": "Career",
        "row_kind": "career",
        "cells": {
            label: _format_stat(label, career_values.get(label))
            for _, label in columns
        },
    })

    return {
        "kind": kind,
        "title": "Summary",
        "season_year": str(season_year),
        "columns": table_columns,
        "rows": formatted_rows,
    }


def _espn_team_abbr(team_id: str | None) -> str | None:
    if not team_id:
        return None
    cache_key = str(team_id)
    cached = _espn_team_abbr_cache.get(cache_key)
    if cached:
        return cached
    try:
        response = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{cache_key}",
            timeout=10,
        )
        response.raise_for_status()
        abbr = (response.json().get("team") or {}).get("abbreviation")
        if abbr:
            _espn_team_abbr_cache[cache_key] = str(abbr)
            return str(abbr)
    except requests.RequestException:
        pass
    return None


def _espn_season_team_by_year(
    categories: dict[str, Any],
    *,
    pitching: bool,
) -> dict[int, str | None]:
    category_name = (
        _ESPN_SEASON_PITCHING_CATEGORY if pitching else _ESPN_SEASON_BATTING_CATEGORY
    )
    category = categories.get(category_name) or {}
    teams_by_year: dict[int, set[str]] = {}
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        team_id = stat.get("teamId")
        if year is None or not team_id:
            continue
        abbr = _espn_team_abbr(team_id)
        if abbr:
            teams_by_year.setdefault(int(year), set()).add(abbr)

    teams: dict[int, str | None] = {}
    for year, abbrs in teams_by_year.items():
        if len(abbrs) > 1:
            teams[year] = _MULTI_TEAM_LABEL
        elif len(abbrs) == 1:
            teams[year] = next(iter(abbrs))
    return teams


def _attach_career_log(
    table: dict[str, Any],
    *,
    espn_categories: dict[str, Any] | None,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    rows = table.get("rows") or []
    season_rows = [row for row in rows if row.get("row_kind") == "season"]
    career_row = next((row for row in rows if row.get("row_kind") == "career"), None)
    if not season_rows:
        return table

    table_columns = list(
        _CAREER_LOG_PITCHING_TABLE_COLUMNS if pitching else _CAREER_LOG_BATTING_TABLE_COLUMNS
    )
    team_by_year = _espn_season_team_by_year(espn_categories or {}, pitching=pitching)

    seasons: list[dict[str, Any]] = []
    for row in season_rows:
        year = int(row["label"])
        cells = row.get("cells") or {}
        table_cells = {
            column: cells.get(column, "—")
            for column in table_columns
        }
        seasons.append({
            "year": year,
            "team": team_by_year.get(year),
            "cells": table_cells,
        })

    career_cells = {
        column: (career_row or {}).get("cells", {}).get(column, "—")
        for column in table_columns
    }

    table["career_log"] = {
        "table_columns": table_columns,
        "header_labels": _CAREER_LOG_HEADER_LABELS,
        "seasons": seasons,
        "career": {"cells": career_cells},
        "season_year": str(season_year),
    }
    return table


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

    season_war, career_war = _safe_war_for_player(
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
    season_war, career_war = _safe_war_for_player(
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


def _safe_war_for_player(
    player_name: str,
    *,
    season_year: int | None,
    pitching: bool,
) -> tuple[str | None, str | None]:
    try:
        return _war_for_player(
            player_name,
            season_year=season_year,
            pitching=pitching,
        )
    except Exception:
        return None, None


def _normalize_war_value(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in {"—", "--", "-"}:
        return None
    return _format_war(value)


def _war_from_espn_categories(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> tuple[str | None, str | None]:
    category_name = "pitching" if pitching else "advanced-batting"
    category = categories.get(category_name) or {}
    labels = category.get("labels") or []
    if "WAR" not in labels:
        return None, None

    war_idx = labels.index("WAR")
    season_raw: Any = None
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if str(year) != str(season_year):
            continue
        values = stat.get("stats") or []
        if war_idx < len(values):
            season_raw = values[war_idx]
        break

    career_raw: Any = None
    totals = category.get("totals") or []
    if war_idx < len(totals):
        career_raw = totals[war_idx]

    if _normalize_war_value(career_raw) is None:
        career_total = 0.0
        found = False
        for stat in category.get("statistics") or []:
            values = stat.get("stats") or []
            if war_idx >= len(values):
                continue
            value = _parse_number(values[war_idx])
            if value is None:
                continue
            career_total += value
            found = True
        if found:
            career_raw = career_total

    return _normalize_war_value(season_raw), _normalize_war_value(career_raw)


def _war_from_fangraphs(
    player_name: str,
    *,
    player_record: dict[str, Any],
    season_year: int,
    pitching: bool,
) -> tuple[str | None, str | None]:
    record = {**player_record, "player_name": player_name}
    if pitching:
        season_row, career_row = _fetch_fangraphs_pitching_frames(
            year=season_year,
            player_record=record,
        )
    else:
        season_row, career_row = _fetch_fangraphs_batting_frames(
            year=season_year,
            player_record=record,
        )
    season_war = _normalize_war_value(season_row.get("WAR")) if season_row is not None else None
    career_war = _normalize_war_value(career_row.get("WAR")) if career_row is not None else None
    return season_war, career_war


def _resolve_war_for_player(
    player_name: str,
    *,
    season_year: int,
    pitching: bool,
    player_record: dict[str, Any] | None,
    espn_categories: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    season_war, career_war = _safe_war_for_player(
        player_name,
        season_year=season_year,
        pitching=pitching,
    )

    if espn_categories and (season_war is None or career_war is None):
        espn_season_war, espn_career_war = _war_from_espn_categories(
            espn_categories,
            pitching=pitching,
            season_year=season_year,
        )
        if season_war is None:
            season_war = espn_season_war
        if career_war is None:
            career_war = espn_career_war

    if player_record and (season_war is None or career_war is None):
        fg_season_war, fg_career_war = _war_from_fangraphs(
            player_name,
            player_record=player_record,
            season_year=season_year,
            pitching=pitching,
        )
        if season_war is None:
            season_war = fg_season_war
        if career_war is None:
            career_war = fg_career_war

    return season_war, career_war


def _inject_war_into_stats_table(
    table: dict[str, Any],
    season_war: str | None,
    career_war: str | None,
) -> dict[str, Any]:
    if season_war is None and career_war is None:
        return table

    columns: list[dict[str, str]] = []
    for column in table.get("columns") or []:
        if column.get("label") != "WAR":
            columns.append(column)
            continue
        columns.append({
            "label": "WAR",
            "season": season_war if season_war is not None else column.get("season", "—"),
            "career": career_war if career_war is not None else column.get("career", "—"),
        })

    updated_rows: list[dict[str, Any]] = []
    for row in table.get("rows") or []:
        cells = dict(row.get("cells") or {})
        if season_war is not None and row.get("label") == str(table.get("season_year")):
            cells["WAR"] = season_war
        if career_war is not None and row.get("row_kind") == "career":
            cells["WAR"] = career_war
        updated_rows.append({**row, "cells": cells})

    result = {**table, "columns": columns}
    if updated_rows:
        result["rows"] = updated_rows
    return result


def _stats_table_has_data(table: dict[str, Any] | None) -> bool:
    if not table:
        return False
    for row in table.get("rows") or []:
        if row.get("row_kind") == "career":
            continue
        for value in (row.get("cells") or {}).values():
            if value and value != "—":
                return True
    for column in table.get("columns") or []:
        season_value = column.get("season")
        if season_value and season_value != "—":
            return True
    return False


def _match_name_rows(frame: pd.DataFrame, player_name: str) -> pd.DataFrame:
    if frame.empty or "Name" not in frame.columns:
        return frame.iloc[0:0]
    rows = frame[frame["Name"] == player_name]
    if not rows.empty:
        return rows
    folded_name = _fold_name(player_name)
    return frame[frame["Name"].map(lambda value: _fold_name(str(value))) == folded_name]


def _fangraphs_pitching_row(
    frame: pd.DataFrame | None,
    *,
    player_name: str,
    year: int,
) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    rows = _match_name_rows(frame, player_name)
    if "Season" in rows.columns:
        season_rows = rows[rows["Season"].astype(str) == str(year)]
        if not season_rows.empty:
            rows = season_rows
    if rows.empty:
        return None
    return rows.iloc[0]


def _fangraphs_pitching_values(row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "W": row.get("W"),
        "L": row.get("L"),
        "ERA": row.get("ERA"),
        "G": row.get("G"),
        "GS": row.get("GS"),
        "SV": row.get("SV"),
        "IP": row.get("IP"),
        "SO": row.get("SO"),
        "WHIP": row.get("WHIP"),
        "WAR": row.get("WAR"),
    }


def _fangraphs_batting_values(row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {}
    values = {
        "AB": row.get("AB"),
        "H": row.get("H"),
        "HR": row.get("HR"),
        "R": row.get("R"),
        "RBI": row.get("RBI"),
        "SB": row.get("SB"),
        "BA": row.get("AVG"),
        "OBP": row.get("OBP"),
        "SLG": row.get("SLG"),
        "OPS": row.get("OPS"),
        "WAR": row.get("WAR"),
    }
    if "OPS+" in row.index:
        values["OPS+"] = row.get("OPS+")
    elif "wRC+" in row.index:
        values["OPS+"] = row.get("wRC+")
    return values


def _fetch_fangraphs_pitching_frames(
    *,
    year: int,
    player_record: dict[str, Any],
) -> tuple[pd.Series | None, pd.Series | None]:
    from pybaseball import pitching_stats

    fangraphs_id = player_record.get("fangraphs_id")
    player_filter = str(fangraphs_id) if fangraphs_id else ""
    debut_year = player_record.get("debut_year") or max(1995, year - 25)
    last_year = max(year, player_record.get("last_year") or year)

    season_frame: pd.DataFrame | None = None
    career_frame: pd.DataFrame | None = None
    try:
        season_frame = pitching_stats(
            year,
            year,
            qual=0,
            split_seasons=True,
            players=player_filter,
        )
    except Exception:
        season_frame = None
    try:
        career_frame = pitching_stats(
            debut_year,
            last_year,
            qual=0,
            split_seasons=False,
            players=player_filter,
        )
    except Exception:
        career_frame = None

    player_name = str(player_record.get("player_name") or "")
    season_row = _fangraphs_pitching_row(season_frame, player_name=player_name, year=year)
    career_row = None
    if career_frame is not None and not career_frame.empty:
        career_rows = _match_name_rows(career_frame, player_name)
        if not career_rows.empty:
            career_row = career_rows.iloc[0]
    return season_row, career_row


def _fetch_fangraphs_batting_frames(
    *,
    year: int,
    player_record: dict[str, Any],
) -> tuple[pd.Series | None, pd.Series | None]:
    from pybaseball import batting_stats

    fangraphs_id = player_record.get("fangraphs_id")
    player_filter = str(fangraphs_id) if fangraphs_id else ""
    debut_year = player_record.get("debut_year") or max(1995, year - 25)
    last_year = max(year, player_record.get("last_year") or year)

    season_frame: pd.DataFrame | None = None
    career_frame: pd.DataFrame | None = None
    try:
        season_frame = batting_stats(
            year,
            qual=0,
            split_seasons=True,
            players=player_filter,
        )
    except Exception:
        season_frame = None
    try:
        career_frame = batting_stats(
            debut_year,
            end_season=last_year,
            qual=0,
            split_seasons=False,
            players=player_filter,
        )
    except Exception:
        career_frame = None

    player_name = str(player_record.get("player_name") or "")
    season_row = _fangraphs_pitching_row(season_frame, player_name=player_name, year=year)
    career_row = None
    if career_frame is not None and not career_frame.empty:
        career_rows = _match_name_rows(career_frame, player_name)
        if not career_rows.empty:
            career_row = career_rows.iloc[0]
    return season_row, career_row


def _fetch_pitching_stats_table_fangraphs(
    player_name: str,
    *,
    player_record: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    record = {**player_record, "player_name": player_name}
    season_row, career_row = _fetch_fangraphs_pitching_frames(year=year, player_record=record)
    if season_row is None and career_row is None:
        return None

    season_war = _format_war(season_row.get("WAR")) if season_row is not None else None
    career_war = _format_war(career_row.get("WAR")) if career_row is not None else None
    if season_war is None or career_war is None:
        bref_season_war, bref_career_war = _safe_war_for_player(
            player_name,
            season_year=year,
            pitching=True,
        )
        if season_war is None:
            season_war = bref_season_war
        if career_war is None:
            career_war = bref_career_war

    season_values = _fangraphs_pitching_values(season_row)
    career_values = _fangraphs_pitching_values(career_row)
    if season_war is not None:
        season_values["WAR"] = season_war
    if career_war is not None:
        career_values["WAR"] = career_war

    return _build_stats_table_result(
        season_year=year,
        columns=_PITCHING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="pitching",
    )


def _fetch_batting_stats_table_fangraphs(
    player_name: str,
    *,
    player_record: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    record = {**player_record, "player_name": player_name}
    season_row, career_row = _fetch_fangraphs_batting_frames(year=year, player_record=record)
    if season_row is None and career_row is None:
        return None

    season_war = _format_war(season_row.get("WAR")) if season_row is not None else None
    career_war = _format_war(career_row.get("WAR")) if career_row is not None else None
    if season_war is None or career_war is None:
        bref_season_war, bref_career_war = _safe_war_for_player(
            player_name,
            season_year=year,
            pitching=False,
        )
        if season_war is None:
            season_war = bref_season_war
        if career_war is None:
            career_war = bref_career_war

    season_values = _fangraphs_batting_values(season_row)
    career_values = _fangraphs_batting_values(career_row)
    if season_war is not None:
        season_values["WAR"] = season_war
    if career_war is not None:
        career_values["WAR"] = career_war

    return _build_stats_table_result(
        season_year=year,
        columns=_BATTING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="batting",
    )


def _fetch_mlb_stat_block(
    mlbam_id: int,
    *,
    group: str,
    stats_type: str,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"stats": stats_type, "group": group}
    if season_year is not None:
        params["season"] = season_year
    try:
        response = requests.get(
            _MLB_STATS_URL.format(player_id=mlbam_id),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return None

    stats_blocks = payload.get("stats") or []
    if not stats_blocks:
        return None
    splits = stats_blocks[0].get("splits") or []
    if not splits:
        return None
    stat = splits[0].get("stat")
    return stat if isinstance(stat, dict) else None


def _mlb_pitching_values(stat: dict[str, Any] | None) -> dict[str, Any]:
    if not stat:
        return {}
    return {
        "W": stat.get("wins"),
        "L": stat.get("losses"),
        "ERA": stat.get("era"),
        "G": stat.get("gamesPlayed"),
        "GS": stat.get("gamesStarted"),
        "SV": stat.get("saves"),
        "IP": stat.get("inningsPitched"),
        "SO": stat.get("strikeOuts"),
        "WHIP": stat.get("whip"),
    }


def _mlb_batting_values(stat: dict[str, Any] | None) -> dict[str, Any]:
    if not stat:
        return {}
    return {
        "AB": stat.get("atBats"),
        "H": stat.get("hits"),
        "HR": stat.get("homeRuns"),
        "R": stat.get("runs"),
        "RBI": stat.get("rbi"),
        "SB": stat.get("stolenBases"),
        "BA": stat.get("avg"),
        "OBP": stat.get("obp"),
        "SLG": stat.get("slg"),
        "OPS": stat.get("ops"),
    }


def _fetch_pitching_stats_table_mlb(
    player_name: str,
    *,
    player_record: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    mlbam_id = player_record.get("mlbam_id")
    if not mlbam_id:
        return None

    season_stat = _fetch_mlb_stat_block(
        mlbam_id,
        group="pitching",
        stats_type="season",
        season_year=year,
    )
    career_stat = _fetch_mlb_stat_block(
        mlbam_id,
        group="pitching",
        stats_type="career",
    )
    if not season_stat and not career_stat:
        return None

    season_war, career_war = _safe_war_for_player(
        player_name,
        season_year=year,
        pitching=True,
    )
    season_values = _mlb_pitching_values(season_stat)
    career_values = _mlb_pitching_values(career_stat)
    if season_war is not None:
        season_values["WAR"] = season_war
    if career_war is not None:
        career_values["WAR"] = career_war

    resolved_year = year
    if season_stat and season_stat.get("season"):
        try:
            resolved_year = int(season_stat["season"])
        except (TypeError, ValueError):
            resolved_year = year

    return _build_stats_table_result(
        season_year=resolved_year,
        columns=_PITCHING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="pitching",
    )


def _fetch_batting_stats_table_mlb(
    player_name: str,
    *,
    player_record: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    mlbam_id = player_record.get("mlbam_id")
    if not mlbam_id:
        return None

    season_stat = _fetch_mlb_stat_block(
        mlbam_id,
        group="hitting",
        stats_type="season",
        season_year=year,
    )
    career_stat = _fetch_mlb_stat_block(
        mlbam_id,
        group="hitting",
        stats_type="career",
    )
    if not season_stat and not career_stat:
        return None

    season_war, career_war = _safe_war_for_player(
        player_name,
        season_year=year,
        pitching=False,
    )
    season_values = _mlb_batting_values(season_stat)
    career_values = _mlb_batting_values(career_stat)
    if season_war is not None:
        season_values["WAR"] = season_war
    if career_war is not None:
        career_values["WAR"] = career_war
    if career_stat is not None:
        career_values["OPS+"] = _compute_career_ops_plus(
            career_stat.get("obp"),
            career_stat.get("slg"),
        )

    resolved_year = year
    if season_stat and season_stat.get("season"):
        try:
            resolved_year = int(season_stat["season"])
        except (TypeError, ValueError):
            resolved_year = year

    return _build_stats_table_result(
        season_year=resolved_year,
        columns=_BATTING_COLUMNS,
        season_values=season_values,
        career_values=career_values,
        kind="batting",
    )


def fetch_player_stats_table(
    player_name: str,
    season_year: str | int | None = None,
    *,
    position: str | None = None,
    espn_categories: dict[str, Any] | None = None,
    espn_player_id: str | None = None,
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
    cache_key = f"{player_name.lower()}:{year}:{'pitch' if pitching else 'bat'}:v10"
    cached = _stats_table_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    player_record = _lookup_player_record(player_name) or {
        "bbref_id": None,
        "mlbam_id": None,
        "fangraphs_id": None,
        "debut_year": None,
        "last_year": year,
    }

    if pitching:
        fetchers = (
            lambda: _fetch_pitching_stats_table(
                player_name,
                player_record=player_record,
                year=year,
            ),
            lambda: _fetch_pitching_stats_table_fangraphs(
                player_name,
                player_record=player_record,
                year=year,
            ),
            lambda: _fetch_pitching_stats_table_mlb(
                player_name,
                player_record=player_record,
                year=year,
            ),
        )
    else:
        fetchers_list: list[Any] = []
        if player_record.get("bbref_id"):
            fetchers_list.append(
                lambda: _fetch_batting_stats_table(
                    player_name,
                    bbref_id=player_record["bbref_id"],
                    year=year,
                )
            )
        fetchers_list.extend([
            lambda: _fetch_batting_stats_table_fangraphs(
                player_name,
                player_record=player_record,
                year=year,
            ),
            lambda: _fetch_batting_stats_table_mlb(
                player_name,
                player_record=player_record,
                year=year,
            ),
        ])
        fetchers = tuple(fetchers_list)

    result: dict[str, Any] | None = None
    try:
        for fetcher in fetchers:
            try:
                candidate = fetcher()
            except Exception:
                continue
            if _stats_table_has_data(candidate):
                result = candidate
                break
        if result:
            categories = espn_categories
            if categories is None and espn_player_id:
                categories = _fetch_espn_stat_categories(espn_player_id)
            result = _expand_stats_table_seasons(
                result,
                player_name=player_name,
                player_record=player_record,
                pitching=pitching,
                year=year,
                espn_categories=categories,
            )
            season_war, career_war = _resolve_war_for_player(
                player_name,
                season_year=year,
                pitching=pitching,
                player_record=player_record,
                espn_categories=categories,
            )
            result = _inject_war_into_stats_table(result, season_war, career_war)
            result = _attach_career_log(
                result,
                espn_categories=categories,
                pitching=pitching,
                season_year=year,
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


def _build_league_average_view(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    from league_player_averages import get_league_player_stats_by_category
    from team_stats import (
        _BATTING_DETAIL_SPECS,
        _PITCHING_DETAIL_SPECS,
        _build_stat_metrics,
    )

    league_stats = get_league_player_stats_by_category(season_year)
    if pitching:
        player_pitching = _parse_player_pitching_stats(categories, season_year=season_year)
        pitching_metrics = _build_stat_metrics(
            player_pitching,
            _PITCHING_DETAIL_SPECS,
            category="pitching",
            league_stats=league_stats.get("pitching") or {},
        )
        return {
            "id": "league_average",
            "label": "League Average",
            "metrics": pitching_metrics or [],
        }

    player_batting = _parse_player_batting_stats(categories, season_year=season_year)
    batting_metrics = _build_stat_metrics(
        player_batting,
        _BATTING_DETAIL_SPECS,
        category="batting",
        league_stats=league_stats.get("batting") or {},
    )
    return {
        "id": "league_average",
        "label": "League Average",
        "metrics": batting_metrics or [],
    }


def _espn_timeline_standard_columns(*, pitching: bool) -> tuple[str, ...]:
    if pitching:
        return (
            "Season", "Tm", "LG", "W", "L", "ERA", "G", "GS", "SV", "IP", "SO", "BB", "WHIP",
        )
    return (
        "Season", "Tm", "LG", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI",
        "BB", "SO", "SB", "AVG", "OBP", "SLG", "OPS",
    )


def _espn_pa_by_year(categories: dict[str, Any]) -> dict[int, str]:
    category = categories.get("expanded-batting") or {}
    labels = category.get("labels") or []
    if "PA" not in labels:
        return {}
    pa_idx = labels.index("PA")
    by_year: dict[int, str] = {}
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if year is None:
            continue
        values = stat.get("stats") or []
        if pa_idx < len(values):
            by_year[int(year)] = str(values[pa_idx])
    return by_year


def _espn_year_source(
    stats: list[dict[str, Any]],
    *,
    labels: list[str],
    pitching: bool,
) -> dict[str, Any] | None:
    usable: list[dict[str, Any]] = []
    for stat in stats:
        values = stat.get("stats") or []
        if any(str(value).strip() not in {"", "--", "-", "—"} for value in values):
            usable.append(stat)
    if not usable:
        return None

    total_rows = [stat for stat in usable if not stat.get("teamId")]
    team_rows = [stat for stat in usable if stat.get("teamId")]

    if total_rows:
        return dict(zip(labels, total_rows[0].get("stats") or []))
    if len(team_rows) == 1:
        return dict(zip(labels, team_rows[0].get("stats") or []))
    if len(team_rows) > 1:
        sources = [
            _espn_stat_source(labels, stat.get("stats") or [])
            for stat in team_rows
        ]
        return (
            _merge_espn_pitching_sources(sources)
            if pitching
            else _merge_espn_batting_sources(sources)
        )
    return dict(zip(labels, usable[0].get("stats") or []))


def _espn_source_to_timeline_cells(
    source: dict[str, Any],
    *,
    pitching: bool,
) -> dict[str, str]:
    if pitching:
        mapping = {
            "GP": "G",
            "K": "SO",
            "W": "W",
            "L": "L",
            "ERA": "ERA",
            "GS": "GS",
            "SV": "SV",
            "IP": "IP",
            "BB": "BB",
            "WHIP": "WHIP",
        }
    else:
        mapping = {
            "GP": "G",
            "AB": "AB",
            "R": "R",
            "H": "H",
            "2B": "2B",
            "3B": "3B",
            "HR": "HR",
            "RBI": "RBI",
            "BB": "BB",
            "SO": "SO",
            "SB": "SB",
            "AVG": "AVG",
            "OBP": "OBP",
            "SLG": "SLG",
            "OPS": "OPS",
        }

    cells: dict[str, str] = {}
    for espn_key, timeline_key in mapping.items():
        if espn_key not in source:
            continue
        value = source[espn_key]
        if timeline_key in {"AVG", "OBP", "SLG", "OPS"}:
            cells[timeline_key] = _format_stat(
                "BA" if timeline_key == "AVG" else timeline_key,
                value,
            )
        elif timeline_key in {"ERA", "WHIP", "IP"}:
            cells[timeline_key] = _format_stat(timeline_key, value)
        else:
            cells[timeline_key] = _format_espn_value(value)
    return cells


def _timeline_row_from_espn_source(
    source: dict[str, Any],
    *,
    pitching: bool,
    columns: tuple[str, ...],
    season_label: str,
    row_kind: str,
    team: str | None = None,
    pa: str | None = None,
) -> dict[str, Any]:
    cells = _espn_source_to_timeline_cells(source, pitching=pitching)
    cells["Season"] = season_label
    cells["Tm"] = team or "—"
    cells["LG"] = "—"
    if pa is not None:
        cells["PA"] = _format_espn_value(pa)
    for column in columns:
        cells.setdefault(column, "—")
    return {
        "label": season_label,
        "row_kind": row_kind,
        "cells": cells,
    }


def _empty_espn_timeline_standard_table(*, pitching: bool, season_year: int) -> dict[str, Any]:
    return {
        "layout": "savant_career",
        "columns": list(_espn_timeline_standard_columns(pitching=pitching)),
        "rows": [],
        "season_year": str(season_year),
    }


def _build_espn_season_stats_standard_table(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    columns = _espn_timeline_standard_columns(pitching=pitching)
    category_name = (
        _ESPN_SEASON_PITCHING_CATEGORY if pitching else _ESPN_SEASON_BATTING_CATEGORY
    )
    category = categories.get(category_name) or {}
    labels = category.get("labels") or []
    if not labels:
        return _empty_espn_timeline_standard_table(
            pitching=pitching,
            season_year=season_year,
        )

    team_by_year = _espn_season_team_by_year(categories, pitching=pitching)
    pa_by_year = {} if pitching else _espn_pa_by_year(categories)

    by_year: dict[int, list[dict[str, Any]]] = {}
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if year is None:
            continue
        by_year.setdefault(int(year), []).append(stat)

    rows: list[dict[str, Any]] = []
    for year in sorted(by_year.keys(), reverse=True):
        source = _espn_year_source(by_year[year], labels=labels, pitching=pitching)
        if not source:
            continue
        rows.append(
            _timeline_row_from_espn_source(
                source,
                pitching=pitching,
                columns=columns,
                season_label=str(year),
                row_kind="season",
                team=team_by_year.get(year),
                pa=pa_by_year.get(year),
            )
        )

    totals = category.get("totals") or []
    if totals:
        career_source = dict(zip(labels, totals))
        rows.append(
            _timeline_row_from_espn_source(
                career_source,
                pitching=pitching,
                columns=columns,
                season_label="Career",
                row_kind="career",
            )
        )

    if not rows:
        return _empty_espn_timeline_standard_table(
            pitching=pitching,
            season_year=season_year,
        )

    table: dict[str, Any] = {
        "layout": "savant_career",
        "columns": list(columns),
        "rows": rows,
        "season_year": str(season_year),
    }
    return _attach_savant_timeline_league_bounds(table, pitching=pitching)


def _build_season_stats_nested_view(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    return {
        "id": "season_stats",
        "label": "Season Stats",
        "nested_panel": {
            "default_view": "standard",
            "views": [
                {
                    "id": "standard",
                    "label": "Standard",
                    "stats_table": _build_espn_season_stats_standard_table(
                        categories,
                        pitching=pitching,
                        season_year=season_year,
                    ),
                },
                {
                    "id": "advanced",
                    "label": "Advanced Stats",
                    "coming_soon": True,
                },
            ],
        },
    }


def _build_player_stats_panel_league_only(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any]:
    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": "league_average",
        "season_year": str(season_year),
        "views": [
            _build_league_average_view(
                categories,
                pitching=pitching,
                season_year=season_year,
            ),
            _build_season_stats_nested_view(
                categories,
                pitching=pitching,
                season_year=season_year,
            ),
        ],
    }


def _build_player_stats_panel(
    categories: dict[str, Any],
    *,
    pitching: bool,
    season_year: int,
    player_name: str = "",
    position: str | None = None,
) -> dict[str, Any] | None:
    views: list[dict[str, Any]] = [
        _build_league_average_view(
            categories,
            pitching=pitching,
            season_year=season_year,
        ),
    ]

    column_labels = [label for _, label in (_PITCHING_COLUMNS if pitching else _BATTING_COLUMNS)]
    stats_table = (
        fetch_player_stats_table(
            player_name,
            season_year,
            position=position,
            espn_categories=categories,
        )
        if player_name
        else None
    )
    if not stats_table:
        stats_table = _empty_stats_table(column_labels, season_year)

    views.append({
        "id": "season_stats",
        "label": "Season Stats",
        "stats_table": stats_table,
    })

    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": "league_average",
        "season_year": str(season_year),
        "views": views,
    }


def _empty_stats_table(labels: list[str] | tuple[str, ...], season_year: int) -> dict[str, Any]:
    empty_values = {label: None for label in labels}
    return _build_stats_table_result(
        season_year=season_year,
        columns=tuple((label, label) for label in labels),
        season_values=empty_values,
        career_values=empty_values,
        kind="pitching" if "ERA" in labels else "batting",
    )


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


def _table_row_value(row: pd.Series | None, key: str) -> Any:
    if row is None:
        return None
    return row.get(key)


def _espn_advanced_batting_row(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, str]:
    from team_stats import _espn_category_season_row

    return _espn_category_season_row(
        categories.get("advanced-batting"),
        season_year,
    )


def _format_hr_pace(ab_per_hr: Any) -> str | None:
    number = _parse_number(ab_per_hr)
    if number is None or number <= 0:
        return None
    pace = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"1 HR per {pace} AB"


_ARCHETYPE_THEMES = {
    "Patient masher": "patient_masher",
    "Power-first": "power_first",
    "Ground-ball contact": "ground_ball",
    "Fly-ball threat": "fly_ball",
    "Contact run producer": "contact_producer",
    "Balanced hitter": "balanced",
}


def _isop_context(isop: float | None) -> str | None:
    if isop is None:
        return None
    if isop >= 0.25:
        return "Elite isolated power"
    if isop >= 0.18:
        return "Plus power"
    if isop >= 0.14:
        return "Average power"
    return "Light power"


def _bb_k_context(bb_k: float | None) -> str | None:
    if bb_k is None:
        return None
    if bb_k >= 0.75:
        return "Elite plate discipline"
    if bb_k >= 0.5:
        return "Patient approach"
    if bb_k >= 0.35:
        return "Average discipline"
    return "Aggressive approach"


def _seca_context(seca: float | None) -> str | None:
    if seca is None:
        return None
    if seca >= 0.38:
        return "Strong secondary value"
    if seca >= 0.33:
        return "Plus secondary value"
    if seca >= 0.28:
        return "Average secondary value"
    return "Limited secondary value"


def _go_fo_context(go_fo: float | None) -> str | None:
    if go_fo is None:
        return None
    if go_fo >= 1.2:
        return "Ground-ball lean"
    if go_fo <= 0.8:
        return "Fly-ball lean"
    return "Balanced contact mix"


def _build_hit_archetype(
    metrics: dict[str, float | None],
    row: dict[str, str],
) -> dict[str, Any]:
    isop = metrics.get("isop")
    ab_hr = metrics.get("ab_hr")
    bb_k = metrics.get("bb_k")
    seca = metrics.get("seca")
    go_fo = metrics.get("go_fo")

    if bb_k is not None and bb_k >= 0.5 and isop is not None and isop >= 0.18:
        label = "Patient masher"
        drivers = ["Elite patience meets plus power"]
    elif isop is not None and isop >= 0.22 and ab_hr is not None and ab_hr <= 18:
        label = "Power-first"
        drivers = ["Power tools drive the profile"]
    elif go_fo is not None and go_fo >= 1.15:
        label = "Ground-ball contact"
        drivers = ["Contact skews to the ground"]
    elif go_fo is not None and go_fo <= 0.75 and isop is not None and isop >= 0.16:
        label = "Fly-ball threat"
        drivers = ["Lift and damage on contact"]
    elif seca is not None and seca >= 0.33:
        label = "Contact run producer"
        drivers = ["Creates runs beyond batting average"]
    else:
        label = "Balanced hitter"
        drivers = ["No single trait dominates the offensive profile"]

    signals: list[dict[str, Any]] = []
    isop_value = _format_espn_value(row.get("ISOP"))
    if isop_value != "—":
        signals.append({
            "kind": "power",
            "label": "ISOP",
            "value": isop_value,
            "detail": _isop_context(isop),
        })
    ab_hr_value = _format_espn_value(row.get("AB/HR"))
    if ab_hr_value != "—":
        signals.append({
            "kind": "power",
            "label": "AB/HR",
            "value": ab_hr_value,
            "detail": _format_hr_pace(row.get("AB/HR")),
        })
    bb_k_value = _format_espn_value(row.get("BB/K"))
    if bb_k_value != "—":
        signals.append({
            "kind": "discipline",
            "label": "BB/K",
            "value": bb_k_value,
            "detail": _bb_k_context(bb_k),
        })
    seca_value = _format_espn_value(row.get("SECA"))
    if seca_value != "—":
        signals.append({
            "kind": "production",
            "label": "SECA",
            "value": seca_value,
            "detail": _seca_context(seca),
        })
    go_fo_value = _format_espn_value(row.get("GO/FO"))
    if go_fo_value != "—":
        signals.append({
            "kind": "contact",
            "label": "GO/FO",
            "value": go_fo_value,
            "detail": _go_fo_context(go_fo),
        })

    return {
        "label": label,
        "theme": _ARCHETYPE_THEMES.get(label, "balanced"),
        "drivers": drivers,
        "signals": signals,
    }


def _hit_profile_pillar_tier(
    pillar_id: str,
    value: float,
) -> tuple[str, str]:
    if pillar_id == "war":
        if value >= 2.5:
            return "good", "Plus value"
        if value >= 1.0:
            return "average", "Solid contributor"
        if value >= 0:
            return "poor", "Below average"
        return "poor", "Replacement level"
    if pillar_id == "rc27":
        if value >= 5.5:
            return "good", "Strong production"
        if value >= 4.3:
            return "average", "League average"
        return "poor", "Below average"
    if pillar_id == "bb_k":
        if value >= 0.60:
            return "good", "Patient approach"
        if value >= 0.40:
            return "average", "League average"
        return "poor", "Aggressive approach"
    return "average", "League average"


def _ground_pct_from_ratio(ratio: float | None) -> float | None:
    if ratio is None or ratio < 0:
        return None
    return round(ratio / (1 + ratio) * 100, 1)


def _build_contact_tendency(
    *,
    ground_count: float,
    fly_count: float,
    ratio: float | None,
    ground_label: str,
    fly_label: str,
    ratio_label: str,
    caption: str,
) -> dict[str, Any] | None:
    ground_pct = _ground_pct_from_ratio(ratio)
    total = ground_count + fly_count
    if ground_pct is None and total > 0:
        ground_pct = round(ground_count / total * 100, 1)
    if ground_pct is None:
        return None
    fly_pct = round(100 - ground_pct, 1)
    return {
        "ground_pct": ground_pct,
        "fly_pct": fly_pct,
        "go_fo": round(ratio, 2) if ratio is not None else None,
        "ground_label": ground_label,
        "fly_label": fly_label,
        "ratio_label": ratio_label,
        "caption": caption,
    }


def _hit_profile_stat(
    label: str,
    value: Any,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    text = _format_espn_value(value)
    if text == "—":
        text = None
    return {
        "label": label,
        "value": text,
        "note": note,
    }


def _empty_hit_profile_panel(*, season_year: int) -> dict[str, Any]:
    return {
        "id": "hit_profile",
        "label": "Advanced Stats",
        "panel_kind": "hit_profile",
        "profile_type": "batter",
        "season_year": str(season_year),
        "archetype": None,
        "pillars": [],
        "contact_tendency": None,
        "groups": [],
    }


def _build_hit_profile_panel(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, Any]:
    row = _espn_advanced_batting_row(categories, season_year=season_year)
    if not row:
        return _empty_hit_profile_panel(season_year=season_year)

    war = _parse_number(row.get("WAR"))
    owar = _parse_number(row.get("OWAR"))
    rc27 = _parse_number(row.get("RC/27"))
    bb_k = _parse_number(row.get("BB/K"))
    isop = _parse_number(row.get("ISOP"))
    seca = _parse_number(row.get("SECA"))
    ab_hr = _parse_number(row.get("AB/HR"))
    go = _parse_number(row.get("GO")) or 0.0
    fo = _parse_number(row.get("FO")) or 0.0
    go_fo = _parse_number(row.get("GO/FO"))

    metrics = {
        "isop": isop,
        "ab_hr": ab_hr,
        "bb_k": bb_k,
        "seca": seca,
        "go_fo": go_fo,
    }
    archetype = _build_hit_archetype(metrics, row)

    pillars: list[dict[str, Any]] = []
    if war is not None:
        war_tier, war_tier_label = _hit_profile_pillar_tier("war", war)
        pillars.append({
            "id": "war",
            "label": "WAR",
            "value": _format_war(war),
            "note": f"oWAR {_format_war(owar)}" if owar is not None else None,
            "tier": war_tier,
            "tier_label": war_tier_label,
        })
    if rc27 is not None:
        rc27_tier, rc27_tier_label = _hit_profile_pillar_tier("rc27", rc27)
        pillars.append({
            "id": "rc27",
            "label": "RC/27",
            "value": f"{rc27:.1f}",
            "note": "Runs created per 27 outs",
            "tier": rc27_tier,
            "tier_label": rc27_tier_label,
        })
    if bb_k is not None:
        bb_k_tier, bb_k_tier_label = _hit_profile_pillar_tier("bb_k", bb_k)
        pillars.append({
            "id": "bb_k",
            "label": "BB/K",
            "value": f"{bb_k:.2f}",
            "note": "Walk-to-strikeout ratio",
            "tier": bb_k_tier,
            "tier_label": bb_k_tier_label,
        })

    contact_tendency = _build_contact_tendency(
        ground_count=go,
        fly_count=fo,
        ratio=go_fo,
        ground_label="Ground outs",
        fly_label="Fly outs",
        ratio_label="GO/FO",
        caption="Share of recorded ground outs vs. fly outs (line drives and other types excluded).",
    )

    power_stats = [
        _hit_profile_stat("ISOP", row.get("ISOP")),
        _hit_profile_stat(
            "AB/HR",
            row.get("AB/HR"),
            note=_format_hr_pace(row.get("AB/HR")),
        ),
    ]
    approach_stats = [
        _hit_profile_stat("BB/PA", row.get("BB/PA")),
        _hit_profile_stat("SECA", row.get("SECA")),
    ]
    production_stats = [
        _hit_profile_stat("RC", row.get("RC")),
        _hit_profile_stat("oWAR", row.get("OWAR")),
    ]

    groups = []
    if any(stat.get("value") for stat in power_stats):
        groups.append({"id": "power", "label": "Power", "stats": power_stats})
    if any(stat.get("value") for stat in approach_stats):
        groups.append({"id": "approach", "label": "Approach", "stats": approach_stats})
    if any(stat.get("value") for stat in production_stats):
        groups.append({"id": "production", "label": "Production", "stats": production_stats})

    if not pillars and not groups:
        return _empty_hit_profile_panel(season_year=season_year)

    return {
        "id": "hit_profile",
        "label": "Advanced Stats",
        "panel_kind": "hit_profile",
        "profile_type": "batter",
        "season_year": str(season_year),
        "archetype": archetype,
        "pillars": pillars,
        "contact_tendency": contact_tendency,
        "groups": groups,
    }


def _espn_pitching_profile_rows(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
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
    return pitching_row, expanded_row, opponent_row


_PITCH_ARCHETYPE_THEMES = {
    "Strikeout artist": "strikeout_artist",
    "Run suppressor": "run_suppressor",
    "Ground-ball pitcher": "ground_ball",
    "Fly-ball pitcher": "fly_ball",
    "Command arm": "command_arm",
    "Balanced arm": "balanced",
}


def _era_context(era: float | None) -> str | None:
    if era is None:
        return None
    if era <= 2.75:
        return "Elite run prevention"
    if era <= 3.75:
        return "League-average ERA"
    return "Elevated ERA"


def _whip_context(whip: float | None) -> str | None:
    if whip is None:
        return None
    if whip <= 1.05:
        return "Elite command"
    if whip <= 1.25:
        return "League-average WHIP"
    return "Walks and hits pile up"


def _k9_context(k9: float | None) -> str | None:
    if k9 is None:
        return None
    if k9 >= 10.0:
        return "Dominant strikeout rate"
    if k9 >= 7.5:
        return "League-average K/9"
    return "Limited swing-and-miss"


def _k_bb_context(k_bb: float | None) -> str | None:
    if k_bb is None:
        return None
    if k_bb >= 4.5:
        return "Elite strikeout-to-walk"
    if k_bb >= 3.0:
        return "Solid command"
    if k_bb >= 2.0:
        return "League-average K/BB"
    return "Control issues"


def _gf_context(gf: float | None) -> str | None:
    if gf is None:
        return None
    if gf >= 1.2:
        return "Ground-ball lean"
    if gf <= 0.8:
        return "Fly-ball lean"
    return "Balanced batted-ball mix"


def _oops_context(oops: float | None) -> str | None:
    if oops is None:
        return None
    if oops <= 0.650:
        return "Limits opponent damage"
    if oops <= 0.730:
        return "League-average contact"
    return "Hard contact allowed"


def _build_pitch_archetype(
    metrics: dict[str, float | None],
    pitching_row: dict[str, str],
    expanded_row: dict[str, str],
    opponent_row: dict[str, str],
) -> dict[str, Any]:
    k9 = metrics.get("k9")
    k_bb = metrics.get("k_bb")
    era = metrics.get("era")
    war = metrics.get("war")
    whip = metrics.get("whip")
    gf = metrics.get("gf")
    oops = _parse_number(opponent_row.get("OOPS"))

    if k9 is not None and k9 >= 10.0 and k_bb is not None and k_bb >= 4.0:
        label = "Strikeout artist"
        drivers = ["Swing-and-miss stuff drives the profile"]
    elif era is not None and era <= 3.25 and war is not None and war >= 2.0:
        label = "Run suppressor"
        drivers = ["Keeps runs off the board"]
    elif gf is not None and gf >= 1.15:
        label = "Ground-ball pitcher"
        drivers = ["Induces ground balls on contact"]
    elif gf is not None and gf <= 0.75:
        label = "Fly-ball pitcher"
        drivers = ["Fly-ball contact profile"]
    elif whip is not None and whip <= 1.10 and k_bb is not None and k_bb >= 3.5:
        label = "Command arm"
        drivers = ["Command and control stand out"]
    else:
        label = "Balanced arm"
        drivers = ["No single trait dominates the pitching profile"]

    signals: list[dict[str, Any]] = []
    war_value = _format_espn_value(pitching_row.get("WAR"))
    if war_value != "—":
        signals.append({
            "kind": "production",
            "label": "WAR",
            "value": war_value,
            "detail": _pitch_profile_pillar_tier("war", war)[1] if war is not None else None,
        })
    era_value = _format_espn_value(pitching_row.get("ERA"))
    if era_value != "—":
        signals.append({
            "kind": "prevention",
            "label": "ERA",
            "value": era_value,
            "detail": _era_context(era),
        })
    whip_value = _format_espn_value(pitching_row.get("WHIP"))
    if whip_value != "—":
        signals.append({
            "kind": "command",
            "label": "WHIP",
            "value": whip_value,
            "detail": _whip_context(whip),
        })
    k9_value = _format_espn_value(expanded_row.get("K/9"))
    if k9_value != "—":
        signals.append({
            "kind": "stuff",
            "label": "K/9",
            "value": k9_value,
            "detail": _k9_context(k9),
        })
    gf_value = _format_espn_value(expanded_row.get("G/F"))
    if gf_value != "—":
        signals.append({
            "kind": "contact",
            "label": "G/F",
            "value": gf_value,
            "detail": _gf_context(gf),
        })
    oops_value = _format_espn_value(opponent_row.get("OOPS"))
    if oops_value != "—":
        signals.append({
            "kind": "contact",
            "label": "OOPS",
            "value": oops_value,
            "detail": _oops_context(oops),
        })

    return {
        "label": label,
        "theme": _PITCH_ARCHETYPE_THEMES.get(label, "balanced"),
        "drivers": drivers,
        "signals": signals,
    }


def _pitch_profile_pillar_tier(
    pillar_id: str,
    value: float,
) -> tuple[str, str]:
    if pillar_id == "war":
        return _hit_profile_pillar_tier("war", value)
    if pillar_id == "era":
        if value <= 2.75:
            return "good", "Elite run prevention"
        if value <= 3.75:
            return "average", "League average"
        return "poor", "Below average"
    if pillar_id == "k9":
        if value >= 10.0:
            return "good", "Dominant strikeouts"
        if value >= 7.5:
            return "average", "League average"
        return "poor", "Below average"
    return "average", "League average"


def _empty_pitch_profile_panel(*, season_year: int) -> dict[str, Any]:
    return {
        "id": "pitch_profile",
        "label": "Advanced Stats",
        "panel_kind": "hit_profile",
        "profile_type": "pitcher",
        "season_year": str(season_year),
        "archetype": None,
        "pillars": [],
        "contact_tendency": None,
        "groups": [],
    }


def _build_pitch_profile_panel(
    categories: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, Any]:
    pitching_row, expanded_row, opponent_row = _espn_pitching_profile_rows(
        categories,
        season_year=season_year,
    )
    if not pitching_row and not expanded_row:
        return _empty_pitch_profile_panel(season_year=season_year)

    war = _parse_number(pitching_row.get("WAR"))
    era = _parse_number(pitching_row.get("ERA"))
    whip = _parse_number(pitching_row.get("WHIP"))
    k9 = _parse_number(expanded_row.get("K/9"))
    k_bb = _parse_number(pitching_row.get("K/BB"))
    gb = _parse_number(expanded_row.get("GB")) or 0.0
    fb = _parse_number(expanded_row.get("FB")) or 0.0
    gf = _parse_number(expanded_row.get("G/F"))

    metrics = {
        "k9": k9,
        "k_bb": k_bb,
        "era": era,
        "war": war,
        "whip": whip,
        "gf": gf,
    }
    archetype = _build_pitch_archetype(
        metrics,
        pitching_row,
        expanded_row,
        opponent_row,
    )

    pillars: list[dict[str, Any]] = []
    if war is not None:
        war_tier, war_tier_label = _pitch_profile_pillar_tier("war", war)
        pillars.append({
            "id": "war",
            "label": "WAR",
            "value": _format_war(war),
            "note": f"ERA {_format_espn_value(pitching_row.get('ERA'))}" if era is not None else None,
            "tier": war_tier,
            "tier_label": war_tier_label,
        })
    if era is not None:
        era_tier, era_tier_label = _pitch_profile_pillar_tier("era", era)
        pillars.append({
            "id": "era",
            "label": "ERA",
            "value": _format_espn_value(pitching_row.get("ERA")),
            "note": f"WHIP {_format_espn_value(pitching_row.get('WHIP'))}" if whip is not None else None,
            "tier": era_tier,
            "tier_label": era_tier_label,
        })
    if k9 is not None:
        k9_tier, k9_tier_label = _pitch_profile_pillar_tier("k9", k9)
        pillars.append({
            "id": "k9",
            "label": "K/9",
            "value": f"{k9:.1f}",
            "note": (
                f"K/BB {_format_espn_value(pitching_row.get('K/BB'))}"
                if pitching_row.get("K/BB") is not None
                else None
            ),
            "tier": k9_tier,
            "tier_label": k9_tier_label,
        })

    contact_tendency = _build_contact_tendency(
        ground_count=gb,
        fly_count=fb,
        ratio=gf,
        ground_label="Ground balls",
        fly_label="Fly balls",
        ratio_label="G/F",
        caption="Share of ground balls vs. fly balls allowed on contact.",
    )

    prevention_stats = [
        _hit_profile_stat("ERA", pitching_row.get("ERA")),
        _hit_profile_stat("WHIP", pitching_row.get("WHIP")),
    ]
    command_stats = [
        _hit_profile_stat("K/9", expanded_row.get("K/9")),
        _hit_profile_stat("K/BB", pitching_row.get("K/BB")),
    ]
    contact_stats = [
        _hit_profile_stat("OOPS", opponent_row.get("OOPS")),
        _hit_profile_stat("OBA", opponent_row.get("OBA")),
    ]

    groups = []
    if any(stat.get("value") for stat in prevention_stats):
        groups.append({"id": "prevention", "label": "Run prevention", "stats": prevention_stats})
    if any(stat.get("value") for stat in command_stats):
        groups.append({"id": "command", "label": "Command", "stats": command_stats})
    if any(stat.get("value") for stat in contact_stats):
        groups.append({"id": "contact", "label": "Contact allowed", "stats": contact_stats})

    if not pillars and not groups:
        return _empty_pitch_profile_panel(season_year=season_year)

    return {
        "id": "pitch_profile",
        "label": "Advanced Stats",
        "panel_kind": "hit_profile",
        "profile_type": "pitcher",
        "season_year": str(season_year),
        "archetype": archetype,
        "pillars": pillars,
        "contact_tendency": contact_tendency,
        "groups": groups,
    }


def _spray_empty_panel(*, season_year: int) -> dict[str, Any]:
    return {
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


def _spray_rate_percent(value: Any) -> float | None:
    number = _parse_number(value)
    if number is None:
        return None
    if number <= 1.0:
        return round(number * 100, 1)
    return round(number, 1)


def _get_batter_exitvelo_table(season_year: int) -> pd.DataFrame | None:
    cached = _exitvelo_batter_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        table = statcast_batter_exitvelo_barrels(season_year, minBBE=0)
        result = table if table is not None and not table.empty else None
    except Exception:
        result = None
    _exitvelo_batter_table_cache[season_year] = (now, result)
    return result


def _get_batter_expected_table(season_year: int) -> pd.DataFrame | None:
    cached = _expected_batter_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        table = statcast_batter_expected_stats(season_year, minPA=0)
        result = table if table is not None and not table.empty else None
    except Exception:
        result = None
    _expected_batter_table_cache[season_year] = (now, result)
    return result


def _get_batted_ball_table(season_year: int) -> pd.DataFrame | None:
    cached = _batted_ball_table_cache.get(season_year)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            _SAVANT_BATTED_BALL_URL.format(year=season_year),
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        table = pd.read_csv(pd.io.common.StringIO(response.text))
        result = table if not table.empty else None
    except Exception:
        result = None
    _batted_ball_table_cache[season_year] = (now, result)
    return result


def _fetch_spray_chart_panel(
    *,
    mlbam_id: int | None,
    season_year: int,
) -> dict[str, Any]:
    empty = _spray_empty_panel(season_year=season_year)
    if not mlbam_id:
        return empty

    try:
        exitvelo_table = _get_batter_exitvelo_table(season_year)
        expected_table = _get_batter_expected_table(season_year)
        batted_ball_table = _get_batted_ball_table(season_year)

        ev_row = (
            exitvelo_table[exitvelo_table["player_id"] == mlbam_id]
            if exitvelo_table is not None
            else pd.DataFrame()
        )
        exp_row = (
            expected_table[expected_table["player_id"] == mlbam_id]
            if expected_table is not None
            else pd.DataFrame()
        )
        bb_row = (
            batted_ball_table[batted_ball_table["id"] == mlbam_id]
            if batted_ball_table is not None
            else pd.DataFrame()
        )

        if ev_row.empty and bb_row.empty:
            return empty

        ev_record = ev_row.iloc[0] if not ev_row.empty else None
        bb_record = bb_row.iloc[0] if not bb_row.empty else None
        exp_record = exp_row.iloc[0] if not exp_row.empty else None

        total = 0
        if bb_record is not None:
            total = int(_parse_number(_table_row_value(bb_record, "bbe")) or 0)
        if not total and ev_record is not None:
            total = int(_parse_number(_table_row_value(ev_record, "attempts")) or 0)
        if not total:
            return empty

        avg_xwoba = _parse_number(_table_row_value(exp_record, "est_woba"))
        if avg_xwoba is None:
            avg_xwoba = _parse_number(_table_row_value(exp_record, "woba"))

        summary = {
            "total": total,
            "avg_ev": _parse_number(_table_row_value(ev_record, "avg_hit_speed")),
            "avg_launch_angle": _parse_number(_table_row_value(ev_record, "avg_hit_angle")),
            "avg_distance": _parse_number(_table_row_value(ev_record, "avg_distance")),
            "avg_xwoba": avg_xwoba,
            "hard_hit_pct": _parse_number(_table_row_value(ev_record, "ev95percent")),
            "barrel_pct": _parse_number(_table_row_value(ev_record, "brl_percent")),
        }

        gb_ev = _parse_number(_table_row_value(ev_record, "gb"))
        fbld_ev = _parse_number(_table_row_value(ev_record, "fbld"))
        types: list[dict[str, Any]] = []
        if bb_record is not None:
            for bb_type, rate_column in _SPRAY_BB_TYPE_RATE_COLUMNS:
                usage = _spray_rate_percent(_table_row_value(bb_record, rate_column))
                if not usage:
                    continue
                count = round(total * usage / 100) if total else 0
                if not count:
                    continue
                type_entry: dict[str, Any] = {
                    "label": _SPRAY_BB_TYPE_LABELS[bb_type],
                    "bb_type": bb_type,
                    "usage": usage,
                    "count": count,
                }
                if bb_type == "ground_ball" and gb_ev is not None:
                    type_entry["ev"] = gb_ev
                elif bb_type in {"line_drive", "fly_ball"} and fbld_ev is not None:
                    type_entry["ev"] = fbld_ev
                types.append(type_entry)

        metrics: list[dict[str, Any]] = []
        if any("ev" in item for item in types):
            metrics = [
                {"id": "ev", "label": "Exit Velo", "unit": "mph", "max": 115.0},
            ]

        return {
            "id": "spray_chart",
            "label": "Batting Metrics",
            "panel_kind": "spray_chart",
            "season_year": str(season_year),
            "summary": summary,
            "legend": [],
            "types": types,
            "metrics": metrics,
            "points": [],
        }
    except Exception:
        return empty


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


def _empty_player_stats_panel_league_only(*, pitching: bool, season_year: int) -> dict[str, Any]:
    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": "league_average",
        "season_year": str(season_year),
        "views": [
            {
                "id": "league_average",
                "label": "League Average",
                "metrics": [],
            },
            {
                "id": "season_stats",
                "label": "Season Stats",
                "nested_panel": {
                    "default_view": "standard",
                    "views": [
                        {
                            "id": "standard",
                            "label": "Standard",
                            "stats_table": _empty_espn_timeline_standard_table(
                                pitching=pitching,
                                season_year=season_year,
                            ),
                        },
                        {
                            "id": "advanced",
                            "label": "Advanced Stats",
                            "coming_soon": True,
                        },
                    ],
                },
            },
        ],
    }


def _empty_player_stats_panel(*, pitching: bool, season_year: int) -> dict[str, Any]:
    column_labels = [label for _, label in (_PITCHING_COLUMNS if pitching else _BATTING_COLUMNS)]
    return {
        "id": "player_stats",
        "label": "Player Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": "league_average",
        "season_year": str(season_year),
        "views": [
            {
                "id": "league_average",
                "label": "League Average",
                "metrics": [],
            },
            {
                "id": "season_stats",
                "label": "Season Stats",
                "stats_table": _empty_stats_table(column_labels, season_year),
            },
        ],
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
    cache_key = f"{player_id}:{year}:{kind}:core:v4"
    cached = _player_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    categories = _fetch_espn_stat_categories(player_id)
    player_stats_panel = _build_player_stats_panel(
        categories,
        pitching=pitching,
        season_year=year,
        player_name=player_name,
        position=position,
    ) or _empty_player_stats_panel(pitching=pitching, season_year=year)
    panels = [player_stats_panel]
    _player_core_panels_cache[cache_key] = (now, panels)
    return panels


def fetch_player_league_bundle(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any]:
    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    if not player_id:
        return {
            "stat_panel": _empty_player_stats_panel_league_only(
                pitching=pitching,
                season_year=year,
            ),
            "profile_panel": _empty_pitch_profile_panel(season_year=year)
            if pitching
            else _empty_hit_profile_panel(season_year=year),
        }

    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:league:v8"
    cached = _player_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    categories = _fetch_espn_stat_categories(player_id)
    stat_panel = _build_player_stats_panel_league_only(
        categories,
        pitching=pitching,
        season_year=year,
    ) or _empty_player_stats_panel_league_only(pitching=pitching, season_year=year)
    profile_panel = (
        _build_pitch_profile_panel(categories, season_year=year)
        if pitching
        else _build_hit_profile_panel(categories, season_year=year)
    )
    result = {
        "stat_panel": stat_panel,
        "profile_panel": profile_panel,
    }
    _player_core_panels_cache[cache_key] = (now, result)
    return result


def fetch_player_league_stat_panel(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any]:
    return fetch_player_league_bundle(
        player_id,
        player_name=player_name,
        position=position,
        season_year=season_year,
    )["stat_panel"]


def _parse_savant_html_table(table: Any) -> dict[str, Any] | None:
    if table is None or not hasattr(table, "find"):
        return None

    header_row = table.find("thead")
    if header_row is None:
        return None
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
    while headers and not headers[0]:
        headers = headers[1:]

    body = table.find("tbody")
    if body is None or not headers:
        return None

    rows: list[dict[str, str]] = []
    for tr in body.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if not any(cells):
            continue
        while cells and cells[0] in {"", "*"}:
            cells = cells[1:]
        if not cells:
            continue
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        rows.append(dict(zip(headers, cells[: len(headers)])))

    if not rows:
        return None
    return {"columns": headers, "rows": rows}


def _find_savant_table_by_anchor(soup: Any, anchor_name: str) -> Any | None:
    link = soup.find("a", attrs={"name": anchor_name})
    if link is None:
        link = soup.find("a", href=f"#{anchor_name}")
    if link is None:
        return None
    heading = link.find_parent("h2")
    if heading is None:
        return None
    return heading.find_next("table")


def _should_drop_savant_summary_row(row: dict[str, str]) -> bool:
    season = str(row.get("Season") or row.get("Year") or "").strip()
    return season.upper() == "MLB"


def _normalize_savant_season_label(season: str) -> tuple[str, str]:
    text = str(season or "").strip()
    if not text:
        return text, "season"
    lowered = text.lower()
    if lowered in {"player", "career"} or lowered.endswith(" seasons"):
        return "Career", "career"
    return text, "season"


def _savant_table_to_stats_table(
    parsed: dict[str, Any] | None,
    *,
    season_year: int,
) -> dict[str, Any]:
    columns = list((parsed or {}).get("columns") or [])
    raw_rows = list((parsed or {}).get("rows") or [])
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if _should_drop_savant_summary_row(row):
            continue
        season = row.get("Season") or row.get("Year") or ""
        label, row_kind = _normalize_savant_season_label(str(season))
        cells = {
            column: (row.get(column) or "—")
            for column in columns
        }
        if row_kind == "career":
            cells["Season"] = "Career"
        rows.append({
            "label": label,
            "row_kind": row_kind,
            "cells": cells,
        })
    return {
        "layout": "savant_career",
        "columns": columns,
        "rows": rows,
        "season_year": str(season_year),
    }


def _fetch_savant_career_tables(
    mlbam_id: int | None,
    *,
    pitching: bool,
    season_year: int,
) -> dict[str, Any] | None:
    if not mlbam_id:
        return None

    cache_key = f"{mlbam_id}:{'pitch' if pitching else 'bat'}:career:v2"
    cached = _savant_career_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    kind = "pitching" if pitching else "hitting"
    url = _SAVANT_PLAYER_PAGE_URL.format(player_id=mlbam_id, kind=kind)
    try:
        from bs4 import BeautifulSoup

        response = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        _savant_career_cache[cache_key] = (now, None)
        return None

    if pitching:
        standard_container = soup.find("div", id="pitchingStandard")
        standard_parsed = _parse_savant_html_table(
            standard_container.find("table") if standard_container else _find_savant_table_by_anchor(
                soup,
                "standard-mlb-pitching-stats",
            ),
        )
        advanced_container = soup.find("div", id="statcast_stats_pitching")
        advanced_parsed = _parse_savant_html_table(
            advanced_container.find("table") if advanced_container else None,
        )
    else:
        standard_container = soup.find("div", id="hittingStandard")
        standard_parsed = _parse_savant_html_table(
            standard_container.find("table") if standard_container else None,
        )
        advanced_parsed = _parse_savant_html_table(
            _find_savant_table_by_anchor(soup, "advanced-mlb-batting-stats"),
        )

    if not standard_parsed and not advanced_parsed:
        _savant_career_cache[cache_key] = (now, None)
        return None

    result = {
        "standard": _savant_table_to_stats_table(standard_parsed, season_year=season_year),
        "advanced": _savant_table_to_stats_table(advanced_parsed, season_year=season_year),
    }
    _savant_career_cache[cache_key] = (now, result)
    return result


def _normalize_innings_pool_value(value: float) -> float:
    whole = int(value)
    partial = round((value - whole) * 10)
    if partial > 2:
        partial = 2
    return float(whole) + partial / 3.0


def _league_pool_values_for_timeline(
    values: list[float],
    *,
    column: str,
) -> list[float]:
    if column == "IP":
        return [_normalize_innings_pool_value(value) for value in values]
    return list(values)


def _season_years_from_savant_table(table: dict[str, Any]) -> list[int]:
    years: set[int] = set()
    for row in table.get("rows") or []:
        season = (row.get("cells") or {}).get("Season") or row.get("label")
        if season in (None, "", "—"):
            continue
        try:
            years.add(int(str(season).strip()))
        except ValueError:
            continue
    return sorted(years)


def _build_savant_timeline_league_bounds(
    seasons: list[int],
    columns: list[str],
    *,
    pitching: bool,
) -> dict[str, dict[str, dict[str, float]]]:
    from league_player_averages import get_league_player_stats_by_category

    key_map = _SAVANT_PITCHING_LEAGUE_KEYS if pitching else _SAVANT_BATTING_LEAGUE_KEYS
    bounds: dict[str, dict[str, dict[str, float]]] = {}
    for season in seasons:
        league_stats = get_league_player_stats_by_category(season)
        category = league_stats.get("pitching" if pitching else "batting") or {}
        year_bounds: dict[str, dict[str, float]] = {}
        for column in columns:
            pool_key = key_map.get(column)
            if not pool_key:
                continue
            raw_values = category.get(pool_key) or []
            values = _league_pool_values_for_timeline(
                [float(value) for value in raw_values],
                column=column,
            )
            if not values:
                continue
            year_bounds[column] = {
                "min": float(min(values)),
                "max": float(max(values)),
            }
        if year_bounds:
            bounds[str(season)] = year_bounds
    return bounds


def _enrich_savant_advanced_teams(
    standard: dict[str, Any],
    advanced: dict[str, Any],
) -> dict[str, Any]:
    team_by_season: dict[str, str] = {}
    for row in standard.get("rows") or []:
        cells = row.get("cells") or {}
        season = cells.get("Season") or row.get("label")
        team = cells.get("Tm")
        if season and team and team not in {"", "—"}:
            team_by_season[str(season)] = str(team)

    for row in advanced.get("rows") or []:
        cells = row.setdefault("cells", {})
        season = cells.get("Season") or row.get("label")
        if season and str(season) in team_by_season:
            cells["Tm"] = team_by_season[str(season)]

    return advanced


def _attach_savant_timeline_league_bounds(
    table: dict[str, Any],
    *,
    pitching: bool,
) -> dict[str, Any]:
    columns = [
        column for column in (table.get("columns") or [])
        if column not in {"Season", "Tm", "LG"}
    ]
    seasons = _season_years_from_savant_table(table)
    if not columns or not seasons:
        return table
    table["league_bounds"] = _build_savant_timeline_league_bounds(
        seasons,
        columns,
        pitching=pitching,
    )
    return table


def fetch_player_season_stats_view(
    player_id: str,
    *,
    player_name: str,
    position: str | None,
    season_year: str | int | None = None,
) -> dict[str, Any]:
    year = _resolve_panel_year(season_year)
    pitching = is_pitcher_position(position)
    kind = "pitching" if pitching else "batting"
    cache_key = f"{player_id}:{year}:{kind}:season:v6"
    cached = _player_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    categories = _fetch_espn_stat_categories(player_id) if player_id else {}
    view = _build_season_stats_nested_view(
        categories,
        pitching=pitching,
        season_year=year,
    )
    _player_core_panels_cache[cache_key] = (now, view)
    return view


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
    cache_key = f"{player_id}:{year}:{kind}:visual:v2"
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
