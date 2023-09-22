from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gdk

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.user import Favorites

import requests

def pretty_duration(secs):
    if not secs:
        return
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60

    if hours > 0:
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    else:
        return f"{int(minutes):02}:{int(seconds):02}"

def add_image(image_widget, item):
    try:
        image_url = item.image()
        response = requests.get(image_url)
    except Exception as e:
        print(str(e))
        return
    if response.status_code == 200:
        image_data = response.content
        file_path = f"tmp_img/{item.id}.jpg"
        with open(file_path, "wb") as file:
            file.write(image_data)

        GLib.idle_add(_add_image, image_widget, file_path)

def _add_image(image_widget, file_path):
    image_widget.set_from_file(file_path)
