import os

import tidalapi
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.mix import Mix, MixV2

from ..pages import artistPage
from ..pages import albumPage

import threading

favourite_tracks = []
favourite_artists = []
favourite_albums = []
favourite_playlists = []

def init():
    global DATA_DIR
    DATA_DIR = os.environ.get('XDG_DATA_HOME')
    CACHE_DIR = os.environ.get('XDG_CACHE_HOME')
    global IMG_DIR
    IMG_DIR = f"{CACHE_DIR}/images"

    if not os.path.exists(IMG_DIR):
        os.makedirs(IMG_DIR)

    print(DATA_DIR)

    global session
    global navigation_view
    global player_object
    global sidebar_list
    global search_entry

def get_favourites():
    global favourite_tracks
    global favourite_artists
    global favourite_albums
    global favourite_playlists

    favourite_artists = session.user.favorites.artists()
    favourite_tracks = session.user.favorites.tracks()
    favourite_albums = session.user.favorites.albums()
    favourite_playlists = session.user.favorites.playlists()

def is_favourited(item):
    global favourite_tracks
    global favourite_artists
    global favourite_albums
    global favourite_playlists

    if isinstance(item, Track):
        for fav in favourite_tracks:
            if (fav.id == item.id):
                return True

    elif isinstance(item, Mix):
        return # still not supported

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

def add_to_my_collection(btn, item):
    if isinstance(item, Track):
        result = session.user.favorites.add_track(item.id)
    elif isinstance(item, Mix):
        return # still not supported
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
        return # still not supported
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
        threading.Thread(target=add_to_my_collection, args=(btn, item,)).start()
    else:
        threading.Thread(target=remove_from_my_collection, args=(btn, item,)).start()

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

def open_uri(label, uri, turn=True):
    print(uri)
    th= threading.Thread(target=_load_object, args=(uri,))
    th.start()
    return turn

def _open_uri(uri, loaded_object):
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            page = artistPage(loaded_object, loaded_object.name)
            page.load()
            navigation_view.push(page)
        case "album":
            page = albumPage(loaded_object, loaded_object.name)
            page.load()
            navigation_view.push(page)

def _load_object(uri):
    uri_parts = uri.split(":")

    match uri_parts[0]:
        case "artist":
            loaded_object = Artist(session, uri_parts[1])
        case "album":
            loaded_object = Album(session, uri_parts[1])

    _open_uri(uri, loaded_object)
