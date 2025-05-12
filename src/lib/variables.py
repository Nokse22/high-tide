from gi.repository import Gdk

import os

from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.mix import Mix, MixV2

from ..pages import artistPage
from ..pages import albumPage

import threading

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
    global sidebar_list
    global search_entry


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
        print("item successfully added to my collection")
        btn.set_icon_name("heart-filled-symbolic")
        get_favourites()
    else:
        print("failed to add item to my collection")


def remove_from_my_collection(btn, item):
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
        print("item successfully removed from my collection")
        btn.set_icon_name("heart-outline-thick-symbolic")


def on_in_to_my_collection_button_clicked(btn, item):
    if btn.get_icon_name() == "heart-outline-thick-symbolic":
        threading.Thread(
            target=th_add_to_my_collection,
            args=(btn, item,),
        ).start()
    else:
        threading.Thread(
            target=remove_from_my_collection,
            args=(btn, item,),
        ).start()


def share_this(item):
    clipboard = Gdk.Display().get_default().get_clipboard()

    if isinstance(item, Track):
        clipboard.set(item.share_url)
    elif isinstance(item, Album):
        clipboard.set(item.share_url)
    elif isinstance(item, Artist):
        clipboard.set(item.share_url)
    elif isinstance(item, Playlist):
        clipboard.set(item.share_url)


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
            page = artistPage(uri_parts[1]).load()
            navigation_view.push(page)
        case "album":
            page = albumPage(uri_parts[1]).load()
            navigation_view.push(page)

    return True
