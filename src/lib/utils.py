from gi.repository import Gdk, Adw
from gi.repository import GLib
from gi.repository import Gio

import os

from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.mix import Mix

from ..pages import HTArtistPage
from ..pages import HTAlbumPage
from ..pages import HTMixPage
from ..pages import HTPlaylistPage

import threading
import requests
import uuid
import re
import html

from gettext import gettext as _

from pathlib import Path

favourite_mixes = []
favourite_tracks = []
favourite_artists = []
favourite_albums = []
favourite_playlists = []
playlist_and_favorite_playlists = []
user_playlists = []


def init():
    global CACHE_DIR
    CACHE_DIR = os.environ.get('XDG_CACHE_HOME')
    if CACHE_DIR == "" or CACHE_DIR is None or "HighTide" not in CACHE_DIR:
        CACHE_DIR = f"{os.environ.get('HOME')}/.cache/high-tide"
    global IMG_DIR
    IMG_DIR = f"{CACHE_DIR}/images"

    if not os.path.exists(IMG_DIR):
        os.makedirs(IMG_DIR)

    global session
    global navigation_view
    global player_object
    global toast_overlay


def get_favourites():
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
        playlist_and_favorite_playlists = user.playlist_and_favorite_playlists()
        user_playlists = user.playlists()
    except Exception as e:
        print(e)

    print(f"Favorite Artists: {len(favourite_artists)}")
    print(f"Favorite Tracks: {len(favourite_tracks)}")
    print(f"Favorite Albums: {len(favourite_albums)}")
    print(f"Favorite Playlists: {len(favourite_playlists)}")
    print(f"Favorite Mixes: {len(favourite_mixes)}")
    print(f"Playlist and Favorite Playlists: {len(playlist_and_favorite_playlists)}")
    print(f"User Playlists: {len(user_playlists)}")


def is_favourited(item):
    global favourite_mixes
    global favourite_tracks
    global favourite_artists
    global favourite_albums
    global favourite_playlists

    if isinstance(item, Track):
        for fav in favourite_tracks:
            if (fav.id == item.id):
                return True

    elif isinstance(item, Mix):
        return  # still not supported

    elif isinstance(item, Album):
        for fav in favourite_albums:
            if (fav.id == item.id):
                return True

    elif isinstance(item, Artist):
        for fav in favourite_artists:
            if (fav.id == item.id):
                return True

    elif isinstance(item, Playlist):
        for fav in favourite_artists:
            if (fav.id == item.id):
                return True

    return False


def send_toast(toast_title, timeout):
    toast_overlay.add_toast(Adw.Toast(
        title=toast_title,
        timeout=timeout))


def th_add_to_my_collection(btn, item):
    if isinstance(item, Track):
        result = session.user.favorites.add_track(item.id)
    elif isinstance(item, Mix):
        return  # still not supported
        result = session.user.favorites.add_mix(item.id)
    elif isinstance(item, Album):
        result = session.user.favorites.add_album(item.id)
    elif isinstance(item, Artist):
        result = session.user.favorites.add_artist(item.id)
    elif isinstance(item, Playlist):
        result = session.user.favorites.add_playlist(item.id)
    else:
        result = False

    if result:
        btn.set_icon_name("heart-filled-symbolic")
        send_toast(_("Successfully added to my collection"), 2)
        get_favourites()
    else:
        send_toast(_("Failed to add item to my collection"), 2)


def th_remove_from_my_collection(btn, item):
    if isinstance(item, Track):
        result = session.user.favorites.remove_track(item.id)
    elif isinstance(item, Mix):
        return  # still not supported
        result = session.user.favorites.remove_mix(item.id)
    elif isinstance(item, Album):
        result = session.user.favorites.remove_album(item.id)
    elif isinstance(item, Artist):
        result = session.user.favorites.remove_artist(item.id)
    elif isinstance(item, Playlist):
        result = session.user.favorites.remove_playlist(item.id)
    else:
        result = False

    if result:
        btn.set_icon_name("heart-outline-thick-symbolic")
        send_toast(_("Successfully removed from my collection"), 2)
    else:
        send_toast(_("Failed to remove item from my collection"), 2)


def on_in_to_my_collection_button_clicked(btn, item):
    if btn.get_icon_name() == "heart-outline-thick-symbolic":
        threading.Thread(
            target=th_add_to_my_collection,
            args=(btn, item,)).start()
    else:
        threading.Thread(
            target=th_remove_from_my_collection,
            args=(btn, item,)).start()


def share_this(item):
    clipboard = Gdk.Display().get_default().get_clipboard()

    share_url = None

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


def get_type(item):
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


def open_uri(label, uri):
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            page = HTArtistPage(uri_parts[1]).load()
            navigation_view.push(page)
        case "album":
            page = HTAlbumPage(uri_parts[1]).load()
            navigation_view.push(page)

    return True


def open_tidal_uri(uri):
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
            page = HTArtistPage(content_id).load()
            navigation_view.push(page)
        case "album":
            page = HTAlbumPage(content_id).load()
            navigation_view.push(page)
        case "track":
            threading.Thread(
                target=th_play_track,
                args=(content_id,)).start()
        case "mix":
            page = HTMixPage(content_id).load()
            navigation_view.push(page)
        case "playlist":
            page = HTPlaylistPage(content_id).load()
            navigation_view.push(page)
        case _:
            print(f"Unsupported content type: {content_type}")
            return False


def th_play_track(track_id):
    track = session.track(track_id)

    player_object.play_this([track])


def pretty_duration(secs):
    if not secs:
        return "00:00"

    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60

    if hours > 0:
        return f"{int(hours)}:{int(minutes):02}:{int(seconds):02}"
    else:
        return f"{int(minutes):2}:{int(seconds):02}"

    return "00:00"


def get_image_url(item):
    if hasattr(item, "id"):
        file_path = Path(f"{IMG_DIR}/{item.id}.jpg")
    else:
        file_path = Path(f"{IMG_DIR}/{uuid.uuid4()}.jpg")

    if file_path.is_file():
        return str(file_path)

    try:
        picture_url = item.image()
        response = requests.get(picture_url)
    except Exception as e:
        print(e)
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_picture(widget, item, cancellable=Gio.Cancellable.new()):
    """Retrieves and adds an picture"""

    if cancellable is None:
        cancellable = Gio.Cancellable.new()

    def _add_picture(widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            widget.set_filename(file_path)

    GLib.idle_add(
        _add_picture, widget, get_image_url(item), cancellable)


def add_image(widget, item, cancellable=Gio.Cancellable.new()):
    """Retrieves and adds an image"""

    def _add_image(widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            widget.set_from_file(file_path)

    GLib.idle_add(
        _add_image, widget, get_image_url(item), cancellable)


def get_video_cover_url(item):
    if hasattr(item, "id"):
        file_path = Path(f"{IMG_DIR}/{item.id}.mp4")
    else:
        file_path = Path(f"{IMG_DIR}/{uuid.uuid4()}.mp4")

    if file_path.is_file():
        return str(file_path)

    try:
        video_url = item.video(dimensions=640)
        response = requests.get(video_url)
    except Exception as e:
        print(e)
        return None
    if response.status_code == 200:
        picture_data = response.content

        with open(file_path, "wb") as file:
            file.write(picture_data)

    return str(file_path)


def add_video_cover(widget, videoplayer, item, cancellable=Gio.Cancellable.new()):
    """Retrieves and adds an video"""

    if cancellable is None:
        cancellable = Gio.Cancellable.new()

    def _add_video_cover(widget, videoplayer, file_path, cancellable):
        if not cancellable.is_cancelled() and file_path:
            videoplayer.pause()
            videoplayer.clear()
            videoplayer.set_loop(True) 
            videoplayer.set_filename(file_path)
            widget.set_paintable(videoplayer)
            videoplayer.play()

    GLib.idle_add(
        _add_video_cover, widget, videoplayer, get_video_cover_url(item), cancellable)


def add_image_to_avatar(widget, item, cancellable=Gio.Cancellable.new()):
    """Same ad the previous function, but for Adwaita's avatar widgets"""

    def _add_image_to_avatar(avatar_widget, file_path, cancellable):
        if not cancellable.is_cancelled():
            file = Gio.File.new_for_path(file_path)
            image = Gdk.Texture.new_from_file(file)
            widget.set_custom_image(image)

    GLib.idle_add(
        _add_image_to_avatar, widget, get_image_url(item), cancellable)


def replace_links(text):
    # Define regular expression pattern to match escaped [wimpLink ...]...[/wimpLink] tags
    pattern = r'\[wimpLink (artistId|albumId)=&quot;(\d+)&quot;\]([^[]+)\[\/wimpLink\]'

    # Escape HTML in the entire text
    escaped_text = html.escape(text)

    # Define a function to replace the matched pattern with the desired format
    def replace(match):
        link_type = match.group(1)
        id_value = match.group(2)
        label = match.group(3)

        if link_type == "artistId":
            return f'<a href="artist:{id_value}">{label}</a>'
        elif link_type == "albumId":
            return f'<a href="album:{id_value}">{label}</a>'
        else:
            return label

    # Replace <br/> with two periods
    escaped_text = escaped_text.replace('&lt;br/&gt;', '\n')

    # Use re.sub() to perform the replacement
    replaced_text = re.sub(pattern, replace, escaped_text)

    return replaced_text
