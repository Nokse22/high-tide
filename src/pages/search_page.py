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

from ..lib import utils


import threading
import requests
import random

from .page import Page

class searchPage(Page):
    __gtype_name__ = 'searchPage'

    def _load_page(self):
        builder = Gtk.Builder.new_from_resource("/io/github/nokse22/high-tide/ui/pages_ui/home_page_template.ui")

        page_content = builder.get_object("_main")
        results_box = builder.get_object("_content")

        query = self.window.search_entry.get_text()

        results = self.window.session.search(query, [Artist, Album, Playlist, Track], 10)

        print(query, results)

        top_hit = results["top_hit"]
        # results_box.append(Gtk.Label(label=top_hit.name))

        carousel, cards_box = self.get_carousel("Artists")
        artists = results["artists"]

        if len(artists) > 0:
            results_box.append(carousel)
            for artist in artists:
                artist_card = self.get_artist_card(artist)
                cards_box.append(artist_card)

        carousel, cards_box = self.get_carousel("Albums")
        albums = results["albums"]
        if len(albums) > 0:
            results_box.append(carousel)
            for album in albums:
                album_card = self.get_album_card(album)
                cards_box.append(album_card)

        scrolled_window = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)

        self.content.remove(self.spinner)
        self.content.append(page_content)

