"""ESPN FIFA World Cup scoreboard client."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import requests

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)
ESPN_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary"
)
ESPN_STANDINGS_URL = (
    "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
)
ESPN_TEAM_ROSTER_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/{team_id}/roster"
)

CACHE_TTL_SECONDS = 30
ROSTER_CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_team_roster_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_standings_cache: tuple[float, list[dict[str, Any]]] | None = None

STRIP_CARDS_PER_PAGE = 4
_STATUS_SORT_ORDER = {"in": 0, "pre": 1, "post": 2}

_WIN_COLOR_MIN_DISTANCE = 45.0
_WIN_COLOR_SKIP = {"#000000", "#ffffff"}


def _parse_score(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _team_logo(team: dict[str, Any]) -> str | None:
    logo = team.get("logo")
    if logo:
        return logo
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href")
    return None


def _normalize_hex(color: Any) -> str | None:
    if not color:
        return None
    color = str(color).strip().lstrip("#")
    if len(color) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in color):
        return f"#{color.lower()}"
    return None


def _color_luminance(color: str) -> float:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _usable_team_color(color: str | None) -> str | None:
    if not color or color in _WIN_COLOR_SKIP:
        return None
    if _color_luminance(color) > 185:
        return None
    return color


def _team_color(team: dict[str, Any]) -> str | None:
    return _usable_team_color(_normalize_hex(team.get("color")))


def _team_alternate_color(team: dict[str, Any]) -> str | None:
    return _usable_team_color(_normalize_hex(team.get("alternateColor")))


def _color_distance(left: str, right: str) -> float:
    left_rgb = (int(left[1:3], 16), int(left[3:5], 16), int(left[5:7], 16))
    right_rgb = (int(right[1:3], 16), int(right[3:5], 16), int(right[5:7], 16))
    return sum((a - b) ** 2 for a, b in zip(left_rgb, right_rgb)) ** 0.5


def _colors_too_similar(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return _color_distance(left, right) < _WIN_COLOR_MIN_DISTANCE


def _team_color_candidates(team: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for value in (_team_color(team), _team_alternate_color(team)):
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def _resolve_win_colors(away: dict[str, Any], home: dict[str, Any]) -> None:
    away_candidates = _team_color_candidates(
        {"color": away.get("color"), "alternateColor": away.get("alternate_color")}
    )
    home_candidates = _team_color_candidates(
        {"color": home.get("color"), "alternateColor": home.get("alternate_color")}
    )

    away_win = _usable_team_color(away.get("color")) or (
        away_candidates[0] if away_candidates else "#56b6c6"
    )
    home_win = _usable_team_color(home.get("color")) or (
        home_candidates[0] if home_candidates else "#22a06b"
    )

    if not _colors_too_similar(away_win, home_win):
        away["win_color"] = away_win
        home["win_color"] = home_win
        return

    home_alternate = home.get("alternate_color")
    if home_alternate and not _colors_too_similar(away_win, home_alternate):
        home["win_color"] = home_alternate
        away["win_color"] = away_win
        return

    away_alternate = away.get("alternate_color")
    if away_alternate and not _colors_too_similar(away_alternate, home_win):
        away["win_color"] = away_alternate
        home["win_color"] = home_win
        return

    away["win_color"] = away_win
    home["win_color"] = home_win


def _team_record(records: list[dict[str, Any]] | dict[str, Any] | str | None) -> str | None:
    if not records:
        return None
    if isinstance(records, str):
        return records
    if isinstance(records, dict):
        display = records.get("displayValue") or records.get("summary")
        if display:
            return str(display)
        items = records.get("items")
        if isinstance(items, list):
            return _team_record(items)
        return None
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("type") == "total":
            return record.get("displayValue") or record.get("summary")
    first = records[0]
    if not isinstance(first, dict):
        return str(first) if first is not None else None
    return first.get("displayValue") or first.get("summary")


def _parse_team(competitor: dict[str, Any]) -> dict[str, Any]:
    team = competitor.get("team") or {}
    record_source = competitor.get("records") or competitor.get("record")
    if isinstance(record_source, dict):
        record_source = record_source.get("items") or [record_source]
    return {
        "id": team.get("id"),
        "abbr": team.get("abbreviation", ""),
        "name": team.get("displayName", ""),
        "short_name": team.get("shortDisplayName", ""),
        "logo": _team_logo(team),
        "color": _team_color(team),
        "alternate_color": _team_alternate_color(team),
        "score": _parse_score(competitor.get("score")),
        "winner": competitor.get("winner"),
        "record": _team_record(record_source),
    }


def parse_match(event: dict[str, Any]) -> dict[str, Any]:
    comp = event["competitions"][0]
    away = home = None
    for competitor in comp.get("competitors", []):
        parsed = _parse_team(competitor)
        if competitor.get("homeAway") == "home":
            home = parsed
        else:
            away = parsed

    status = event.get("status") or {}
    status_type = status.get("type") or {}
    match_id = event.get("id")

    if away and home:
        _resolve_win_colors(away, home)

    status_detail = (
        status_type.get("shortDetail")
        or status_type.get("detail")
        or status_type.get("description", "")
    )

    return {
        "id": str(match_id) if match_id is not None else None,
        "name": event.get("shortName") or event.get("name", ""),
        "start_time": event.get("date"),
        "status_state": status_type.get("state", "pre"),
        "status_detail": status_detail,
        "away": away,
        "home": home,
        "espn_link": f"https://www.espn.com/soccer/match/_/gameId/{match_id}",
    }


def _scoreboard_sort_key(match: dict[str, Any]) -> tuple[int, str]:
    state = match.get("status_state", "pre")
    priority = _STATUS_SORT_ORDER.get(state, 1)
    return priority, match.get("start_time") or ""


def fetch_scoreboard(
    game_date: date,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    date_key = game_date.strftime("%Y%m%d")
    now = time.time()
    cached = _cache.get(date_key)
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    response = requests.get(
        ESPN_SCOREBOARD_URL,
        params={"dates": date_key, "limit": 50},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    matches = [
        parse_match(event)
        for event in payload.get("events") or []
    ]
    matches.sort(key=_scoreboard_sort_key)
    _cache[date_key] = (now, matches)
    return matches


def find_next_matches(
    after: date,
    max_days: int = 14,
) -> tuple[date | None, list[dict[str, Any]]]:
    for offset in range(1, max_days + 1):
        candidate = after + timedelta(days=offset)
        matches = fetch_scoreboard(candidate)
        if matches:
            return candidate, matches
    return None, []


def scoreboard_snapshot(
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    yesterday = today - timedelta(days=1)

    today_matches = fetch_scoreboard(today)
    yesterday_matches = fetch_scoreboard(yesterday)

    upcoming_date = None
    upcoming_matches: list[dict[str, Any]] = []
    if not today_matches:
        upcoming_date, upcoming_matches = find_next_matches(today)

    has_live = any(match.get("status_state") == "in" for match in today_matches)

    return {
        "today": today,
        "yesterday": yesterday,
        "today_games": today_matches,
        "yesterday_games": yesterday_matches,
        "upcoming_date": upcoming_date,
        "upcoming_games": upcoming_matches,
        "has_live": has_live,
    }


def strip_initial_page(
    strip_matches: list[dict[str, Any]],
    match_id: str,
) -> int:
    for index, match in enumerate(strip_matches):
        if str(match.get("id")) == str(match_id):
            return (index + 1) // STRIP_CARDS_PER_PAGE
    return 0


def _format_american_odds(value: Any) -> str | None:
    if value is None:
        return None
    try:
        odds = int(value)
    except (TypeError, ValueError):
        return None
    return f"+{odds}" if odds > 0 else str(odds)


def _parse_last_five(last_five_games: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in last_five_games or []:
        team = block.get("team") or {}
        games = []
        for event in block.get("events") or []:
            opponent = event.get("opponent") or {}
            games.append({
                "result": event.get("gameResult"),
                "score": event.get("score"),
                "opponent_abbr": opponent.get("abbreviation"),
                "competition": event.get("competitionName"),
                "date": event.get("gameDate"),
            })
        games.sort(key=lambda game: game.get("date") or "", reverse=True)
        blocks.append({
            "abbr": team.get("abbreviation", ""),
            "name": team.get("displayName", ""),
            "logo": team.get("logo"),
            "games": games,
        })
    return blocks


def _parse_head_to_head(head_to_head: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in head_to_head or []:
        team = block.get("team") or {}
        games = []
        for event in block.get("events") or []:
            opponent = event.get("opponent") or {}
            games.append({
                "result": event.get("gameResult"),
                "score": event.get("score"),
                "opponent_abbr": opponent.get("abbreviation"),
                "competition": event.get("competitionName"),
                "date": event.get("gameDate"),
            })
        blocks.append({
            "abbr": team.get("abbreviation", ""),
            "name": team.get("displayName", ""),
            "logo": team.get("logo"),
            "games": games,
        })
    return blocks


_MATCH_TEAM_STAT_SPECS: list[tuple[str, str, bool]] = [
    ("possessionPct", "Possession", False),
    ("totalShots", "Shots", False),
    ("shotsOnTarget", "Shots on Target", False),
    ("wonCorners", "Corners", False),
    ("accuratePasses", "Accurate Passes", False),
    ("foulsCommitted", "Fouls", True),
    ("yellowCards", "Yellow Cards", True),
    ("redCards", "Red Cards", True),
    ("saves", "Saves", False),
    ("offsides", "Offsides", True),
]

_TOURNAMENT_TEAM_STAT_SPECS: list[tuple[str, str, bool]] = [
    ("totalGoals", "Goals", False),
    ("goalAssists", "Assists", False),
    ("goalsConceded", "Goals Conceded", True),
    ("groupPts", "Points", False),
]

_TIMELINE_SKIP_TYPES = frozenset({
    "start delay",
    "end delay",
})


def _apply_standings_pts_to_team_box(
    team_box: list[dict[str, Any]],
    standings: list[dict[str, Any]] | None,
) -> None:
    pts_by_abbr: dict[str, Any] = {}
    for group in standings or []:
        for team in group.get("teams") or []:
            abbr = team.get("abbr")
            if abbr:
                pts_by_abbr[abbr] = team.get("pts")
    for box in team_box:
        abbr = box.get("abbr")
        if abbr in pts_by_abbr:
            box["groupPts"] = pts_by_abbr[abbr]


def _stats_map(statistics: list[dict[str, Any]] | None) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for stat in statistics or []:
        name = stat.get("name")
        if not name:
            continue
        mapped[name] = stat.get("displayValue")
        if stat.get("value") is not None:
            mapped[f"{name}__value"] = stat.get("value")
    return mapped


def _parse_team_box_side(
    team_block: dict[str, Any],
    *,
    home_away: str,
    specs: list[tuple[str, str, bool]],
) -> dict[str, Any]:
    team = team_block.get("team") or {}
    stats = _stats_map(team_block.get("statistics"))
    parsed: dict[str, Any] = {
        "home_away": home_away,
        "abbr": team.get("abbreviation", ""),
        "name": team.get("displayName", ""),
        "logo": _team_logo(team),
    }
    for key, label, lower_is_better in specs:
        parsed[key] = stats.get(key)
        parsed[f"{key}__label"] = label
        parsed[f"{key}__lower_is_better"] = lower_is_better
    return parsed


def _parse_team_box(
    teams: list[dict[str, Any]] | None,
    *,
    away_id: str,
    home_id: str,
    specs: list[tuple[str, str, bool]],
) -> list[dict[str, Any]]:
    away_box = home_box = None
    for team_block in teams or []:
        team = team_block.get("team") or {}
        team_id = str(team.get("id") or "")
        if team_id == away_id:
            away_box = _parse_team_box_side(team_block, home_away="away", specs=specs)
        elif team_id == home_id:
            home_box = _parse_team_box_side(team_block, home_away="home", specs=specs)
    boxes: list[dict[str, Any]] = []
    if away_box:
        boxes.append(away_box)
    if home_box:
        boxes.append(home_box)
    return boxes


def _parse_form_events(form_blocks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in form_blocks or []:
        team = block.get("team") or {}
        games = []
        for event in block.get("events") or []:
            opponent = event.get("opponent") or {}
            games.append({
                "date": event.get("gameDate"),
                "score": event.get("score"),
                "at_vs": event.get("atVs"),
                "opponent_abbr": opponent.get("abbreviation"),
                "opponent_name": opponent.get("displayName"),
                "competition": event.get("competitionName"),
            })
        blocks.append({
            "abbr": team.get("abbreviation", ""),
            "name": team.get("displayName", ""),
            "logo": _team_logo(team),
            "games": games,
        })
    return blocks


def _parse_roster_player(entry: dict[str, Any]) -> dict[str, Any] | None:
    athlete = entry.get("athlete") or {}
    if not athlete.get("displayName") and not athlete.get("fullName"):
        return None
    position = entry.get("position") or {}
    if isinstance(position, dict):
        pos_label = position.get("abbreviation") or position.get("name") or ""
    else:
        pos_label = str(position) if position else ""
    stats = _stats_map(entry.get("stats"))
    headshot = athlete.get("headshot") or {}
    return {
        "id": athlete.get("id"),
        "name": athlete.get("displayName") or athlete.get("fullName"),
        "short_name": athlete.get("shortName"),
        "jersey": entry.get("jersey"),
        "position": pos_label,
        "starter": bool(entry.get("starter")),
        "subbed_in": entry.get("subbedIn"),
        "subbed_out": entry.get("subbedOut"),
        "headshot": headshot.get("href") if isinstance(headshot, dict) else None,
        "goals": stats.get("totalGoals", "0"),
        "assists": stats.get("goalAssists", "0"),
        "yellow_cards": stats.get("yellowCards", "0"),
        "red_cards": stats.get("redCards", "0"),
        "shots": stats.get("totalShots", "0"),
        "saves": stats.get("saves"),
    }


_ROSTER_SECTION_SPECS = (
    ("goalkeepers", "Goalkeepers"),
    ("defenders", "Defenders"),
    ("midfielders", "Midfielders"),
    ("forwards", "Forwards"),
    ("substitutes", "Substitutes"),
)
_SQUAD_SECTION_SPECS = _ROSTER_SECTION_SPECS[:4]


def _roster_position_group(position: Any) -> str:
    if isinstance(position, dict):
        abbr = (position.get("abbreviation") or "").upper()
        name = (position.get("name") or position.get("displayName") or "").lower()
    else:
        abbr = str(position or "").upper()
        name = abbr.lower()
    if abbr == "SUB" or "substitute" in name:
        return "substitutes"
    if abbr == "G" or "goalkeeper" in name:
        return "goalkeepers"
    if (
        "defender" in name
        or abbr in {"CD", "CD-L", "CD-R", "LB", "RB", "CB"}
        or "back" in name
    ):
        return "defenders"
    if (
        "forward" in name
        or "striker" in name
        or abbr in {"FW", "CF", "ST"}
        or (abbr.startswith("F") and abbr != "SUB")
    ):
        return "forwards"
    if "midfield" in name or abbr.startswith("M") or abbr in {"CM", "DM", "AM", "LM", "RM"}:
        return "midfielders"
    return "midfielders"


def _roster_player_sort_key(player: dict[str, Any]) -> tuple[int, int, str]:
    jersey = player.get("jersey")
    if jersey is not None and str(jersey).isdigit():
        return (0, int(jersey), player.get("name") or "")
    return (1, 999, player.get("name") or "")


def _parse_roster_side_sections(block: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {
        key: [] for key, _ in _ROSTER_SECTION_SPECS
    }
    for entry in block.get("roster") or []:
        if not isinstance(entry, dict):
            continue
        player = _parse_roster_player(entry)
        if not player:
            continue
        section_key = _roster_position_group(entry.get("position"))
        grouped[section_key].append(
            {
                "id": player["id"],
                "name": player["name"],
                "jersey": player["jersey"],
                "position": player["position"],
                "headshot": player["headshot"],
                "filter": section_key.rstrip("s")
                if section_key != "substitutes"
                else "substitute",
            }
        )
    sections = []
    for key, title in _ROSTER_SECTION_SPECS:
        players = grouped.get(key) or []
        if not players:
            continue
        players.sort(key=_roster_player_sort_key)
        sections.append({"id": key, "title": title, "players": players})
    team = block.get("team") or {}
    return {
        "abbr": team.get("abbreviation", ""),
        "name": team.get("displayName", ""),
        "logo": _team_logo(team),
        "formation": block.get("formation"),
        "sections": sections,
    }


def _squad_position_group(position: Any) -> str:
    if isinstance(position, dict):
        abbr = (position.get("abbreviation") or "").upper()
        name = (position.get("name") or position.get("displayName") or "").lower()
    else:
        abbr = str(position or "").upper()
        name = abbr.lower()
    if abbr == "G" or "goalkeeper" in name:
        return "goalkeepers"
    if abbr == "D" or "defender" in name:
        return "defenders"
    if abbr == "F" or "forward" in name:
        return "forwards"
    if abbr == "M" or "midfield" in name:
        return "midfielders"
    return "midfielders"


def _parse_squad_athlete(athlete: dict[str, Any]) -> dict[str, Any] | None:
    if not athlete.get("displayName") and not athlete.get("fullName"):
        return None
    position = athlete.get("position") or {}
    if isinstance(position, dict):
        pos_label = position.get("abbreviation") or position.get("name") or ""
    else:
        pos_label = str(position) if position else ""
    section_key = _squad_position_group(position)
    headshot = athlete.get("headshot") or {}
    headshot_url = headshot.get("href") if isinstance(headshot, dict) else None
    return {
        "id": athlete.get("id"),
        "name": athlete.get("displayName") or athlete.get("fullName"),
        "jersey": athlete.get("jersey"),
        "position": pos_label,
        "headshot": headshot_url,
        "filter": section_key.rstrip("s"),
    }


def _iter_squad_athletes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    athletes: list[dict[str, Any]] = []
    for entry in payload.get("athletes") or []:
        if not isinstance(entry, dict):
            continue
        items = entry.get("items")
        if items:
            athletes.extend(item for item in items if isinstance(item, dict))
        else:
            athletes.append(entry)
    return athletes


def _parse_team_squad_roster_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    grouped: dict[str, list[dict[str, Any]]] = {
        key: [] for key, _ in _SQUAD_SECTION_SPECS
    }
    for athlete in _iter_squad_athletes(payload):
        player = _parse_squad_athlete(athlete)
        if not player:
            continue
        section_key = _squad_position_group(athlete.get("position"))
        grouped[section_key].append(player)

    sections = []
    for key, title in _SQUAD_SECTION_SPECS:
        players = grouped.get(key) or []
        if not players:
            continue
        players.sort(key=_roster_player_sort_key)
        sections.append({"id": key, "title": title, "players": players})
    if not sections:
        return None

    team = payload.get("team") or {}
    return {
        "abbr": team.get("abbreviation", ""),
        "name": team.get("displayName", ""),
        "logo": _team_logo(team),
        "sections": sections,
    }


def fetch_team_squad_roster(
    team_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    team_id = str(team_id)
    now = time.time()
    cached = _team_roster_cache.get(team_id)
    if not force_refresh and cached and now - cached[0] < ROSTER_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            ESPN_TEAM_ROSTER_URL.format(team_id=team_id),
            timeout=15,
        )
        response.raise_for_status()
    except (requests.RequestException, ValueError):
        return None

    roster = _parse_team_squad_roster_payload(response.json())
    if roster:
        _team_roster_cache[team_id] = (now, roster)
    return roster


def attach_preview_rosters(match: dict[str, Any]) -> None:
    """Attach full tournament squad rosters for pre-match preview."""
    if match.get("status_state") != "pre":
        return

    preview = match.setdefault("preview", {})
    existing = preview.get("rosters") or {}
    if existing.get("away") or existing.get("home"):
        return

    away_id = str((match.get("away") or {}).get("id") or "")
    home_id = str((match.get("home") or {}).get("id") or "")
    if not away_id or not home_id:
        return

    with ThreadPoolExecutor(max_workers=2) as executor:
        away_future = executor.submit(fetch_team_squad_roster, away_id)
        home_future = executor.submit(fetch_team_squad_roster, home_id)
        away_roster = away_future.result()
        home_roster = home_future.result()

    if not away_roster and not home_roster:
        return

    preview["rosters"] = {
        "away": away_roster,
        "home": home_roster,
    }


def _parse_match_rosters(
    rosters: list[dict[str, Any]] | None,
    *,
    away_id: str,
    home_id: str,
) -> dict[str, Any] | None:
    away_roster = home_roster = None
    for block in rosters or []:
        team = block.get("team") or {}
        team_id = str(team.get("id") or "")
        parsed = _parse_roster_side_sections(block)
        if team_id == away_id:
            away_roster = parsed
        elif team_id == home_id:
            home_roster = parsed
    if not away_roster and not home_roster:
        return None
    if away_roster and not away_roster.get("sections"):
        away_roster = None
    if home_roster and not home_roster.get("sections"):
        home_roster = None
    if not away_roster and not home_roster:
        return None
    return {
        "away": away_roster,
        "home": home_roster,
    }


def _parse_roster_side(block: dict[str, Any]) -> dict[str, Any]:
    players = []
    for entry in block.get("roster") or []:
        if not isinstance(entry, dict):
            continue
        player = _parse_roster_player(entry)
        if player:
            players.append(player)
    starters = [player for player in players if player.get("starter")]
    substitutes = [player for player in players if not player.get("starter")]
    return {
        "formation": block.get("formation"),
        "starters": starters,
        "substitutes": substitutes,
        "players": players,
    }


def _parse_lineups(
    rosters: list[dict[str, Any]] | None,
    *,
    away_id: str,
    home_id: str,
) -> dict[str, Any] | None:
    away_lineup = home_lineup = None
    for block in rosters or []:
        team = block.get("team") or {}
        team_id = str(team.get("id") or "")
        parsed = _parse_roster_side(block)
        parsed["abbr"] = team.get("abbreviation", "")
        parsed["name"] = team.get("displayName", "")
        parsed["logo"] = _team_logo(team)
        if team_id == away_id:
            away_lineup = parsed
        elif team_id == home_id:
            home_lineup = parsed
    if not away_lineup and not home_lineup:
        return None
    if away_lineup and not away_lineup.get("players"):
        away_lineup = None
    if home_lineup and not home_lineup.get("players"):
        home_lineup = None
    if not away_lineup and not home_lineup:
        return None
    return {
        "away": away_lineup,
        "home": home_lineup,
    }


def _parse_leaders_blocks(
    leaders: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in leaders or []:
        team = block.get("team") or {}
        categories = []
        for category in block.get("leaders") or []:
            entries = category.get("leaders") or []
            if not entries:
                continue
            leader = entries[0]
            athlete = leader.get("athlete") or {}
            categories.append({
                "category": category.get("displayName") or category.get("name"),
                "player": athlete.get("displayName") or athlete.get("fullName"),
                "player_id": athlete.get("id"),
                "value": leader.get("displayValue") or leader.get("value"),
            })
        if categories:
            blocks.append({
                "abbr": team.get("abbreviation", ""),
                "name": team.get("displayName", ""),
                "logo": _team_logo(team),
                "color": _team_color(team) or "#1a2332",
                "categories": categories,
            })
    return blocks


def _event_side(team: dict[str, Any] | None, away_id: str, home_id: str) -> str | None:
    if not team:
        return None
    team_id = str(team.get("id") or "")
    if team_id == away_id:
        return "away"
    if team_id == home_id:
        return "home"
    return None


def _parse_key_events(
    events: list[dict[str, Any]] | None,
    *,
    away_id: str,
    home_id: str,
) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for event in events or []:
        event_type = (event.get("type") or {}).get("text") or ""
        if event_type.lower() in _TIMELINE_SKIP_TYPES:
            continue
        team = event.get("team") or {}
        participants = []
        for participant in event.get("participants") or []:
            athlete = participant.get("athlete") or {}
            name = athlete.get("displayName") or athlete.get("fullName")
            if name:
                participants.append(name)
        parsed.append({
            "type": event_type,
            "type_id": (event.get("type") or {}).get("type"),
            "clock": (event.get("clock") or {}).get("displayValue"),
            "text": event.get("text"),
            "side": _event_side(team, away_id, home_id),
            "participants": participants,
            "scoring": "goal" in event_type.lower(),
            "card": "card" in event_type.lower(),
            "substitution": event_type.lower() == "substitution",
        })
    return parsed


def _parse_commentary(
    commentary: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in commentary or []:
        text = entry.get("text")
        if not text:
            continue
        clock = entry.get("time") or entry.get("clock") or {}
        items.append({
            "clock": clock.get("displayValue") if isinstance(clock, dict) else str(clock),
            "text": text,
            "type": (entry.get("type") or {}).get("text"),
        })
    return items


def _parse_group_name(comp: dict[str, Any]) -> str | None:
    groups = comp.get("groups") or {}
    if isinstance(groups, dict):
        return groups.get("name") or groups.get("abbreviation")
    if isinstance(groups, list) and groups:
        first = groups[0]
        if isinstance(first, dict):
            return first.get("name") or first.get("abbreviation")
    return None


def _parse_officials(game_info: dict[str, Any]) -> list[dict[str, str]]:
    officials: list[dict[str, str]] = []
    for official in game_info.get("officials") or []:
        name = official.get("displayName") or official.get("shortDisplayName")
        if not name:
            continue
        position = (official.get("position") or {}).get("name") or "Official"
        officials.append({"name": name, "role": position})
    return officials


def _competition_notes(comp: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for note in comp.get("notes") or []:
        if not isinstance(note, dict):
            continue
        text = note.get("text") or note.get("headline")
        if text and text not in notes:
            notes.append(text)
    return notes


def _entry_logo(entry: dict[str, Any], team: dict[str, Any] | None = None) -> str | None:
    logo = entry.get("logo")
    if isinstance(logo, list) and logo:
        href = logo[0].get("href") if isinstance(logo[0], dict) else None
        if href:
            return href
    if isinstance(logo, str):
        return logo
    return _team_logo(team or {})


def _abbr_from_logo_href(href: str | None) -> str:
    if not href:
        return ""
    basename = href.rsplit("/", 1)[-1]
    code = basename.split(".", 1)[0]
    return code.upper() if code else ""


def _parse_standings_entry(entry: dict[str, Any]) -> dict[str, Any]:
    team_field = entry.get("team")
    if isinstance(team_field, dict):
        team = team_field
        team_id = team.get("id")
        name = team.get("displayName") or team.get("name") or ""
        abbr = team.get("abbreviation") or ""
        logo = _entry_logo(entry, team)
        color = _team_color(team)
    elif isinstance(team_field, str):
        team_id = entry.get("id")
        name = team_field
        logo = _entry_logo(entry, {})
        abbr = _abbr_from_logo_href(logo)
        color = None
    else:
        team_id = entry.get("id")
        name = abbr = ""
        logo = _entry_logo(entry, {})
        color = None

    stats = {
        stat.get("abbreviation"): stat.get("displayValue")
        for stat in entry.get("stats") or []
        if isinstance(stat, dict) and stat.get("abbreviation")
    }
    wins = stats.get("W")
    draws = stats.get("D")
    losses = stats.get("L")
    return {
        "id": team_id,
        "abbr": abbr,
        "name": name,
        "logo": logo,
        "color": color,
        "gp": stats.get("GP"),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "gd": stats.get("GD"),
        "pts": stats.get("P"),
        "record": stats.get("Total") or (
            f"{wins or '0'}-{draws or '0'}-{losses or '0'}"
            if wins is not None or draws is not None or losses is not None
            else None
        ),
        "pct": stats.get("PPG"),
    }


def _standings_pts_value(team: dict[str, Any]) -> int:
    pts = team.get("pts")
    try:
        return int(pts)
    except (TypeError, ValueError):
        return 0


def _standings_gd_value(team: dict[str, Any]) -> int:
    gd = team.get("gd")
    if gd in (None, ""):
        return 0
    try:
        return int(str(gd).replace("+", ""))
    except (TypeError, ValueError):
        return 0


def _sort_standings_teams(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        teams,
        key=lambda team: (
            -_standings_pts_value(team),
            -_standings_gd_value(team),
            team.get("name") or "",
        ),
    )


def _parse_group_standings_from_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    standings_root = payload.get("standings") or {}
    groups: list[dict[str, Any]] = []
    for group in standings_root.get("groups") or []:
        header = group.get("header")
        if isinstance(header, str):
            group_name = header
        elif isinstance(header, dict):
            group_name = header.get("title") or header.get("name") or "Group"
        else:
            group_name = group.get("name") or group.get("abbreviation") or "Group"
        entries_block = group.get("standings") or {}
        if not isinstance(entries_block, dict):
            entries_block = {}
        entries = entries_block.get("entries") or []
        teams = _sort_standings_teams([
            _parse_standings_entry(entry)
            for entry in entries
            if isinstance(entry, dict)
        ])
        groups.append({
            "name": group_name,
            "teams": teams,
        })
    return groups


def _event_from_summary(payload: dict[str, Any]) -> dict[str, Any]:
    header = payload.get("header") or {}
    comp = (header.get("competitions") or [{}])[0]
    away_abbr = home_abbr = ""
    for competitor in comp.get("competitors") or []:
        abbr = (competitor.get("team") or {}).get("abbreviation", "")
        if competitor.get("homeAway") == "home":
            home_abbr = abbr
        else:
            away_abbr = abbr
    short_name = f"{away_abbr} @ {home_abbr}" if away_abbr and home_abbr else ""
    return {
        "id": header.get("id"),
        "date": comp.get("date"),
        "shortName": short_name,
        "name": short_name,
        "competitions": [comp],
        "status": comp.get("status") or {},
    }


def parse_match_detail(payload: dict[str, Any]) -> dict[str, Any]:
    match = parse_match(_event_from_summary(payload))
    comp = (payload.get("header") or {}).get("competitions", [{}])[0]

    for competitor in comp.get("competitors") or []:
        record = _team_record(competitor.get("record"))
        if competitor.get("homeAway") == "home":
            match["home"]["record"] = record
        else:
            match["away"]["record"] = record

    game_info = payload.get("gameInfo") or {}
    venue = game_info.get("venue") or {}
    venue_images = venue.get("images") or []
    venue_image = None
    if venue_images:
        first_image = venue_images[0]
        if isinstance(first_image, dict):
            venue_image = first_image.get("href")
        elif isinstance(first_image, str):
            venue_image = first_image

    pickcenter = payload.get("pickcenter") or [{}]
    pick = pickcenter[0] if pickcenter else {}
    if not isinstance(pick, dict):
        pick = {}
    away_odds = pick.get("awayTeamOdds") or {}
    home_odds = pick.get("homeTeamOdds") or {}
    draw_odds = pick.get("drawOdds") or {}

    broadcasts = []
    for item in payload.get("broadcasts") or []:
        media = item.get("media") or {}
        name = media.get("shortName") or media.get("name") or item.get("station")
        if name and name not in broadcasts:
            broadcasts.append(name)

    match["preview"] = {
        "venue": venue.get("fullName"),
        "venue_city": (venue.get("address") or {}).get("city"),
        "venue_state": (venue.get("address") or {}).get("state"),
        "venue_country": (venue.get("address") or {}).get("country"),
        "venue_image": venue_image,
        "spread": pick.get("spread"),
        "over_under": pick.get("overUnder"),
        "away_moneyline": _format_american_odds(away_odds.get("moneyLine")),
        "home_moneyline": _format_american_odds(home_odds.get("moneyLine")),
        "draw_moneyline": _format_american_odds(draw_odds.get("moneyLine")),
        "last_five": _parse_last_five(payload.get("lastFiveGames")),
        "head_to_head": _parse_head_to_head(payload.get("headToHeadGames")),
        "group_standings": _parse_group_standings_from_summary(payload),
        "broadcasts": broadcasts,
        "group_name": _parse_group_name(comp),
        "officials": _parse_officials(game_info),
        "attendance": game_info.get("attendance"),
        "notes": _competition_notes(comp),
        "recent_form": _parse_form_events((payload.get("boxscore") or {}).get("form")),
        "tournament_leaders": _parse_leaders_blocks(payload.get("leaders")),
    }

    away_id = str((match.get("away") or {}).get("id") or "")
    home_id = str((match.get("home") or {}).get("id") or "")
    boxscore = payload.get("boxscore") or {}
    status_state = match.get("status_state")
    is_pre = status_state == "pre"

    match_stats = _parse_team_box(
        boxscore.get("teams"),
        away_id=away_id,
        home_id=home_id,
        specs=_TOURNAMENT_TEAM_STAT_SPECS if is_pre else _MATCH_TEAM_STAT_SPECS,
    )
    roster_blocks = payload.get("rosters")
    lineups = _parse_lineups(roster_blocks, away_id=away_id, home_id=home_id)
    match_rosters = _parse_match_rosters(roster_blocks, away_id=away_id, home_id=home_id)
    key_events = _parse_key_events(
        payload.get("keyEvents"),
        away_id=away_id,
        home_id=home_id,
    )
    commentary = _parse_commentary(payload.get("commentary"))

    if is_pre:
        group_standings = match["preview"]["group_standings"]
        _apply_standings_pts_to_team_box(match_stats, group_standings)
        match["preview"]["tournament_stats"] = match_stats
    else:
        match["live"] = {
            "team_box": match_stats,
            "lineups": lineups,
            "leaders": _parse_leaders_blocks(payload.get("leaders")),
            "key_events": key_events,
            "commentary": commentary,
            "scoring_events": [event for event in key_events if event.get("scoring")],
        }

    if is_pre:
        match["preview"]["rosters"] = match_rosters

    article = payload.get("article") or {}
    if article.get("headline"):
        links = article.get("links") or {}
        web = links.get("web") or {}
        recap = {
            "headline": article.get("headline"),
            "description": article.get("description"),
            "link": web.get("href"),
        }
        if is_pre:
            match["preview"]["article"] = recap
        else:
            match.setdefault("live", {})["article"] = recap

    return match


def fetch_match_summary(
    match_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    now = time.time()
    cached = _summary_cache.get(match_id)
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    response = requests.get(
        ESPN_SUMMARY_URL,
        params={"event": match_id},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("header"):
        raise ValueError(f"No summary for match {match_id}")

    detail = parse_match_detail(payload)
    attach_preview_rosters(detail)
    _summary_cache[match_id] = (now, detail)
    return detail


def parse_standings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for child in payload.get("children") or []:
        standings = child.get("standings") or {}
        entries = standings.get("entries") or []
        groups.append({
            "name": child.get("name") or child.get("abbreviation") or "Group",
            "abbr": child.get("abbreviation"),
            "teams": _sort_standings_teams([
                _parse_standings_entry(entry) for entry in entries
            ]),
        })
    return groups


def fetch_standings(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    global _standings_cache
    now = time.time()
    if (
        not force_refresh
        and _standings_cache
        and now - _standings_cache[0] < CACHE_TTL_SECONDS
    ):
        return _standings_cache[1]

    response = requests.get(ESPN_STANDINGS_URL, timeout=15)
    response.raise_for_status()
    groups = parse_standings(response.json())
    _standings_cache = (now, groups)
    return groups
