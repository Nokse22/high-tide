# mix_page.py
#
# Copyright 2023 Nokse
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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib

import threading

from ..widgets import HTGenericTrackWidget
from ..widgets import HTCarouselWidget
from ..widgets import HTCardWidget
from ..widgets import HTTracksListWidget
from ..widgets import HTAutoLoadWidget

from ..lib import utils

from ..disconnectable_iface import IDisconnectable

from gettext import gettext as _


class Page(Adw.NavigationPage, IDisconnectable):
    __gtype_name__ = "Page"

    """It's the base class for all types of pages,
    it contains all the shared functions"""

    def __init__(self):
        IDisconnectable.__init__(self)
        super().__init__()

        self.set_title(_("Loading..."))

        self.builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/page_template.ui"
        )

        self.content = self.builder.get_object("_content")
        self.content_stack = self.builder.get_object("_content_stack")
        self.object = self.builder.get_object("_main")
        self.scrolled_window = self.builder.get_object("_scrolled_window")

        self.set_child(self.object)

    def load(self):
        """Called when the page is created, it just starts a thread running
        the actual function to load the page UI"""

        def _loaded():
            self._load_finish()
            self.content_stack.set_visible_child_name("content")

        def _load():
            try:
                self._load_async()
            except Exception as e:
                print(e)
                return

            GLib.idle_add(_loaded)

        threading.Thread(target=_load).start()

        return self

    def _load_async(self):
        """Fetch all data here"""
        raise NotImplementedError

    def _load_finish(self):
        """Update the UI here"""
        raise NotImplementedError

    def append(self, widget):
        if isinstance(widget, IDisconnectable):
            self.disconnectables.append(widget)
        self.content.append(widget)

    def get_card(self, item):
        card = HTCardWidget(item)
        self.disconnectables.append(card)
        return card

    def get_track_listing(self, track):
        track_listing = HTGenericTrackWidget(track, False)
        self.disconnectables.append(track_listing)
        return track_listing

    def get_album_track_listing(self, track):
        track_listing = HTGenericTrackWidget(track, True)
        self.disconnectables.append(track_listing)
        return track_listing

    def on_play_button_clicked(self, btn):
        utils.player_object.play_this(self.item)

    def on_shuffle_button_clicked(self, btn):
        utils.player_object.shuffle_this(self.item)

    def new_link_carousel_for(self, title, items):
        """Similar to the last function but used to display links to other
        pages like in the explore page to display genres..."""

        cards_box = Gtk.Box()
        box = Gtk.Box(
            orientation=1,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
            overflow=Gtk.Overflow.HIDDEN,
        )
        title_box = Gtk.Box(margin_top=12, margin_bottom=6)
        title_box.append(
            Gtk.Label(label=title, xalign=0, css_classes=["title-3"], ellipsize=3)
        )
        prev_button = Gtk.Button(
            icon_name="go-next-symbolic",
            margin_start=6,
            halign=Gtk.Align.END,
            css_classes=["circular"],
        )
        next_button = Gtk.Button(
            icon_name="go-previous-symbolic",
            hexpand=True,
            halign=Gtk.Align.END,
            css_classes=["circular"],
        )
        title_box.append(next_button)
        title_box.append(prev_button)

        box.append(title_box)
        cards_box = Adw.Carousel(
            halign=Gtk.Align.FILL, allow_scroll_wheel=False, allow_long_swipes=True
        )
        cards_box.set_overflow(Gtk.Overflow.VISIBLE)
        box.append(cards_box)

        self.signals.append((
            prev_button,
            prev_button.connect("clicked", self.carousel_go_prev, cards_box, 1),
        ))

        self.signals.append((
            next_button,
            next_button.connect("clicked", self.carousel_go_next, cards_box, 1),
        ))

        buttons_for_page = 0

        flow_box = Gtk.FlowBox(homogeneous=True, height_request=100)
        cards_box.append(flow_box)
        self.append(box)

        for index, item in enumerate(items):
            if buttons_for_page == 4:
                flow_box = Gtk.FlowBox(homogeneous=True, height_request=100)
                cards_box.append(flow_box)
                buttons_for_page = 0
            button = self.get_page_link_card(item)
            flow_box.append(button)
            buttons_for_page += 1

    def carousel_go_prev(self, btn, carousel, jump=2):
        pos = carousel.get_position()
        if pos + 2 >= carousel.get_n_pages():
            if pos + 1 == carousel.get_n_pages():
                return
            else:
                next_page = carousel.get_nth_page(pos + 1)
        else:
            next_page = carousel.get_nth_page(pos + jump)
        if next_page is not None:
            carousel.scroll_to(next_page, True)

    def carousel_go_next(self, btn, carousel, jump=2):
        pos = carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = carousel.get_nth_page(0)
        else:
            next_page = carousel.get_nth_page(pos - jump)

        carousel.scroll_to(next_page, True)

    def get_carousel(self, carousel_title):
        carousel = HTCarouselWidget(carousel_title)
        self.disconnectables.append(carousel)
        return carousel

    def new_carousel_for(self, carousel_title, carousel_content, more_function=None):
        if len(carousel_content) == 0:
            return

        carousel = HTCarouselWidget(carousel_title)
        carousel.set_items(carousel_content)

        if more_function:
            carousel.set_more_function(more_function)

        self.append(carousel)

    def new_track_list_for(self, list_title, list_content, more_function=None):
        if len(list_content) == 0:
            return

        tracks_list_widget = HTTracksListWidget(list_title)
        tracks_list_widget.set_tracks_list(list_content)

        if more_function:
            tracks_list_widget.set_more_function(more_function)

        self.append(tracks_list_widget)

    def new_auto_load_for(self, list_title, list_content=None, more_function=None):
        if len(list_content) == 0:
            return

        auto_load = HTAutoLoadWidget()
        auto_load.set_scrolled_window(self.scrolled_window)

        if more_function:
            auto_load.set_function(more_function)

        if list_content:
            auto_load.set_items(list_content)

    def on_playlist_button_clicked(self, btn, playlist):
        utils.sidebar_list.select_row(None)

        from .playlist_page import HTPlaylistPage

        page = HTPlaylistPage(playlist, playlist.name).load()
        utils.navigation_view.push(page)

    def get_page_link_card(self, page_link):
        button = Gtk.Button(
            label=page_link.title,
            margin_start=12,
            margin_end=12,
            hexpand=True,
            width_request=200,
            vexpand=True,
        )
        self.signals.append((
            button,
            button.connect("clicked", self.on_page_link_clicked, page_link),
        ))

        return button

    def on_page_link_clicked(self, btn, page_link):
        from .generic_page import HTGenericPage

        page = HTGenericPage.new_from_function(page_link.get).load()
        utils.navigation_view.push(page)
