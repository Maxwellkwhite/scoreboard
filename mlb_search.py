"""MLB team and player search for navbar autocomplete."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from espn_mlb import _fetch_mlb_teams_lookup
from team_stats import _get_cached_team_roster, _normalize_player_name

_INDEX_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_INDEX_CACHE_TTL_SECONDS = 300


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


def _unique_team_ids(teams_lookup: dict[str, dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    team_ids: list[str] = []
    for meta in teams_lookup.values():
        team_id = meta.get("id")
        if team_id and team_id not in seen:
            seen.add(team_id)
            team_ids.append(team_id)
    return team_ids


def _build_player_index(season_year: int) -> list[dict[str, Any]]:
    teams_lookup = _fetch_mlb_teams_lookup()
    team_ids = _unique_team_ids(teams_lookup)
    players: list[dict[str, Any]] = []
    seen_players: set[str] = set()

    def collect(team_id: str) -> list[dict[str, Any]]:
        roster = _get_cached_team_roster(team_id, season_year)
        meta = teams_lookup.get(team_id) or {}
        out: list[dict[str, Any]] = []
        for section in roster.get("sections") or []:
            for player in section.get("players") or []:
                player_id = player.get("id")
                if not player_id:
                    continue
                out.append(
                    {
                        "id": player_id,
                        "name": player.get("name") or "",
                        "position": player.get("position") or "",
                        "team_id": team_id,
                        "team_abbr": meta.get("abbr") or "",
                        "team_color": meta.get("color") or "#1a2332",
                    }
                )
        return out

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(collect, team_id) for team_id in team_ids]
        for future in as_completed(futures):
            try:
                for player in future.result():
                    player_id = player["id"]
                    if player_id in seen_players:
                        continue
                    seen_players.add(player_id)
                    players.append(player)
            except Exception:
                continue
    return players


def _get_player_index() -> list[dict[str, Any]]:
    global _INDEX_CACHE
    now = time.time()
    season_year = date.today().year
    if _INDEX_CACHE and now - _INDEX_CACHE[0] < _INDEX_CACHE_TTL_SECONDS:
        return _INDEX_CACHE[1]
    players = _build_player_index(season_year)
    _INDEX_CACHE = (now, players)
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

    player_results: list[tuple[int, dict[str, Any]]] = []
    for player in _get_player_index():
        score = _match_score(q, player.get("name") or "")
        if score:
            player_results.append(
                (
                    score,
                    {
                        "id": player["id"],
                        "name": player["name"],
                        "position": player.get("position") or "",
                        "team_abbr": player.get("team_abbr") or "",
                        "team_color": player.get("team_color") or "#1a2332",
                    },
                )
            )

    player_results.sort(key=lambda item: (-item[0], item[1]["name"]))
    players = [player for _, player in player_results[:limit_players]]

    return {"teams": teams, "players": players}
