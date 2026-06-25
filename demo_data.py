from __future__ import annotations

import copy
from typing import Any

from espn_mlb import _resolve_win_colors

DEMO_MLB_GAMES_RAW: list[dict[str, Any]] = [
    {
        "index": 0,
        "status_state": "in",
        "status_detail": "Top 7th",
        "batting_side": "away",
        "balls": 1,
        "strikes": 2,
        "outs": 1,
        "on_first": True,
        "on_second": False,
        "on_third": False,
        "away": {
            "abbr": "NYM",
            "short_name": "Mets",
            "name": "New York Mets",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/21.png",
            "color": "#002D72",
            "alternate_color": "#FF5910",
            "score": 4,
        },
        "home": {
            "abbr": "PHI",
            "short_name": "Phillies",
            "name": "Philadelphia Phillies",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/22.png",
            "color": "#E81828",
            "alternate_color": "#002D72",
            "score": 3,
        },
    },
    {
        "index": 1,
        "status_state": "in",
        "status_detail": "Bot 6th",
        "batting_side": "home",
        "balls": 2,
        "strikes": 1,
        "outs": 2,
        "on_first": True,
        "on_second": True,
        "on_third": True,
        "away": {
            "abbr": "NYY",
            "short_name": "Yankees",
            "name": "New York Yankees",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/10.png",
            "color": "#132448",
            "alternate_color": "#C4CED4",
            "score": 2,
        },
        "home": {
            "abbr": "BOS",
            "short_name": "Red Sox",
            "name": "Boston Red Sox",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/2.png",
            "color": "#BD3039",
            "alternate_color": "#0C2340",
            "score": 2,
        },
    },
    {
        "index": 2,
        "status_state": "in",
        "status_detail": "Top 8th",
        "batting_side": "away",
        "balls": 0,
        "strikes": 0,
        "outs": 0,
        "on_first": False,
        "on_second": False,
        "on_third": False,
        "away": {
            "abbr": "LAD",
            "short_name": "Dodgers",
            "name": "Los Angeles Dodgers",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/19.png",
            "color": "#005A9C",
            "alternate_color": "#EF3E42",
            "score": 5,
        },
        "home": {
            "abbr": "SF",
            "short_name": "Giants",
            "name": "San Francisco Giants",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/26.png",
            "color": "#FD5A1E",
            "alternate_color": "#27251F",
            "score": 4,
        },
    },
    {
        "index": 3,
        "status_state": "in",
        "status_detail": "Bot 9th",
        "batting_side": "home",
        "balls": 1,
        "strikes": 2,
        "outs": 1,
        "on_first": True,
        "on_second": False,
        "on_third": False,
        "away": {
            "abbr": "CHC",
            "short_name": "Cubs",
            "name": "Chicago Cubs",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/16.png",
            "color": "#0E3386",
            "alternate_color": "#CC3433",
            "score": 1,
        },
        "home": {
            "abbr": "STL",
            "short_name": "Cardinals",
            "name": "St. Louis Cardinals",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/24.png",
            "color": "#BE0A14",
            "alternate_color": "#0C2340",
            "score": 1,
        },
    },
    {
        "index": 4,
        "status_state": "in",
        "status_detail": "Top 6th",
        "batting_side": "away",
        "balls": 3,
        "strikes": 2,
        "outs": 2,
        "on_first": False,
        "on_second": True,
        "on_third": False,
        "away": {
            "abbr": "HOU",
            "short_name": "Astros",
            "name": "Houston Astros",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/18.png",
            "color": "#002D62",
            "alternate_color": "#EB6E1F",
            "score": 3,
        },
        "home": {
            "abbr": "ATL",
            "short_name": "Braves",
            "name": "Atlanta Braves",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/15.png",
            "color": "#CE1141",
            "alternate_color": "#13274F",
            "score": 2,
        },
    },
    {
        "index": 5,
        "status_state": "in",
        "status_detail": "Bot 8th",
        "batting_side": "home",
        "balls": 2,
        "strikes": 0,
        "outs": 1,
        "on_first": True,
        "on_second": False,
        "on_third": True,
        "away": {
            "abbr": "SEA",
            "short_name": "Mariners",
            "name": "Seattle Mariners",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/12.png",
            "color": "#0C2C56",
            "alternate_color": "#005C5C",
            "score": 6,
        },
        "home": {
            "abbr": "TEX",
            "short_name": "Rangers",
            "name": "Texas Rangers",
            "logo": "https://a.espncdn.com/i/teamlogos/mlb/500/13.png",
            "color": "#003278",
            "alternate_color": "#C0111F",
            "score": 5,
        },
    },
]


def get_demo_mlb_games() -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for raw in DEMO_MLB_GAMES_RAW:
        game = copy.deepcopy(raw)
        away = game["away"]
        home = game["home"]
        _resolve_win_colors(away, home)
        games.append(game)
    return games


def demo_games_for_js(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for game in games:
        away = game["away"]
        home = game["home"]
        configs.append({
            "label": f"{away['short_name']} @ {home['short_name']}",
            "away": {
                "color": away["color"],
                "alternate_color": away.get("alternate_color"),
                "abbr": away["abbr"],
                "short_name": away["short_name"],
                "name": away["name"],
                "logo": away["logo"],
            },
            "home": {
                "color": home["color"],
                "alternate_color": home.get("alternate_color"),
                "abbr": home["abbr"],
                "short_name": home["short_name"],
                "name": home["name"],
                "logo": home["logo"],
            },
            "initial": {
                "status": game["status_state"],
                "battingSide": game["batting_side"],
                "awayScore": away["score"],
                "homeScore": home["score"],
                "statusDetail": game["status_detail"],
                "balls": game["balls"],
                "strikes": game["strikes"],
                "outs": game["outs"],
                "onFirst": game["on_first"],
                "onSecond": game["on_second"],
                "onThird": game["on_third"],
            },
        })
    return configs
