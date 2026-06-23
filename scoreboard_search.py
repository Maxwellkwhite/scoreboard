"""Unified MLB and World Cup search for navbar autocomplete."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from espn_mlb import _fetch_mlb_teams_lookup
from espn_world_cup import fetch_standings
from team_stats import _normalize_player_name

logger = logging.getLogger(__name__)

ESPN_SEARCH_URL = "https://site.api.espn.com/apis/common/v3/search"
MLB_PLAYER_LEAGUE = "mlb"
WC_PLAYER_LEAGUE = "fifa.world"


def _match_score(query: str, *candidates: str) -> int:
    q = _normalize_player_name(query)
    if not q or len(q) < 2:
        return 0
    best = 0
    for raw in candidates:
        if not raw:
            continue
        norm = _normalize_player_name(raw)
        if norm == q:
            best = max(best, 100)
        elif norm.startswith(q):
            best = max(best, 80)
        elif any(part.startswith(q) for part in norm.split()):
            best = max(best, 60)
        elif q in norm:
            best = max(best, 40)
    return best


def _team_color_hex(raw: str | None) -> str:
    color = (raw or "").strip()
    if not color:
        return "#1a2332"
    if not color.startswith("#"):
        color = f"#{color}"
    return color


def _player_href_from_links(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("links") or []:
        rel = link.get("rel") or []
        if "playercard" in rel and link.get("href"):
            return str(link["href"])
    return fallback


def _parse_mlb_player_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "player" or item.get("league") != MLB_PLAYER_LEAGUE:
        return None
    player_id = item.get("id")
    name = item.get("displayName") or ""
    if not player_id or not name:
        return None

    team_abbr = ""
    team_color = "#1a2332"
    for relationship in item.get("teamRelationships") or []:
        if relationship.get("type") != "team":
            continue
        core = relationship.get("core") or {}
        team_abbr = str(core.get("abbreviation") or "")
        team_color = _team_color_hex(core.get("color"))
        break

    player_id = str(player_id)
    return {
        "id": player_id,
        "name": name,
        "position": "",
        "team_abbr": team_abbr,
        "team_color": team_color,
        "sport": "mlb",
        "href": f"/player/{player_id}",
        "external": False,
    }


def _parse_world_cup_player_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "player" or item.get("league") != WC_PLAYER_LEAGUE:
        return None
    player_id = item.get("id")
    name = item.get("displayName") or ""
    if not player_id or not name:
        return None

    team_abbr = ""
    team_color = "#1a2332"
    for relationship in item.get("teamRelationships") or []:
        if relationship.get("type") != "team":
            continue
        core = relationship.get("core") or {}
        team_abbr = str(core.get("abbreviation") or "")
        team_color = _team_color_hex(core.get("color"))
        break

    player_id = str(player_id)
    return {
        "id": player_id,
        "name": name,
        "position": "",
        "team_abbr": team_abbr,
        "team_color": team_color,
        "sport": "world_cup",
        "href": f"/world-cup/player/{player_id}",
        "external": False,
    }


def _search_players_espn(
    query: str,
    *,
    league: str,
    parser,
    limit: int = 8,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query": query,
        "limit": max(limit * 2, 12),
        "type": "player",
        "league": league,
    }
    try:
        response = requests.get(ESPN_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        logger.exception("ESPN player search failed for query %r league=%s", query, league)
        return []

    players: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in payload.get("items") or []:
        player = parser(item)
        if not player or player["id"] in seen_ids:
            continue
        seen_ids.add(player["id"])
        players.append(player)
        if len(players) >= limit:
            break
    return players


def _search_local_teams(
    query: str,
    teams_lookup: dict[str, dict[str, Any]],
    *,
    sport: str,
    href_for_team,
    limit: int = 5,
) -> list[dict[str, Any]]:
    q = query.strip()
    seen_ids: set[str] = set()
    team_results: list[tuple[int, dict[str, Any]]] = []

    for meta in teams_lookup.values():
        team_id = meta.get("id")
        if not team_id or team_id in seen_ids:
            continue
        seen_ids.add(team_id)
        score = _match_score(q, meta.get("abbr") or "", meta.get("name") or "")
        if not score:
            continue
        team_results.append(
            (
                score,
                {
                    "id": str(team_id),
                    "name": meta.get("name") or "",
                    "abbr": meta.get("abbr") or "",
                    "logo": meta.get("logo") or "",
                    "color": meta.get("color") or "#1a2332",
                    "sport": sport,
                    "href": href_for_team(str(team_id)),
                    "external": False,
                },
            )
        )

    team_results.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [team for _, team in team_results[:limit]]


def _fetch_world_cup_teams_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    try:
        groups = fetch_standings()
    except requests.RequestException:
        logger.exception("World Cup standings lookup failed")
        return lookup

    for group in groups:
        for team in group.get("teams") or []:
            team_id = team.get("id")
            if not team_id:
                continue
            team_id = str(team_id)
            if team_id in lookup:
                continue
            lookup[team_id] = {
                "id": team_id,
                "name": team.get("name") or "",
                "abbr": team.get("abbr") or "",
                "logo": team.get("logo") or "",
                "color": team.get("color") or "#1a2332",
            }
    return lookup


def search_mlb(
    query: str,
    *,
    limit_teams: int = 5,
    limit_players: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    q = query.strip()
    if len(q) < 2:
        return {"teams": [], "players": []}

    teams = _search_local_teams(
        q,
        _fetch_mlb_teams_lookup(),
        sport="mlb",
        href_for_team=lambda team_id: f"/team/{team_id}",
        limit=limit_teams,
    )
    players = _search_players_espn(
        q,
        league=MLB_PLAYER_LEAGUE,
        parser=_parse_mlb_player_item,
        limit=limit_players,
    )
    return {"teams": teams, "players": players}


def search_world_cup(
    query: str,
    *,
    limit_teams: int = 5,
    limit_players: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    q = query.strip()
    if len(q) < 2:
        return {"teams": [], "players": []}

    teams = _search_local_teams(
        q,
        _fetch_world_cup_teams_lookup(),
        sport="world_cup",
        href_for_team=lambda team_id: f"/world-cup/team/{team_id}",
        limit=limit_teams,
    )
    players = _search_players_espn(
        q,
        league=WC_PLAYER_LEAGUE,
        parser=_parse_world_cup_player_item,
        limit=limit_players,
    )
    return {"teams": teams, "players": players}


def search_all(
    query: str,
    *,
    limit_teams: int = 5,
    limit_players: int = 8,
) -> dict[str, Any]:
    q = query.strip()
    if len(q) < 2:
        return {"sections": []}

    with ThreadPoolExecutor(max_workers=2) as executor:
        mlb_future = executor.submit(
            search_mlb,
            q,
            limit_teams=limit_teams,
            limit_players=limit_players,
        )
        wc_future = executor.submit(
            search_world_cup,
            q,
            limit_teams=limit_teams,
            limit_players=limit_players,
        )
        mlb = mlb_future.result()
        wc = wc_future.result()

    sections: list[dict[str, Any]] = []
    if mlb["teams"] or mlb["players"]:
        sections.append(
            {
                "sport": "mlb",
                "label": "MLB",
                "teams": mlb["teams"],
                "players": mlb["players"],
            }
        )
    if wc["teams"] or wc["players"]:
        sections.append(
            {
                "sport": "world_cup",
                "label": "World Cup",
                "teams": wc["teams"],
                "players": wc["players"],
            }
        )
    return {"sections": sections}
