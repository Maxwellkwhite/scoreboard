"""Team season stats and stat panels via ESPN APIs."""

from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

import requests

ESPN_TEAM_STATISTICS_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_id}/statistics"
)
ESPN_TEAM_ROSTER_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_id}/roster"
)
ESPN_TEAM_INJURIES_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries?team={team_id}"
)
ESPN_TEAM_SCHEDULE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_id}/schedule"
)
ESPN_ATHLETE_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}"
)
ESPN_ATHLETE_STATS_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}/stats"
)

_CACHE_TTL_SECONDS = 300
_team_panels_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_team_core_panels_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_team_roster_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_team_leaders_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_matchup_leaders_panel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_team_roster_data_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_team_summary_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_athlete_season_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

_TEAM_SUMMARY_BATTING = (
    ("avg", "AVG"),
    ("runs", "R"),
    ("homeRuns", "HR"),
    ("RBIs", "RBI"),
    ("onBasePct", "OBP"),
    ("slugAvg", "SLG"),
    ("OPS", "OPS"),
)
_TEAM_SUMMARY_PITCHING = (
    ("ERA", "ERA"),
    ("WHIP", "WHIP"),
    ("strikeouts", "SO"),
    ("walks", "BB"),
    ("saves", "SV"),
    ("opponentAvg", "OPP AVG"),
)

_BATTING_LEADER_SPECS = (
    ("WAR", "WAR", True),
    ("homeRuns", "HR", True),
    ("RBIs", "RBI", True),
    ("avg", "AVG", True),
    ("OPS", "OPS", True),
    ("stolenBases", "SB", True),
)
_BATTING_ADVANCED_LEADER_SPECS = (
    ("RC", "RC", True),
    ("RC/27", "RC/27", True),
    ("ISOP", "ISO", True),
)
_PITCHING_LEADER_SPECS = (
    ("WAR", "WAR", True),
    ("ERA", "ERA", False),
    ("strikeouts", "SO", True),
    ("wins", "W", True),
    ("saves", "SV", True),
    ("WHIP", "WHIP", False),
)
_PITCHING_ADVANCED_LEADER_SPECS = (
    ("K/9", "K/9", True),
    ("QS", "QS", True),
    ("OOPS", "OPP OPS", False),
)
_FIELDING_LEADER_SPECS = (
    ("fieldingPct", "FLD%", True),
    ("putouts", "PO", True),
    ("assists", "A", True),
    ("errors", "E", False),
    ("doublePlays", "DP", True),
)

_PITCHER_POSITIONS = frozenset({"P", "SP", "RP", "CP", "CL", "LR", "MR", "SU"})
_LEADER_TOP_N = 5
_LEADER_FETCH_WORKERS = 20
_PITCHING_RATE_STATS_REQUIRING_IP = frozenset({"ERA", "WHIP", "OOPS"})
_MIN_PITCHING_LEADER_IP = 5.0

_BATTING_DETAIL_SPECS = (
    ("avg", "AVG"),
    ("onBasePct", "OBP"),
    ("slugAvg", "SLG"),
    ("OPS", "OPS"),
    ("runs", "Runs"),
    ("hits", "Hits"),
    ("doubles", "2B"),
    ("triples", "3B"),
    ("homeRuns", "HR"),
    ("RBIs", "RBI"),
    ("walks", "BB"),
    ("strikeouts", "SO"),
    ("stolenBases", "SB"),
    ("atBats", "AB"),
    ("plateAppearances", "PA"),
)
_PITCHING_DETAIL_SPECS = (
    ("ERA", "ERA"),
    ("WHIP", "WHIP"),
    ("innings", "IP"),
    ("wins", "W"),
    ("losses", "L"),
    ("saves", "SV"),
    ("strikeouts", "SO"),
    ("walks", "BB"),
    ("hits", "H"),
    ("earnedRuns", "ER"),
    ("homeRuns", "HR"),
    ("strikeoutsPerNineInnings", "K/9"),
    ("opponentAvg", "OPP AVG"),
    ("qualityStarts", "QS"),
)
_FIELDING_DETAIL_SPECS = (
    ("fieldingPct", "FLD%"),
    ("putouts", "PO"),
    ("assists", "A"),
    ("errors", "E"),
    ("doublePlays", "DP"),
    ("totalChances", "TC"),
    ("fullInningsPlayed", "INN"),
)
_LOWER_IS_BETTER_STATS = frozenset({
    "ERA", "WHIP", "earnedRuns", "losses", "walks", "hits", "homeRuns",
    "opponentAvg", "errors", "strikeouts",
})
# Pitching strikeouts and walks: for team pitching, K is higher better, BB is lower better
_PITCHING_LOWER_IS_BETTER = frozenset({
    "ERA", "WHIP", "earnedRuns", "losses", "walks", "hits", "homeRuns", "opponentAvg",
})
_BATTING_LOWER_IS_BETTER = frozenset({"strikeouts"})
_FIELDING_LOWER_IS_BETTER = frozenset({"errors"})
_RATE_MEDIAN_STATS = frozenset({
    "avg", "onBasePct", "slugAvg", "OPS", "WHIP", "opponentAvg",
    "fieldingPct", "ERA", "strikeoutsPerNineInnings", "winPct",
    "innings", "fullInningsPlayed",
})

ESPN_TEAMS_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams"
)

_team_statistics_cache: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _format_rate(value: Any, decimals: int = 3) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    if abs(number) < 1 and decimals == 3:
        return f"{number:.{decimals}f}".lstrip("0")
    return f"{number:.{decimals}f}"


def _format_stat_value(stat_name: str, value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "—"
    if stat_name in {"avg", "onBasePct", "slugAvg", "OPS", "WHIP", "opponentAvg", "fieldingPct", "wOBA", "ISOP", "OOPS"}:
        return _format_rate(number, 3)
    if stat_name in {"ERA", "FIP", "xFIP"}:
        return f"{number:.2f}"
    if stat_name in {"WAR", "RC/27"}:
        rounded = round(number, 1)
        return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"
    if stat_name == "OPS+":
        return str(round(number))
    if stat_name in {"strikeoutsPerNineInnings", "winPct", "K/9"}:
        return f"{number:.2f}"
    if stat_name in {"innings", "fullInningsPlayed"}:
        return f"{number:.1f}"
    if float(number).is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _category_stats_map(categories: list[dict[str, Any]], category_name: str) -> dict[str, Any]:
    for category in categories:
        if category.get("name") != category_name:
            continue
        return {
            stat.get("name"): stat.get("value")
            for stat in category.get("stats") or []
            if stat.get("name")
        }
    return {}


def _fetch_team_statistics(team_id: str) -> dict[str, dict[str, Any]]:
    cached = _team_statistics_cache.get(team_id)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    response = requests.get(
        ESPN_TEAM_STATISTICS_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    categories = ((payload.get("results") or {}).get("stats") or {}).get("categories") or []
    result = {
        "batting": _category_stats_map(categories, "batting"),
        "pitching": _category_stats_map(categories, "pitching"),
        "fielding": _category_stats_map(categories, "fielding"),
    }
    _team_statistics_cache[team_id] = (now, result)
    return result


def _get_mlb_team_ids() -> list[str]:
    response = requests.get(ESPN_TEAMS_URL, timeout=15)
    response.raise_for_status()
    payload = response.json()
    team_ids: list[str] = []
    for item in (
        (payload.get("sports") or [{}])[0]
        .get("leagues", [{}])[0]
        .get("teams", [])
    ):
        team = item.get("team") or {}
        team_id = team.get("id")
        if team_id is not None:
            team_ids.append(str(team_id))
    return team_ids


def _get_league_stats_by_category(season_year: int) -> dict[str, dict[str, list[float]]]:
    from league_team_averages import get_league_team_stats_by_category

    return get_league_team_stats_by_category(season_year)


def _stat_lower_is_better(category: str, stat_name: str) -> bool:
    if category == "pitching":
        return stat_name in _PITCHING_LOWER_IS_BETTER
    if category == "batting":
        return stat_name in _BATTING_LOWER_IS_BETTER
    if category == "fielding":
        return stat_name in _FIELDING_LOWER_IS_BETTER
    return stat_name in _LOWER_IS_BETTER_STATS


def _scale_stat_position(value: float, min_value: float, max_value: float) -> float:
    span = max_value - min_value
    if span <= 0:
        return 50.0
    return max(0.0, min(100.0, (value - min_value) / span * 100.0))


def _median(values: list[float], *, stat_name: str) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    if stat_name in _RATE_MEDIAN_STATS:
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    return ordered[mid - 1]


def _build_stat_metrics(
    stats: dict[str, Any],
    specs: tuple[tuple[str, str], ...],
    *,
    category: str,
    league_stats: dict[str, list[float]],
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for stat_name, label in specs:
        if stat_name not in stats:
            continue
        team_value = _parse_number(stats.get(stat_name))
        if team_value is None:
            continue

        league_values = league_stats.get(stat_name) or []
        league_median = _median(league_values, stat_name=stat_name)
        if league_values:
            min_value = min(league_values)
            max_value = max(league_values)
            bar_pct = _scale_stat_position(team_value, min_value, max_value)
            league_pct = (
                _scale_stat_position(league_median, min_value, max_value)
                if league_median is not None
                else None
            )
        else:
            bar_pct = 50.0
            league_pct = None

        lower_is_better = _stat_lower_is_better(category, stat_name)
        better = None
        above_median = None
        if league_median is not None:
            if team_value > league_median:
                above_median = True
            elif team_value < league_median:
                above_median = False
            if lower_is_better:
                better = team_value < league_median
            else:
                better = team_value > league_median
            if abs(team_value - league_median) < 1e-9:
                better = True
                above_median = None

        metrics.append({
            "id": stat_name,
            "label": label,
            "display": _format_stat_value(stat_name, team_value),
            "league_display": (
                _format_stat_value(stat_name, league_median)
                if league_median is not None
                else None
            ),
            "bar_pct": round(bar_pct, 1),
            "league_pct": round(league_pct, 1) if league_pct is not None else None,
            "better": better,
            "above_median": above_median,
        })
    return metrics


def _build_summary_table(
    stats_by_category: dict[str, dict[str, Any]],
    *,
    season_year: int,
) -> dict[str, Any] | None:
    batting = stats_by_category.get("batting") or {}
    pitching = stats_by_category.get("pitching") or {}
    columns: list[dict[str, str]] = []

    for stat_name, label in _TEAM_SUMMARY_BATTING:
        if stat_name in batting:
            columns.append({
                "label": label,
                "season": _format_stat_value(stat_name, batting.get(stat_name)),
                "career": "—",
            })
    for stat_name, label in _TEAM_SUMMARY_PITCHING:
        if stat_name in pitching:
            columns.append({
                "label": label,
                "season": _format_stat_value(stat_name, pitching.get(stat_name)),
                "career": "—",
            })

    if not columns:
        return None
    return {
        "season_year": str(season_year),
        "columns": columns,
    }


def _build_stat_rows(
    stats: dict[str, Any],
    specs: tuple[tuple[str, str], ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for stat_name, label in specs:
        if stat_name not in stats:
            continue
        rows.append({
            "label": label,
            "value": _format_stat_value(stat_name, stats.get(stat_name)),
        })
    return rows


_PITCHER_RP_ABBRS = frozenset({"RP", "CP", "CL", "P", "SU", "LR", "MR"})

_ROSTER_FILTERS = (
    ("all", "All"),
    ("sp", "SP"),
    ("rp", "RP"),
    ("c", "C"),
    ("if", "Infield"),
    ("of", "Outfield"),
)
_FORTY_MAN_EXCLUDE_STATUSES = frozenset({"minors", "minors-special", "non-roster-invite"})
_IL_STATUS_LABELS = {
    "injured7": "10-Day IL",
    "15-day-il": "15-Day IL",
    "10-day-il": "10-Day IL",
    "injured15": "15-Day IL",
    "injured60": "60-Day IL",
    "60-day-il": "60-Day IL",
}


def _player_id_from_athlete(athlete: dict[str, Any]) -> str:
    if athlete.get("id"):
        return str(athlete["id"])
    for link in athlete.get("links") or []:
        href = str(link.get("href") or "")
        match = re.search(r"/id/(\d+)", href)
        if match:
            return match.group(1)
    return ""


def _roster_filter_key(pos_abbr: str) -> str:
    pos = (pos_abbr or "").upper()
    if pos == "SP":
        return "sp"
    if pos in _PITCHER_RP_ABBRS:
        return "rp"
    if pos == "C":
        return "c"
    if pos in {"1B", "2B", "3B", "SS", "IF"}:
        return "if"
    if pos in {"LF", "CF", "RF", "OF", "DH"}:
        return "of"
    return "other"


def _roster_status_variant(status_type: str, injuries: list[dict[str, Any]]) -> str:
    status = (status_type or "active").lower()
    if status in _IL_STATUS_LABELS or "il" in status or status.startswith("injured"):
        return "out" if "60" in status else "injured"
    if injuries:
        injury_status = str(injuries[0].get("status") or "").lower()
        if any(token in injury_status for token in ("out", "surgery", "60", "il", "long")):
            return "out"
        return "injured"
    if status == "active":
        return "active"
    if status in {"inactive", "minors", "rehab", "suspended"}:
        return "inactive"
    return "unknown"


def _roster_il_label(status_type: str, status_label: str) -> str:
    status_key = (status_type or "").lower()
    if status_key in _IL_STATUS_LABELS:
        return _IL_STATUS_LABELS[status_key]
    label = (status_label or "").strip()
    if label and label not in {"Active", "Minors"}:
        return label
    return ""


def _roster_meta_line(
    athlete: dict[str, Any],
    *,
    injury_note: str,
    status_label: str,
    status_type: str = "",
) -> str:
    il_label = _roster_il_label(status_type, status_label)
    if il_label:
        return il_label
    if injury_note:
        return injury_note
    debut_year = athlete.get("debutYear")
    current_year = date.today().year
    if debut_year:
        try:
            if int(debut_year) == current_year:
                return f"MLB debut {debut_year}"
        except (TypeError, ValueError):
            pass
    experience = athlete.get("experience") or {}
    years = experience.get("years")
    if years == 0:
        return "Rookie"
    if status_label and status_label not in {"Active"}:
        return status_label
    return ""


def _parse_roster_player(
    athlete: dict[str, Any],
    *,
    injury_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    position = athlete.get("position") or {}
    pos_abbr = position.get("abbreviation") or ""
    headshot = athlete.get("headshot") or {}
    headshot_href = headshot.get("href") if isinstance(headshot, dict) else headshot
    status = athlete.get("status") or {}
    status_type = str(status.get("type") or "active")
    status_label = str(status.get("name") or status.get("abbreviation") or "")
    injuries = athlete.get("injuries") or []
    player_id = _player_id_from_athlete(athlete)
    injury_note = ""
    if injury_lookup and player_id in injury_lookup:
        injury_info = injury_lookup[player_id]
        status_label = injury_info.get("status") or status_label
        injury_note = injury_info.get("short_comment") or injury_info.get("long_comment") or ""
    elif injuries:
        injury = injuries[0]
        injury_note = (
            injury.get("shortComment")
            or injury.get("longComment")
            or injury.get("status")
            or ""
        )

    return {
        "id": player_id,
        "name": athlete.get("displayName") or athlete.get("fullName") or "",
        "jersey": athlete.get("jersey"),
        "position": pos_abbr,
        "position_name": position.get("name") or "",
        "headshot": headshot_href,
        "filter": _roster_filter_key(pos_abbr),
        "status_variant": _roster_status_variant(status_type, injuries),
        "meta": _roster_meta_line(
            athlete,
            injury_note=str(injury_note),
            status_label=status_label,
            status_type=status_type,
        ),
    }


def _roster_sort_key(player: dict[str, Any]) -> tuple[int, str]:
    variant = player.get("status_variant") or "active"
    if variant == "active":
        order = 0
    elif variant == "injured":
        order = 1
    else:
        order = 2
    return (order, str(player.get("name") or "").lower())


def _classify_roster_player(player: dict[str, Any]) -> str:
    pos = (player.get("position") or "").upper()
    if pos == "SP":
        return "rotation"
    if pos in _PITCHER_RP_ABBRS:
        return "bullpen"
    if pos == "C":
        return "catchers"
    if pos in {"1B", "2B", "3B", "SS", "IF"}:
        return "infield"
    if pos in {"LF", "CF", "RF", "OF", "DH"}:
        return "outfield"
    return "outfield"


def _fetch_team_injury_lookup(team_id: str) -> dict[str, dict[str, str]]:
    try:
        response = requests.get(
            ESPN_TEAM_INJURIES_URL.format(team_id=team_id),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return {}

    lookup: dict[str, dict[str, str]] = {}
    for injury in payload.get("injuries") or []:
        athlete = injury.get("athlete") or {}
        player_id = _player_id_from_athlete(athlete)
        if not player_id:
            continue
        lookup[player_id] = {
            "status": str(injury.get("status") or ""),
            "short_comment": str(injury.get("shortComment") or ""),
            "long_comment": str(injury.get("longComment") or ""),
        }
    return lookup


def _fetch_site_roster_athletes(team_id: str) -> list[dict[str, Any]]:
    response = requests.get(
        ESPN_TEAM_ROSTER_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    athletes: list[dict[str, Any]] = []
    for group in payload.get("athletes") or []:
        for athlete in group.get("items") or []:
            if not athlete.get("id"):
                continue
            status_type = str((athlete.get("status") or {}).get("type") or "")
            if status_type in _FORTY_MAN_EXCLUDE_STATUSES:
                continue
            athletes.append(athlete)
    return athletes


def _fetch_team_roster(team_id: str, *, season_year: int | None = None) -> dict[str, Any]:
    year = season_year or date.today().year
    injury_lookup = _fetch_team_injury_lookup(team_id)
    athletes = _fetch_site_roster_athletes(team_id)

    grouped: dict[str, list[dict[str, Any]]] = {
        "rotation": [],
        "bullpen": [],
        "catchers": [],
        "infield": [],
        "outfield": [],
    }
    for athlete in athletes:
        player = _parse_roster_player(athlete, injury_lookup=injury_lookup)
        if not player.get("id"):
            continue
        section_key = _classify_roster_player(player)
        grouped[section_key].append(player)

    section_titles = {
        "rotation": "Starting Rotation",
        "bullpen": "Bullpen",
        "catchers": "Catchers",
        "infield": "Infield",
        "outfield": "Outfield",
    }
    sections: list[dict[str, Any]] = []
    for section_id, title in section_titles.items():
        players = sorted(grouped[section_id], key=_roster_sort_key)
        if players:
            sections.append({"id": section_id, "title": title, "players": players})

    return {
        "filters": [{"id": filter_id, "label": label} for filter_id, label in _ROSTER_FILTERS],
        "sections": sections,
    }


def _normalize_player_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        if first and last:
            text = f"{first} {last}"
    return re.sub(r"[^a-z ]", "", text).strip()


def _espn_category_season_row(
    category: dict[str, Any] | None,
    season_year: int,
) -> dict[str, str]:
    if not category:
        return {}
    labels = category.get("labels") or []
    for stat in category.get("statistics") or []:
        year = (stat.get("season") or {}).get("year")
        if str(year) == str(season_year):
            return dict(zip(labels, stat.get("stats") or []))
    return {}


_BATTING_ESPN_ROW_MAP = {
    "AVG": "avg",
    "OPS": "OPS",
    "HR": "homeRuns",
    "RBI": "RBIs",
    "SB": "stolenBases",
    "WAR": "WAR",
}
_PITCHING_ESPN_ROW_MAP = {
    "ERA": "ERA",
    "WHIP": "WHIP",
    "IP": "innings",
    "W": "wins",
    "L": "losses",
    "SV": "saves",
    "K": "strikeouts",
    "SO": "strikeouts",
    "BB": "walks",
    "WAR": "WAR",
}
_FIELDING_ESPN_ROW_MAP = {
    "FLD%": "fieldingPct",
    "PO": "putouts",
    "A": "assists",
    "E": "errors",
    "DP": "doublePlays",
    "TC": "totalChances",
    "INN": "fullInningsPlayed",
}


def _espn_row_has_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip() not in {"", "—", "--", "-"}


def _apply_espn_row(
    stats: dict[str, Any],
    row: dict[str, str],
    mapping: dict[str, str],
) -> None:
    for espn_label, stat_key in mapping.items():
        value = row.get(espn_label)
        if _espn_row_has_value(value):
            stats[stat_key] = value


def _merge_espn_batting_stats(
    stats: dict[str, Any],
    categories: dict[str, dict[str, Any]],
    *,
    season_year: int,
) -> None:
    career_row = _espn_category_season_row(
        categories.get("career-batting"),
        season_year,
    )
    advanced_row = _espn_category_season_row(
        categories.get("advanced-batting"),
        season_year,
    )
    _apply_espn_row(stats, career_row, _BATTING_ESPN_ROW_MAP)
    for label in ("WAR", "RC", "RC/27", "ISOP"):
        value = advanced_row.get(label)
        if _espn_row_has_value(value):
            stats[label] = value


def _merge_espn_pitching_stats(
    stats: dict[str, Any],
    categories: dict[str, dict[str, Any]],
    *,
    season_year: int,
) -> None:
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

    _apply_espn_row(stats, pitching_row, _PITCHING_ESPN_ROW_MAP)

    for label in ("K/9", "QS"):
        value = expanded_row.get(label)
        if _espn_row_has_value(value):
            stats[label] = value

    oops = opponent_row.get("OOPS")
    if _espn_row_has_value(oops):
        stats["OOPS"] = oops


def _merge_espn_fielding_stats(
    stats: dict[str, Any],
    categories: dict[str, dict[str, Any]],
    *,
    season_year: int,
) -> None:
    fielding_row = _espn_category_season_row(
        categories.get("fielding"),
        season_year,
    )
    _apply_espn_row(stats, fielding_row, _FIELDING_ESPN_ROW_MAP)


def _fetch_athlete_leader_stats(
    player: dict[str, Any],
    *,
    season_year: int,
) -> dict[str, Any] | None:
    player_id = str(player.get("id") or "")
    if not player_id:
        return None

    cache_key = f"{player_id}:{season_year}"
    cached = _athlete_season_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    position = str(player.get("position") or "").upper()
    is_pitcher = position in _PITCHER_POSITIONS
    stats: dict[str, Any] = {}

    try:
        stats_response = requests.get(
            ESPN_ATHLETE_STATS_URL.format(player_id=player_id),
            timeout=15,
        )
        stats_response.raise_for_status()
        categories = {
            category.get("name"): category
            for category in stats_response.json().get("categories") or []
            if category.get("name")
        }
        if is_pitcher:
            _merge_espn_pitching_stats(stats, categories, season_year=season_year)
        else:
            _merge_espn_batting_stats(stats, categories, season_year=season_year)
            _merge_espn_fielding_stats(stats, categories, season_year=season_year)

        if not stats:
            result = None
        else:
            result = {
                "id": player_id,
                "name": player.get("name") or "",
                "position": position,
                "headshot": player.get("headshot"),
                "stats": stats,
                "pitching": is_pitcher,
            }
    except Exception:
        result = None

    _athlete_season_cache[cache_key] = (now, result)
    return result


def _leader_value(stats: dict[str, Any], stat_name: str) -> float | None:
    return _parse_number(stats.get(stat_name))


def _build_leader_categories(
    players: list[dict[str, Any]],
    specs: tuple[tuple[str, str, bool], ...],
    *,
    top_n: int = _LEADER_TOP_N,
) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for stat_name, label, higher_is_better in specs:
        ranked = []
        for athlete in players:
            value = _leader_value(athlete["stats"], stat_name)
            if value is None:
                continue
            if stat_name in _PITCHING_RATE_STATS_REQUIRING_IP:
                innings = _parse_number(athlete["stats"].get("innings"))
                if innings is None or innings < _MIN_PITCHING_LEADER_IP:
                    continue
            ranked.append({
                "id": athlete["id"],
                "name": athlete["name"],
                "headshot": athlete.get("headshot"),
                "value": _format_stat_value(stat_name, value),
                "sort_value": value,
            })
            if athlete.get("team_side"):
                ranked[-1].update({
                    "team_side": athlete["team_side"],
                    "team_id": athlete.get("team_id"),
                    "team_abbr": athlete.get("team_abbr"),
                    "team_color": athlete.get("team_color"),
                })
        ranked.sort(key=lambda row: row["sort_value"], reverse=higher_is_better)
        top = ranked[:top_n]
        if top:
            for row in top:
                row.pop("sort_value", None)
            categories.append({"title": label, "leaders": top})
    return categories


def _leader_team_meta(team: dict[str, Any] | None, side: str) -> dict[str, str]:
    team = team or {}
    return {
        "team_side": side,
        "team_id": str(team.get("id") or ""),
        "team_abbr": str(team.get("abbr") or ""),
        "team_color": str(team.get("win_color") or team.get("color") or "#1a2332"),
    }


def _fetch_leader_athletes(
    players: list[dict[str, Any]],
    *,
    season_year: int,
) -> list[dict[str, Any]]:
    athletes: list[dict[str, Any]] = []
    if not players:
        return athletes

    with ThreadPoolExecutor(max_workers=_LEADER_FETCH_WORKERS) as executor:
        futures = {
            executor.submit(
                _fetch_athlete_leader_stats,
                player,
                season_year=season_year,
            ): player
            for player in players
        }
        for future in as_completed(futures):
            athlete = future.result()
            if athlete and athlete.get("stats"):
                athletes.append(athlete)
    return athletes


def _leader_views_from_athletes(
    athletes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []

    position_players = [a for a in athletes if not a.get("pitching")]
    batting_specs = _BATTING_LEADER_SPECS + _BATTING_ADVANCED_LEADER_SPECS
    batting_categories = _build_leader_categories(position_players, batting_specs)
    if batting_categories:
        views.append({"id": "batting", "label": "Batting", "categories": batting_categories})

    pitching_players = [a for a in athletes if a.get("pitching")]
    pitching_specs = _PITCHING_LEADER_SPECS + _PITCHING_ADVANCED_LEADER_SPECS
    pitching_categories = _build_leader_categories(pitching_players, pitching_specs)
    if pitching_categories:
        views.append({"id": "pitching", "label": "Pitching", "categories": pitching_categories})

    fielding_categories = _build_leader_categories(position_players, _FIELDING_LEADER_SPECS)
    if fielding_categories:
        views.append({"id": "fielding", "label": "Fielding", "categories": fielding_categories})

    return views


def _build_leader_views(
    roster_sections: list[dict[str, Any]],
    *,
    season_year: int,
) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    for section in roster_sections:
        for player in section.get("players") or []:
            if player.get("id"):
                players.append(player)

    athletes = _fetch_leader_athletes(players, season_year=season_year)
    return _leader_views_from_athletes(athletes)


def _game_month_key(iso_date: str | None) -> str | None:
    if not iso_date or len(iso_date) < 7:
        return None
    return iso_date[:7]


def _game_day(iso_date: str | None) -> int | None:
    if not iso_date or len(iso_date) < 10:
        return None
    try:
        return int(iso_date[8:10])
    except ValueError:
        return None


def _default_schedule_month(
    months: list[dict[str, Any]],
    games: list[dict[str, Any]],
) -> str:
    if not months:
        return ""
    month_ids = {month["id"] for month in months}
    today_key = date.today().strftime("%Y-%m")
    if today_key in month_ids:
        return today_key

    today_iso = date.today().isoformat()
    for game in games:
        game_date = (game.get("date") or "")[:10]
        if game_date >= today_iso and not game.get("result"):
            month_key = _game_month_key(game.get("date"))
            if month_key in month_ids:
                return month_key

    return months[0]["id"]


def _parse_espn_score(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, dict):
        display = value.get("displayValue")
        if display is not None and str(display).strip() not in {"", "—", "--"}:
            parsed = _parse_number(display)
            return int(parsed) if parsed is not None else None
        raw = value.get("value")
        if raw is not None:
            parsed = _parse_number(raw)
            return int(parsed) if parsed is not None else None
        return None
    parsed = _parse_number(value)
    return int(parsed) if parsed is not None else None


def _is_postponed_status(status: dict[str, Any]) -> bool:
    name = str(status.get("name") or "").upper()
    state = str(status.get("state") or "").lower()
    detail = " ".join(
        str(status.get(key) or "")
        for key in ("detail", "shortDetail", "description")
    ).lower()
    if "POSTPONED" in name or state == "postponed":
        return True
    return "postpon" in detail


def _parse_schedule_games(team_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    games: list[dict[str, Any]] = []

    for event in payload.get("events") or []:
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        team_comp = None
        opp_comp = None
        for competitor in competitors:
            competitor_team_id = str((competitor.get("team") or {}).get("id") or "")
            if competitor_team_id == str(team_id):
                team_comp = competitor
            else:
                opp_comp = competitor
        if not team_comp or not opp_comp:
            continue

        status = (competition.get("status") or {}).get("type") or {}
        is_postponed = _is_postponed_status(status)
        is_completed = not is_postponed and (
            bool(status.get("completed")) or status.get("state") == "post"
        )
        team_score = _parse_espn_score(team_comp.get("score"))
        opp_score = _parse_espn_score(opp_comp.get("score"))
        opp_team = opp_comp.get("team") or {}
        home_away = team_comp.get("homeAway") or ""
        iso_date = event.get("date")
        game = {
            "id": str(competition.get("id") or event.get("id") or ""),
            "date": iso_date,
            "day": _game_day(iso_date),
            "opponent_id": str(opp_team.get("id") or ""),
            "opponent_abbr": opp_team.get("abbreviation") or "",
            "opponent_name": opp_team.get("displayName") or "",
            "home_away": home_away,
            "status": status.get("shortDetail") or status.get("detail") or "",
            "team_score": team_score,
            "opponent_score": opp_score,
            "result": None,
            "postponed": is_postponed,
        }
        if is_postponed:
            game["status"] = "Postponed"
            game["team_score"] = None
            game["opponent_score"] = None
        elif is_completed and team_score is not None and opp_score is not None:
            game["result"] = (
                "W" if team_score > opp_score
                else ("L" if team_score < opp_score else "T")
            )
        elif is_completed and not game.get("status"):
            game["status"] = "Final"

        games.append(game)

    games.sort(key=lambda row: row.get("date") or "")

    months_map: dict[str, list[dict[str, Any]]] = {}
    for game in games:
        month_key = _game_month_key(game.get("date"))
        if not month_key:
            continue
        months_map.setdefault(month_key, []).append(game)

    months: list[dict[str, Any]] = []
    for month_key in sorted(months_map.keys()):
        year_str, month_str = month_key.split("-", 1)
        month_number = int(month_str)
        month_label = date(int(year_str), month_number, 1).strftime("%B %Y")
        months.append({
            "id": month_key,
            "label": month_label,
            "year": int(year_str),
            "month": month_number,
            "games": months_map[month_key],
        })

    return {
        "months": months,
        "default_month": _default_schedule_month(months, games),
    }


def _fetch_team_schedule(team_id: str) -> dict[str, Any]:
    response = requests.get(
        ESPN_TEAM_SCHEDULE_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    return _parse_schedule_games(team_id, response.json())


def fetch_team_stats_table(team_id: str, *, season_year: int | None = None) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:summary"
    cached = _team_summary_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        stats_by_category = _fetch_team_statistics(team_id)
        result = _build_summary_table(stats_by_category, season_year=year)
    except Exception:
        result = None

    _team_summary_cache[cache_key] = (now, result)
    return result


def _get_cached_team_roster(team_id: str, season_year: int) -> dict[str, Any]:
    cache_key = f"{team_id}:{season_year}:roster:v1"
    cached = _team_roster_data_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    roster = _fetch_team_roster(team_id, season_year=season_year)
    _team_roster_data_cache[cache_key] = (now, roster)
    return roster


def _build_team_stats_panel(
    stats_by_category: dict[str, dict[str, Any]],
    *,
    season_year: int,
    league_stats: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    batting_metrics = _build_stat_metrics(
        stats_by_category.get("batting") or {},
        _BATTING_DETAIL_SPECS,
        category="batting",
        league_stats=league_stats.get("batting") or {},
    )
    pitching_metrics = _build_stat_metrics(
        stats_by_category.get("pitching") or {},
        _PITCHING_DETAIL_SPECS,
        category="pitching",
        league_stats=league_stats.get("pitching") or {},
    )
    fielding_metrics = _build_stat_metrics(
        stats_by_category.get("fielding") or {},
        _FIELDING_DETAIL_SPECS,
        category="fielding",
        league_stats=league_stats.get("fielding") or {},
    )

    stat_views: list[dict[str, Any]] = []
    if batting_metrics:
        stat_views.append({"id": "batting", "label": "Batting", "metrics": batting_metrics})
    if pitching_metrics:
        stat_views.append({"id": "pitching", "label": "Pitching", "metrics": pitching_metrics})
    if fielding_metrics:
        stat_views.append({"id": "fielding", "label": "Fielding", "metrics": fielding_metrics})
    if not stat_views:
        return None

    return {
        "id": "team_stats",
        "label": "Team Stats",
        "panel_kind": "toggle_stat_bars",
        "default_view": stat_views[0]["id"],
        "season_year": str(season_year),
        "views": stat_views,
    }


def _build_schedule_panel(team_id: str) -> dict[str, Any] | None:
    schedule = _fetch_team_schedule(team_id)
    if not schedule.get("months"):
        return None
    return {
        "id": "schedule",
        "label": "Schedule",
        "panel_kind": "schedule_calendar",
        "default_month": schedule.get("default_month"),
        "months": schedule.get("months") or [],
    }


def _build_roster_panel(roster: dict[str, Any]) -> dict[str, Any] | None:
    roster_sections = roster.get("sections") or []
    if not roster_sections:
        return None
    return {
        "id": "roster",
        "label": "Roster",
        "panel_kind": "roster_cards",
        "default_filter": "all",
        "filters": roster.get("filters") or [],
        "sections": roster_sections,
    }


def _build_leaders_panel(
    roster_sections: list[dict[str, Any]],
    *,
    season_year: int,
) -> dict[str, Any] | None:
    leader_views = _build_leader_views(roster_sections, season_year=season_year)
    if not leader_views:
        return None
    return {
        "id": "leaders",
        "label": "Team Leaders",
        "panel_kind": "toggle_leaders",
        "default_view": leader_views[0]["id"],
        "season_year": str(season_year),
        "views": leader_views,
    }


def fetch_team_team_stats_panel(
    team_id: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:team-stats:v1"
    cached = _team_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panel: dict[str, Any] | None = None
    try:
        stats_by_category = _fetch_team_statistics(team_id)
        league_stats = _get_league_stats_by_category(year)
        panel = _build_team_stats_panel(
            stats_by_category,
            season_year=year,
            league_stats=league_stats,
        )
    except Exception:
        panel = None

    _team_core_panels_cache[cache_key] = (now, panel)
    return panel


def fetch_team_schedule_stat_panel(
    team_id: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:schedule:v1"
    cached = _team_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panel: dict[str, Any] | None = None
    try:
        panel = _build_schedule_panel(team_id)
    except Exception:
        panel = None

    _team_core_panels_cache[cache_key] = (now, panel)
    return panel


def fetch_team_core_stat_panels(
    team_id: str,
    *,
    season_year: int | None = None,
) -> list[dict[str, Any]]:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:core:v1"
    cached = _team_core_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panels: list[dict[str, Any]] = []
    team_stats_panel = fetch_team_team_stats_panel(team_id, season_year=year)
    if team_stats_panel:
        panels.append(team_stats_panel)

    schedule_panel = fetch_team_schedule_stat_panel(team_id, season_year=year)
    if schedule_panel:
        panels.append(schedule_panel)

    _team_core_panels_cache[cache_key] = (now, panels)
    return panels


def fetch_team_roster_stat_panel(
    team_id: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:roster:v1"
    cached = _team_roster_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panel: dict[str, Any] | None = None
    try:
        roster = _get_cached_team_roster(team_id, year)
        panel = _build_roster_panel(roster)
    except Exception:
        panel = None

    _team_roster_panel_cache[cache_key] = (now, panel)
    return panel


def fetch_team_leaders_stat_panel(
    team_id: str,
    *,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:leaders:v3"
    cached = _team_leaders_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panel: dict[str, Any] | None = None
    try:
        roster = _get_cached_team_roster(team_id, year)
        roster_sections = roster.get("sections") or []
        panel = _build_leaders_panel(roster_sections, season_year=year)
    except Exception:
        panel = None

    _team_leaders_panel_cache[cache_key] = (now, panel)
    return panel


def build_matchup_leaders_panel(
    away_id: str,
    home_id: str,
    *,
    away_team: dict[str, Any] | None = None,
    home_team: dict[str, Any] | None = None,
    season_year: int | None = None,
) -> dict[str, Any] | None:
    year = season_year or date.today().year
    cache_key = f"{away_id}:{home_id}:{year}:matchup-leaders:v2"
    cached = _matchup_leaders_panel_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panel: dict[str, Any] | None = None
    try:
        away_roster = _get_cached_team_roster(away_id, year)
        home_roster = _get_cached_team_roster(home_id, year)
        roster_players: list[dict[str, Any]] = []
        team_meta_by_id: dict[str, dict[str, str]] = {}
        for side, team, roster in (
            ("away", away_team, away_roster),
            ("home", home_team, home_roster),
        ):
            meta = _leader_team_meta(team, side)
            for section in roster.get("sections") or []:
                for player in section.get("players") or []:
                    player_id = player.get("id")
                    if not player_id:
                        continue
                    player_id = str(player_id)
                    if player_id not in team_meta_by_id:
                        roster_players.append(player)
                        team_meta_by_id[player_id] = meta

        athletes = _fetch_leader_athletes(roster_players, season_year=year)
        for athlete in athletes:
            meta = team_meta_by_id.get(str(athlete.get("id") or ""))
            if meta:
                athlete.update(meta)

        leader_views = _leader_views_from_athletes(athletes)
        if leader_views:
            panel = {
                "id": "matchup_leaders",
                "label": "Team Leaders",
                "panel_kind": "toggle_leaders",
                "default_view": leader_views[0]["id"],
                "season_year": str(year),
                "views": leader_views,
            }
    except Exception:
        panel = None

    _matchup_leaders_panel_cache[cache_key] = (now, panel)
    return panel


def fetch_team_stat_panels(
    team_id: str,
    *,
    season_year: int | None = None,
) -> list[dict[str, Any]]:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:v20"
    cached = _team_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panels: list[dict[str, Any]] = []
    panels.extend(fetch_team_core_stat_panels(team_id, season_year=year))

    leaders_panel = fetch_team_leaders_stat_panel(team_id, season_year=year)
    if leaders_panel:
        panels.insert(1, leaders_panel)

    roster_panel = fetch_team_roster_stat_panel(team_id, season_year=year)
    if roster_panel:
        insert_at = 2 if leaders_panel else 1
        panels.insert(insert_at, roster_panel)

    _team_panels_cache[cache_key] = (now, panels)
    return panels
