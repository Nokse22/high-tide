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
import uuid
from gettext import gettext as _
from pathlib import Path
from typing import Any, List

import requests
from gi.repository import Adw, Gdk, Gio, GLib
from tidalapi import Album, Artist, Mix, Playlist, Track

from ..pages import HTAlbumPage, HTArtistPage, HTMixPage, HTPlaylistPage
from .cache import HTCache

favourite_mixes: List[Mix] = []
favourite_tracks: List[Track] = []
favourite_artists: List[Artist] = []
favourite_albums: List[Album] = []
favourite_playlists: List[Playlist] = []
playlist_and_favorite_playlists: List[Playlist] = []
user_playlists: List[Playlist] = []


def init() -> None:
    """Initialize the utils module by setting up cache directories and global objects.

    Sets up the cache directory structure, creates necessary directories,
    and initializes the global cache object for TIDAL API responses.
    """
    global CACHE_DIR
    CACHE_DIR = os.environ.get("XDG_CACHE_HOME")
    if CACHE_DIR == "" or CACHE_DIR is None or "high-tide" not in CACHE_DIR:
        CACHE_DIR = f"{os.environ.get('HOME')}/.cache/high-tide"
    global IMG_DIR
    IMG_DIR = f"{CACHE_DIR}/images"

    if not os.path.exists(IMG_DIR):
        os.makedirs(IMG_DIR)

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
            devices.append({
                "hw_device": hw_string,
                "name": f"{card_full_name} - {device_full_name} ({hw_string})",
            })

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

                devices.append({
                    "hw_device": hw_string,
                    "name": f"{card_name} ({hw_string})",
                })

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
    global playlist_and_favorite_playlists
    global user_playlists

    user = session.user

    try:
        favourite_artists = user.favorites.artists()
        favourite_tracks = user.favorites.tracks()
        favourite_albums = user.favorites.albums()
        favourite_playlists = user.favorites.playlists()
        favourite_mixes = user.favorites.mixes()
        user_playlists = user.playlists()

        count = user.favorites.get_playlists_count()
        limit = 50
        offset = 0
        pages = []

        while offset < count:
            pages += user.playlist_and_favorite_playlists(offset = offset)
            offset += limit

        playlist_and_favorite_playlists = pages
    except Exception as e:
        print(e)

    print(f"Favorite Artists: {len(favourite_artists)}")
    print(f"Favorite Tracks: {len(favourite_tracks)}")
    print(f"Favorite Albums: {len(favourite_albums)}")
    print(f"Favorite Playlists: {len(favourite_playlists)}")
    print(f"Favorite Mixes: {len(favourite_mixes)}")
    print(f"Playlist and Favorite Playlists: {len(playlist_and_favorite_playlists)}")
    print(f"User Playlists: {len(user_playlists)}")


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
        btn.set_icon_name("heart-filled-symbolic")
        send_toast(_("Successfully added to my collection"), 2)
        get_favourites()
    else:
        send_toast(_("Failed to add item to my collection"), 2)


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
        btn.set_icon_name("heart-outline-thick-symbolic")
        send_toast(_("Successfully removed from my collection"), 2)
    else:
        send_toast(_("Failed to remove item from my collection"), 2)


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


def open_uri(label: str, uri: str) -> bool:
    """Open a URI by navigating to the appropriate page in the application.

    Args:
        label: Display label for the URI (currently unused)
        uri: A URI string in format "type:id" (e.g., "artist:123456")
    """
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            page = HTArtistPage.new_from_id(uri_parts[1]).load()
            navigation_view.push(page)
        case "album":
            page = HTAlbumPage.new_from_id(uri_parts[1]).load()
            navigation_view.push(page)

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
            page = HTArtistPage.new_from_id(content_id).load()
            navigation_view.push(page)
        case "album":
            page = HTAlbumPage.new_from_id(content_id).load()
            navigation_view.push(page)
        case "track":
            threading.Thread(target=th_play_track, args=(content_id,)).start()
        case "mix":
            page = HTMixPage(content_id).load()
            navigation_view.push(page)
        case "playlist":
            page = HTPlaylistPage(content_id).load()
            navigation_view.push(page)
        case _:
            print(f"Unsupported content type: {content_type}")
            return False


def th_play_track(track_id: str) -> None:
    """Thread function to play a specific track by ID.

    Args:
        track_id: The TIDAL track ID to play
    """
    track: Track = session.track(track_id)

    player_object.play_this([track])


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
        file_path = Path(f"{IMG_DIR}/{item.id}_{dimensions}.jpg")
    else:
        file_path = Path(f"{IMG_DIR}/{uuid.uuid4()}_{dimensions}.jpg")

    if file_path.is_file():
        return str(file_path)

    try:
        picture_url = item.image(dimensions=dimensions)
        response = requests.get(picture_url)
    except Exception as e:
        print(e)
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_picture(
    widget: Any, item: Any, cancellable: Gio.Cancellable = Gio.Cancellable.new()
) -> None:
    """Retrieve and set an image for a widget from a TIDAL item.

    Downloads the image if necessary and sets it on the widget using set_filename().

    Args:
        widget: A GTK widget that supports set_filename()
        item: A TIDAL object with image data
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
        get_image_url(item, get_best_dimensions(widget)),
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
        file_path = Path(f"{IMG_DIR}/{item.id}_{dimensions}.mp4")
    else:
        file_path = Path(f"{IMG_DIR}/{uuid.uuid4()}_{dimensions}.mp4")

    if file_path.is_file():
        return str(file_path)

    try:
        video_url = item.video(dimensions=dimensions)
        response = requests.get(video_url)
    except Exception as e:
        print(e)
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
    in_bg: bool,
    cancellable: Gio.Cancellable = Gio.Cancellable.new(),
) -> None:
    """Retrieve and set a video cover for a video player widget from a TIDAL item.

    Downloads the video if necessary and configures the video player.

    Args:
        widget: The container widget
        videoplayer: The GtkMediaFile
        item: A TIDAL object with video data
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
        get_video_cover_url(item, get_best_dimensions(widget)),
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
