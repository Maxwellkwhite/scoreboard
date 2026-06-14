"""Team season stats and stat panels via ESPN APIs."""

from __future__ import annotations

import time
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
ESPN_TEAM_SCHEDULE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_id}/schedule"
)
ESPN_ATHLETE_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}"
)

_CACHE_TTL_SECONDS = 300
_team_panels_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
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
    ("homeRuns", "HR", True),
    ("RBIs", "RBI", True),
    ("avg", "AVG", True),
    ("OPS", "OPS", True),
    ("stolenBases", "SB", True),
)
_PITCHING_LEADER_SPECS = (
    ("ERA", "ERA", False),
    ("strikeouts", "SO", True),
    ("wins", "W", True),
    ("saves", "SV", True),
    ("WHIP", "WHIP", False),
)

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
    if stat_name in {"avg", "onBasePct", "slugAvg", "OPS", "WHIP", "opponentAvg", "fieldingPct"}:
        return _format_rate(number, 3)
    if stat_name in {"ERA", "strikeoutsPerNineInnings", "winPct"}:
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
    response = requests.get(
        ESPN_TEAM_STATISTICS_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    categories = ((payload.get("results") or {}).get("stats") or {}).get("categories") or []
    return {
        "batting": _category_stats_map(categories, "batting"),
        "pitching": _category_stats_map(categories, "pitching"),
        "fielding": _category_stats_map(categories, "fielding"),
    }


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


def _fetch_team_roster(team_id: str) -> list[dict[str, Any]]:
    response = requests.get(
        ESPN_TEAM_ROSTER_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    groups: list[dict[str, Any]] = []
    for group in payload.get("athletes") or []:
        players: list[dict[str, Any]] = []
        for athlete in group.get("items") or []:
            player_id = athlete.get("id")
            if not player_id:
                continue
            position = athlete.get("position") or {}
            players.append({
                "id": str(player_id),
                "name": athlete.get("displayName") or athlete.get("fullName") or "",
                "jersey": athlete.get("jersey"),
                "position": position.get("abbreviation") or position.get("name") or "",
            })
        if players:
            groups.append({
                "title": group.get("position") or "Players",
                "players": players,
            })
    return groups


def _fetch_athlete_season_stats(player_id: str) -> dict[str, Any] | None:
    cached = _athlete_season_cache.get(player_id)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            ESPN_ATHLETE_URL.format(player_id=player_id),
            timeout=15,
        )
        response.raise_for_status()
        athlete = (response.json().get("athlete") or {})
        position = ((athlete.get("position") or {}).get("abbreviation") or "").upper()
        stats_summary = athlete.get("statsSummary") or {}
        stats: dict[str, Any] = {}
        for stat in stats_summary.get("statistics") or []:
            name = stat.get("name") or ""
            if name:
                stats[name] = stat.get("value")
        result = {
            "id": str(player_id),
            "name": athlete.get("displayName") or "",
            "position": position,
            "stats": stats,
            "pitching": position in {"P", "SP", "RP", "CP", "CL", "LR", "MR", "SU"},
        }
    except Exception:
        result = None

    _athlete_season_cache[player_id] = (now, result)
    return result


def _leader_value(stats: dict[str, Any], stat_name: str) -> float | None:
    return _parse_number(stats.get(stat_name))


def _build_leader_groups(
    roster_groups: list[dict[str, Any]],
    *,
    season_year: int,
) -> list[dict[str, Any]]:
    player_ids: list[str] = []
    for group in roster_groups:
        for player in group.get("players") or []:
            if player.get("id"):
                player_ids.append(player["id"])

    athletes: list[dict[str, Any]] = []
    if player_ids:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(_fetch_athlete_season_stats, player_id): player_id
                for player_id in player_ids
            }
            for future in as_completed(futures):
                athlete = future.result()
                if athlete and athlete.get("stats"):
                    athletes.append(athlete)

    leader_groups: list[dict[str, Any]] = []

    batting_players = [a for a in athletes if not a.get("pitching")]
    batting_leaders: list[dict[str, Any]] = []
    for stat_name, label, higher_is_better in _BATTING_LEADER_SPECS:
        ranked = []
        for athlete in batting_players:
            value = _leader_value(athlete["stats"], stat_name)
            if value is None:
                continue
            ranked.append({
                "id": athlete["id"],
                "name": athlete["name"],
                "value": _format_stat_value(stat_name, value),
                "sort_value": value,
            })
        ranked.sort(key=lambda row: row["sort_value"], reverse=higher_is_better)
        top = ranked[:3]
        if top:
            for row in top:
                row.pop("sort_value", None)
            batting_leaders.append({"title": label, "leaders": top})
    if batting_leaders:
        leader_groups.append({
            "title": "Batting Leaders",
            "categories": batting_leaders,
        })

    pitching_players = [a for a in athletes if a.get("pitching")]
    pitching_categories: list[dict[str, Any]] = []
    for stat_name, label, higher_is_better in _PITCHING_LEADER_SPECS:
        ranked = []
        for athlete in pitching_players:
            value = _leader_value(athlete["stats"], stat_name)
            if value is None:
                continue
            ranked.append({
                "id": athlete["id"],
                "name": athlete["name"],
                "value": _format_stat_value(stat_name, value),
                "sort_value": value,
            })
        ranked.sort(key=lambda row: row["sort_value"], reverse=higher_is_better)
        top = ranked[:3]
        if top:
            for row in top:
                row.pop("sort_value", None)
            pitching_categories.append({"title": label, "leaders": top})
    if pitching_categories:
        leader_groups.append({
            "title": "Pitching Leaders",
            "categories": pitching_categories,
        })

    return leader_groups


def _parse_schedule_games(team_id: str, payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    completed: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []

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
        is_completed = bool(status.get("completed"))
        team_score = team_comp.get("score")
        opp_score = opp_comp.get("score")
        opp_team = opp_comp.get("team") or {}
        home_away = team_comp.get("homeAway") or ""
        game = {
            "id": str(competition.get("id") or event.get("id") or ""),
            "date": event.get("date"),
            "opponent_id": str(opp_team.get("id") or ""),
            "opponent_abbr": opp_team.get("abbreviation") or "",
            "opponent_name": opp_team.get("displayName") or "",
            "home_away": home_away,
            "status": status.get("shortDetail") or status.get("detail") or "",
            "team_score": team_score,
            "opponent_score": opp_score,
            "result": None,
        }
        if is_completed and team_score is not None and opp_score is not None:
            try:
                team_runs = int(team_score)
                opp_runs = int(opp_score)
                game["result"] = "W" if team_runs > opp_runs else ("L" if team_runs < opp_runs else "T")
            except (TypeError, ValueError):
                pass

        if is_completed:
            completed.append(game)
        else:
            upcoming.append(game)

    return {
        "recent": completed[-10:][::-1],
        "upcoming": upcoming[:10],
    }


def _fetch_team_schedule(team_id: str) -> dict[str, list[dict[str, Any]]]:
    response = requests.get(
        ESPN_TEAM_SCHEDULE_URL.format(team_id=team_id),
        timeout=20,
    )
    response.raise_for_status()
    return _parse_schedule_games(team_id, response.json())


def _build_history_panel(team_detail: dict[str, Any]) -> dict[str, Any]:
    cards: list[dict[str, str]] = []
    for label, key in (
        ("Standing", "standing_summary"),
        ("Ballpark", "venue"),
        ("Home Record", "home_record"),
        ("Road Record", "road_record"),
        ("Division GB", "division_gb"),
        ("Streak", "streak"),
    ):
        value = team_detail.get(key)
        if value:
            cards.append({"label": label, "value": str(value)})
    return {
        "id": "history",
        "label": "Team Info",
        "panel_kind": "info_cards",
        "cards": cards,
    }


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


def fetch_team_stat_panels(
    team_id: str,
    *,
    season_year: int | None = None,
    team_detail: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    year = season_year or date.today().year
    cache_key = f"{team_id}:{year}:panels:v2"
    cached = _team_panels_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    panels: list[dict[str, Any]] = []
    try:
        stats_by_category = _fetch_team_statistics(team_id)
        batting_rows = _build_stat_rows(stats_by_category.get("batting") or {}, _BATTING_DETAIL_SPECS)
        pitching_rows = _build_stat_rows(stats_by_category.get("pitching") or {}, _PITCHING_DETAIL_SPECS)
        fielding_rows = _build_stat_rows(stats_by_category.get("fielding") or {}, _FIELDING_DETAIL_SPECS)

        stat_views: list[dict[str, Any]] = []
        if batting_rows:
            stat_views.append({"id": "batting", "label": "Batting", "rows": batting_rows})
        if pitching_rows:
            stat_views.append({"id": "pitching", "label": "Pitching", "rows": pitching_rows})
        if fielding_rows:
            stat_views.append({"id": "fielding", "label": "Fielding", "rows": fielding_rows})
        if stat_views:
            panels.append({
                "id": "team_stats",
                "label": "Team Stats",
                "panel_kind": "toggle_stat_table",
                "default_view": stat_views[0]["id"],
                "season_year": str(year),
                "views": stat_views,
            })

        roster_groups = _fetch_team_roster(team_id)
        leader_groups = _build_leader_groups(roster_groups, season_year=year)
        if leader_groups:
            panels.append({
                "id": "leaders",
                "label": "Team Leaders",
                "panel_kind": "leaders_table",
                "season_year": str(year),
                "groups": leader_groups,
            })

        if roster_groups:
            panels.append({
                "id": "roster",
                "label": "Roster",
                "panel_kind": "roster_groups",
                "groups": roster_groups,
            })

        schedule = _fetch_team_schedule(team_id)
        if schedule.get("recent") or schedule.get("upcoming"):
            panels.append({
                "id": "schedule",
                "label": "Schedule",
                "panel_kind": "schedule_list",
                "recent": schedule.get("recent") or [],
                "upcoming": schedule.get("upcoming") or [],
            })
    except Exception:
        panels = []

    if team_detail:
        history_panel = _build_history_panel(team_detail)
        if history_panel.get("cards"):
            panels.append(history_panel)

    _team_panels_cache[cache_key] = (now, panels)
    return panels
