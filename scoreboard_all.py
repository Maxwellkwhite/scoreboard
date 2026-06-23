"""Combined multi-sport scoreboard helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

_STATUS_SORT_ORDER = {"in": 0, "pre": 1, "post": 2}


def tag_games(games: list[dict[str, Any]], sport: str) -> list[dict[str, Any]]:
    return [{**game, "sport": sport} for game in games]


def merge_and_sort(
    *game_lists: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for games in game_lists:
        merged.extend(games)
    merged.sort(key=_scoreboard_sort_key)
    return merged


def _scoreboard_sort_key(game: dict[str, Any]) -> tuple[int, str]:
    state = game.get("status_state", "pre")
    priority = _STATUS_SORT_ORDER.get(state, 1)
    return priority, game.get("start_time") or ""


def all_scoreboard_snapshot(
    today: date | None = None,
) -> dict[str, Any]:
    from espn_mlb import scoreboard_snapshot as mlb_snapshot
    from espn_world_cup import scoreboard_snapshot as wc_snapshot

    today = today or date.today()
    mlb = mlb_snapshot(today)
    wc = wc_snapshot(today)

    today_games = merge_and_sort(
        tag_games(mlb["today_games"], "mlb"),
        tag_games(wc["today_games"], "world_cup"),
    )
    yesterday_games = merge_and_sort(
        tag_games(mlb["yesterday_games"], "mlb"),
        tag_games(wc["yesterday_games"], "world_cup"),
    )

    upcoming_date = None
    upcoming_games: list[dict[str, Any]] = []
    if not today_games:
        mlb_upcoming = tag_games(mlb.get("upcoming_games") or [], "mlb")
        wc_upcoming = tag_games(wc.get("upcoming_games") or [], "world_cup")
        upcoming_games = merge_and_sort(mlb_upcoming, wc_upcoming)
        if upcoming_games:
            dates = [
                value
                for value in (mlb.get("upcoming_date"), wc.get("upcoming_date"))
                if value is not None
            ]
            upcoming_date = min(dates) if dates else None

    return {
        "today": today,
        "yesterday": mlb["yesterday"],
        "today_games": today_games,
        "yesterday_games": yesterday_games,
        "upcoming_date": upcoming_date,
        "upcoming_games": upcoming_games,
        "has_live": bool(mlb.get("has_live") or wc.get("has_live")),
    }


def fetch_all_scoreboard(game_date: date) -> list[dict[str, Any]]:
    from espn_mlb import fetch_scoreboard as fetch_mlb_scoreboard
    from espn_world_cup import fetch_scoreboard as fetch_wc_scoreboard

    return merge_and_sort(
        tag_games(fetch_mlb_scoreboard(game_date), "mlb"),
        tag_games(fetch_wc_scoreboard(game_date), "world_cup"),
    )
