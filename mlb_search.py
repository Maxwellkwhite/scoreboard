"""MLB team and player search for navbar autocomplete."""

from __future__ import annotations

import logging
from typing import Any

import requests

from espn_mlb import _fetch_mlb_teams_lookup
from team_stats import _normalize_player_name

logger = logging.getLogger(__name__)

ESPN_SEARCH_URL = "https://site.api.espn.com/apis/common/v3/search"


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


def _parse_player_search_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "player" or item.get("league") != "mlb":
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

    return {
        "id": str(player_id),
        "name": name,
        "position": "",
        "team_abbr": team_abbr,
        "team_color": team_color,
    }


def _search_players_espn(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            ESPN_SEARCH_URL,
            params={"query": query, "limit": max(limit * 2, 12), "type": "player"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        logger.exception("ESPN player search failed for query %r", query)
        return []

    players: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in payload.get("items") or []:
        player = _parse_player_search_item(item)
        if not player or player["id"] in seen_ids:
            continue
        seen_ids.add(player["id"])
        players.append(player)
        if len(players) >= limit:
            break
    return players


def search_mlb(
    query: str,
    *,
    limit_teams: int = 5,
    limit_players: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    q = query.strip()
    if len(q) < 2:
        return {"teams": [], "players": []}

    teams_lookup = _fetch_mlb_teams_lookup()
    seen_ids: set[str] = set()
    team_results: list[tuple[int, dict[str, Any]]] = []

    for meta in teams_lookup.values():
        team_id = meta.get("id")
        if not team_id or team_id in seen_ids:
            continue
        seen_ids.add(team_id)
        score = _match_score(q, meta.get("abbr") or "", meta.get("name") or "")
        if score:
            team_results.append(
                (
                    score,
                    {
                        "id": team_id,
                        "name": meta.get("name") or "",
                        "abbr": meta.get("abbr") or "",
                        "logo": meta.get("logo") or "",
                        "color": meta.get("color") or "#1a2332",
                    },
                )
            )

    team_results.sort(key=lambda item: (-item[0], item[1]["name"]))
    teams = [team for _, team in team_results[:limit_teams]]
    players = _search_players_espn(q, limit=limit_players)

    return {"teams": teams, "players": players}
