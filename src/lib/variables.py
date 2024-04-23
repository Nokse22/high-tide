import os

import tidalapi
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from ..pages import artistPage
from ..pages import albumPage

import threading

def init():
    global DATA_DIR
    DATA_DIR = os.environ.get('XDG_DATA_HOME')
    global IMG_DIR
    IMG_DIR = f"{DATA_DIR}/images"

    if not os.path.exists(IMG_DIR):
        # shutil.rmtree(IMG_DIR)
        os.makedirs(IMG_DIR)

    print(DATA_DIR)

    global session

    global navigation_view

    global player_object

    global sidebar_list

    global favourite_tracks

def open_uri(label, uri):
    print(uri)
    th= threading.Thread(target=_load_object, args=(uri,))
    th.start()
    return True

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
