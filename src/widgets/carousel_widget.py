# carousel.py
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

import threading
from typing import Callable

from gi.repository import GLib, Gtk, Adw
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track
from tidalapi.mix import Mix, MixV2
from tidalapi.playlist import Playlist

from ..disconnectable_iface import IDisconnectable
from ..lib import utils
from ..widgets.card_widget import HTCardWidget


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/carousel_widget.ui"
)
class HTCarouselWidget(Gtk.Box, IDisconnectable):
    """A horizontal scrolling carousel widget for displaying multiple TIDAL items.

    This widget creates a scrollable carousel with navigation arrows to display
    collections of TIDAL content (albums, artists, playlists, etc.) in a
    horizontal layout. It supports "See More" functionality to navigate to
    detailed pages and automatic card creation for TIDAL items.
    """

    __gtype_name__ = "HTCarouselWidget"

    title_label = Gtk.Template.Child()
    context_button = Gtk.Template.Child()
    context_image = Gtk.Template.Child()
    context_label = Gtk.Template.Child()
    context_title_label = Gtk.Template.Child()
    next_button = Gtk.Template.Child()
    prev_button = Gtk.Template.Child()
    carousel_scrolled_window = Gtk.Template.Child()
    cards_box = Gtk.Template.Child()
    more_button = Gtk.Template.Child()

    def __init__(self, _title=""):
        IDisconnectable.__init__(self)
        super().__init__()

        self.signals.append((
            self.next_button,
            self.next_button.connect("clicked", self.carousel_go_next),
        ))

        self.signals.append((
            self.prev_button,
            self.prev_button.connect("clicked", self.carousel_go_prev),
        ))

        self.signals.append((
            self.more_button,
            self.more_button.connect("clicked", self.on_more_clicked),
        ))

        self.title = _title
        self.title_label.set_label(self.title)

        self.more_function = None
        # What the songs on the More page are played from (see play_this's source)
        self.more_source = None
        # (placeholder, page size) to let the More page be searched, see
        # HTFromFunctionPage.enable_search
        self.more_search = None

        self.items = []

        adjustment = self.carousel_scrolled_window.get_hadjustment()
        self.signals.append((
            adjustment,
            adjustment.connect("value-changed", self._update_button_sensitivity),
        ))

    def set_more_function(self, function: Callable) -> None:
        """Set the function to call when the "See More" button is clicked.

        Args:
            function: A callable that returns page content
        """
        self.more_button.set_visible(True)
        self.more_function = function

    def set_context(self, item) -> None:
        """Show what the row is about, as TIDAL does for "Because you listened
        to": the item's picture, the row's title small above it and the item's
        name as the title. Clicking it opens the item.

        Args:
            item: The album, track, artist, playlist or mix the row is about
        """
        if isinstance(item, Track):
            action, target = "win.push-album-page", item.album.id if item.album else None
        elif isinstance(item, Album):
            action, target = "win.push-album-page", item.id
        elif isinstance(item, Artist):
            action, target = "win.push-artist-page", item.id
            self.context_image.add_css_class("artist-picture")
        elif isinstance(item, Playlist):
            action, target = "win.push-playlist-page", item.id
        elif isinstance(item, (Mix, MixV2)):
            action, target = "win.push-mix-page", item.id
        else:
            return

        name = getattr(item, "name", None) or getattr(item, "title", None) or ""
        self.context_label.set_label(self.title)
        self.context_title_label.set_label(name)
        self.context_button.set_tooltip_text(name)
        if target is not None:
            self.context_button.set_action_name(action)
            self.context_button.set_action_target_value(GLib.Variant("s", str(target)))
        self.title_label.set_visible(False)
        self.context_button.set_visible(True)
        threading.Thread(
            target=utils.add_image, args=(self.context_image, item), daemon=True
        ).start()

    def set_items(self, items_list) -> None:
        """Set the list of items to display in the carousel.

        Creates card widgets for each item in the list and adds them to the carousel.

        Args:
            items_list: List of TIDAL objects to display as cards
        """
        self.items = items_list

        # Clear the cards when the items are set again
        child = self.cards_box.get_first_child()
        while child:
            if child in self.disconnectables:
                child.disconnect_all()
                self.disconnectables.remove(child)
            self.cards_box.remove(child)
            child = self.cards_box.get_first_child()
        self.more_button.set_visible(self.more_function is not None)

        cards_added = 0
        for index, item in enumerate(self.items):
            if index >= 8:
                self.more_button.set_visible(True)
                break
            card = HTCardWidget(item)
            self.disconnectables.append(card)
            self.cards_box.append(card)
            cards_added += 1

        if cards_added > 1:
            self.next_button.set_sensitive(True)

        GLib.idle_add(self._update_button_sensitivity)

    def add_header_button(self, button: Gtk.Button) -> None:
        """Add a button to the carousel header, next to the More button.

        Args:
            button: The button to add
        """
        self.more_button.get_parent().insert_child_after(button, self.more_button)

    def _update_button_sensitivity(self, *args):
        adjustment = self.carousel_scrolled_window.get_hadjustment()
        if not adjustment:
            return
        value = adjustment.get_value()
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()
        max_scroll = upper - page_size

        self.prev_button.set_sensitive(value > 0)
        self.next_button.set_sensitive(value < max_scroll)

    def on_more_clicked(self, *args):
        """Handle "See More" button clicks by navigating to a detailed page"""
        from ..pages import HTFromFunctionPage

        if self.more_function is None:
            page = HTFromFunctionPage(self.title)
            page.set_items(self.items)
        else:
            page = HTFromFunctionPage(self.title)
            page.set_function(self.more_function)
        if self.more_source is not None:
            page.auto_load.source = self.more_source
        if self.more_search is not None:
            page.enable_search(*self.more_search)

        page.load()
        utils.navigation_view.push(page)

    def carousel_go_next(self, *args):
        """Navigate to the next set of items in the carousel"""
        adjustment = self.carousel_scrolled_window.get_hadjustment()
        if not adjustment:
            return
        page_size = adjustment.get_page_size()
        value = adjustment.get_value()
        upper = adjustment.get_upper()
        new_value = min(value + page_size, upper - page_size)
        self._animate_carousel(adjustment, value, new_value)

    def carousel_go_prev(self, *args):
        """Navigate to the previous set of items in the carousel"""
        adjustment = self.carousel_scrolled_window.get_hadjustment()
        if not adjustment:
            return
        page_size = adjustment.get_page_size()
        value = adjustment.get_value()
        new_value = max(value - page_size, 0)
        self._animate_carousel(adjustment, value, new_value)

    def _animate_carousel(self, adjustment, from_value, to_value):
        """Animate the carousel scroll using Adwaita spring animation"""
        if from_value == to_value:
            return

        target = Adw.CallbackAnimationTarget.new(adjustment.set_value)

        spring_params = Adw.SpringParams.new(
            damping_ratio=1.0,
            mass=1.0,
            stiffness=1200.0
        )

        animation = Adw.SpringAnimation.new(
            self.carousel_scrolled_window,
            from_value,
            to_value,
            spring_params,
            target
        )
        animation.set_clamp(True)
        animation.play()
