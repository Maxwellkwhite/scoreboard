"""ESPN MLB scoreboard client (pattern from ha-teamtracker)."""

from __future__ import annotations

import re
import time
import unicodedata
from datetime import date, timedelta
from typing import Any

import requests
from markupsafe import Markup, escape

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
)
ESPN_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary"
)
ESPN_STANDINGS_URL = (
    "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings"
)
ESPN_TEAMS_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams"
)
ESPN_TEAM_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_id}"
)
ESPN_ATHLETE_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}"
)
CACHE_TTL_SECONDS = 30
TEAMS_CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_standings_cache: tuple[float, list[dict[str, Any]]] | None = None
_teams_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
_athlete_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_team_detail_cache: dict[str, tuple[float, dict[str, Any]]] = {}


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


def _athlete_id(athlete: dict[str, Any] | None) -> str | None:
    if not athlete:
        return None
    player_id = athlete.get("id")
    return str(player_id) if player_id else None


_WIN_COLOR_MIN_DISTANCE = 45.0
_WIN_COLOR_SKIP = {"#000000", "#ffffff"}


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

    best_distance = -1.0
    for away_option in away_candidates or [away_win]:
        for home_option in home_candidates or [home_win]:
            distance = _color_distance(away_option, home_option)
            if distance > best_distance:
                best_distance = distance
                away_win = away_option
                home_win = home_option

    away["win_color"] = away_win
    home["win_color"] = home_win


def _is_between_innings(status_detail: str | None) -> bool:
    if not status_detail:
        return False
    return bool(re.search(r"\b(mid|middle|end)\b", status_detail.strip().lower()))


def _batting_side_from_status(status_detail: str | None) -> str | None:
    if not status_detail:
        return None
    detail = status_detail.strip().lower()
    if re.search(r"\b(top)\b", detail):
        return "away"
    if re.search(r"\b(bot|bottom)\b", detail):
        return "home"
    if re.search(r"\b(mid|middle)\b", detail):
        return "home"
    if re.search(r"\bend\b", detail):
        # "End 5th" (top half done) — away just batted; explicit half wins when present.
        if re.search(r"\b(bot|bottom)\b", detail):
            return "home"
        return "away"
    return None


def _batting_side_from_situation(
    situation: dict[str, Any] | None,
    away: dict[str, Any] | None,
    home: dict[str, Any] | None,
) -> str | None:
    situation = situation or {}

    def side_for_team_id(team_id: Any) -> str | None:
        if not team_id:
            return None
        team_id = str(team_id)
        if away and str(away.get("id")) == team_id:
            return "away"
        if home and str(home.get("id")) == team_id:
            return "home"
        return None

    batter = situation.get("batter") or {}
    side = side_for_team_id((batter.get("athlete") or {}).get("team", {}).get("id"))
    if side:
        return side

    due_up = situation.get("dueUp") or []
    if due_up:
        side = side_for_team_id((due_up[0].get("athlete") or {}).get("team", {}).get("id"))
        if side:
            return side

    return None


def _resolve_batting_side(
    situation: dict[str, Any] | None,
    away: dict[str, Any] | None,
    home: dict[str, Any] | None,
    status_detail: str | None,
) -> str | None:
    # Between innings, ESPN summary often clears the batter while status still
    # reflects the half; prefer status so detail matches the scoreboard card.
    if _is_between_innings(status_detail):
        status_side = _batting_side_from_status(status_detail)
        if status_side:
            return status_side
    side = _batting_side_from_situation(situation, away, home)
    if side:
        return side
    return _batting_side_from_status(status_detail)


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
        "probable_pitcher": _parse_probable(competitor),
    }


def parse_game(event: dict[str, Any]) -> dict[str, Any]:
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
    situation = comp.get("situation") or {}
    game_id = event.get("id")

    if away and home:
        _resolve_win_colors(away, home)

    status_detail = (
        status_type.get("shortDetail")
        or status_type.get("detail")
        or status_type.get("description", "")
    )
    batting_side = _resolve_batting_side(situation, away, home, status_detail)

    return {
        "id": str(game_id) if game_id is not None else None,
        "name": event.get("shortName") or event.get("name", ""),
        "start_time": event.get("date"),
        "status_state": status_type.get("state", "pre"),
        "status_detail": status_detail,
        "batting_side": batting_side,
        "away": away,
        "home": home,
        "inning": situation.get("inning"),
        "balls": situation.get("balls"),
        "strikes": situation.get("strikes"),
        "outs": situation.get("outs"),
        "on_first": situation.get("onFirst"),
        "on_second": situation.get("onSecond"),
        "on_third": situation.get("onThird"),
        "espn_link": f"https://www.espn.com/mlb/game/_/gameId/{game_id}",
    }


STRIP_CARDS_PER_PAGE = 4

_STATUS_SORT_ORDER = {"in": 0, "pre": 1, "post": 2}


def strip_initial_page(
    strip_games: list[dict[str, Any]],
    game_id: str,
) -> int:
    """Carousel page for game detail strip (card 0 is the scoreboard link)."""
    for index, game in enumerate(strip_games):
        if str(game.get("id")) == str(game_id):
            return (index + 1) // STRIP_CARDS_PER_PAGE
    return 0


def _scoreboard_sort_key(game: dict[str, Any]) -> tuple[int, str]:
    state = game.get("status_state", "pre")
    priority = _STATUS_SORT_ORDER.get(state, 1)
    return priority, game.get("start_time") or ""


def fetch_scoreboard(
    game_date: date,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Return normalized games for a calendar day (ESPN dates=YYYYMMDD)."""
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
    games = [parse_game(event) for event in payload.get("events", [])]
    games.sort(key=_scoreboard_sort_key)

    _cache[date_key] = (now, games)
    return games


def find_next_games(
    after: date,
    max_days: int = 7,
) -> tuple[date | None, list[dict[str, Any]]]:
    """First future day with at least one scheduled game."""
    for offset in range(1, max_days + 1):
        candidate = after + timedelta(days=offset)
        games = fetch_scoreboard(candidate)
        if games:
            return candidate, games
    return None, []


def _team_record(records: list[dict[str, Any]] | dict[str, Any] | None) -> str | None:
    if not records:
        return None
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


def _probable_stat_categories(statistics: Any) -> list[dict[str, Any]]:
    if isinstance(statistics, dict):
        splits = statistics.get("splits")
        if isinstance(splits, dict):
            categories = splits.get("categories") or []
            return categories if isinstance(categories, list) else []
        if isinstance(splits, list):
            categories: list[dict[str, Any]] = []
            for split in splits:
                if not isinstance(split, dict):
                    continue
                split_categories = split.get("categories") or []
                if isinstance(split_categories, list):
                    categories.extend(split_categories)
            return categories
        categories = statistics.get("categories") or []
        return categories if isinstance(categories, list) else []
    if isinstance(statistics, list):
        categories: list[dict[str, Any]] = []
        for entry in statistics:
            if not isinstance(entry, dict):
                continue
            entry_categories = entry.get("categories") or []
            if isinstance(entry_categories, list):
                categories.extend(entry_categories)
        return categories
    return []


_SKIP_PROBABLE_STAT_KEYS = frozenset({"HT", "HEIGHT", "HGT", "H"})


def _parse_probable(competitor: dict[str, Any]) -> dict[str, Any] | None:
    for probable in competitor.get("probables") or []:
        if probable.get("name") != "probableStartingPitcher":
            continue
        athlete = probable.get("athlete") or {}
        stats: dict[str, str] = {}
        for category in _probable_stat_categories(probable.get("statistics")):
            if not isinstance(category, dict):
                continue
            key = category.get("abbreviation") or category.get("name")
            if not key:
                continue
            key_str = str(key).strip().upper()
            if key_str in _SKIP_PROBABLE_STAT_KEYS or "HEIGHT" in key_str:
                continue
            stats[str(key)] = category.get("displayValue", "")
        headshot = athlete.get("headshot") or {}
        headshot_href = headshot if isinstance(headshot, str) else headshot.get("href")
        throws = athlete.get("throws")
        throws_display = (
            throws if isinstance(throws, str)
            else (throws or {}).get("displayValue")
        )
        if throws_display and (
            str(throws_display).strip().upper() in _SKIP_PROBABLE_STAT_KEYS
            or "HEIGHT" in str(throws_display).upper()
            or "'" in str(throws_display)
        ):
            throws_display = None
        return {
            "id": _athlete_id(athlete),
            "name": athlete.get("displayName", ""),
            "headshot": headshot_href,
            "jersey": athlete.get("jersey"),
            "throws": throws_display,
            "stats": stats,
        }
    return None


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
            })
        blocks.append({
            "abbr": team.get("abbreviation", ""),
            "name": team.get("displayName", ""),
            "logo": team.get("logo"),
            "games": games,
        })
    return blocks


def _stat_display(stats: list[dict[str, Any]] | None, name: str) -> str | None:
    for stat in stats or []:
        if stat.get("name") == name:
            return stat.get("displayValue")
    return None


def _linescore_side(competitor: dict[str, Any]) -> dict[str, Any]:
    innings = []
    total_hits = 0
    total_errors = 0
    for inning in competitor.get("linescores") or []:
        innings.append(inning.get("displayValue", "0"))
        total_hits += inning.get("hits") or 0
        total_errors += inning.get("errors") or 0
    return {
        "innings": innings,
        "runs": _parse_score(competitor.get("score")),
        "hits": total_hits,
        "errors": total_errors,
    }


def _parse_linescore(competitors: list[dict[str, Any]]) -> dict[str, Any] | None:
    away_side = home_side = None
    away_abbr = home_abbr = ""
    for competitor in competitors:
        team = competitor.get("team") or {}
        side = _linescore_side(competitor)
        side["abbr"] = team.get("abbreviation", "")
        if competitor.get("homeAway") == "home":
            home_side = side
            home_abbr = side["abbr"]
        else:
            away_side = side
            away_abbr = side["abbr"]
    if not away_side or not home_side:
        return None

    inning_count = max(9, len(away_side["innings"]), len(home_side["innings"]))
    columns = []
    for index in range(inning_count):
        columns.append({
            "number": index + 1,
            "away": away_side["innings"][index] if index < len(away_side["innings"]) else "",
            "home": home_side["innings"][index] if index < len(home_side["innings"]) else "",
        })

    return {
        "away_abbr": away_abbr,
        "home_abbr": home_abbr,
        "columns": columns,
        "away": away_side,
        "home": home_side,
    }


def _parse_team_box(boxscore_teams: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    teams = []
    for entry in boxscore_teams or []:
        team = entry.get("team") or {}
        groups = {group.get("name"): group for group in entry.get("statistics") or []}
        batting = (groups.get("batting") or {}).get("stats") or []
        pitching = (groups.get("pitching") or {}).get("stats") or []
        teams.append({
            "abbr": team.get("abbreviation", ""),
            "home_away": entry.get("homeAway"),
            "batting_hits": _stat_display(batting, "hits"),
            "batting_runs": _stat_display(batting, "runs"),
            "batting_strikeouts": _stat_display(batting, "strikeouts"),
            "batting_walks": _stat_display(batting, "walks"),
            "pitching_hits": _stat_display(pitching, "hits"),
            "pitching_strikeouts": _stat_display(pitching, "strikeouts"),
            "pitching_walks": _stat_display(pitching, "walks"),
            "pitching_earned_runs": _stat_display(pitching, "earnedRuns"),
        })
    return teams


def _athlete_stat_map(
    keys: list[Any] | None,
    values: list[Any] | None,
) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in zip(keys or [], values or [])
        if value is not None
    }


def _pitching_decision(entry: dict[str, Any]) -> str | None:
    for note in entry.get("notes") or []:
        if note.get("type") == "pitchingDecision":
            text = (note.get("text") or "").strip()
            if text:
                return text
    return None


def _pitching_decision_role(decision: str | None) -> str | None:
    if not decision:
        return None
    lead = decision.strip()[0].upper()
    return {"W": "win", "L": "loss", "S": "save"}.get(lead)


def _pitching_decision_record(decision: str | None) -> str | None:
    if not decision or "," not in decision:
        return None
    record = decision.split(",", 1)[1].strip()
    return record or None


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _pitching_decision_record_display(
    decision: str | None,
    role: str,
) -> str | None:
    record = _pitching_decision_record(decision)
    if not record:
        return None
    if role == "save":
        try:
            return f"{_ordinal(int(record))} Save"
        except ValueError:
            return f"{record} Save"
    return record


def _parse_pitching_decisions(
    lineups: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not lineups:
        return None

    decisions: dict[str, Any] = {}
    for side in ("away", "home"):
        team_lineup = lineups.get(side) or {}
        abbr = team_lineup.get("abbr", "")
        for pitcher in team_lineup.get("pitchers") or []:
            decision_text = pitcher.get("decision")
            role = _pitching_decision_role(decision_text)
            if not role or role in decisions:
                continue
            decisions[role] = {
                "id": pitcher.get("id"),
                "name": pitcher.get("name"),
                "team_abbr": abbr,
                "side": side,
                "record": _pitching_decision_record_display(decision_text, role),
                "ip": pitcher.get("ip"),
                "hits": pitcher.get("hits"),
                "er": pitcher.get("er"),
                "bb": pitcher.get("bb"),
                "k": pitcher.get("k"),
                "season_era": pitcher.get("season_era"),
            }

    return decisions or None


def _parse_team_lineup(team_block: dict[str, Any]) -> dict[str, Any]:
    team = team_block.get("team") or {}
    lineup: dict[str, Any] = {
        "abbr": team.get("abbreviation", ""),
        "batters": [],
        "pitchers": [],
    }
    for stat_group in team_block.get("statistics") or []:
        stat_type = stat_group.get("type")
        keys = stat_group.get("keys") or []
        for entry in stat_group.get("athletes") or []:
            athlete = entry.get("athlete") or {}
            name = athlete.get("shortName") or athlete.get("displayName") or ""
            if not name:
                continue
            stats = _athlete_stat_map(keys, entry.get("stats"))
            position = (entry.get("position") or athlete.get("position") or {}).get(
                "abbreviation", ""
            )
            if stat_type == "batting":
                lineup["batters"].append({
                    "id": _athlete_id(athlete),
                    "name": name,
                    "bat_order": entry.get("batOrder"),
                    "position": position,
                    "starter": bool(entry.get("starter")),
                    "line": stats.get("hits-atBats") or "0-0",
                    "ab": stats.get("atBats") or "0",
                    "runs": stats.get("runs") or "0",
                    "hits": stats.get("hits") or "0",
                    "rbi": stats.get("RBIs") or "0",
                    "hr": stats.get("homeRuns") or "0",
                    "bb": stats.get("walks") or "0",
                    "k": stats.get("strikeouts") or "0",
                    "season_avg": stats.get("avg") or "—",
                    "season_obp": stats.get("onBasePct") or "—",
                    "season_slg": stats.get("slugAvg") or "—",
                })
            elif stat_type == "pitching":
                lineup["pitchers"].append({
                    "id": _athlete_id(athlete),
                    "name": name,
                    "starter": bool(entry.get("starter")),
                    "ip": stats.get("fullInnings.partInnings") or "—",
                    "hits": stats.get("hits") or "0",
                    "runs": stats.get("runs") or "0",
                    "er": stats.get("earnedRuns") or "0",
                    "bb": stats.get("walks") or "0",
                    "k": stats.get("strikeouts") or "0",
                    "hr": stats.get("homeRuns") or "0",
                    "season_era": stats.get("ERA") or "—",
                    "decision": _pitching_decision(entry),
                })

    lineup["batters"].sort(
        key=lambda batter: (batter.get("bat_order") if batter.get("bat_order") is not None else 99, batter["name"])
    )
    lineup["pitchers"].sort(
        key=lambda pitcher: (0 if pitcher.get("starter") else 1, pitcher["name"])
    )
    return lineup


def _parse_lineups(
    payload: dict[str, Any],
    away: dict[str, Any] | None,
    home: dict[str, Any] | None,
) -> dict[str, Any] | None:
    player_blocks = (payload.get("boxscore") or {}).get("players") or []
    if not player_blocks:
        return None

    away_id = str((away or {}).get("id") or "")
    home_id = str((home or {}).get("id") or "")
    parsed_away = parsed_home = None

    for team_block in player_blocks:
        team_id = str((team_block.get("team") or {}).get("id") or "")
        parsed = _parse_team_lineup(team_block)
        if not parsed["batters"] and not parsed["pitchers"]:
            continue
        if team_id and team_id == away_id:
            parsed_away = parsed
        elif team_id and team_id == home_id:
            parsed_home = parsed

    if not parsed_away and not parsed_home:
        return None
    return {
        "away": parsed_away or {"abbr": (away or {}).get("abbr", ""), "batters": [], "pitchers": []},
        "home": parsed_home or {"abbr": (home or {}).get("abbr", ""), "batters": [], "pitchers": []},
    }


def _preview_win_pct(live_pct: Any, projected_pct: Any) -> float | None:
    if live_pct is not None:
        return float(live_pct)
    if projected_pct is not None:
        return float(projected_pct)
    return None


def _parse_win_probability(
    entries: list[dict[str, Any]] | None,
) -> dict[str, float] | None:
    if not entries:
        return None
    latest = entries[-1]
    home_pct = latest.get("homeWinPercentage")
    if home_pct is None:
        return None
    home_pct = round(float(home_pct) * 100, 1)
    return {
        "away_pct": round(100 - home_pct, 1),
        "home_pct": home_pct,
    }


def _scoring_side_from_play(
    play: dict[str, Any],
    *,
    away_id: str,
    home_id: str,
    prev_away: int | None,
    prev_home: int | None,
    away_score: int | None,
    home_score: int | None,
) -> str | None:
    team_id = str((play.get("team") or {}).get("id") or "")
    if team_id and away_id and team_id == away_id:
        return "away"
    if team_id and home_id and team_id == home_id:
        return "home"
    if away_score is not None and prev_away is not None and away_score > prev_away:
        return "away"
    if home_score is not None and prev_home is not None and home_score > prev_home:
        return "home"
    return None


def _parse_play_item(play: dict[str, Any]) -> dict[str, Any] | None:
    text = (play.get("text") or "").strip()
    play_type = (play.get("type") or {}).get("type")
    if not text:
        return None
    if play_type == "start-batterpitcher":
        return None
    if text.startswith("Pitch ") and play_type != "end-inning":
        return None
    return {
        "text": text,
        "away_score": _parse_score(play.get("awayScore")),
        "home_score": _parse_score(play.get("homeScore")),
        "scoring": bool(play.get("scoringPlay")),
        "period": (play.get("period") or {}).get("displayValue"),
    }


def _parse_play_feed(plays: list[dict[str, Any]] | None, *, limit: int = 10) -> list[dict[str, Any]]:
    feed = []
    for play in reversed(plays or []):
        item = _parse_play_item(play)
        if not item:
            continue
        feed.append(item)
        if len(feed) >= limit:
            break
    feed.reverse()
    return feed


def _parse_plays_by_inning(
    plays: list[dict[str, Any]] | None,
    *,
    away_id: str = "",
    home_id: str = "",
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    prev_away = prev_home = None
    for play in plays or []:
        item = _parse_play_item(play)
        if not item:
            continue
        if item.get("scoring"):
            scoring_side = _scoring_side_from_play(
                play,
                away_id=away_id,
                home_id=home_id,
                prev_away=prev_away,
                prev_home=prev_home,
                away_score=item.get("away_score"),
                home_score=item.get("home_score"),
            )
            if scoring_side:
                item["scoring_side"] = scoring_side
        away_score = item.get("away_score")
        home_score = item.get("home_score")
        if away_score is not None:
            prev_away = away_score
        if home_score is not None:
            prev_home = home_score
        inning = item.pop("period") or "Game"
        if inning not in groups:
            groups[inning] = []
            order.append(inning)
        groups[inning].append(item)
    return [{"inning": inning, "plays": groups[inning]} for inning in order]


def _parse_scoring_plays(
    plays: list[dict[str, Any]] | None,
    *,
    away_id: str = "",
    home_id: str = "",
) -> list[dict[str, Any]]:
    scoring = []
    prev_away = prev_home = None
    for play in plays or []:
        away_score = _parse_score(play.get("awayScore"))
        home_score = _parse_score(play.get("homeScore"))
        if not play.get("scoringPlay"):
            if away_score is not None:
                prev_away = away_score
            if home_score is not None:
                prev_home = home_score
            continue
        text = (play.get("text") or "").strip()
        if not text:
            continue
        entry = {
            "text": text,
            "away_score": away_score,
            "home_score": home_score,
            "period": (play.get("period") or {}).get("displayValue"),
            "scoring": True,
        }
        scoring_side = _scoring_side_from_play(
            play,
            away_id=away_id,
            home_id=home_id,
            prev_away=prev_away,
            prev_home=prev_home,
            away_score=away_score,
            home_score=home_score,
        )
        if scoring_side:
            entry["scoring_side"] = scoring_side
        scoring.append(entry)
        if away_score is not None:
            prev_away = away_score
        if home_score is not None:
            prev_home = home_score
    return scoring[-10:]


def _names_from_pitch_play(text: str) -> tuple[str | None, str | None]:
    match = re.match(r"^(.+?) pitches to (.+)$", text, re.IGNORECASE)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def _add_player_name(players: dict[str, str], athlete: dict[str, Any] | None) -> None:
    if not athlete:
        return
    player_id = athlete.get("id")
    name = (
        athlete.get("displayName")
        or athlete.get("shortName")
        or athlete.get("fullName")
    )
    if player_id and name:
        players[str(player_id)] = name


def _merge_athlete_record(
    records: dict[str, dict[str, Any]],
    athlete: dict[str, Any] | None,
) -> None:
    if not athlete or not athlete.get("id"):
        return
    player_id = str(athlete["id"])
    existing = records.get(player_id, {})
    records[player_id] = {**existing, **athlete}


def _athlete_records_from_game(
    payload: dict[str, Any],
    competitors: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    for competitor in competitors or []:
        for probable in competitor.get("probables") or []:
            _merge_athlete_record(records, probable.get("athlete"))

    boxscore = payload.get("boxscore") or {}
    for team_block in boxscore.get("players") or []:
        for stat in team_block.get("statistics") or []:
            for entry in stat.get("athletes") or []:
                _merge_athlete_record(records, entry.get("athlete"))

    for roster_block in payload.get("rosters") or []:
        for entry in roster_block.get("roster") or []:
            _merge_athlete_record(records, entry.get("athlete"))

    for play in payload.get("plays") or []:
        for participant in play.get("participants") or []:
            _merge_athlete_record(records, participant.get("athlete"))

    return records


def _player_map_from_game(
    payload: dict[str, Any],
    competitors: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    records = _athlete_records_from_game(payload, competitors)
    players: dict[str, str] = {}
    for athlete in records.values():
        _add_player_name(players, athlete)
    return players


def _player_name_variants(name: str, athlete: dict[str, Any] | None = None) -> list[str]:
    variants: list[str] = []

    def add(value: str | None) -> None:
        text = (value or "").strip()
        if not text or text in variants:
            return
        variants.append(text)

    if athlete:
        add(athlete.get("displayName"))
        add(athlete.get("shortName"))
        add(athlete.get("fullName"))
        add(athlete.get("lastName"))

    add(name)

    for source in variants[:]:
        if "." in source:
            add(source.split(".")[-1].strip())
        parts = source.split()
        if len(parts) >= 2:
            add(parts[-1])

    return variants


def _player_link_entries(
    player_map: dict[str, str],
    athlete_records: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    athlete_records = athlete_records or {}
    entries: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for player_id, name in player_map.items():
        athlete = athlete_records.get(player_id)
        for variant in _player_name_variants(name, athlete):
            key = (player_id, variant)
            if key in seen:
                continue
            seen.add(key)
            entries.append(key)
    entries.sort(key=lambda item: len(item[1]), reverse=True)
    return entries


def _runner_player_id(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        player_id = value.get("playerId") or value.get("id")
        return str(player_id) if player_id else None
    return None


def _runner_name(value: Any, player_map: dict[str, str]) -> str | None:
    player_id = _runner_player_id(value)
    if not player_id:
        return None
    return player_map.get(player_id)


def _player_batting_stats_map(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    stats_map: dict[str, dict[str, str]] = {}
    for team_block in (payload.get("boxscore") or {}).get("players") or []:
        for stat_group in team_block.get("statistics") or []:
            if stat_group.get("type") != "batting":
                continue
            keys = stat_group.get("keys") or []
            for entry in stat_group.get("athletes") or []:
                athlete = entry.get("athlete") or {}
                player_id = athlete.get("id")
                if not player_id:
                    continue
                values = entry.get("stats") or []
                stats_map[str(player_id)] = {
                    str(key): str(value)
                    for key, value in zip(keys, values)
                    if value is not None
                }
    return stats_map


def _parse_due_up(
    situation: dict[str, Any],
    player_map: dict[str, str],
    batting_stats_map: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    batting_stats_map = batting_stats_map or {}
    due_up: list[dict[str, Any]] = []
    for entry in situation.get("dueUp") or []:
        athlete = entry.get("athlete") or {}
        player_id = entry.get("playerId") or athlete.get("id")
        name = None
        if player_id:
            name = player_map.get(str(player_id))
        if not name:
            name = athlete.get("shortName") or athlete.get("displayName")
        if not name:
            continue

        stats = batting_stats_map.get(str(player_id), {}) if player_id else {}
        due_up.append({
            "id": str(player_id) if player_id else None,
            "name": name,
            "bat_order": entry.get("batOrder"),
            "line": stats.get("hits-atBats") or "0-0",
            "runs": stats.get("runs") or "0",
            "hits": stats.get("hits") or "0",
            "rbi": stats.get("RBIs") or "0",
        })
    return due_up


def _parse_live_situation(
    situation: dict[str, Any] | None,
    plays: list[dict[str, Any]] | None,
    competitors: list[dict[str, Any]] | None = None,
    player_map: dict[str, str] | None = None,
    status_detail: str | None = None,
    batting_stats_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    situation = situation or {}
    notes = [
        note.get("text")
        for note in situation.get("situationNotes") or []
        if note.get("text")
    ]
    pitcher_name = batter_name = None
    matchup_text = None
    for play in reversed(plays or []):
        text = (play.get("text") or "").strip()
        if not text:
            continue
        pitcher_candidate, batter_candidate = _names_from_pitch_play(text)
        if pitcher_candidate and batter_candidate:
            pitcher_name = pitcher_candidate
            batter_name = batter_candidate
            matchup_text = text
            break
        if (play.get("type") or {}).get("type") == "start-batterpitcher":
            matchup_text = text

    players = player_map or {}
    pitcher_id = (situation.get("pitcher") or {}).get("playerId")
    batter_id = (situation.get("batter") or {}).get("playerId")
    if not pitcher_name and pitcher_id:
        pitcher_name = players.get(str(pitcher_id))
    if not batter_name and batter_id:
        batter_name = players.get(str(batter_id))

    due_up = _parse_due_up(situation, players, batting_stats_map)
    show_due_up = _is_between_innings(status_detail) and bool(due_up)
    if show_due_up:
        pitcher_name = None
        batter_name = None

    return {
        "balls": situation.get("balls"),
        "strikes": situation.get("strikes"),
        "outs": situation.get("outs"),
        "on_first": bool(situation.get("onFirst")),
        "on_second": bool(situation.get("onSecond")),
        "on_third": bool(situation.get("onThird")),
        "first_runner": _runner_name(situation.get("onFirst"), players),
        "second_runner": _runner_name(situation.get("onSecond"), players),
        "third_runner": _runner_name(situation.get("onThird"), players),
        "first_runner_id": _runner_player_id(situation.get("onFirst")),
        "second_runner_id": _runner_player_id(situation.get("onSecond")),
        "third_runner_id": _runner_player_id(situation.get("onThird")),
        "notes": notes,
        "matchup_text": matchup_text,
        "pitcher_name": pitcher_name,
        "pitcher_id": str(pitcher_id) if pitcher_id else None,
        "batter_name": batter_name,
        "batter_id": str(batter_id) if batter_id else None,
        "due_up": due_up,
        "show_due_up": show_due_up,
    }


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


def fetch_game_summary(
    game_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    now = time.time()
    cached = _summary_cache.get(game_id)
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    response = requests.get(
        ESPN_SUMMARY_URL,
        params={"event": game_id},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("header"):
        raise ValueError(f"No summary for game {game_id}")

    detail = parse_game_detail(payload)
    _summary_cache[game_id] = (now, detail)
    return detail


def parse_game_detail(payload: dict[str, Any]) -> dict[str, Any]:
    game = parse_game(_event_from_summary(payload))
    comp = (payload.get("header") or {}).get("competitions", [{}])[0]

    away_record = home_record = None
    away_probable = home_probable = None
    for competitor in comp.get("competitors") or []:
        parsed_probable = _parse_probable(competitor)
        record = _team_record(competitor.get("record"))
        if competitor.get("homeAway") == "home":
            home_record = record
            home_probable = parsed_probable
            game["home"]["record"] = record
            game["home"]["probable_pitcher"] = parsed_probable
        else:
            away_record = record
            away_probable = parsed_probable
            game["away"]["record"] = record
            game["away"]["probable_pitcher"] = parsed_probable

    game_info = payload.get("gameInfo") or {}
    venue = game_info.get("venue") or {}
    weather = game_info.get("weather") or {}
    venue_images = venue.get("images") or []
    venue_image = venue_images[0].get("href") if venue_images else None

    predictor = payload.get("predictor") or {}
    away_pred = predictor.get("awayTeam") or {}
    home_pred = predictor.get("homeTeam") or {}

    pick = (payload.get("pickcenter") or [{}])[0]
    season_series = (payload.get("seasonseries") or [{}])[0]

    broadcasts = []
    for item in payload.get("broadcasts") or []:
        media = item.get("media") or {}
        name = media.get("shortName") or media.get("name") or item.get("station")
        if name and name not in broadcasts:
            broadcasts.append(name)

    live_win_pct = _parse_win_probability(payload.get("winprobability"))
    plays = payload.get("plays") or []
    athlete_records = _athlete_records_from_game(payload, comp.get("competitors"))
    player_map = _player_map_from_game(payload, comp.get("competitors"))
    player_link_entries = [
        {"id": player_id, "name": name}
        for player_id, name in _player_link_entries(player_map, athlete_records)
    ]
    batting_stats_map = _player_batting_stats_map(payload)
    live_situation = _parse_live_situation(
        payload.get("situation"),
        plays,
        comp.get("competitors"),
        player_map,
        status_detail=game.get("status_detail"),
        batting_stats_map=batting_stats_map,
    )

    if live_situation.get("balls") is not None:
        game["balls"] = live_situation["balls"]
        game["strikes"] = live_situation["strikes"]
        game["outs"] = live_situation["outs"]
        game["on_first"] = live_situation["on_first"]
        game["on_second"] = live_situation["on_second"]
        game["on_third"] = live_situation["on_third"]

    game["batting_side"] = _resolve_batting_side(
        payload.get("situation"),
        game.get("away"),
        game.get("home"),
        game.get("status_detail"),
    )

    game["preview"] = {
        "venue": venue.get("fullName"),
        "venue_city": (venue.get("address") or {}).get("city"),
        "venue_state": (venue.get("address") or {}).get("state"),
        "venue_image": venue_image,
        "weather_temp": weather.get("temperature"),
        "weather_condition": weather.get("displayValue"),
        "away_win_pct": _preview_win_pct(
            (live_win_pct or {}).get("away_pct"),
            away_pred.get("gameProjection"),
        ),
        "home_win_pct": _preview_win_pct(
            (live_win_pct or {}).get("home_pct"),
            home_pred.get("gameProjection"),
        ),
        "spread": pick.get("spread"),
        "over_under": pick.get("overUnder"),
        "series_summary": season_series.get("summary"),
        "series_score": season_series.get("seriesScore"),
        "last_five": _parse_last_five(payload.get("lastFiveGames")),
        "broadcasts": broadcasts,
    }
    away_id = str((game.get("away") or {}).get("id") or "")
    home_id = str((game.get("home") or {}).get("id") or "")
    live_data: dict[str, Any] = {
        "linescore": _parse_linescore(comp.get("competitors") or []),
        "situation": live_situation,
        "team_box": _parse_team_box((payload.get("boxscore") or {}).get("teams")),
        "recent_plays": _parse_play_feed(plays),
        "scoring_plays": _parse_scoring_plays(plays, away_id=away_id, home_id=home_id),
        "win_probability": live_win_pct,
        "player_map": player_map,
        "player_link_entries": player_link_entries,
    }
    if game.get("status_state") == "post":
        live_data["plays_by_inning"] = _parse_plays_by_inning(
            plays,
            away_id=away_id,
            home_id=home_id,
        )
    lineups = _parse_lineups(payload, game.get("away"), game.get("home"))
    if lineups:
        live_data["lineups"] = lineups
        pitching_decisions = _parse_pitching_decisions(lineups)
        if pitching_decisions:
            live_data["pitching_decisions"] = pitching_decisions
    game["live"] = live_data
    return game


def _standing_stat(entry: dict[str, Any], name: str) -> str | None:
    for stat in entry.get("stats") or []:
        if stat.get("name") == name:
            value = stat.get("displayValue")
            return str(value) if value not in (None, "") else None
    return None


def _fetch_mlb_teams_lookup(*, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _teams_cache
    now = time.time()
    if (
        not force_refresh
        and _teams_cache
        and now - _teams_cache[0] < TEAMS_CACHE_TTL_SECONDS
    ):
        return _teams_cache[1]

    response = requests.get(ESPN_TEAMS_URL, timeout=15)
    response.raise_for_status()
    payload = response.json()
    lookup: dict[str, dict[str, Any]] = {}
    for item in (
        (payload.get("sports") or [{}])[0]
        .get("leagues", [{}])[0]
        .get("teams", [])
    ):
        team = item.get("team") or {}
        team_id = team.get("id")
        abbr = team.get("abbreviation")
        meta = {
            "id": str(team_id) if team_id is not None else None,
            "abbr": abbr,
            "name": team.get("displayName") or "",
            "logo": _team_logo(team),
            "color": _team_color(team),
            "alternate_color": _team_alternate_color(team),
        }
        if team_id is not None:
            lookup[str(team_id)] = meta
        if abbr:
            lookup[str(abbr)] = meta

    _teams_cache = (now, lookup)
    return lookup


def _parse_standing_team(
    entry: dict[str, Any],
    teams_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    team = entry.get("team") or {}
    team_id = team.get("id")
    abbr = team.get("abbreviation", "")
    meta = (
        teams_lookup.get(str(team_id))
        or teams_lookup.get(str(abbr))
        or {}
    )
    color = meta.get("color") or _team_color(team) or "#1a2332"
    return {
        "id": str(team_id) if team_id is not None else "",
        "abbr": abbr,
        "name": team.get("displayName", ""),
        "logo": meta.get("logo") or _team_logo(team),
        "color": color,
        "alternate_color": meta.get("alternate_color") or _team_alternate_color(team),
        "wins": _standing_stat(entry, "wins"),
        "losses": _standing_stat(entry, "losses"),
        "pct": _standing_stat(entry, "winPercent"),
        "gb": _standing_stat(entry, "divisionGamesBehind"),
        "streak": _standing_stat(entry, "streak"),
    }


def _normalize_division_label(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\bCent\b", "Central", text)


def _division_short_name(division: dict[str, Any]) -> str:
    short_name = division.get("shortName") or division.get("name", "")
    return _normalize_division_label(short_name)


def parse_standings(
    payload: dict[str, Any],
    teams_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    teams_lookup = teams_lookup or {}
    leagues: list[dict[str, Any]] = []
    for league in payload.get("children") or []:
        divisions: list[dict[str, Any]] = []
        for division in league.get("children") or []:
            entries = (division.get("standings") or {}).get("entries") or []
            teams = [
                _parse_standing_team(entry, teams_lookup)
                for entry in entries
            ]
            divisions.append({
                "abbr": division.get("abbreviation", ""),
                "name": _normalize_division_label(division.get("name", "")),
                "short_name": _division_short_name(division),
                "teams": teams,
            })
        leagues.append({
            "abbr": league.get("abbreviation", ""),
            "name": league.get("name", ""),
            "divisions": divisions,
        })

    league_order = {"AL": 0, "NL": 1}
    leagues.sort(key=lambda league: league_order.get(league["abbr"], 99))
    return leagues


def fetch_standings(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    global _standings_cache
    now = time.time()
    if (
        not force_refresh
        and _standings_cache
        and now - _standings_cache[0] < CACHE_TTL_SECONDS
    ):
        return _standings_cache[1]

    teams_lookup = _fetch_mlb_teams_lookup(force_refresh=force_refresh)
    response = requests.get(
        ESPN_STANDINGS_URL,
        params={"level": 3},
        timeout=15,
    )
    response.raise_for_status()
    leagues = parse_standings(response.json(), teams_lookup)
    _standings_cache = (now, leagues)
    return leagues


def scoreboard_snapshot(
    today: date | None = None,
) -> dict[str, Any]:
    """Bundle today, yesterday, and optional upcoming slate."""
    today = today or date.today()
    yesterday = today - timedelta(days=1)

    today_games = fetch_scoreboard(today)
    yesterday_games = fetch_scoreboard(yesterday)

    upcoming_date = None
    upcoming_games: list[dict[str, Any]] = []
    if not today_games:
        upcoming_date, upcoming_games = find_next_games(today)

    has_live = any(game.get("status_state") == "in" for game in today_games)

    return {
        "today": today,
        "yesterday": yesterday,
        "today_games": today_games,
        "yesterday_games": yesterday_games,
        "upcoming_date": upcoming_date,
        "upcoming_games": upcoming_games,
        "has_live": has_live,
    }


def _fold_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return folded.casefold()


def linkify_player_names(
    text: str | None,
    player_map: dict[str, str] | None,
    *,
    athlete_records: dict[str, dict[str, Any]] | None = None,
) -> Markup:
    if not text:
        return Markup("")
    if not player_map:
        return Markup(escape(text))

    entries = _player_link_entries(player_map, athlete_records)
    if not entries:
        return Markup(escape(text))

    entry_by_folded: dict[str, tuple[str, str]] = {}
    for player_id, name in entries:
        folded = _fold_for_match(name)
        if folded not in entry_by_folded or len(name) > len(entry_by_folded[folded][1]):
            entry_by_folded[folded] = (player_id, name)

    parts = re.split(r"(\W+)", str(text))
    linked: list[str] = []
    for part in parts:
        if not part or not part.strip() or not re.search(r"\w", part):
            linked.append(escape(part))
            continue
        match = entry_by_folded.get(_fold_for_match(part))
        if match:
            player_id, _name = match
            linked.append(
                f'<a href="/player/{escape(player_id)}" class="player-link">{escape(part)}</a>'
            )
        else:
            linked.append(escape(part))
    return Markup("".join(linked))


def _parse_season_year(season_label: str | None) -> str | None:
    if not season_label:
        return None
    match = re.search(r"(20\d{2})", season_label)
    return match.group(1) if match else None


def parse_player_detail(payload: dict[str, Any]) -> dict[str, Any]:
    athlete = payload.get("athlete") or {}
    team = athlete.get("team") or {}
    position = athlete.get("position") or {}
    stats_summary = athlete.get("statsSummary") or {}
    season_stats: list[dict[str, Any]] = []
    for stat in stats_summary.get("statistics") or []:
        season_stats.append({
            "label": stat.get("shortDisplayName") or stat.get("displayName") or "",
            "name": stat.get("name") or "",
            "display": stat.get("displayValue") or "—",
            "value": stat.get("value"),
            "rank": stat.get("rankDisplayValue"),
        })

    season_label = stats_summary.get("displayName")
    return {
        "id": str(athlete.get("id") or ""),
        "name": athlete.get("displayName") or "",
        "short_name": athlete.get("shortName") or "",
        "headshot": (athlete.get("headshot") or {}).get("href"),
        "jersey": athlete.get("jersey") or athlete.get("displayJersey"),
        "position": position.get("abbreviation") or position.get("displayName"),
        "team": {
            "id": str(team.get("id") or ""),
            "abbr": team.get("abbreviation") or "",
            "name": team.get("displayName") or "",
            "logo": _team_logo(team),
        },
        "bats_throws": athlete.get("displayBatsThrows"),
        "height": athlete.get("displayHeight"),
        "weight": athlete.get("displayWeight"),
        "birth_place": athlete.get("displayBirthPlace"),
        "birth_date": athlete.get("displayDOB"),
        "age": athlete.get("age"),
        "experience": athlete.get("displayExperience"),
        "debut_year": athlete.get("debutYear"),
        "status": (athlete.get("status") or {}).get("name"),
        "season_label": season_label,
        "season_year": _parse_season_year(season_label),
        "season_stats": season_stats,
        "stats_table": None,
    }


def fetch_player_stats(
    player_name: str,
    season_year: str | None = None,
    *,
    position: str | None = None,
    espn_player_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_stats_table

        return fetch_player_stats_table(
            player_name,
            season_year,
            position=position,
            espn_player_id=espn_player_id,
        )
    except Exception:
        return None


def fetch_player_extra_stat_panels(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> list[dict[str, Any]]:
    try:
        from player_stats import fetch_player_core_stat_panels

        return fetch_player_core_stat_panels(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return []


def fetch_player_league_stat_panel(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_league_stat_panel as _fetch_league

        return _fetch_league(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return None


def fetch_player_season_stats_view(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_season_stats_view as _fetch_season

        return _fetch_season(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return None


def fetch_player_visual_stat_panel(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_visual_stat_panel as _fetch_visual

        return _fetch_visual(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return None


def fetch_player_percentile_stat_panel(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_percentile_stat_panel as _fetch_percentile

        return _fetch_percentile(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return None


def fetch_player_splits_stat_panel(
    player_id: str,
    *,
    player_name: str | None = None,
    position: str | None = None,
    season_year: str | None = None,
) -> dict[str, Any] | None:
    try:
        from player_stats import fetch_player_splits_stat_panel as _fetch_splits

        return _fetch_splits(
            player_id,
            player_name=player_name or "",
            position=position,
            season_year=season_year,
        )
    except Exception:
        return None


def fetch_player_percentile_ranks(
    player_name: str,
    *,
    position: str | None = None,
    season_year: str | int | None = None,
) -> dict[str, Any]:
    empty = {
        "id": "percentile_ranks",
        "label": "Percentile Rankings",
        "panel_kind": "percentile_ranks",
        "season_year": str(season_year or ""),
        "qualified": False,
        "available_years": [],
        "groups": [],
    }
    try:
        from player_stats import (
            fetch_batter_percentile_panel,
            fetch_pitcher_percentile_panel,
            is_pitcher_position,
        )

        year = None
        if season_year is not None:
            try:
                year = int(season_year)
            except (TypeError, ValueError):
                year = None
        if is_pitcher_position(position):
            return fetch_pitcher_percentile_panel(player_name, season_year=year)
        return fetch_batter_percentile_panel(player_name, season_year=year)
    except Exception:
        return empty


def fetch_player(
    player_id: str,
    *,
    force_refresh: bool = False,
    include_stats: bool = True,
) -> dict[str, Any]:
    now = time.time()
    cached = _athlete_cache.get(player_id)
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        detail = cached[1]
        if include_stats and not detail.get("stats_table"):
            stats_table = fetch_player_stats(
                detail.get("name") or "",
                detail.get("season_year"),
                position=detail.get("position"),
            )
            if stats_table:
                detail = {**detail, "stats_table": stats_table}
                if stats_table.get("season_year"):
                    detail["season_year"] = stats_table["season_year"]
                _athlete_cache[player_id] = (now, detail)
        return detail

    response = requests.get(
        ESPN_ATHLETE_URL.format(player_id=player_id),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("athlete"):
        raise ValueError(f"No athlete for player {player_id}")

    detail = parse_player_detail(payload)
    if include_stats:
        stats_table = fetch_player_stats(
            detail.get("name") or "",
            detail.get("season_year"),
            position=detail.get("position"),
        )
        if stats_table:
            detail["stats_table"] = stats_table
            if stats_table.get("season_year"):
                detail["season_year"] = stats_table["season_year"]

    _athlete_cache[player_id] = (now, detail)
    return detail


def _team_record_stats(team: dict[str, Any]) -> dict[str, Any]:
    items = ((team.get("record") or {}).get("items") or [])
    if not items:
        return {}
    stats = {
        stat.get("name"): stat.get("value")
        for stat in items[0].get("stats") or []
        if stat.get("name")
    }
    return stats


def _format_team_streak(value: Any) -> str | None:
    number = value
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if number > 0:
        return f"W{number}"
    if number < 0:
        return f"L{abs(number)}"
    return None


def parse_team_detail(payload: dict[str, Any]) -> dict[str, Any]:
    team = payload.get("team") or {}
    franchise = team.get("franchise") or {}
    venue = franchise.get("venue") or {}
    record_stats = _team_record_stats(team)
    wins = record_stats.get("wins")
    losses = record_stats.get("losses")
    home_wins = record_stats.get("homeWins")
    home_losses = record_stats.get("homeLosses")
    road_wins = record_stats.get("roadWins")
    road_losses = record_stats.get("roadLosses")
    division_gb = record_stats.get("divisionGamesBehind")
    win_pct = record_stats.get("winPercent")

    record = None
    if wins is not None and losses is not None:
        record = f"{int(float(wins))}–{int(float(losses))}"

    home_record = None
    if home_wins is not None and home_losses is not None:
        home_record = f"{int(float(home_wins))}–{int(float(home_losses))}"

    road_record = None
    if road_wins is not None and road_losses is not None:
        road_record = f"{int(float(road_wins))}–{int(float(road_losses))}"

    pct = None
    if win_pct is not None:
        try:
            pct = f"{float(win_pct):.3f}".lstrip("0")
        except (TypeError, ValueError):
            pct = None

    return {
        "id": str(team.get("id") or ""),
        "abbr": team.get("abbreviation") or "",
        "name": team.get("displayName") or "",
        "short_name": team.get("shortDisplayName") or "",
        "location": team.get("location") or franchise.get("location") or "",
        "logo": _team_logo(team),
        "color": _team_color(team),
        "alternate_color": _team_alternate_color(team),
        "record": record or team.get("recordSummary"),
        "pct": pct,
        "standing_summary": _normalize_division_label(team.get("standingSummary") or ""),
        "venue": venue.get("fullName") or venue.get("shortName"),
        "home_record": home_record,
        "road_record": road_record,
        "division_gb": (
            f"{float(division_gb):g} GB"
            if division_gb is not None and str(division_gb) not in {"", "-"}
            else None
        ),
        "streak": _format_team_streak(record_stats.get("streak")),
        "season_year": str(date.today().year),
        "stats_table": None,
    }


def fetch_team_stats(team_id: str, season_year: str | int | None = None) -> dict[str, Any] | None:
    try:
        from team_stats import fetch_team_stats_table

        year = None
        if season_year is not None:
            try:
                year = int(season_year)
            except (TypeError, ValueError):
                year = date.today().year
        if year is None:
            year = date.today().year
        return fetch_team_stats_table(team_id, season_year=year)
    except Exception:
        return None


def fetch_team_extra_stat_panels(
    team_id: str,
    *,
    season_year: str | int | None = None,
) -> list[dict[str, Any]]:
    try:
        from team_stats import fetch_team_stat_panels

        year = None
        if season_year is not None:
            try:
                year = int(season_year)
            except (TypeError, ValueError):
                year = date.today().year
        if year is None:
            year = date.today().year
        return fetch_team_stat_panels(
            team_id,
            season_year=year,
        )
    except Exception:
        return []


def fetch_team_core_stat_panels(
    team_id: str,
    *,
    season_year: str | int | None = None,
) -> list[dict[str, Any]]:
    try:
        from team_stats import fetch_team_core_stat_panels as _fetch_core

        year = _coerce_season_year(season_year)
        return _fetch_core(team_id, season_year=year)
    except Exception:
        return []


def fetch_team_roster_stat_panel(
    team_id: str,
    *,
    season_year: str | int | None = None,
) -> dict[str, Any] | None:
    try:
        from team_stats import fetch_team_roster_stat_panel as _fetch_roster

        year = _coerce_season_year(season_year)
        return _fetch_roster(team_id, season_year=year)
    except Exception:
        return None


def fetch_team_leaders_stat_panel(
    team_id: str,
    *,
    season_year: str | int | None = None,
) -> dict[str, Any] | None:
    try:
        from team_stats import fetch_team_leaders_stat_panel as _fetch_leaders

        year = _coerce_season_year(season_year)
        return _fetch_leaders(team_id, season_year=year)
    except Exception:
        return None


def _coerce_season_year(season_year: str | int | None) -> int:
    if season_year is not None:
        try:
            return int(season_year)
        except (TypeError, ValueError):
            pass
    return date.today().year


def fetch_team(
    team_id: str,
    *,
    force_refresh: bool = False,
    include_stats: bool = True,
) -> dict[str, Any]:
    now = time.time()
    cached = _team_detail_cache.get(team_id)
    if not force_refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
        detail = cached[1]
        if include_stats and not detail.get("stats_table"):
            stats_table = fetch_team_stats(team_id, detail.get("season_year"))
            if stats_table:
                detail = {**detail, "stats_table": stats_table}
                if stats_table.get("season_year"):
                    detail["season_year"] = stats_table["season_year"]
                _team_detail_cache[team_id] = (now, detail)
        return detail

    response = requests.get(
        ESPN_TEAM_URL.format(team_id=team_id),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("team"):
        raise ValueError(f"No team for id {team_id}")

    detail = parse_team_detail(payload)
    if include_stats:
        stats_table = fetch_team_stats(team_id, detail.get("season_year"))
        if stats_table:
            detail["stats_table"] = stats_table
            if stats_table.get("season_year"):
                detail["season_year"] = stats_table["season_year"]

    _team_detail_cache[team_id] = (now, detail)
    return detail
