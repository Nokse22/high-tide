# utils.py
#
# Copyright 2025 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import html
import json
import os
import re
import subprocess
import threading
import time
import uuid
import logging
from contextlib import contextmanager
from gettext import gettext as _
from pathlib import Path
from typing import Any, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from gi.repository import Adw, Gdk, Gio, GLib

import tidalapi
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist
from tidalapi.media import Track, Video
from tidalapi.types import ItemOrder, OrderDirection

from .cache import HTCache

logger = logging.getLogger(__name__)

favourite_mixes: List[Mix] = []
favourite_tracks: List[Track] = []
favourite_artists: List[Artist] = []
favourite_albums: List[Album] = []
favourite_playlists: List[Playlist] = []
playlist_and_favorite_playlists: List[Playlist] = []
user_playlists: List[Playlist] = []
blocked_artists: List[Artist] = []
blocked_tracks: List[Track] = []
blocked_videos: List[Video] = []
blocked_loaded = threading.Event()


def init() -> None:
    """Initialize the utils module by setting up cache directories and global objects.

    Sets up the cache directory structure, creates necessary directories,
    and initializes the global cache object for TIDAL API responses.
    """
    global CACHE_DIR
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache and Path(xdg_cache).name == "high-tide":
        CACHE_DIR = Path(xdg_cache)
    else:
        base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
        CACHE_DIR = base / "high-tide"
    CACHE_DIR.mkdir(exist_ok=True, parents=True)

    global IMG_DIR
    IMG_DIR = Path(CACHE_DIR, "images")
    IMG_DIR.mkdir(exist_ok=True)

    global MUSIC_DIR
    MUSIC_DIR = Path(CACHE_DIR, "music")
    MUSIC_DIR.mkdir(exist_ok=True)

    global session
    global navigation_view
    global player_object
    global toast_overlay
    global cache
    session = None
    cache = HTCache(session)


def get_alsa_devices() -> List[dict]:
    """Get ALSA devices"""
    try:
        alsa_devices = get_alsa_devices_from_aplay()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        alsa_devices = get_alsa_devices_from_proc()
    return alsa_devices


def get_alsa_devices_from_aplay() -> List[dict]:
    """Get ALSA devices from aplay -l"""
    result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)

    devices = [
        {
            "hw_device": "default",
            "name": _("Default"),
        }
    ]
    for line in result.stdout.split("\n"):
        # Example String: card 3: KA13 [FiiO KA13], device 0: USB Audio [USB Audio]
        match = re.match(
            r"^card\s+\d+:\s+([^[]+)\s+\[([^\]]+)\],\s+device\s+(\d+):\s+([^[]+)\s+\[([^\]]+)\]",
            line,
        )
        if match:
            card_short_name = match.group(1).strip()  # "KA13"
            card_full_name = match.group(2).strip()  # "FiiO KA13"
            device = int(match.group(3))  # 0
            device_short_name = match.group(4).strip()  # "USB Audio"
            device_full_name = match.group(5).strip()  # "USB Audio"

            # Persistent device string
            hw_string = f"hw:CARD={card_short_name},DEV={device}"
            devices.append(
                {
                    "hw_device": hw_string,
                    "name": f"{card_full_name} - {device_full_name} ({hw_string})",
                }
            )

    return devices


def get_alsa_devices_from_proc() -> List[dict]:
    """Get ALSA devices from files in /proc/asound"""
    cards = {}
    card_names = {}
    with open("/proc/asound/cards", "r") as f:
        for line in f:
            # Example String:  3 [KA13           ]: USB-Audio - FiiO KA13
            match = re.match(r"^\s*(\d+)\s+\[([^\]]+)\]\s*:\s*.+?\s-\s(.+)$", line)
            if match:
                index = int(match.group(1))
                shortname = match.group(2).strip()
                fullname = match.group(3).strip()
                cards[index] = fullname
                card_names[index] = shortname

    devices = [
        {
            "hw_device": "default",
            "name": _("Default"),
        }
    ]
    with open("/proc/asound/devices", "r") as f:
        for line in f:
            # Example String:  19: [ 3- 0]: digital audio playback
            match = re.match(
                r"^\s*\d+:\s+\[\s*(\d+)-\s*(\d+)\]:\s*digital audio playback", line
            )
            if match:
                card, device = int(match.group(1)), int(match.group(2))
                card_name = cards.get(card, f"Card {card}")
                short_name = card_names.get(card, f"{card}")

                # Persistent device string
                hw_string = f"hw:CARD={short_name},DEV={device}"

                devices.append(
                    {
                        "hw_device": hw_string,
                        "name": f"{card_name} ({hw_string})",
                    }
                )

    return devices


def get_artist(artist_id: str) -> Artist:
    """Get an artist object by ID from the cache.

    Args:
        artist_id: The TIDAL artist ID

    Returns:
        Artist: The artist object from TIDAL API
    """
    global cache
    return cache.get_artist(artist_id)


def get_album(album_id: str) -> Album:
    """Get an album object by ID from the cache.

    Args:
        album_id: The TIDAL album ID

    Returns:
        Album: The album object from TIDAL API
    """
    global cache
    return cache.get_album(album_id)


def get_track(track_id: str) -> Track:
    """Get a track object by ID from the cache.

    Args:
        track_id: The TIDAL track ID

    Returns:
        Track: The track object from TIDAL API
    """
    global cache
    return cache.get_track(track_id)


def get_playlist(playlist_id: str) -> Playlist:
    """Get a playlist object by ID from the cache.

    Args:
        playlist_id: The TIDAL playlist ID

    Returns:
        Playlist: The playlist object from TIDAL API
    """
    global cache
    return cache.get_playlist(playlist_id)


def get_mix(mix_id: str) -> Mix:
    """Get a mix object by ID from the cache.

    Args:
        mix_id: The TIDAL mix ID

    Returns:
        Mix: The mix object from TIDAL API
    """
    global cache
    return cache.get_mix(mix_id)


def _album_release_key(album: Album) -> tuple:
    return (album.name.casefold(), album.version or "", album.num_tracks)


def _album_version_rank(album: Album) -> tuple:
    return (
        "STEREO" in (album.audio_modes or []),
        bool(album.explicit),
        "HIRES_LOSSLESS" in (album.media_metadata_tags or []),
    )


class AlbumVersionFilter:
    """Wraps an artist album request (like Artist.get_albums) so each release
    is listed once, picking the version TIDAL shows on its own artist page:
    stereo over Dolby Atmos only, explicit over clean, then hi-res.

    TIDAL lists every version (clean, explicit, Dolby Atmos) as a separate album,
    next to each other. Since the caller's offset counts deduplicated albums, the
    API offset is tracked here instead; an offset of 0 starts over.
    """

    page_size = 50

    def __init__(self, function) -> None:
        self.function = function
        self._reset()

    def _reset(self) -> None:
        self.api_offset = 0
        self.seen = set()
        self.pending = []
        self.done = False

    def __call__(self, limit: int | None = None, offset: int = 0) -> List[Album]:
        if offset == 0:
            self._reset()

        while not self.done and len(self.pending) < (limit or self.page_size):
            albums = self.function(limit=self.page_size, offset=self.api_offset)

            if len(albums) < self.page_size:
                self.done = True
            else:
                # Versions of the last release may continue on the next page
                last_key = _album_release_key(albums[-1])
                complete = len(albums)
                while complete > 0 and _album_release_key(albums[complete - 1]) == last_key:
                    complete -= 1
                if complete > 0:
                    albums = albums[:complete]
            self.api_offset += len(albums)

            best = {}
            for album in albums:
                key = _album_release_key(album)
                if key in self.seen:
                    continue
                if key not in best or _album_version_rank(album) > _album_version_rank(best[key]):
                    best[key] = album
            self.seen.update(best)
            self.pending.extend(best.values())

        albums, self.pending = self.pending[:limit], self.pending[limit:] if limit else []
        return albums


def get_favourites() -> None:
    """Load all user favorites from TIDAL API and cache them globally.

    Retrieves and caches the user's favorite mixes, tracks, artists, albums,
    playlists, and user-created playlists for quick access throughout the app.
    """
    global favourite_mixes
    global favourite_tracks
    global favourite_artists
    global favourite_albums
    global favourite_playlists

    user = session.user

    try:
        favourite_artists = user.favorites.artists()
        favourite_tracks = user.favorites.tracks(
            order=ItemOrder.Date, 
            order_direction=OrderDirection.Descending
        )
        favourite_albums = user.favorites.albums()
        favourite_playlists = user.favorites.playlists()
        favourite_mixes = user.favorites.mixes()
        get_playlists()
    except Exception:
        logger.exception("Error while getting Favourites")

    logger.info(f"Favorite Artists: {len(favourite_artists)}")
    logger.info(f"Favorite Tracks: {len(favourite_tracks)}")
    logger.info(f"Favorite Albums: {len(favourite_albums)}")
    logger.info(f"Favorite Playlists: {len(favourite_playlists)}")
    logger.info(f"Favorite Mixes: {len(favourite_mixes)}")
    logger.info(
        f"Playlist and Favorite Playlists: {len(playlist_and_favorite_playlists)}"
    )
    logger.info(f"User Playlists: {len(user_playlists)}")


def get_playlists(fresh: bool = False) -> None:
    """Load the user's playlists, and their playlists plus favorite playlists.

    Args:
        fresh: Bypass the API disk cache, e.g. after a playlist was changed
    """
    if fresh:
        with _fresh_api_requests():
            _load_playlists()
    else:
        _load_playlists()


def _load_playlists() -> None:
    global playlist_and_favorite_playlists
    global user_playlists

    user = session.user

    user_playlists = user.playlists()

    count = user.favorites.get_playlists_count()
    limit = 50
    offset = 0
    pages = []

    while offset < count:
        pages += user.playlist_and_favorite_playlists(offset=offset)
        offset += limit

    playlist_and_favorite_playlists = pages


def is_favourited(item: Any) -> bool:
    """Check if a TIDAL item is in the user's favorites.

    Args:
        item: A TIDAL object (Track, Mix, Album, Artist, or Playlist)

    Returns:
        bool: True if the item is favorited, False otherwise
    """
    global favourite_mixes
    global favourite_tracks
    global favourite_artists
    global favourite_albums
    global favourite_playlists

    if isinstance(item, Track):
        for fav in favourite_tracks:
            if fav.id == item.id:
                return True
    elif isinstance(item, Mix):
        for fav in favourite_mixes:
            if fav.id == item.id:
                return True
    elif isinstance(item, Album):
        for fav in favourite_albums:
            if fav.id == item.id:
                return True
    elif isinstance(item, Artist):
        for fav in favourite_artists:
            if fav.id == item.id:
                return True
    elif isinstance(item, Playlist):
        for fav in favourite_playlists:
            if fav.id == item.id:
                return True

    return False


def get_blocked() -> None:
    """Load the artists, tracks and videos the user blocked from TIDAL API.

    TIDAL leaves blocked items out of mixes and radio, but they still show up
    everywhere else, so High Tide keeps the lists to show and undo blocks.
    """
    global blocked_artists
    global blocked_tracks
    global blocked_videos

    try:
        # Blocks change when the user blocks or unblocks something, so don't
        # serve these from the API disk cache
        with _fresh_api_requests():
            blocked_artists = _get_blocked_items("artists", session.parse_artist)
            blocked_tracks = _get_blocked_items("tracks", session.parse_track)
            blocked_videos = _get_blocked_items("videos", session.parse_video)
    except Exception:
        logger.exception("Error while getting blocked items")

    blocked_loaded.set()

    logger.info(f"Blocked Artists: {len(blocked_artists)}")
    logger.info(f"Blocked Tracks: {len(blocked_tracks)}")
    logger.info(f"Blocked Videos: {len(blocked_videos)}")


def _get_blocked_items(item_type: str, parse: Any) -> List[Any]:
    items = []
    offset = 0
    limit = 50

    while True:
        page = session.request.request(
            "GET",
            f"users/{session.user.id}/blocks/{item_type}",
            params={"limit": limit, "offset": offset},
        ).json()
        items += [parse(entry["item"]) for entry in page["items"]]
        offset += limit
        if offset >= page["totalNumberOfItems"]:
            return items


def _get_block_type(item: Any) -> str | None:
    if isinstance(item, Track):
        return "track"
    if isinstance(item, Video):
        return "video"
    if isinstance(item, Artist):
        return "artist"
    return None


def _get_blocked_list(item: Any) -> List[Any]:
    if isinstance(item, Track):
        return blocked_tracks
    if isinstance(item, Video):
        return blocked_videos
    return blocked_artists


def is_blocked(item: Any) -> bool:
    """Check if an artist, track or video was blocked by the user.

    Args:
        item: A TIDAL Artist, Track or Video

    Returns:
        bool: True if the item itself is blocked
    """
    if _get_block_type(item) is None:
        return False

    return any(blocked.id == item.id for blocked in _get_blocked_list(item))


def is_blocked_by_artist(item: Any) -> bool:
    """Check if a track or video is blocked, directly or through one of its artists.

    Args:
        item: A TIDAL Track or Video

    Returns:
        bool: True if the item or any of its artists is blocked
    """
    if is_blocked(item):
        return True

    artists = getattr(item, "artists", None) or []
    return any(is_blocked(artist) for artist in artists)


def is_hidden_by_block(item: Any) -> bool:
    """Check if an item should be left out of suggestions because of a block.

    Args:
        item: A TIDAL object

    Returns:
        bool: True for blocked artists, and tracks, videos and albums that are
            blocked or by a blocked artist
    """
    if isinstance(item, Artist):
        return is_blocked(item)
    if isinstance(item, (Track, Video)):
        return is_blocked_by_artist(item)
    if isinstance(item, Album):
        artists = item.artists or [item.artist]
        return any(artist and is_blocked(artist) for artist in artists)
    return False


def th_block(item: Any, callback: Any = None) -> None:
    """Thread function to block an artist, track or video on TIDAL.

    Args:
        item: A TIDAL Artist, Track or Video
        callback: Called on the main thread with True after the item is blocked
    """
    item_type = _get_block_type(item)

    try:
        session.request.request(
            "POST",
            f"users/{session.user.id}/blocks/{item_type}s",
            data={f"{item_type}Id": item.id},
        )
    except Exception:
        logger.exception(f"Failed to block {item_type} {item.id}")
        GLib.idle_add(send_toast, _("Failed to block"), 2)
        return

    GLib.idle_add(_on_blocked_changed, item, True, callback)


def th_unblock(item: Any, callback: Any = None) -> None:
    """Thread function to unblock an artist, track or video on TIDAL.

    Args:
        item: A TIDAL Artist, Track or Video
        callback: Called on the main thread with False after the item is unblocked
    """
    item_type = _get_block_type(item)

    try:
        session.request.request(
            "DELETE", f"users/{session.user.id}/blocks/{item_type}s/{item.id}"
        )
    except Exception:
        logger.exception(f"Failed to unblock {item_type} {item.id}")
        GLib.idle_add(send_toast, _("Failed to unblock"), 2)
        return

    GLib.idle_add(_on_blocked_changed, item, False, callback)


def _on_blocked_changed(item: Any, blocked: bool, callback: Any) -> None:
    blocked_list = _get_blocked_list(item)
    blocked_list[:] = [other for other in blocked_list if other.id != item.id]

    if blocked:
        blocked_list.append(item)
        send_toast(_("Blocked {}").format(item.name), 2)
        player_object.skip_blocked()
    else:
        send_toast(_("Unblocked {}").format(item.name), 2)

    if callback:
        callback(blocked)


def fill_block_menu(menu: Gio.Menu, track: Track, action_prefix: str) -> None:
    """Fill a menu with block/unblock items for a track and its artists.

    The items use the actions {action_prefix}.toggle-block-track (no target) and
    {action_prefix}.toggle-block-artist (int16 index into the track's artists).

    Args:
        menu: The menu to fill, its items are replaced
        track: The track the items are for
        action_prefix: The action group prefix, e.g. "win"
    """
    menu.remove_all()

    menu.append(
        _("Unblock track") if is_blocked(track) else _("Block track"),
        f"{action_prefix}.toggle-block-track",
    )

    artists = get_track_artists(track)
    if len(artists) == 1:
        item = Gio.MenuItem.new(
            _("Unblock artist") if is_blocked(artists[0]) else _("Block artist"),
            None,
        )
        item.set_action_and_target_value(
            f"{action_prefix}.toggle-block-artist", GLib.Variant.new_int16(0)
        )
        menu.append_item(item)
        return

    artists_submenu = Gio.Menu()
    for index, artist in enumerate(artists):
        label = _("Unblock {}") if is_blocked(artist) else _("Block {}")
        item = Gio.MenuItem.new(label.format(artist.name), None)
        item.set_action_and_target_value(
            f"{action_prefix}.toggle-block-artist", GLib.Variant.new_int16(index)
        )
        artists_submenu.append_item(item)
    menu.append_submenu(_("Block artist"), artists_submenu)


def get_track_artists(track: Track) -> List[Artist]:
    """Get the artists of a track, falling back to its main artist."""
    return track.artists or [track.artist]


def toggle_blocked(item: Any, callback: Any = None) -> None:
    """Block or unblock an item depending on its current state.

    Args:
        item: A TIDAL Artist, Track or Video
        callback: Called on the main thread with the new blocked state
    """
    target = th_unblock if is_blocked(item) else th_block
    threading.Thread(target=target, args=(item, callback)).start()


def send_toast(toast_title: str, timeout: int) -> None:
    """Display a toast notification to the user.

    Args:
        toast_title (str): The message to display in the toast
        timeout (int): Duration in seconds before the toast disappears
    """
    toast_overlay.add_toast(Adw.Toast(title=toast_title, timeout=timeout))


def th_add_to_my_collection(btn: Any, item: Any) -> None:
    """Thread function to add a TIDAL item to the user's favorites.

    Args:
        btn: The favorite button widget (for UI updates)
        item: The TIDAL item to add to favorites
    """
    if isinstance(item, Track):
        result = session.user.favorites.add_track(str(item.id))
    elif isinstance(item, Mix):
        return  # still not supported
        result = session.user.favorites.add_mix(str(item.id))
    elif isinstance(item, Album):
        result = session.user.favorites.add_album(str(item.id))
    elif isinstance(item, Artist):
        result = session.user.favorites.add_artist(str(item.id))
    elif isinstance(item, Playlist):
        result = session.user.favorites.add_playlist(str(item.id))
    else:
        result = False

    if result:
        GLib.idle_add(btn.set_icon_name, "heart-filled-symbolic")
        GLib.idle_add(send_toast, _("Successfully added to my collection"), 2)
        get_favourites()
    else:
        GLib.idle_add(send_toast, _("Failed to add item to my collection"), 2)


def th_remove_from_my_collection(btn: Any, item: Any) -> None:
    """Thread function to remove a TIDAL item from the user's favorites.

    Args:
        btn: The favorite button widget (for UI updates)
        item: The TIDAL item to remove from favorites
    """
    if isinstance(item, Track):
        result = session.user.favorites.remove_track(str(item.id))
    elif isinstance(item, Mix):
        return  # still not supported
        result = session.user.favorites.remove_mix(str(item.id))
    elif isinstance(item, Album):
        result = session.user.favorites.remove_album(str(item.id))
    elif isinstance(item, Artist):
        result = session.user.favorites.remove_artist(str(item.id))
    elif isinstance(item, Playlist):
        result = session.user.favorites.remove_playlist(str(item.id))
    else:
        result = False

    if result:
        GLib.idle_add(btn.set_icon_name, "heart-outline-thick-symbolic")
        GLib.idle_add(send_toast, _("Successfully removed from my collection"), 2)
    else:
        GLib.idle_add(send_toast, _("Failed to remove item from my collection"), 2)


def on_in_to_my_collection_button_clicked(btn: Any, item: Any) -> None:
    """Handle favorite/unfavorite button clicks by starting appropriate thread.

    Args:
        btn: The favorite button that was clicked
        item: The TIDAL item to add or remove from favorites
    """
    if btn.get_icon_name() == "heart-outline-thick-symbolic":
        threading.Thread(target=th_add_to_my_collection, args=(btn, item)).start()
    else:
        threading.Thread(target=th_remove_from_my_collection, args=(btn, item)).start()


def is_own_playlist(playlist: Any) -> bool:
    """Check if a playlist was made by the logged in user, so it can be edited.

    Args:
        playlist: A TIDAL Playlist

    Returns:
        bool: True if the user created the playlist
    """
    if isinstance(playlist, UserPlaylist):
        return True
    if not isinstance(playlist, Playlist) or playlist.creator is None:
        return False
    return str(playlist.creator.id) == str(session.user.id)


def _get_fresh_user_playlist(playlist: Playlist) -> UserPlaylist:
    # Loads the playlist again, so edits use its current etag and track count
    # (add() inserts at num_tracks, so an old count puts tracks in the middle)
    fresh = UserPlaylist(session, playlist.id)
    cache.playlists[str(playlist.id)] = fresh
    return fresh


def _on_playlists_changed() -> None:
    get_playlists(fresh=True)
    GLib.idle_add(_update_collection_page)


def _update_collection_page() -> None:
    page = navigation_view.find_page("collection")
    if page:
        page.update_playlists()


def th_add_to_playlist(playlist: Playlist, track: Track) -> None:
    """Thread function to add a track at the end of one of the user's playlists.

    Args:
        playlist: The playlist to add the track to
        track: The track to add
    """
    try:
        with _fresh_api_requests():
            added = _get_fresh_user_playlist(playlist).add([str(track.id)])
    except Exception:
        logger.exception(f"Failed to add {track.id} to playlist {playlist.id}")
        GLib.idle_add(send_toast, _("Failed to add to playlist"), 2)
        return

    if added:
        GLib.idle_add(send_toast, _("Added to {}").format(playlist.name), 2)
    else:
        GLib.idle_add(send_toast, _("Already in {}").format(playlist.name), 2)


def th_remove_from_playlist(
    playlist: Playlist, track: Track, index: int | None, callback: Any = None
) -> None:
    """Thread function to remove a track from one of the user's playlists.

    Args:
        playlist: The playlist to remove the track from
        track: The track to remove
        index: The position of the track in the playlist, if known
        callback: Called on the main thread after the track is removed
    """
    try:
        with _fresh_api_requests():
            fresh = _get_fresh_user_playlist(playlist)
            at_index = (
                fresh.tracks(limit=1, offset=index) if index is not None else []
            )
            if at_index and at_index[0].id == track.id:
                removed = fresh.remove_by_index(index)
            else:
                removed = fresh.remove_by_id(str(track.id))
    except Exception:
        logger.exception(f"Failed to remove {track.id} from playlist {playlist.id}")
        removed = False

    if not removed:
        GLib.idle_add(send_toast, _("Failed to remove from playlist"), 2)
        return

    GLib.idle_add(send_toast, _("Removed from {}").format(playlist.name), 2)
    if callback:
        GLib.idle_add(callback)


def new_playlist(track: Track | None = None) -> None:
    """Ask for a name and description and create a new playlist.

    Args:
        track: A track to add to the new playlist
    """
    from ..new_playlist import NewPlaylistWindow

    dialog = NewPlaylistWindow()

    def on_create(dialog, title, description):
        dialog.close()
        threading.Thread(
            target=th_create_playlist, args=(title, description, track)
        ).start()

    dialog.connect("create-playlist", on_create)
    dialog.present(navigation_view.get_root())


def th_create_playlist(
    title: str, description: str, track: Track | None = None
) -> None:
    """Thread function to create a playlist and optionally add a track to it.

    Args:
        title: The playlist title
        description: The playlist description
        track: A track to add to the new playlist
    """
    try:
        playlist = session.user.create_playlist(title, description)
        if track:
            playlist.add([str(track.id)])
    except Exception:
        logger.exception("Failed to create playlist")
        GLib.idle_add(send_toast, _("Failed to create playlist"), 2)
        return

    if track:
        GLib.idle_add(send_toast, _("Added to {}").format(title), 2)
    else:
        GLib.idle_add(send_toast, _("Created {}").format(title), 2)
    _on_playlists_changed()


def th_edit_playlist(
    playlist: Playlist, title: str, description: str, callback: Any = None
) -> None:
    """Thread function to change the title and description of a playlist.

    Args:
        playlist: The playlist to edit
        title: The new title
        description: The new description
        callback: Called on the main thread with the edited playlist
    """
    try:
        with _fresh_api_requests():
            fresh = _get_fresh_user_playlist(playlist)
            if not fresh.edit(title, description):
                raise RuntimeError("edit failed")
            fresh = _get_fresh_user_playlist(playlist)
    except Exception:
        logger.exception(f"Failed to edit playlist {playlist.id}")
        GLib.idle_add(send_toast, _("Failed to save the playlist"), 2)
        return

    if callback:
        GLib.idle_add(callback, fresh)
    _on_playlists_changed()


def th_set_playlist_public(
    playlist: Playlist, public: bool, callback: Any = None
) -> None:
    """Thread function to make a playlist public or private.

    Args:
        playlist: The playlist to change
        public: True to make it public, False to make it private
        callback: Called on the main thread with the changed playlist
    """
    try:
        with _fresh_api_requests():
            fresh = _get_fresh_user_playlist(playlist)
            if public:
                fresh.set_playlist_public()
            else:
                fresh.set_playlist_private()
    except Exception:
        logger.exception(f"Failed to change playlist {playlist.id} visibility")
        GLib.idle_add(send_toast, _("Failed to change the playlist"), 2)
        return

    if public:
        GLib.idle_add(send_toast, _("{} is now public").format(fresh.name), 2)
    else:
        GLib.idle_add(send_toast, _("{} is now private").format(fresh.name), 2)
    if callback:
        GLib.idle_add(callback, fresh)


def th_delete_playlist(playlist: Playlist, callback: Any = None) -> None:
    """Thread function to delete one of the user's playlists.

    Args:
        playlist: The playlist to delete
        callback: Called on the main thread after the playlist is deleted
    """
    try:
        with _fresh_api_requests():
            if not _get_fresh_user_playlist(playlist).delete():
                raise RuntimeError("delete failed")
    except Exception:
        logger.exception(f"Failed to delete playlist {playlist.id}")
        GLib.idle_add(send_toast, _("Failed to delete the playlist"), 2)
        return

    cache.playlists.pop(str(playlist.id), None)
    GLib.idle_add(send_toast, _("Deleted {}").format(playlist.name), 2)
    if callback:
        GLib.idle_add(callback)
    _on_playlists_changed()


def share_this(item: Any) -> None:
    """Copy a TIDAL item's share URL to the system clipboard.

    Args:
        item: A TIDAL object with a share_url attribute
    """
    clipboard: Gdk.Clipboard = Gdk.Display().get_default().get_clipboard()

    share_url: str | None = None

    if isinstance(item, Track):
        share_url = item.share_url
    elif isinstance(item, Album):
        share_url = item.share_url
    elif isinstance(item, Artist):
        share_url = item.share_url
    elif isinstance(item, Playlist):
        share_url = item.share_url
    else:
        return

    if share_url:
        clipboard.set(share_url + "?u")

        send_toast(_("Copied share URL in the clipboard"), 2)


def get_type(item: Any) -> str:
    """Get the string type identifier for a TIDAL item.

    Args:
        item: A TIDAL object (Track, Mix, Album, Artist, or Playlist)

    Returns:
        str: The type as a lowercase string ("track", "mix", "album", "artist", or "playlist")
    """
    if isinstance(item, Track):
        return "track"
    elif isinstance(item, Mix):
        return "mix"
    elif isinstance(item, Album):
        return "album"
    elif isinstance(item, Artist):
        return "artist"
    elif isinstance(item, Playlist):
        return "playlist"


def push_page(tag: str, page_factory) -> None:
    """Push a page, reusing it if one with the same tag is already open.

    If a page with the given tag is in the navigation stack, pop back to it
    instead of pushing a duplicate. The tag should be unique per entity
    (e.g. "album-123") so the same entity reuses one page however it's opened.

    Args:
        tag: A unique tag identifying the page (type and id)
        page_factory: A callable that builds and returns the page to push
    """
    if navigation_view.find_page(tag):
        navigation_view.pop_to_tag(tag)
        return

    page = page_factory()
    page.set_tag(tag)
    navigation_view.push(page)


def open_uri(label: str, uri: str) -> bool:
    """Open a URI by navigating to the appropriate page in the application.

    Args:
        label: Display label for the URI (currently unused)
        uri: A URI string in format "type:id" (e.g., "artist:123456")
    """
    from ..pages import HTAlbumPage, HTArtistPage
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            id = uri_parts[1]
            push_page(f"artist-{id}", lambda: HTArtistPage.new_from_id(id).load())
        case "album":
            id = uri_parts[1]
            push_page(f"album-{id}", lambda: HTAlbumPage.new_from_id(id).load())

    # TODO implement the rest?
    return True


def open_tidal_uri(uri: str) -> None:
    """Handles opening uri like tidal://track/1234"""
    from ..pages import HTAlbumPage, HTArtistPage, HTMixPage, HTPlaylistPage

    if not uri.startswith("tidal://"):
        raise ValueError("Invalid URI format: URI must start with 'tidal://'")

    uri_parts = uri[8:].split("/")

    if len(uri_parts) < 2:
        raise ValueError(f"Invalid URI format: {uri}")

    content_type = uri_parts[0].lower()
    content_id = uri_parts[1]

    if not content_id:
        raise ValueError(f"Invalid content ID in URI: {uri}")

    match content_type:
        case "artist":
            push_page(
                f"artist-{content_id}",
                lambda: HTArtistPage.new_from_id(content_id).load(),
            )
        case "album":
            push_page(
                f"album-{content_id}",
                lambda: HTAlbumPage.new_from_id(content_id).load(),
            )
        case "track":
            threading.Thread(target=th_play_track, args=(content_id,)).start()
        case "mix":
            push_page(f"mix-{content_id}", lambda: HTMixPage(content_id).load())
        case "playlist":
            push_page(
                f"playlist-{content_id}",
                lambda: HTPlaylistPage(content_id).load(),
            )
        case _:
            logger.warning(f"Unsupported content type: {content_type}")
            return False


def th_play_track(track_id: str) -> None:
    """Thread function to play a specific track by ID.

    Args:
        track_id: The TIDAL track ID to play
    """
    track: Track = session.track(track_id)

    GLib.idle_add(player_object.play_this, [track])


def pretty_duration(secs: int | None) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        secs (int): Duration in seconds

    Returns:
        str: Formatted duration string (MM:SS or HH:MM:SS for durations over an hour)
    """
    if not secs:
        return "00:00"

    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60

    if hours > 0:
        return f"{int(hours)}:{int(minutes):02}:{int(seconds):02}"
    else:
        return f"{int(minutes):02}:{int(seconds):02}"

    return "00:00"


def get_best_dimensions(widget: Any) -> int:
    """Determine the best image dimensions for a widget.

    Args:
        widget: A GTK widget to measure

    Returns:
        int: The best image dimension from available sizes (80, 160, 320, 640, 1280)
    """
    edge = widget.get_height()
    dimensions = [80, 160, 320, 640, 1280]
    # The function for fractional scaling is not available in GTKWidget
    scale = 1.0
    native = widget.get_native()
    if native:
        surface = native.get_surface()
        if surface:
            scale = surface.get_scale()
    return next((x for x in dimensions if x > (edge * scale)), dimensions[-1])


def get_image_url(item: Any, dimensions: int = 320) -> str | None:
    """Get the local file path for an item's image, downloading if necessary.

    Args:
        item: A TIDAL object with image data
        dimensions (int): The desired image dimensions (default: 320)

    Returns:
        str: Path to the local image file, or None if download failed
    """
    if hasattr(item, "id"):
        file_path = IMG_DIR / f"{item.id}_{dimensions}.jpg"
    else:
        file_path = IMG_DIR / f"{uuid.uuid4()}_{dimensions}.jpg"

    if file_path.is_file():
        return str(file_path)

    try:
        picture_url = item.image(dimensions=dimensions)
        response = requests.get(picture_url)
    except Exception:
        logger.exception("Could not get image")
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_picture(
    widget: Any,
    item: Any,
    dimensions: int,
    cancellable: Gio.Cancellable = Gio.Cancellable.new(),
) -> None:
    """Retrieve and set an image for a widget from a TIDAL item.

    Downloads the image if necessary and sets it on the widget using set_filename().

    Args:
        widget: A GTK widget that supports set_filename()
        item: A TIDAL object with image data
        dimensions (int): The image dimensions to download
        cancellable: Optional GCancellable for canceling the operation
    """

    if cancellable is None:
        cancellable = Gio.Cancellable.new()

    def _add_picture(widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            widget.set_filename(file_path)

    GLib.idle_add(
        _add_picture,
        widget,
        get_image_url(item, dimensions),
        cancellable,
    )


def add_image(
    widget: Any, item: Any, cancellable: Gio.Cancellable = Gio.Cancellable.new()
) -> None:
    """Retrieve and set an image for a widget from a TIDAL item.

    Downloads the image if necessary and sets it on the widget using set_from_file().

    Args:
        widget: A GTK widget that supports set_from_file()
        item: A TIDAL object with image data
        cancellable: Optional GCancellable for canceling the operation
    """

    def _add_image(
        widget: Any, file_path: str | None, cancellable: Gio.Cancellable
    ) -> None:
        if not cancellable.is_cancelled():
            widget.set_from_file(file_path)

    GLib.idle_add(_add_image, widget, get_image_url(item), cancellable)


def get_video_cover_url(item: Any, dimensions: int = 320) -> str | None:
    """Get the local file path for an item's video cover, downloading if necessary.

    Args:
        item: A TIDAL object with video data
        dimensions (int): The desired video dimensions (default: 640)

    Returns:
        str: Path to the local video file, or None if download failed
    """
    if hasattr(item, "id"):
        file_path = IMG_DIR / f"{item.id}_{dimensions}.mp4"
    else:
        file_path = IMG_DIR / f"{uuid.uuid4()}_{dimensions}.mp4"

    if file_path.is_file():
        return str(file_path)

    try:
        video_url = item.video(dimensions=dimensions)
        response = requests.get(video_url)
    except Exception:
        logger.exception("Could not get video")
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_video_cover(
    widget: Any,
    videoplayer: Any,
    item: Any,
    dimensions: int,
    in_bg: bool,
    cancellable: Gio.Cancellable = Gio.Cancellable.new(),
) -> None:
    """Retrieve and set a video cover for a video player widget from a TIDAL item.

    Downloads the video if necessary and configures the video player.

    Args:
        widget: The container widget
        videoplayer: The GtkMediaFile
        item: A TIDAL object with video data
        dimensions (int): The video dimensions to download
        in_bg (bool): Whether the window is currently in background (not in focus)
        cancellable: Optional GCancellable for canceling the operation
    """

    if cancellable is None:
        cancellable = Gio.Cancellable.new()

    def _add_video_cover(
        widget: Any,
        videoplayer: Any,
        file_path: str | None,
        in_bg: bool,
        cancellable: Gio.Cancellable,
    ) -> None:
        if not cancellable.is_cancelled() and file_path:
            videoplayer.set_loop(True)
            videoplayer.set_filename(file_path)
            widget.set_paintable(videoplayer)
            if not in_bg:
                videoplayer.play()

    GLib.idle_add(
        _add_video_cover,
        widget,
        videoplayer,
        get_video_cover_url(item, dimensions),
        in_bg,
        cancellable,
    )


def add_image_to_avatar(
    widget: Any, item: Any, cancellable: Gio.Cancellable = Gio.Cancellable.new()
) -> None:
    """Retrieve and set an image for an Adwaita Avatar widget from a TIDAL item.

    Args:
        widget: An Adw.Avatar widget
        item: A TIDAL object with image data
        cancellable: Optional GCancellable for canceling the operation
    """

    def _add_image_to_avatar(
        avatar_widget: Any, file_path: str | None, cancellable: Gio.Cancellable
    ) -> None:
        if not cancellable.is_cancelled():
            file = Gio.File.new_for_path(file_path)
            image = Gdk.Texture.new_from_file(file)
            widget.set_custom_image(image)

    GLib.idle_add(_add_image_to_avatar, widget, get_image_url(item), cancellable)


def replace_links(text: str) -> str:
    """Replace TIDAL wimpLink tags in text with clickable HTML links.

    Converts [wimpLink artistId="123"]Artist Name[/wimpLink] format links
    to proper HTML anchor tags for display in markup-enabled widgets.

    Args:
        text (str): Input text containing wimpLink tags

    Returns:
        str: HTML-escaped text with wimpLink tags converted to anchor tags
    """
    # Define regular expression pattern to match [wimpLink ...]...[/wimpLink] tags
    pattern = r"\[wimpLink (artistId|albumId)=&quot;(\d+)&quot;\]([^[]+)\[\/wimpLink\]"

    # Escape HTML in the entire text
    escaped_text = html.escape(text)

    # Define a function to replace the matched pattern with the desired format
    def replace(match_obj: Any) -> str:
        link_type = match_obj.group(1)
        id_value = match_obj.group(2)
        label = match_obj.group(3)

        if link_type == "artistId":
            return f'<a href="artist:{id_value}">{label}</a>'
        elif link_type == "albumId":
            return f'<a href="album:{id_value}">{label}</a>'
        else:
            return label

    # Replace <br/> with two periods
    escaped_text = escaped_text.replace("&lt;br/&gt;", "\n")

    # Use re.sub() to perform the replacement
    replaced_text = re.sub(pattern, replace, escaped_text)

    return replaced_text


#
#   HOME PAGE DISK CACHE
#


class _ApiCache:
    """Disk cache for TIDAL API GET responses (see ADR 0001)."""

    max_age = 24 * 60 * 60

    def __init__(self, cache_dir: Path):
        self.root = Path(cache_dir) / "api"
        self.root.mkdir(parents=True, exist_ok=True)
        self.user_id: str | None = None
        self._original_request = None
        # Set per thread when requests must not be served from the cache
        self._local = threading.local()

    @contextmanager
    def fresh_requests(self):
        """Bypass the cache for requests made from this thread in the block."""
        previous = getattr(self._local, "bypass", False)
        self._local.bypass = True
        try:
            yield
        finally:
            self._local.bypass = previous

    def install(self, request_session: requests.Session) -> None:
        self._original_request = request_session.request

        def cached_request(method, url, **kwargs):
            cacheable = self._cacheable(method, url)
            bypass = getattr(self._local, "bypass", False)
            if not cacheable or bypass:
                response = self._original_request(method, url, **kwargs)
                if cacheable and response.status_code == 200:
                    # Refresh the cache with the fresh response
                    self._write(self._path(url, kwargs.get("params")), response)
                return response

            path = self._path(url, kwargs.get("params"))
            cached = self._read(path)
            if cached is not None:
                return self._response(url, cached)

            response = self._original_request(method, url, **kwargs)
            if response.status_code == 200:
                self._write(path, response)
            return response

        request_session.request = cached_request

    def _cacheable(self, method, url) -> bool:
        return (
            method.upper() == "GET"
            and "api.tidal.com" in url
            and "playbackinfo" not in url
        )

    def _path(self, url, params) -> Path:
        raw = f"{url}|{sorted((params or {}).items())}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
        user_dir = self.root / (self.user_id or "anon")
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{digest}.json"

    def _read(self, path: Path) -> dict | None:
        try:
            with open(path) as f:
                envelope = json.load(f)
            if time.time() - envelope["ts"] > self.max_age:
                return None
            return {"body": envelope["body"], "headers": envelope.get("headers", {})}
        except Exception:
            return None

    def _write(self, path: Path, response: requests.Response) -> None:
        try:
            headers = {k: v for k, v in response.headers.items()}
            with open(path, "w") as f:
                json.dump({"ts": time.time(), "body": response.text, "headers": headers}, f)
        except Exception:
            logger.exception("Could not write API cache")

    def _response(self, url: str, cached: dict) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = cached["body"].encode()
        response.headers = requests.structures.CaseInsensitiveDict(cached.get("headers", {}))
        response.request = requests.PreparedRequest()
        response.request.url = url
        return response


def _api_cache():
    request_session = getattr(session, "request_session", None)
    return getattr(request_session, "_api_cache", None)


def set_cache_user(user_id: str | None) -> None:
    cache = _api_cache()
    if cache is not None and user_id is not None:
        cache.user_id = user_id


@contextmanager
def _fresh_api_requests():
    """Bypass the API disk cache for requests made in the block.

    Used after changing playlists or blocks, where the cached GET responses
    would still describe the old state.
    """
    cache = _api_cache()
    if cache is None:
        yield
    else:
        with cache.fresh_requests():
            yield


def create_tidal_session():
    tidal_session = tidalapi.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    request_session = tidal_session.request_session
    request_session.mount("https://", HTTPAdapter(max_retries=retry))
    api_cache = _ApiCache(CACHE_DIR)
    api_cache.install(request_session)
    request_session._api_cache = api_cache
    return tidal_session


def setup_logging():
    global CACHE_DIR

    log_to_file = os.getenv("LOG_TO_FILE")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    handlers = []
    if log_to_file:
        handlers.append(logging.FileHandler(CACHE_DIR + "/high-tide.log"))
    handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )

def evict_cache(cache_dir, max_gb):
    if not cache_dir or not cache_dir.exists():
        return

    max_bytes = max_gb * 1024 ** 3
    files = sorted(
        cache_dir.iterdir(),
        key=lambda f: f.stat().st_atime
    )
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= max_bytes:
            break
        total -= f.stat().st_size
        f.unlink()
        logger.info(f"Evicted from cache: {f.name}")
