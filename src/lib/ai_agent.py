# ai_agent.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import threading
from gettext import gettext as _

from tidalapi.media import Track
from tidalapi.artist import Artist

from . import utils
from .ai_providers import (
    call_anthropic,
    call_gemini,
    call_ollama,
    call_openai,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a music curation assistant. Generate TIDAL search queries to build "
    "a personalized radio station.\n\n"
    "Respond with JSON only — no markdown fences, no prose:\n\n"
    "{\n"
    '  "title": "Human-readable radio title",\n'
    '  "strategy": "search",\n'
    '  "search_queries": ["query1", "query2"],\n'
    '  "playlist_names": [],\n'
    '  "suggestions": ["More energetic", "Earlier era", "Add more variety", "Slower tempo"],\n'
    '  "quality_criteria": {\n'
    '    "decade": "",\n'
    '    "energy": "",\n'
    '    "genres": []\n'
    "  }\n"
    "}\n\n"
    "Rules:\n"
    "- Maximum 5 search_queries\n"
    "- Maximum 3 playlist_names (use names from user context when strategy is playlist)\n"
    "- Maximum 4 suggestions — phrase as follow-up instructions, not descriptions\n"
    '- quality_criteria.decade: format "1990s" / "2000s", or "" if not applicable\n'
    '- quality_criteria.energy: "high" / "medium" / "low", or ""\n'
    "- quality_criteria.genres: list of genre strings"
)

_MAX_HISTORY_TURNS = 8


def _call_provider(
    messages: list,
    provider: str,
    api_key: str,
    model: str,
    cancel_event: threading.Event,
    base_url: str = "",
    system: str = "",
) -> str:
    logger.debug("Calling provider=%s model=%s turns=%d", provider, model, len(messages))
    match provider:
        case "openai":
            return call_openai(messages, api_key, model, cancel_event, system=system)
        case "anthropic":
            return call_anthropic(messages, api_key, model, cancel_event, system=system)
        case "gemini":
            return call_gemini(messages, api_key, model, cancel_event, system=system)
        case "ollama":
            return call_ollama(messages, model, base_url, cancel_event, system=system)
        case _:
            raise ValueError(f"Unknown provider: {provider}")


def _parse_response(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(lines[1:])
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]

    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object in LLM response")

    data = json.loads(stripped[start:end])
    for key in ("title", "search_queries"):
        if key not in data:
            raise ValueError(f"Missing required key: {key}")

    data["search_queries"] = data.get("search_queries", [])[:5]
    data["playlist_names"] = data.get("playlist_names", [])[:3]
    data["suggestions"] = data.get("suggestions", [])[:4]
    logger.debug(
        "Parsed response: title=%r queries=%s playlists=%s",
        data.get("title"),
        data["search_queries"],
        data["playlist_names"],
    )
    return data


def _build_user_message(
    prompt: str,
    playlists=None,
    favourite_artists=None,
    favourite_tracks=None,
) -> str:
    parts = [f"Request: {prompt}"]

    if favourite_artists:
        names = [a.name for a in favourite_artists[:20] if hasattr(a, "name")]
        if names:
            parts.append(f"Favourite artists: {', '.join(names)}")

    if favourite_tracks:
        entries = [
            f"{t.name} by {t.artist.name}"
            for t in favourite_tracks[:30]
            if hasattr(t, "name") and hasattr(t, "artist") and t.artist
        ]
        if entries:
            parts.append(f"Favourite tracks: {', '.join(entries)}")

    if playlists:
        pl_names = [p.name for p in playlists if hasattr(p, "name")]
        if pl_names:
            parts.append(f"User playlists: {', '.join(pl_names)}")

    return "\n\n".join(parts)


def _resolve_seeds(
    search_queries: list,
    playlist_names: list,
    cancel_event: threading.Event,
) -> list:
    seeds = []
    seen_ids: set = set()

    for query in search_queries[:5]:
        if cancel_event.is_set():
            break
        try:
            results = utils.session.search(query, [Track, Artist], limit=5)
            seed = None
            top_hit = results.get("top_hit")
            if isinstance(top_hit, (Track, Artist)):
                seed = top_hit
            elif results.get("tracks"):
                seed = results["tracks"][0]
            elif results.get("artists"):
                seed = results["artists"][0]

            if seed is not None and seed.id not in seen_ids:
                logger.debug("Query %r → seed %s id=%s", query, type(seed).__name__, seed.id)
                seeds.append(seed)
                seen_ids.add(seed.id)
            else:
                logger.debug("Query %r → no usable seed", query)
        except Exception:
            logger.exception("Search failed for query: %s", query)

    for name in playlist_names[:3]:
        if cancel_event.is_set():
            break
        for playlist in utils.user_playlists:
            if hasattr(playlist, "name") and playlist.name == name:
                try:
                    pl_tracks = list(playlist.tracks())
                    if pl_tracks and pl_tracks[0].id not in seen_ids:
                        seeds.append(pl_tracks[0])
                        seen_ids.add(pl_tracks[0].id)
                except Exception:
                    logger.exception("Failed to load playlist: %s", name)
                break

    result = seeds[:5]
    logger.debug("Resolved %d seeds (capped from %d) from %d queries + %d playlist names", len(result), len(seeds), len(search_queries), len(playlist_names))
    return result


def _get_radio_tracks(seeds: list, cancel_event: threading.Event) -> list:
    all_tracks: list = []
    seen_ids: set = set()
    fallback: list = []

    for seed in seeds:
        if cancel_event.is_set():
            break
        if not isinstance(seed, (Track, Artist)):
            continue
        try:
            mix = seed.get_radio_mix()
            before = len(all_tracks)
            for track in list(mix.items())[:100]:
                if hasattr(track, "id") and track.id not in seen_ids:
                    all_tracks.append(track)
                    seen_ids.add(track.id)
            logger.debug("Seed %s added %d tracks", seed.id, len(all_tracks) - before)
        except Exception:
            logger.exception("get_radio_mix failed for seed %s", seed.id)
            if isinstance(seed, Track) and seed.artist:
                # Try the track's artist radio before giving up
                try:
                    mix = seed.artist.get_radio_mix()
                    before = len(all_tracks)
                    for track in list(mix.items())[:100]:
                        if hasattr(track, "id") and track.id not in seen_ids:
                            all_tracks.append(track)
                            seen_ids.add(track.id)
                    logger.debug("Artist fallback for track seed %s added %d tracks", seed.id, len(all_tracks) - before)
                except Exception:
                    logger.debug("Artist fallback also failed for track seed %s, using track itself", seed.id)
                    fallback.append(seed)
            elif isinstance(seed, Artist):
                # Artist radio failed — use top tracks as fallback pool
                try:
                    top = [t for t in list(seed.get_top_tracks())[:20] if hasattr(t, "id") and t.id not in seen_ids]
                    for t in top:
                        seen_ids.add(t.id)
                    fallback.extend(top)
                    logger.debug("Artist top_tracks fallback for seed %s: %d tracks", seed.id, len(top))
                except Exception:
                    logger.debug("Artist top_tracks fallback failed for seed %s", seed.id)

    result = all_tracks[:100] if all_tracks else fallback[:100]
    logger.debug("Total radio tracks: %d (fallback=%s)", len(result), not all_tracks)
    return result


def _decade_prefilter(tracks: list, quality_criteria: dict) -> list:
    decade_str = quality_criteria.get("decade", "")
    if not decade_str or len(decade_str) < 4:
        return tracks
    try:
        start_year = int(decade_str[:4])
    except ValueError:
        return tracks
    end_year = start_year + 9
    filtered = [
        t for t in tracks
        if (
            t.album
            and t.album.release_date
            and start_year <= t.album.release_date.year <= end_year
        )
    ]
    logger.debug("Decade filter %s: %d → %d tracks", decade_str, len(tracks), len(filtered) if filtered else len(tracks))
    return filtered if filtered else tracks


def _critic_filter(
    prompt: str,
    quality_criteria: dict,
    tracks: list,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
    cancel_event: threading.Event,
) -> list:
    if cancel_event.is_set() or not tracks:
        return tracks

    capped = tracks[:60]
    rows = "\n".join(
        f"{i}. {t.name} — "
        f"{getattr(t.artist, 'name', '?') if t.artist else '?'} "
        f"({t.album.release_date.year if t.album and t.album.release_date else '?'})"
        for i, t in enumerate(capped)
    )
    critic_msg = (
        f"Original request: {prompt}\n"
        f"Quality criteria: {json.dumps(quality_criteria)}\n\n"
        f"Track list:\n{rows}\n\n"
        "Return a JSON array of 0-based indices for tracks scoring 4-5/5 for "
        "relevance. Only the array, nothing else. Example: [0, 2, 5]"
    )

    try:
        response = _call_provider(
            [{"role": "user", "content": critic_msg}],
            provider,
            api_key,
            model,
            cancel_event,
            base_url=base_url,
        )
        text = response.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            return tracks
        indices = json.loads(text[start:end])
        if not isinstance(indices, list):
            return tracks
        valid = sorted(
            {i for i in indices if isinstance(i, int) and 0 <= i < len(capped)}
        )
        filtered = [capped[i] for i in valid]
        logger.debug("Critic filter: %d → %d tracks", len(capped), len(filtered) if filtered else len(tracks))
        return filtered if filtered else tracks
    except Exception:
        logger.exception("Critic pass failed, returning unfiltered list")
        return tracks


def generate_radio(
    prompt: str,
    provider: str,
    api_key: str,
    model: str,
    cancel_event: threading.Event,
    playlists=None,
    favourite_artists=None,
    favourite_tracks=None,
    conversation_history=None,
    base_url: str = "",
    use_critic: bool = False,
) -> tuple:
    """Return (title, tracks, suggestions, updated_history)."""
    logger.debug("generate_radio prompt=%r provider=%s model=%s history_turns=%d use_critic=%s", prompt, provider, model, len(conversation_history or []), use_critic)
    history = list(conversation_history or [])
    if len(history) > _MAX_HISTORY_TURNS:
        # Trim at an even boundary so history always starts with a user message.
        # Anthropic (and well-behaved providers) require alternating user/assistant
        # starting with user; an odd slice would leave a leading assistant message.
        trim = len(history) - _MAX_HISTORY_TURNS
        if trim % 2:
            trim += 1
        history = history[trim:]

    user_msg = _build_user_message(
        prompt,
        playlists=playlists,
        favourite_artists=favourite_artists,
        favourite_tracks=favourite_tracks,
    )
    messages = history + [{"role": "user", "content": user_msg}]

    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    raw = _call_provider(
        messages,
        provider,
        api_key,
        model,
        cancel_event,
        base_url=base_url,
        system=_SYSTEM_PROMPT,
    )

    # Store only the bare prompt (not the context-enriched message) so that
    # favourite artists / tracks / playlists are not re-sent on every turn.
    # Context is rebuilt fresh from the current state on each generate_radio call.
    updated_history = history + [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": raw},
    ]

    data = _parse_response(raw)
    title = data.get("title", _("AI Radio"))
    search_queries = data["search_queries"]
    playlist_names = data.get("playlist_names", [])
    suggestions = data.get("suggestions", [])
    quality_criteria = data.get("quality_criteria", {})

    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    seeds = _resolve_seeds(search_queries, playlist_names, cancel_event)

    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    tracks = _get_radio_tracks(seeds, cancel_event)

    if quality_criteria:
        tracks = _decade_prefilter(tracks, quality_criteria)

    # Critic pass: only on first generation (no history), when opted in
    if use_critic and not history:
        tracks = _critic_filter(
            prompt,
            quality_criteria,
            tracks,
            provider,
            api_key,
            model,
            base_url,
            cancel_event,
        )

    logger.debug("generate_radio done: title=%r tracks=%d suggestions=%d", title, len(tracks), len(suggestions))
    return title, tracks, suggestions, updated_history
