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

from ..lib import utils

import threading
import requests
import random
import os

class Page(Adw.NavigationPage):
    __gtype_name__ = 'Page'

    def __init__(self, _window, _item, _name):
        super().__init__()

        # self.builder = None

        self.window = _window
        self.set_title(_name)

        self.builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/pages_ui/page_template.ui')
        self.item = _item

        self.content = self.builder.get_object("_content")
        self.object = self.builder.get_object("_main")
        self.spinner = self.builder.get_object("_spinner")

        self.set_child(self.object)

    def load(self):
        th = threading.Thread(target=self._load_page)
        th.deamon = True
        th.start()

    def _load_page(self):
        return

    def get_artist_label(self, artist):
        artist_button = Gtk.Button(css_classes=["artist-button", "link-text"])
        artist_button.set_child(Gtk.Inscription(hexpand=True, text=artist.name, css_classes=["artist-button", "link-text"]))
        artist_button.connect("clicked", self.on_artist_button_clicked, artist)
        return artist_button

    def get_album_card(self, item):
        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(item.name)
        builder.get_object('_detail_label').set_visible(False)
        builder.get_object('_details_box').append(self.get_artist_label(item.artist))
        image = builder.get_object('_image')
        th = threading.Thread(target=self.add_image, args=(image, item))
        th.deamon = True
        th.start()
        builder.get_object('_button').connect("clicked", self.on_album_button_clicked, item)
        return builder.get_object('_main')

    def get_track_listing(self, track):
        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/detailed_track_listing.ui')

        builder.get_object('_track_title_label').set_label(track.name)
        builder.get_object('_track_artist_box').append(self.get_artist_label(track.artist))
        builder.get_object('_track_album_label').set_label(track.album.name)

        builder.get_object('_track_title_label_2').set_label(track.name)
        builder.get_object('_track_artist_box_2').append(self.get_artist_label(track.artist))

        image = builder.get_object('_image')
        # image_link = f"https://resources.tidal.com/images/{track.album.cover.replace('-', '/')}/80x80.jpg"
        th = threading.Thread(target=self.add_image, args=(image, track.album))
        th.deamon = True
        th.start()
        builder.get_object('_track_duration_label').set_label(utils.pretty_duration(track.duration))

        return builder.get_object('_main')

    def get_mix_card(self, item):
        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(item.title)
        builder.get_object('_detail_label').set_text(item.sub_title)
        image = builder.get_object('_image')
        th = threading.Thread(target=self.add_image, args=(image, item))
        th.deamon = True
        th.start()
        builder.get_object('_button').connect("clicked", self.on_mix_button_clicked, item)
        return builder.get_object('_main')

    def on_mix_button_clicked(self, btn, mix):
        self.window.sidebar_list.select_row(None)

        from .mix_page import mixPage

        page = mixPage(self.window, mix, mix.title)
        page.load()
        self.window.navigation_view.push(page)

    def get_album_track_listing(self, track):
        box = Gtk.Box(spacing=6)
        box.append(Gtk.Label(label=track.name, xalign=0, ellipsize=3, hexpand=True))
        box.append(Gtk.Label(label=utils.pretty_duration(track.duration), xalign=0, ellipsize=3, halign=Gtk.Align.END, hexpand=True))
        return box

    def on_play_button_clicked(self, btn):
        self.window.player_object.current_mix_album = self.item
        self.window.player_object.current_mix_album_list = self.item.items()
        track = self.window.player_object.current_mix_album_list[0]
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = 0

    def on_shuffle_button_clicked(self, btn):
        # self.window.player_object.shuffle(True)
        self.window.player_object.current_mix_album = self.item
        self.window.player_object.current_mix_album_list = self.item.items()
        self.window.player_object.play_shuffle()

    def on_artist_button_clicked(self, btn, artist):
        print(artist)
        self.window.sidebar_list.select_row(None)

        from .artist_page import artistPage

        page = artistPage(self.window, artist, artist.name)
        page.load()
        self.window.navigation_view.push(page)

    def add_image(self, image_widget, item):
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

            GLib.idle_add(self._add_image, image_widget, file_path)

    def _add_image(self, image_widget, file_path):
        image_widget.set_from_file(file_path)

    def add_image_to_avatar(self, avatar_widget, image_url):
        try:
            response = requests.get(image_url)
        except:
            return

        if response.status_code == 200:
            image_data = response.content
            file_path = f"{random.randint(0, 100)}.jpg"
            with open(file_path, "wb") as file:
                file.write(image_data)

            GLib.idle_add(self._add_image_to_avatar, avatar_widget, file_path)

    def _add_image_to_avatar(self, avatar_widget, file_path):
        file = Gio.File.new_for_path(file_path)
        image = Gdk.Texture.new_from_resource(file)
        avatar_widget.set_custom_image(image)

    def on_row_selected(self, list_box, row):
        index = int(row.get_child().get_name())

        self.window.player_object.current_mix_album = self.item
        self.window.player_object.current_mix_album_list = self.item.items()
        track = self.window.player_object.current_mix_album_list[index]
        self.window.player_object.play_track(track)
        self.window.player_object.current_song_index = index

    def get_carousel(self, title):
        cards_box = Gtk.Box()
        box = Gtk.Box(orientation=1, margin_bottom=12, margin_start=12, margin_end=12)
        title_box = Gtk.Box(margin_top=12)
        title_box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-3"]))
        prev_button = Gtk.Button(icon_name="go-next-symbolic", margin_start=6, halign=Gtk.Align.END, css_classes=["circular"])
        next_button = Gtk.Button(icon_name="go-previous-symbolic", hexpand=True, halign=Gtk.Align.END, css_classes=["circular"])
        title_box.append(next_button)
        title_box.append(prev_button)

        box.append(title_box)
        cards_box = Adw.Carousel(halign=Gtk.Align.START, allow_scroll_wheel=False, allow_long_swipes=True)
        cards_box.set_overflow(Gtk.Overflow.VISIBLE)
        box.append(cards_box)

        prev_button.connect("clicked", self.carousel_go_prev, cards_box)
        next_button.connect("clicked", self.carousel_go_next, cards_box)

        return box, cards_box

    def carousel_go_prev(self, btn, carousel):
        pos = carousel.get_position()
        if pos + 2 >= carousel.get_n_pages():
            if pos + 1 == carousel.get_n_pages():
                return
            else:
                next_page = carousel.get_nth_page(pos + 1)
        else:
            next_page = carousel.get_nth_page(pos + 2)
        if next_page != None:
            carousel.scroll_to(next_page, True)

    def carousel_go_next(self, btn, carousel):
        pos = carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = carousel.get_nth_page(0)
        else:
            next_page = carousel.get_nth_page(pos - 2)

        carousel.scroll_to(next_page, True)

    def get_playlist_card(self, playlist):
        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(playlist.name)
        creator = playlist.creator
        if creator:
            creator = creator.name
        else:
            creator = "TIDAL"
        builder.get_object('_detail_label').set_text(f"by {creator}")
        # builder.get_object('_details_box').append(self.get_artist_label(item.artist))
        image = builder.get_object('_image')
        th = threading.Thread(target=self.add_image, args=(image, playlist))
        th.deamon = True
        th.start()
        builder.get_object('_button').connect("clicked", self.on_playlist_button_clicked, playlist)
        return builder.get_object('_main')

    def on_playlist_button_clicked(self, btn, playlist):
        self.window.sidebar_list.select_row(None)

        from .playlist_page import playlistPage

        page = playlistPage(self.window, playlist, playlist.name)
        page.load()
        self.window.navigation_view.push(page)

    def on_album_button_clicked(self, btn, album):
        self.window.sidebar_list.select_row(None)
        self.window.player_object.current_mix_album = album

        from .album_page import albumPage

        page = albumPage(self.window, album, album.name)
        page.load()
        self.window.navigation_view.push(page)

    def get_artist_page(self, artist):
        from .artist_page import artistPage

        page = artistPage(self.window, artist, artist.name)
        page.load()
        self.window.navigation_view.push(page)

    def get_artist_card(self, item): #ported
        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(item.name)
        builder.get_object('_detail_label').set_text("Artist")
        # builder.get_object('_details_box').append(self.get_artist_label(item.artist))
        image = builder.get_object('_image')
        image.add_css_class("artist-picture")

        th = threading.Thread(target=self.add_image, args=(image, item))
        th.deamon = True
        th.start()

        builder.get_object('_button').connect("clicked", self.on_artist_button_clicked, item)
        return builder.get_object('_main')

    def get_page_item_card(self, page_item):
        # image_url = page_item.image()

        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(page_item.short_header)
        builder.get_object('_detail_label').set_text(page_item.short_sub_header[0:50])
        # builder.get_object('_details_box').append(self.get_artist_label(item.artist))
        image = builder.get_object('_image')
        # th = threading.Thread(target=self.add_image, args=(image, image_url))
        # th.deamon = True
        # th.start()
        # builder.get_object('_button').connect("clicked", self.on_playlist_button_clicked, page_item)
        return builder.get_object('_main')

    def get_page_item_card(self, page_item):
        # image_url = page_item.image()

        builder = Gtk.Builder.new_from_resource('/io/github/nokse22/high-tide/ui/card_template.ui')

        builder.get_object('_title_label').set_text(page_item.short_header)
        builder.get_object('_detail_label').set_text(page_item.short_sub_header[0:50])
        # builder.get_object('_details_box').append(self.get_artist_label(item.artist))
        image = builder.get_object('_image')
        # th = threading.Thread(target=self.add_image, args=(image, image_url))
        # th.deamon = True
        # th.start()
        # builder.get_object('_button').connect("clicked", self.on_playlist_button_clicked, page_item)
        return builder.get_object('_main')

    def get_page_link_card(self, page_link):

        button = Gtk.Button(label=page_link.title, margin_start=12, margin_end=12,
                hexpand=True, width_request=200, vexpand=True)

        button.connect("clicked", self.on_page_link_clicked, page_link)

        return button

    def on_page_link_clicked(self, btn, page_link):

        from .generic_page import genericPage

        page = genericPage(self.window, page_link, page_link.title)
        page.load()
        self.window.navigation_view.push(page)
