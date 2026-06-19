"""ESPN FIFA World Cup scoreboard client."""

from __future__ import annotations

import time
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

CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}
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


def _team_color(team: dict[str, Any]) -> str | None:
    return _normalize_hex(team.get("color"))


def _team_alternate_color(team: dict[str, Any]) -> str | None:
    alternate = _normalize_hex(team.get("alternateColor"))
    if alternate in _WIN_COLOR_SKIP:
        return None
    return alternate


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

    away_win = away.get("color") or (away_candidates[0] if away_candidates else "#56b6c6")
    home_win = home.get("color") or (home_candidates[0] if home_candidates else "#22a06b")

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
            })
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
            "games": games,
        })
    return blocks


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
        teams = [
            _parse_standings_entry(entry)
            for entry in entries
            if isinstance(entry, dict)
        ]
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
    }
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
            "teams": [_parse_standings_entry(entry) for entry in entries],
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
