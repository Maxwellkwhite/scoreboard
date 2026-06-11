"""ESPN MLB scoreboard client (pattern from ha-teamtracker)."""

from __future__ import annotations

import re
import time
from datetime import date, timedelta
from typing import Any

import requests

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
)
ESPN_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary"
)
CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}


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
    side = _batting_side_from_situation(situation, away, home)
    if side:
        return side
    return _batting_side_from_status(status_detail)


def _parse_team(competitor: dict[str, Any]) -> dict[str, Any]:
    team = competitor.get("team") or {}
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
    games.sort(key=lambda game: game.get("start_time") or "")

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


def _team_record(records: list[dict[str, Any]] | None) -> str | None:
    if not records:
        return None
    for record in records:
        if record.get("type") == "total":
            return record.get("displayValue") or record.get("summary")
    first = records[0]
    return first.get("displayValue") or first.get("summary")


def _parse_probable(competitor: dict[str, Any]) -> dict[str, Any] | None:
    for probable in competitor.get("probables") or []:
        if probable.get("name") != "probableStartingPitcher":
            continue
        athlete = probable.get("athlete") or {}
        stats: dict[str, str] = {}
        for category in (
            (probable.get("statistics") or {})
            .get("splits", {})
            .get("categories", [])
        ):
            key = category.get("abbreviation") or category.get("name")
            if key:
                stats[str(key)] = category.get("displayValue", "")
        headshot = athlete.get("headshot") or {}
        return {
            "name": athlete.get("displayName", ""),
            "headshot": headshot.get("href"),
            "jersey": athlete.get("jersey"),
            "throws": (athlete.get("throws") or {}).get("displayValue"),
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


def _parse_play_feed(plays: list[dict[str, Any]] | None, *, limit: int = 10) -> list[dict[str, Any]]:
    feed = []
    for play in reversed(plays or []):
        text = (play.get("text") or "").strip()
        play_type = (play.get("type") or {}).get("type")
        if not text:
            continue
        if play_type == "start-batterpitcher":
            continue
        if text.startswith("Pitch ") and play_type != "end-inning":
            continue
        feed.append({
            "text": text,
            "away_score": _parse_score(play.get("awayScore")),
            "home_score": _parse_score(play.get("homeScore")),
            "scoring": bool(play.get("scoringPlay")),
            "period": (play.get("period") or {}).get("displayValue"),
        })
        if len(feed) >= limit:
            break
    feed.reverse()
    return feed


def _parse_scoring_plays(plays: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    scoring = []
    for play in plays or []:
        if not play.get("scoringPlay"):
            continue
        text = (play.get("text") or "").strip()
        if not text:
            continue
        scoring.append({
            "text": text,
            "away_score": _parse_score(play.get("awayScore")),
            "home_score": _parse_score(play.get("homeScore")),
            "period": (play.get("period") or {}).get("displayValue"),
        })
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
    name = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName")
    if player_id and name:
        players[str(player_id)] = name


def _player_map_from_game(
    payload: dict[str, Any],
    competitors: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    players: dict[str, str] = {}
    for competitor in competitors or []:
        for probable in competitor.get("probables") or []:
            _add_player_name(players, probable.get("athlete"))

    boxscore = payload.get("boxscore") or {}
    for team_block in boxscore.get("players") or []:
        for stat in team_block.get("statistics") or []:
            for entry in stat.get("athletes") or []:
                _add_player_name(players, entry.get("athlete"))

    for roster_block in payload.get("rosters") or []:
        for entry in roster_block.get("roster") or []:
            _add_player_name(players, entry.get("athlete"))

    return players


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


def _parse_live_situation(
    situation: dict[str, Any] | None,
    plays: list[dict[str, Any]] | None,
    competitors: list[dict[str, Any]] | None = None,
    player_map: dict[str, str] | None = None,
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
        "notes": notes,
        "matchup_text": matchup_text,
        "pitcher_name": pitcher_name,
        "batter_name": batter_name,
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
    player_map = _player_map_from_game(payload, comp.get("competitors"))
    live_situation = _parse_live_situation(
        payload.get("situation"),
        plays,
        comp.get("competitors"),
        player_map,
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
        "away_win_pct": (live_win_pct or {}).get("away_pct") or away_pred.get("gameProjection"),
        "home_win_pct": (live_win_pct or {}).get("home_pct") or home_pred.get("gameProjection"),
        "spread": pick.get("spread"),
        "over_under": pick.get("overUnder"),
        "series_summary": season_series.get("summary"),
        "series_score": season_series.get("seriesScore"),
        "last_five": _parse_last_five(payload.get("lastFiveGames")),
        "broadcasts": broadcasts,
    }
    game["live"] = {
        "linescore": _parse_linescore(comp.get("competitors") or []),
        "situation": live_situation,
        "team_box": _parse_team_box((payload.get("boxscore") or {}).get("teams")),
        "recent_plays": _parse_play_feed(plays),
        "scoring_plays": _parse_scoring_plays(plays),
        "win_probability": live_win_pct,
    }
    return game


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
