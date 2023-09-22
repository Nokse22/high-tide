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

class genericPage(Page):
    __gtype_name__ = 'genericPage'

    def _load_page(self):
        builder = Gtk.Builder.new_from_file("/home/lorenzo/Projects/high-tide/data/ui/pages_ui/home_page_template.ui")

        page_content = builder.get_object("_main")
        generic_page_content = builder.get_object("_content")

        generic_content = self.item.get()

        # print(generic_content.categories)

        for index, category in enumerate(generic_content.categories):
            items = []

            carousel, cards_box = self.get_carousel(category.title)

            if not isinstance(category.items[0], Track):
                generic_page_content.append(carousel)
            else:
                continue
            # print("\n\t\t" + category.title)

            print(category.items)

            for item in category.items:
                if isinstance(item, PageItem): # Featured
                    button = self.get_page_item_card(item)
                    cards_box.append(button)
                elif isinstance(item, PageLink): # Generes and moods
                    items.append("\t" + item.title)
                    button = self.get_page_link_card(item)
                    cards_box.append(button)
                elif isinstance(item, Mix): # Mixes and for you
                    button = self.get_mix_card(item)
                    cards_box.append(button)
                elif isinstance(item, Album):
                    album_card = self.get_album_card(item)
                    cards_box.append(album_card)
                elif isinstance(item, Artist):
                    button = self.get_artist_card(item)
                    cards_box.append(button)
                elif isinstance(item, Playlist):
                    button = self.get_playlist_card(item)
                    cards_box.append(button)

        self.content.remove(self.spinner)
        self.content.append(page_content)
