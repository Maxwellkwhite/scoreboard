"""World Cup team and player stat panels for detail pages."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from espn_world_cup import (
    fetch_player,
    fetch_scoreboard,
    fetch_standings,
    fetch_team,
    fetch_team_core_events,
    fetch_team_schedule_payload,
    fetch_team_squad_roster,
)


def _parse_score(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("displayValue")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


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
) -> str | None:
    if not months:
        return None
    today_key = date.today().strftime("%Y-%m")
    month_ids = [month["id"] for month in months]
    if today_key in month_ids:
        return today_key
    for game in games:
        month_key = _game_month_key(game.get("date"))
        if month_key in month_ids:
            return month_key
    return months[0]["id"]


def _is_postponed_status(status: dict[str, Any]) -> bool:
    label = (
        status.get("description")
        or status.get("detail")
        or status.get("shortDetail")
        or ""
    ).lower()
    return "postpon" in label or "cancel" in label or "abandon" in label


def parse_team_schedule(team_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    games: list[dict[str, Any]] = []
    for event in payload.get("events") or []:
        competition = (event.get("competitions") or [{}])[0]
        team_comp = None
        opp_comp = None
        for competitor in competition.get("competitors") or []:
            competitor_team_id = str((competitor.get("team") or {}).get("id") or "")
            if competitor_team_id == str(team_id):
                team_comp = competitor
            else:
                opp_comp = competitor
        if not team_comp or not opp_comp:
            continue

        status = (competition.get("status") or event.get("status") or {}).get("type") or {}
        is_postponed = _is_postponed_status(status)
        is_completed = not is_postponed and (
            bool(status.get("completed")) or status.get("state") == "post"
        )
        team_score = _parse_score(team_comp.get("score"))
        opp_score = _parse_score(opp_comp.get("score"))
        opp_team = opp_comp.get("team") or {}
        game = {
            "id": str(competition.get("id") or event.get("id") or ""),
            "date": event.get("date"),
            "day": _game_day(event.get("date")),
            "opponent_id": str(opp_team.get("id") or ""),
            "opponent_abbr": opp_team.get("abbreviation") or "",
            "opponent_name": opp_team.get("displayName") or "",
            "home_away": team_comp.get("homeAway") or "",
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
        game["status_state"] = status.get("state", "pre")
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
        "games": games,
    }


def _scoreboard_date_key(iso_date: str | None) -> str | None:
    if not iso_date or len(iso_date) < 10:
        return None
    year, month, day = iso_date[:10].split("-")
    return f"{year}{month}{day}"


def _scoreboard_date_candidates(iso_date: str | None) -> list[str]:
    if not iso_date or len(iso_date) < 10:
        return []
    year, month, day = map(int, iso_date[:10].split("-"))
    base = date(year, month, day)
    keys = [
        base.strftime("%Y%m%d"),
        (base - timedelta(days=1)).strftime("%Y%m%d"),
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def _team_game_from_match(match: dict[str, Any], team_id: str) -> dict[str, Any]:
    team_id = str(team_id)
    away = match.get("away") or {}
    home = match.get("home") or {}
    if str(away.get("id")) == team_id:
        team_side, opp = away, home
        home_away = "away"
    elif str(home.get("id")) == team_id:
        team_side, opp = home, away
        home_away = "home"
    else:
        raise ValueError("team not in match")

    status_state = match.get("status_state", "pre")
    if status_state == "post":
        team_score = team_side.get("score")
        opp_score = opp.get("score")
    else:
        team_score = None
        opp_score = None
    result = None
    if status_state == "post" and team_score is not None and opp_score is not None:
        result = (
            "W" if team_score > opp_score
            else ("L" if team_score < opp_score else "T")
        )

    return {
        "id": str(match.get("id") or ""),
        "date": match.get("start_time"),
        "day": _game_day(match.get("start_time")),
        "opponent_id": str(opp.get("id") or ""),
        "opponent_abbr": opp.get("abbr") or "",
        "opponent_name": opp.get("name") or "",
        "home_away": home_away,
        "status": match.get("status_detail") or "",
        "status_state": status_state,
        "team_score": team_score,
        "opponent_score": opp_score,
        "result": result,
        "postponed": False,
    }


def _merge_team_game(games_by_id: dict[str, dict[str, Any]], game: dict[str, Any]) -> None:
    game_id = str(game.get("id") or "")
    if not game_id:
        return
    existing = games_by_id.get(game_id)
    if not existing:
        games_by_id[game_id] = game
        return
    # Prefer richer site-schedule rows when both sources have the same match.
    if existing.get("result") is None and game.get("result"):
        games_by_id[game_id] = game
    elif game.get("status_state") == "pre" and existing.get("status_state") == "post":
        games_by_id[game_id] = game


def fetch_all_team_games(team_id: str) -> list[dict[str, Any]]:
    team_id = str(team_id)
    games_by_id: dict[str, dict[str, Any]] = {}

    payload = fetch_team_schedule_payload(team_id)
    for game in parse_team_schedule(team_id, payload).get("games") or []:
        _merge_team_game(games_by_id, game)

    core_events = fetch_team_core_events(team_id)
    missing_ids = {
        str(event.get("id") or "")
        for event in core_events
        if str(event.get("id") or "") not in games_by_id
    }
    dates_fetched: set[str] = set()
    for event in core_events:
        if str(event.get("id") or "") not in missing_ids:
            continue
        for date_key in _scoreboard_date_candidates(event.get("date")):
            if date_key in dates_fetched:
                continue
            dates_fetched.add(date_key)
            year = int(date_key[:4])
            month = int(date_key[4:6])
            day = int(date_key[6:8])
            try:
                board = fetch_scoreboard(date(year, month, day))
            except Exception:
                continue
            for match in board:
                match_id = str(match.get("id") or "")
                if match_id not in missing_ids:
                    continue
                away_id = str((match.get("away") or {}).get("id") or "")
                home_id = str((match.get("home") or {}).get("id") or "")
                if team_id not in {away_id, home_id}:
                    continue
                try:
                    game = _team_game_from_match(match, team_id)
                except ValueError:
                    continue
                _merge_team_game(games_by_id, game)
                missing_ids.discard(match_id)

    games = list(games_by_id.values())
    games.sort(key=lambda row: row.get("date") or "")
    return games


def _is_upcoming_game(game: dict[str, Any]) -> bool:
    if game.get("result") or game.get("postponed"):
        return False
    state = game.get("status_state", "pre")
    return state in {"pre", "in"}


def build_team_games_panel(team_id: str) -> dict[str, Any] | None:
    games = fetch_all_team_games(str(team_id))
    if not games:
        return None

    completed = [game for game in games if game.get("result")]
    upcoming = [game for game in games if _is_upcoming_game(game)]
    upcoming_game = upcoming[0] if upcoming else None
    last_five = list(reversed(completed[-5:]))

    if not upcoming_game and not last_five:
        return None

    return {
        "id": "games",
        "label": "Games",
        "panel_kind": "team_games_overview",
        "upcoming_game": upcoming_game,
        "last_five": last_five,
    }


_ROSTER_FILTERS = [
    ("all", "All"),
    ("goalkeeper", "GK"),
    ("defender", "DEF"),
    ("midfielder", "MID"),
    ("forward", "FWD"),
]


def build_team_standings_table(team_id: str) -> dict[str, Any] | None:
    row = None
    for group in fetch_standings():
        for team in group.get("teams") or []:
            if str(team.get("id")) == str(team_id):
                row = team
                break
        if row:
            break
    if not row:
        return None

    return {
        "season_year": str(date.today().year),
        "columns": [
            {"label": "GP", "season": row.get("gp") or "—"},
            {"label": "W-D-L", "season": row.get("record") or "—"},
            {"label": "GD", "season": row.get("gd") or "—"},
            {"label": "PTS", "season": row.get("pts") or "—"},
        ],
    }


def build_team_roster_panel(team_id: str) -> dict[str, Any] | None:
    roster = fetch_team_squad_roster(str(team_id))
    if not roster or not roster.get("sections"):
        return None
    return {
        "id": "roster",
        "label": "Roster",
        "panel_kind": "roster_cards",
        "default_filter": "all",
        "filters": [{"id": filter_id, "label": label} for filter_id, label in _ROSTER_FILTERS],
        "sections": roster.get("sections") or [],
    }


def build_team_schedule_panel(team_id: str) -> dict[str, Any] | None:
    return build_team_games_panel(team_id)


def fetch_team_stats_bundle(team_id: str) -> dict[str, Any]:
    team = fetch_team(str(team_id))
    stats_table = build_team_standings_table(team_id)
    return {
        "team": team,
        "stats_table": stats_table,
        "stat_panels": [],
    }


def fetch_player_stats_bundle(player_id: str) -> dict[str, Any]:
    player = fetch_player(str(player_id))
    team = player.get("team") or {}
    columns = [
        {"label": "Position", "season": player.get("position") or "—"},
        {"label": "Jersey", "season": player.get("jersey") or "—"},
        {"label": "Nationality", "season": player.get("citizenship") or "—"},
        {"label": "Team", "season": team.get("abbr") or team.get("name") or "—"},
    ]
    if team.get("group_name"):
        columns.append({"label": "Group", "season": team.get("group_name")})

    stat_panel = {
        "id": "player_stats",
        "label": "World Cup",
        "panel_kind": "toggle_stat_bars",
        "default_view": "tournament",
        "views": [
            {
                "id": "tournament",
                "label": "Tournament",
                "stats_table": {
                    "season_year": player.get("season_year") or str(date.today().year),
                    "columns": columns,
                },
            }
        ],
    }
    return {
        "player": player,
        "stat_panel": stat_panel,
        "profile_panel": None,
    }
