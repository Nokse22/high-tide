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

import html
import os
import re
import subprocess
import threading
import base64
from types import SimpleNamespace
import time
import uuid
import logging
from gettext import gettext as _
from gettext import ngettext
from pathlib import Path
from typing import Any, Callable, Dict, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import tidalapi
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.playlist import Folder, Playlist, UserPlaylist
from tidalapi.media import Track, Video

from ..pages import HTAlbumPage, HTArtistPage, HTMixPage, HTPlaylistPage
from . import ai
from .cache import HTCache

logger = logging.getLogger(__name__)

favourite_mixes: List[Mix] = []
favourite_tracks: List[Track] = []


class MyTracks:
    """The user's saved tracks, as what songs are played from (shown as Playing
    from in the player). Reported to TIDAL like songs played on their own."""

    id = "my-tracks"

    @property
    def name(self) -> str:
        return _("My Tracks")


MY_TRACKS = MyTracks()
favourite_artists: List[Artist] = []
favourite_albums: List[Album] = []
favourite_playlists: List[Playlist] = []
playlist_and_favorite_playlists: List[Playlist] = []
user_playlists: List[Playlist] = []
blocked_artists: List[Artist] = []
blocked_tracks: List[Track] = []
blocked_videos: List[Video] = []
blocked_loaded = threading.Event()
favourites_loaded = threading.Event()
# Kept, so changes to the sort settings keep being reported
_sort_settings = None
# The user's playlist folders seen so far, by id (their pages look them up here)
folders: Dict[str, Any] = {}
# Pick clean over explicit album versions (the prefer-clean-versions setting)
prefer_clean_versions = False


def init() -> None:
    """Initialize the utils module by setting up cache directories and global objects.

    Sets up the cache directory structure, creates necessary directories,
    and initializes the global cache object for TIDAL API responses.
    """
    ai.install()
    _install_artist_cover_fallback()

    global _sort_settings
    _sort_settings = Gio.Settings.new("io.github.nokse22.high-tide")
    _sort_settings.connect("changed", _on_sort_setting_changed)
    _install_row_context()
    _install_my_tracks_link()

    global CACHE_DIR
    CACHE_DIR = os.environ.get("XDG_CACHE_HOME")
    if CACHE_DIR == "" or CACHE_DIR is None or "high-tide" not in CACHE_DIR:
        CACHE_DIR = f"{os.environ.get('HOME')}/.cache/high-tide"

    CACHE_DIR = Path(CACHE_DIR)
    CACHE_DIR.mkdir(exist_ok=True)

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
        try:
            alsa_devices = get_alsa_devices_from_proc()
        except OSError:
            # No sound card, so only the default output can be offered
            logger.info("No ALSA devices found")
            alsa_devices = [{"hw_device": "default", "name": _("Default")}]
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


def album_release_key(album: Album) -> tuple:
    return (album.name.casefold(), album.version or "", album.num_tracks)


def _album_version_rank(album: Album) -> tuple:
    return (
        bool(album.explicit) != prefer_clean_versions,
        "STEREO" in (album.audio_modes or []),
        "HIRES_LOSSLESS" in (album.media_metadata_tags or []),
    )


class AlbumVersionFilter:
    """Wraps an artist album request (like Artist.get_albums) so each release
    is listed once, picking the version TIDAL shows on its own artist page:
    explicit over clean (or the other way around with the prefer-clean-versions
    setting), then stereo over Dolby Atmos only, then hi-res. TIDAL streams
    Dolby Atmos versions to High Tide in stereo, so an explicit version that only
    exists in Dolby Atmos still plays like the others.

    TIDAL lists every version (clean, explicit, Dolby Atmos) as a separate album,
    next to each other. Since the caller's offset counts deduplicated albums, the
    API offset is tracked here instead; an offset of 0 starts over.
    """

    page_size = 50

    def __init__(self, function, exclude=()) -> None:
        self.function = function
        # Releases (album_release_key) shown elsewhere, left out of this list
        self.exclude = set(exclude)
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
                last_key = album_release_key(albums[-1])
                complete = len(albums)
                while complete > 0 and album_release_key(albums[complete - 1]) == last_key:
                    complete -= 1
                if complete > 0:
                    albums = albums[:complete]
            self.api_offset += len(albums)

            best = {}
            for album in albums:
                key = album_release_key(album)
                if key in self.seen or key in self.exclude:
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

    # Each list loads on its own: one that fails keeps what it had (empty at
    # first) without leaving the others empty
    favourite_artists = _load_favourites(
        "artists", sorted_fetch("artists", user.favorites.artists), favourite_artists
    )
    favourite_tracks = _load_favourites(
        "tracks", sorted_fetch("tracks", user.favorites.tracks), favourite_tracks
    )
    favourite_albums = _load_favourites(
        "albums", sorted_fetch("albums", user.favorites.albums), favourite_albums
    )
    favourite_playlists = _load_favourites(
        "playlists", user.favorites.playlists, favourite_playlists
    )
    favourite_mixes = _load_favourites(
        "mixes", sorted_fetch("mixes", user.favorites.mixes), favourite_mixes
    )
    get_playlists()

    favourites_loaded.set()

    logger.info(f"Favorite Artists: {len(favourite_artists)}")
    logger.info(f"Favorite Tracks: {len(favourite_tracks)}")
    logger.info(f"Favorite Albums: {len(favourite_albums)}")
    logger.info(f"Favorite Playlists: {len(favourite_playlists)}")
    logger.info(f"Favorite Mixes: {len(favourite_mixes)}")
    logger.info(
        f"Playlist and Favorite Playlists: {len(playlist_and_favorite_playlists)}"
    )
    logger.info(f"User Playlists: {len(user_playlists)}")


_favourites_refresh_lock = threading.Lock()
_favourites_refresh_again = False


def refresh_favourites() -> None:
    """Load the favourites again in the background, then show them on the
    Collection page. Asked again while loading, it loads once more after."""
    global _favourites_refresh_again
    _favourites_refresh_again = True
    threading.Thread(target=_th_refresh_favourites, daemon=True).start()


def _th_refresh_favourites() -> None:
    global _favourites_refresh_again
    while _favourites_refresh_again:
        if not _favourites_refresh_lock.acquire(blocking=False):
            return  # the thread already loading picks it up
        try:
            while _favourites_refresh_again:
                _favourites_refresh_again = False
                get_favourites()
        finally:
            _favourites_refresh_lock.release()
    GLib.idle_add(_on_favourites_refreshed)


def _on_favourites_refreshed() -> None:
    _update_collection_page()
    window = navigation_view.get_root()
    if hasattr(window, "update_in_my_collection_button"):
        window.update_in_my_collection_button()


def get_playlists() -> None:
    """Load the user's playlists, and their playlists plus favorite playlists."""
    global user_playlists
    global _user_playlists_loaded_at

    user = session.user

    user_playlists = _load_favourites("user playlists", user.playlists, user_playlists)
    _user_playlists_loaded_at = time.monotonic()
    _load_playlists_and_favorite_playlists()


# How each Collection list can be sorted: the sort-<kind> setting's value, its label,
# TIDAL's order name and the direction it's shown in unless reversed. The defaults
# keep the orders shown before (TIDAL's default for albums and artists is by name).
SORTS = {
    "playlists": [
        ("created", _("Created date"), "DATE", "DESC"),
        ("updated", _("Updated date"), "DATE_UPDATED", "DESC"),
        ("name", _("Alphabetical"), "NAME", "ASC"),
    ],
    "albums": [
        ("date", _("Date added"), "DATE", "DESC"),
        ("name", _("Alphabetical"), "NAME", "ASC"),
        ("artist", _("Artist"), "ARTIST", "ASC"),
        ("release", _("Release date"), "RELEASE_DATE", "DESC"),
    ],
    "tracks": [
        ("date", _("Date added"), "DATE", "DESC"),
        ("name", _("Title"), "NAME", "ASC"),
        ("artist", _("Artist"), "ARTIST", "ASC"),
        ("album", _("Album"), "ALBUM", "ASC"),
        ("length", _("Length"), "LENGTH", "ASC"),
    ],
    "artists": [
        ("date", _("Date added"), "DATE", "DESC"),
        ("name", _("Alphabetical"), "NAME", "ASC"),
    ],
    "mixes": [
        ("date", _("Date added"), "DATE", "DESC"),
        ("name", _("Alphabetical"), "NAME", "ASC"),
        ("type", _("Mix type"), "MIX_TYPE", "ASC"),
    ],
}


def sort_order(kind: str) -> tuple:
    """TIDAL's order and direction names for a Collection list, as chosen"""
    settings = Gio.Settings.new("io.github.nokse22.high-tide")
    value = settings.get_string(f"sort-{kind}")
    order, direction = next(
        ((o, d) for v, _label, o, d in SORTS[kind] if v == value),
        SORTS[kind][0][2:],
    )
    if settings.get_boolean(f"sort-{kind}-reversed"):
        direction = "ASC" if direction == "DESC" else "DESC"
    return order, direction


def sorted_fetch(kind: str, fetch: Callable) -> Callable:
    """fetch (a python-tidal favorites call) asking for the chosen order"""

    def fetch_sorted(*args, **kwargs):
        order, direction = sort_order(kind)
        # python-tidal only reads .value from its order enums, and they don't
        # have every order TIDAL takes (e.g. RELEASE_DATE)
        kwargs["order"] = SimpleNamespace(value=order)
        kwargs["order_direction"] = SimpleNamespace(value=direction)
        return fetch(*args, **kwargs)

    return fetch_sorted


def _parse_collection_item(item: dict) -> Any:
    """A playlist or folder from TIDAL's playlist folder listing"""
    data = item.get("data") or {}
    if item.get("itemType") == "FOLDER":
        folder = Folder(session, None).parse(item)
        folder.name = folder.name or data.get("name")
        folders[str(folder.id)] = folder
        return folder
    # This listing sends the creator's missing name as null, which python-tidal
    # shows as "TIDAL"; the old one left it out ("me")
    creator = data.get("creator")
    if isinstance(creator, dict):
        for key in [k for k, v in creator.items() if v is None]:
            del creator[key]
    return session.parse_playlist(data)


def folder_contents(folder_id: str = "root") -> list:
    """The playlists and folders in one of the user's playlist folders ("root" for
    the top level), in the chosen order (TIDAL sorts them; it pages them with a
    cursor). Like TIDAL, a playlist in a folder is only listed in that folder."""
    order, direction = sort_order("playlists")
    items = []
    cursor = None
    while True:
        params = {
            "folderId": folder_id,
            "limit": 50,
            "order": order,
            "orderDirection": direction,
        }
        if cursor:
            params["cursor"] = cursor
        json_obj = session.request.request(
            "GET",
            "my-collection/playlists/folders",
            base_url=session.config.api_v2_location,
            params=params,
        ).json()
        page = []
        for item in json_obj.get("items", []):
            try:
                page.append(_parse_collection_item(item))
            except Exception:
                logger.exception("Could not read an item of a playlist folder")
        items.extend(page)
        cursor = json_obj.get("cursor")
        if not cursor or not json_obj.get("items"):
            return items


def _load_sorted_playlists() -> list:
    return folder_contents("root")


_playlists_load_lock = threading.Lock()
_playlists_load_count = 0


def _load_playlists_and_favorite_playlists() -> None:
    """Load the user's playlists plus favorite playlists (the Collection's row)"""
    global playlist_and_favorite_playlists, _playlists_load_count

    with _playlists_load_lock:
        _playlists_load_count += 1
        this_load = _playlists_load_count
    playlists = _load_favourites(
        "playlists and favorite playlists",
        _load_sorted_playlists,
        playlist_and_favorite_playlists,
    )
    # Loads can overlap (the order changed twice in a row): the last one started
    # has the current order, so an older one finishing later is dropped
    with _playlists_load_lock:
        if this_load == _playlists_load_count:
            playlist_and_favorite_playlists = playlists


def sort_menu(kind: str) -> tuple:
    """A "Sort by" menu for a Collection list and the actions it uses (prefix
    "sort"): its orders, then Reverse order. Insert the actions on the widget
    showing the menu."""
    settings = Gio.Settings.new("io.github.nokse22.high-tide")
    actions = Gio.SimpleActionGroup()
    actions.add_action(settings.create_action(f"sort-{kind}"))
    actions.add_action(settings.create_action(f"sort-{kind}-reversed"))
    actions.settings = settings  # kept alive with the actions
    menu = Gio.Menu()
    orders = Gio.Menu()
    for value, label, _order, _direction in SORTS[kind]:
        orders.append(label, f"sort.sort-{kind}::{value}")
    menu.append_section(None, orders)
    reverse = Gio.Menu()
    reverse.append(_("Reverse order"), f"sort.sort-{kind}-reversed")
    menu.append_section(None, reverse)
    return menu, actions


_resort_counts: dict = {}


def new_folder() -> None:
    """Ask for a name and create a playlist folder at the top level"""
    ask_folder_name(
        _("New Folder"),
        _("Create"),
        "",
        lambda name: threading.Thread(
            target=th_create_folder, args=(name,), daemon=True
        ).start(),
    )


def th_create_folder(name: str) -> None:
    """Thread function to create a playlist folder at the top level"""
    try:
        session.user.create_folder(title=name)
    except Exception:
        logger.exception(f"Failed to create the folder {name}")
        GLib.idle_add(send_toast, _("Failed to create the folder"), 2)
        return
    GLib.idle_add(send_toast, _("Created {}").format(name), 2)
    GLib.idle_add(_on_folders_changed)


# Called on the main thread after folders or what's in them changed (open folder
# pages load again)
folder_listeners: List[Callable[[], None]] = []


def _on_folders_changed() -> None:
    resort("playlists")
    for listener in list(folder_listeners):
        listener()


def _trn(item: Any) -> str:
    if isinstance(item, Folder):
        return item.trn or f"trn:folder:{item.id}"
    return f"trn:playlist:{item.id}"


def _move_to_folder(items: list, folder_id: str) -> None:
    session.request.request(
        "PUT",
        "my-collection/playlists/folders/move",
        base_url=session.config.api_v2_location,
        params={"folderId": folder_id, "trns": ",".join(_trn(i) for i in items)},
    )


def th_move_to_folder(item: Any, folder_id: str) -> None:
    """Thread function to move a playlist or folder into a folder ("root" for none)

    Args:
        item: The playlist or folder to move
        folder_id: The folder to move it into, or "root"
    """
    try:
        _move_to_folder([item], folder_id)
    except Exception:
        logger.exception(f"Failed to move {item.id} to folder {folder_id}")
        GLib.idle_add(send_toast, _("Failed to move {}").format(item.name), 2)
        return
    folder = folders.get(folder_id)
    if folder is None:
        message = _("Moved {} out of its folder").format(item.name)
    else:
        message = _("Moved {} to {}").format(item.name, folder.name)
    GLib.idle_add(send_toast, message, 2)
    GLib.idle_add(_on_folders_changed)


def th_rename_folder(folder: Any, name: str, callback: Any = None) -> None:
    """Thread function to rename one of the user's playlist folders"""
    try:
        if not folder.rename(name):
            raise RuntimeError("rename failed")
    except Exception:
        logger.exception(f"Failed to rename folder {folder.id}")
        GLib.idle_add(send_toast, _("Failed to rename the folder"), 2)
        return
    folder.name = name
    GLib.idle_add(send_toast, _("Renamed to {}").format(name), 2)
    if callback:
        GLib.idle_add(callback)
    GLib.idle_add(_on_folders_changed)


def th_delete_folder(folder: Any, callback: Any = None) -> None:
    """Thread function to delete one of the user's playlist folders. What's in it
    is moved to the top level first, so no playlist goes with it."""
    try:
        contents = folder_contents(folder.id)
        if contents:
            _move_to_folder(contents, "root")
        if not folder.remove():
            raise RuntimeError("remove failed")
    except Exception:
        logger.exception(f"Failed to delete folder {folder.id}")
        GLib.idle_add(send_toast, _("Failed to delete the folder"), 2)
        GLib.idle_add(_on_folders_changed)
        return
    folders.pop(str(folder.id), None)
    GLib.idle_add(send_toast, _("Deleted {}").format(folder.name), 2)
    if callback:
        GLib.idle_add(callback)
    GLib.idle_add(_on_folders_changed)


def ask_folder_name(heading: str, response_label: str, name: str, on_name: Callable) -> None:
    """Ask for a folder name; on_name(name) is called with it"""
    entry = Gtk.Entry(placeholder_text=_("Name"), activates_default=True, text=name)
    dialog = Adw.AlertDialog(heading=heading, extra_child=entry)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("ok", response_label)
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")

    def update(*_args):
        text = entry.get_text().strip()
        dialog.set_response_enabled("ok", bool(text) and text != name)

    entry.connect("changed", update)
    update()

    def on_response(_dialog, response):
        text = entry.get_text().strip()
        if response == "ok" and text:
            on_name(text)

    dialog.connect("response", on_response)
    dialog.present(navigation_view.get_root())


def folder_menu(folder: Any, on_deleted: Callable | None = None) -> tuple:
    """The menu of a playlist folder (rename, delete, a new playlist in it) and
    its actions (prefix "folder"); insert them on the widget showing the menu"""
    actions = Gio.SimpleActionGroup()

    def rename(*_args):
        ask_folder_name(
            _("Rename Folder"),
            _("Rename"),
            folder.name or "",
            lambda name: threading.Thread(
                target=th_rename_folder, args=(folder, name), daemon=True
            ).start(),
        )

    def delete(*_args):
        dialog = Adw.AlertDialog(
            heading=_("Delete {}?").format(folder.name),
            body=_("The playlists in it move to the top level."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response == "delete":
                threading.Thread(
                    target=th_delete_folder, args=(folder, on_deleted), daemon=True
                ).start()

        dialog.connect("response", on_response)
        dialog.present(navigation_view.get_root())

    for name, callback in (
        ("rename", rename),
        ("delete", delete),
        ("new-playlist", lambda *_: new_playlist(folder_id=folder.id)),
    ):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        actions.add_action(action)

    menu = Gio.Menu()
    menu.append(_("Rename folder…"), "folder.rename")
    menu.append(_("Delete folder…"), "folder.delete")
    menu.append(_("New playlist…"), "folder.new-playlist")
    return menu, actions


def resort(kind: str) -> None:
    """Load a Collection list again in its chosen order, and show it"""

    def load():
        global favourite_albums, favourite_tracks, favourite_artists, favourite_mixes
        if kind == "playlists":
            _load_playlists_and_favorite_playlists()
        else:
            # Only the last one started may set the list (the order changed twice)
            with _playlists_load_lock:
                _resort_counts[kind] = _resort_counts.get(kind, 0) + 1
                this_load = _resort_counts[kind]
            user = session.user
            current = globals()[f"favourite_{kind}"]
            items = _load_favourites(
                kind, sorted_fetch(kind, getattr(user.favorites, kind)), current
            )
            with _playlists_load_lock:
                if this_load == _resort_counts[kind]:
                    globals()[f"favourite_{kind}"] = items
        GLib.idle_add(_update_collection_page)

    threading.Thread(target=load, daemon=True).start()


def _on_sort_setting_changed(settings, key: str) -> None:
    if key.startswith("sort-"):
        resort(key.removeprefix("sort-").removesuffix("-reversed"))


# Reloading the user's playlists when a song menu opens, so ones made in other
# apps show up: every time, unless they were loaded less than this many seconds
# ago (opening several menus in a row asks once)
USER_PLAYLISTS_RELOAD_INTERVAL = 3
_user_playlists_loaded_at = 0.0
_user_playlists_reloading = False
_user_playlists_reloaded_callbacks: List[Callable[[], None]] = []


def reload_user_playlists(on_reloaded: Callable[[], None]) -> None:
    """Load the user's playlists again in the background, unless that was done in
    the last USER_PLAYLISTS_RELOAD_INTERVAL seconds. on_reloaded is called on the
    main thread once they are loaded (not at all when they're recent enough)."""
    global _user_playlists_reloading
    if _user_playlists_reloading:
        _user_playlists_reloaded_callbacks.append(on_reloaded)
        return
    since = time.monotonic() - _user_playlists_loaded_at
    if since < USER_PLAYLISTS_RELOAD_INTERVAL:
        logger.info(f"User playlists loaded {since:.1f} s ago, not loading them again")
        return
    _user_playlists_reloading = True
    _user_playlists_reloaded_callbacks.append(on_reloaded)

    def reload():
        global user_playlists, _user_playlists_loaded_at
        playlists = _load_favourites(
            "user playlists", session.user.playlists, user_playlists
        )
        _user_playlists_loaded_at = time.monotonic()
        GLib.idle_add(done, playlists)

    logger.info("Loading the user playlists again")

    def done(playlists):
        global user_playlists, _user_playlists_reloading
        logger.info(f"User playlists: {len(playlists)} (was {len(user_playlists)})")
        changed = [p.id for p in playlists] != [p.id for p in user_playlists]
        user_playlists = playlists
        _user_playlists_reloading = False
        if changed:
            # Made or deleted in another app: the Collection page shows them too
            threading.Thread(target=_on_user_playlists_reloaded, daemon=True).start()
        callbacks = list(_user_playlists_reloaded_callbacks)
        _user_playlists_reloaded_callbacks.clear()
        for callback in callbacks:
            callback()
        return False

    threading.Thread(target=reload, daemon=True).start()


def _load_favourites(name: str, load: Callable[[], list], current: list) -> list:
    try:
        return load()
    except Exception:
        logger.exception(f"Error while getting the favorite {name}")
        return current


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


_queued_toast = None


def show_queued_toast() -> None:
    """"Added to queue", one toast shown again on each click instead of a pile"""
    global _queued_toast
    if _queued_toast is None:
        _queued_toast = Adw.Toast(title=_("Added to queue"), timeout=2)
        _queued_toast.connect("dismissed", lambda *_: _forget_queued_toast())
    toast_overlay.add_toast(_queued_toast)


def _forget_queued_toast() -> None:
    global _queued_toast
    _queued_toast = None


def queue_menu(item) -> tuple:
    """A menu section with Play next and Add to queue for a whole album,
    playlist or mix (#259), and its actions (prefix "queue")"""
    menu = Gio.Menu()
    menu.append(_("Play next"), "queue.play-next")
    menu.append(_("Add to queue"), "queue.add-to-queue")
    actions = Gio.SimpleActionGroup()
    for name, next_up in (("play-next", True), ("add-to-queue", False)):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args, n=next_up: queue_whole(item, n))
        actions.add_action(action)
    return menu, actions


def queue_whole(item, next_up: bool) -> None:
    """Queue every song of an album, playlist or mix, the songs Play would play"""

    def fetch():
        tracks = []
        try:
            thing = get_mix(item.id) if type(item).__name__ == "MixV2" else item
            tracks = player_object.get_track_list(thing) or []
        except Exception:
            logger.exception(f"Couldn't get the songs of {item} to queue them")
        tracks = [
            t for t in tracks if not ai.is_hidden(t) and not is_hidden_by_block(t)
        ]
        GLib.idle_add(done, tracks)

    def done(tracks):
        if not tracks:
            send_toast(_("Couldn't add the songs to the queue"), 3)
            return False
        player_object.add_tracks_to_queue(tracks, next_up)
        count = len(tracks)
        if next_up:
            text = ngettext("{} song plays next", "{} songs play next", count)
        else:
            text = ngettext("{} song added to the queue", "{} songs added to the queue", count)
        send_toast(text.format(count), 2)
        return False

    threading.Thread(target=fetch, daemon=True).start()


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


def is_hidden_track(track: Any) -> bool:
    """Check if the player should leave a track out of playback.

    Args:
        track: A TIDAL Track

    Returns:
        bool: True if the track is blocked, or AI-generated and set to be hidden
    """
    return is_blocked_by_artist(track) or ai.is_hidden(track)


def filter_ai_items(items: List[Any]) -> List[Any]:
    """Leave out AI-generated items when the preference hides them.

    Args:
        items: TIDAL tracks or albums

    Returns:
        list: The items that should be shown
    """
    return ai.filter_items(items)


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
        player_object.skip_hidden()
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


# Logged in with a QR code (TIDAL's device login) rather than in the browser. Its
# songs come from TIDAL's newer address: the older one gives that login only AAC
# for CD-quality songs (since April 2026), the newer one FLAC without DRM. The
# browser login keeps the older address: the newer one gives it DRM-locked audio.
device_login = False

# What a quality setting may ask the newer address for, best last
_MANIFEST_FORMATS = {
    "LOW": "HEAACV1",
    "HIGH": "HEAACV1,AACLC",
    "LOSSLESS": "HEAACV1,AACLC,FLAC",
    "HI_RES_LOSSLESS": "HEAACV1,AACLC,FLAC,FLAC_HIRES",
}
_QUALITY_OF_FORMAT = {
    "FLAC_HIRES": "HI_RES_LOSSLESS",
    "FLAC": "LOSSLESS",
    "AACLC": "HIGH",
    "HEAACV1": "LOW",
}
_QUALITY_RANK = {"LOW": 0, "HIGH": 1, "LOSSLESS": 2, "HI_RES_LOSSLESS": 3}


def _quality_name(quality: Any) -> str:
    return str(getattr(quality, "value", quality) or "LOSSLESS")


def get_stream(track: Track) -> Any:
    """The stream of a track to play: from TIDAL's newer address for a QR login,
    as python-tidal's Stream (DASH), so the player treats both the same."""
    if not device_login:
        return track.get_stream()
    from tidalapi.media import Stream

    quality = _quality_name(session.audio_quality)
    json_obj = session.request.request(
        "GET",
        f"trackManifests/{track.id}",
        base_url="https://openapi.tidal.com/v2/",
        params={
            "manifestType": "MPEG_DASH",
            "formats": _MANIFEST_FORMATS.get(quality, _MANIFEST_FORMATS["LOSSLESS"]),
            "uriScheme": "HTTPS",
            "usage": "PLAYBACK",
            "adaptive": "false",
        },
    ).json()
    attributes = json_obj["data"]["attributes"]
    if attributes.get("drmData"):
        raise RuntimeError(f"TIDAL sent {track.id} with DRM, it can't be played")
    uri = attributes["uri"]
    if uri.startswith("data:"):
        mpd = base64.b64decode(uri.split(",", 1)[1]).decode()
    else:
        response = session.request_session.get(uri, timeout=20)
        response.raise_for_status()
        mpd = response.text
    formats = attributes.get("formats") or []
    best = max(
        (_QUALITY_OF_FORMAT.get(f, "LOW") for f in formats),
        key=lambda q: _QUALITY_RANK[q],
        default="LOW",
    )
    rates = re.findall(r'audioSamplingRate="(\d+)"', mpd)
    track_norm = attributes.get("trackAudioNormalizationData") or {}
    album_norm = attributes.get("albumAudioNormalizationData") or {}
    return Stream().parse(
        {
            "trackId": track.id,
            "audioMode": "STEREO",
            "audioQuality": best,
            "manifestMimeType": "application/dash+xml",
            "manifestHash": attributes.get("hash"),
            "manifest": base64.b64encode(mpd.encode()).decode(),
            "albumReplayGain": album_norm.get("replayGain", 1.0),
            "albumPeakAmplitude": album_norm.get("peakAmplitude", 1.0),
            "trackReplayGain": track_norm.get("replayGain", 1.0),
            "trackPeakAmplitude": track_norm.get("peakAmplitude", 1.0),
            "bitDepth": 24 if best == "HI_RES_LOSSLESS" else 16,
            "sampleRate": int(rates[0]) if rates else 44100,
        }
    )


_lower_quality_noticed = False


def check_stream_quality(track: Track, stream: Any) -> None:
    """Say so, once a session, when TIDAL sends a song in lower quality than both
    the quality setting and the best the song comes in"""
    global _lower_quality_noticed
    chosen = _quality_name(session.audio_quality)
    tags = set(getattr(track, "media_metadata_tags", None) or [])
    if "HIRES_LOSSLESS" in tags:
        best = "HI_RES_LOSSLESS"
    elif "LOSSLESS" in tags or getattr(track, "audio_quality", None) in (
        "LOSSLESS",
        "HI_RES_LOSSLESS",
    ):
        best = "LOSSLESS"
    else:
        return  # nothing to compare with
    expected = min(chosen, best, key=lambda q: _QUALITY_RANK.get(q, 2))
    sent = _quality_name(getattr(stream, "audio_quality", None))
    if _QUALITY_RANK.get(sent, 2) >= _QUALITY_RANK.get(expected, 2):
        return
    logger.warning(
        f"TIDAL sent {track.id} as {sent}, chosen {chosen}, the song has {best}"
    )
    if _lower_quality_noticed:
        return
    _lower_quality_noticed = True
    if device_login:
        message = _(
            "TIDAL sent this song in lower quality than chosen. To get full "
            "quality again, log out and log back in with “Sign in another way”."
        )
    else:
        message = _("TIDAL sent this song in lower quality than chosen")
    GLib.idle_add(send_toast, message, 8)


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
        btn: The favorite button widget (for UI updates), or None
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
        if btn is not None:
            GLib.idle_add(set_in_my_collection_button, btn, True)
        GLib.idle_add(send_toast, _("Successfully added to my collection"), 2)
        refresh_favourites()
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
        GLib.idle_add(set_in_my_collection_button, btn, False)
        GLib.idle_add(send_toast, _("Successfully removed from my collection"), 2)
        refresh_favourites()
    else:
        GLib.idle_add(send_toast, _("Failed to remove item from my collection"), 2)


def set_in_my_collection_button(btn: Any, in_collection: bool) -> None:
    """Show on a heart button whether its item is in the user's collection.

    Args:
        btn: The heart button
        in_collection: True if the item is in the collection
    """
    if in_collection:
        btn.set_icon_name("heart-filled-symbolic")
        btn.set_tooltip_text(_("Remove from My Collection"))
    else:
        btn.set_icon_name("heart-outline-thick-symbolic")
        btn.set_tooltip_text(_("Add to My Collection"))


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


def _on_user_playlists_reloaded() -> None:
    _load_playlists_and_favorite_playlists()
    GLib.idle_add(_update_collection_page)


def _on_playlists_changed() -> None:
    get_playlists()
    GLib.idle_add(_update_collection_page)


def _update_collection_page() -> None:
    page = navigation_view.find_page("collection")
    if page:
        page.update_items()


def th_add_to_playlist(playlist: Playlist, track: Track) -> None:
    """Thread function to add a track at the end of one of the user's playlists.

    Args:
        playlist: The playlist to add the track to
        track: The track to add
    """
    try:
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


def new_playlist(track: Track | None = None, folder_id: str = "root") -> None:
    """Ask for a name and description and create a new playlist.

    Args:
        track: A track to add to the new playlist
        folder_id: The folder to make it in (the top level by default)
    """
    from ..new_playlist import NewPlaylistWindow

    dialog = NewPlaylistWindow()

    def on_create(dialog, title, description):
        dialog.close()
        threading.Thread(
            target=th_create_playlist, args=(title, description, track, folder_id)
        ).start()

    dialog.connect("create-playlist", on_create)
    dialog.present(navigation_view.get_root())


def th_create_playlist(
    title: str,
    description: str,
    track: Track | None = None,
    folder_id: str = "root",
) -> None:
    """Thread function to create a playlist and optionally add a track to it.

    Args:
        title: The playlist title
        description: The playlist description
        track: A track to add to the new playlist
    """
    try:
        playlist = session.user.create_playlist(title, description, folder_id)
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
    if folder_id != "root":
        GLib.idle_add(_on_folders_changed)


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
    elif isinstance(item, Folder):
        return "folder"


def matches_search(item: Any, query: str) -> bool:
    """Whether a list search for query (lowercase) finds item: by its name or
    title, its artists, a song's album, a playlist's creator or a mix's subtitle"""
    names = [
        getattr(item, "full_name", None),
        getattr(item, "name", None),
        getattr(item, "title", None),
        getattr(item, "sub_title", None),
    ]
    names += [getattr(a, "name", None) for a in (getattr(item, "artists", None) or [])]
    for attribute in ("album", "creator"):
        related = getattr(item, attribute, None)
        if related is not None:
            names.append(getattr(related, "name", None))
    return any(query in name.lower() for name in names if isinstance(name, str))


def push_page(key: str, make_page) -> None:
    """Open a page, unless the same page is already the one shown.

    If the same page is further back, that page is moved to the top instead of
    opening a new copy, so going back and forth between pages (a song's album and
    artist, say) doesn't pile up copies of them, and the page shows at once,
    already loaded. Nothing opened in between is closed.

    Args:
        key: Identifies the page (type and id, e.g. "album-123")
        make_page: Builds and returns the page to push
    """
    if getattr(navigation_view.get_visible_page(), "page_key", None) == key:
        return

    older = _pages_with_key(key)
    if older:
        page = older[-1]
        # Take it out of the stack (the page shown stays the same), then push it
        # again, so it slides in like a new page
        navigation_view.replace([p for p in _navigation_pages() if p not in older])
        for other in older[:-1]:
            other.disconnect_all()
        navigation_view.push(page)
        return

    page = make_page()
    page.page_key = key
    navigation_view.push(page)


def _navigation_pages() -> list:
    stack = navigation_view.get_navigation_stack()
    return [stack.get_item(i) for i in range(stack.get_n_items())]


def _pages_with_key(key: str) -> list:
    return [p for p in _navigation_pages() if getattr(p, "page_key", None) == key]


def open_uri(label: str, uri: str) -> bool:
    """Open a URI by navigating to the appropriate page in the application.

    Args:
        label: Display label for the URI (currently unused)
        uri: A URI string in format "type:id" (e.g., "artist:123456")
    """
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            artist_id = uri_parts[1]
            push_page(
                f"artist-{artist_id}",
                lambda: HTArtistPage.new_from_id(artist_id).load(),
            )
        case "album":
            album_id = uri_parts[1]
            push_page(
                f"album-{album_id}",
                lambda: HTAlbumPage.new_from_id(album_id).load(),
            )

    # TODO implement the rest?
    return True


def open_tidal_uri(uri: str) -> None:
    """Handles opening uri like tidal://track/1234"""

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
            push_page(
                f"mix-{content_id}",
                lambda: HTMixPage.new_from_id(content_id).load(),
            )
        case "playlist":
            push_page(
                f"playlist-{content_id}",
                lambda: HTPlaylistPage.new_from_id(content_id).load(),
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


def _install_row_context() -> None:
    """Keep what a home row like "Because you listened to" is about.

    TIDAL sends it as the row's header (an album, track, artist...), but
    python-tidal 0.8 ignores it. It's kept as the row's context_item.
    """
    try:
        from tidalapi.page import HorizontalListWithContext
    except ImportError:
        return

    parse = HorizontalListWithContext.parse

    def parse_with_context(self, json_obj):
        result = parse(self, json_obj)
        self.context_item = None
        header = json_obj.get("header") or {}
        parse_item = self.item_types.get(header.get("type"))
        if parse_item is not None and header.get("data"):
            try:
                self.context_item = parse_item(header["data"])
            except Exception:
                logger.exception("Could not read what a home row is about")
        return result

    HorizontalListWithContext.parse = parse_with_context


def _install_my_tracks_link() -> None:
    """Show the "My Tracks" card TIDAL puts in home rows like Recently played.

    TIDAL sends it as a DEEP_LINK item (to tidal://my-collection/tracks), which
    python-tidal 0.8 skips, so people missed their liked songs there (#179).
    It becomes MY_TRACKS, shown as a card opening the saved tracks.
    """
    try:
        from tidalapi.page import SimpleList
    except ImportError:
        return
    if getattr(SimpleList.get_item, "with_my_tracks", False):
        return
    get_item = SimpleList.get_item

    def get_item_with_my_tracks(self, json_obj):
        if json_obj.get("type") == "DEEP_LINK":
            data = json_obj.get("data") or {}
            if (data.get("url") or data.get("id")) == "tidal://my-collection/tracks":
                return MY_TRACKS
        return get_item(self, json_obj)

    get_item_with_my_tracks.with_my_tracks = True
    SimpleList.get_item = get_item_with_my_tracks


def _install_artist_cover_fallback() -> None:
    """Show one of an artist's album covers when TIDAL has no picture of them.

    TIDAL sends the cover in selectedAlbumCoverFallback and its own apps show it,
    but python-tidal 0.8 ignores it and uses a placeholder picture instead.
    """
    if getattr(Artist.parse_artist, "with_cover_fallback", False):
        return
    original_parse = Artist.parse_artist

    def parse(self, json_obj, *args, **kwargs):
        artist = original_parse(self, json_obj, *args, **kwargs)
        fallback = json_obj.get("selectedAlbumCoverFallback")
        if not json_obj.get("picture") and fallback:
            # Artist(session, id) keeps itself and drops the copy parse returns
            self.picture = artist.picture = fallback
        return artist

    parse.with_cover_fallback = True
    Artist.parse_artist = parse


def search_playlists(query: str, limit: int = 10) -> List[Playlist] | None:
    """Search playlists the way tidal.com does, so playlists people made show
    up next to TIDAL's (#216). The search tidalapi uses only finds TIDAL's.

    Returns:
        The playlists, or None if TIDAL's search couldn't be used
    """
    try:
        json_obj = session.request.request(
            "GET",
            "search/",
            params={
                "query": query,
                "limit": limit,
                "types": "PLAYLISTS",
                "includeUserPlaylists": "true",
                "countryCode": session.country_code,
                "locale": session.locale,
                "deviceType": "BROWSER",
                "platform": "WEB",
            },
            base_url=session.config.api_v2_location,
        ).json()
        items = json_obj["playlists"]["items"]
    except Exception:
        logger.exception("Could not search playlists made by people")
        return None

    playlists = []
    for item in items:
        # Named a little differently than in the search tidalapi reads
        item.setdefault("numberOfVideos", item.get("numberOfVideoTracks", 0))
        if item.get("type") == "USER" and not item.get("creator"):
            item["creator"] = {"id": item.get("userId")}
            if item.get("profileName"):
                item["creator"]["name"] = item["profileName"]
        try:
            playlists.append(session.parse_playlist(item))
        except Exception:
            logger.exception(f"Could not read playlist {item.get('uuid')}")
    return playlists


# Seconds to wait for a picture's server to answer, and between parts of it
DOWNLOAD_TIMEOUT = (10, 30)


def _download_cached(
    file_path: Path, get_url: Callable[[], str], what: str
) -> str | None:
    """Download a picture or video cover to the cache, unless it's there already.

    Returns:
        str: The file's path, or None if it couldn't be downloaded
    """
    if file_path.is_file():
        return str(file_path)

    try:
        response = requests.get(get_url(), timeout=DOWNLOAD_TIMEOUT)
    except Exception:
        logger.exception(f"Could not get {what}")
        return None
    if response.status_code != 200:
        logger.warning(f"Could not get {what}: HTTP {response.status_code}")
        return None

    # Written under another name and renamed once complete, so a file that is
    # there is whole: all the rows of an album ask for its cover at once
    part_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.part")
    try:
        part_path.write_bytes(response.content)
        os.replace(part_path, file_path)
    except OSError:
        logger.exception(f"Could not save {what}")
        part_path.unlink(missing_ok=True)
        return None
    return str(file_path)


def get_image_url(item: Any, dimensions: int = 320) -> str | None:
    """Get the local file path for an item's image, downloading if necessary.

    Args:
        item: A TIDAL object with image data
        dimensions (int): The desired image dimensions (default: 320)

    Returns:
        str: Path to the local image file, or None if download failed
    """
    if isinstance(item, Artist) and item.picture:
        # Named after the picture, so a placeholder saved before is replaced when
        # TIDAL gets a picture or an album cover for the artist
        file_path = IMG_DIR / f"artist_{item.picture}_{dimensions}.jpg"
    elif hasattr(item, "id"):
        file_path = IMG_DIR / f"{item.id}_{dimensions}.jpg"
    else:
        file_path = IMG_DIR / f"{uuid.uuid4()}_{dimensions}.jpg"

    return _download_cached(
        file_path, lambda: item.image(dimensions=dimensions), "image"
    )


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
        if file_path and not cancellable.is_cancelled():
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
        if file_path and not cancellable.is_cancelled():
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

    return _download_cached(
        file_path, lambda: item.video(dimensions=dimensions), "video"
    )


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
        if file_path and not cancellable.is_cancelled():
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


def create_tidal_session():
    tidal_session = tidalapi.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    tidal_session.request_session.mount("https://", adapter)
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
