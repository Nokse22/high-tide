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

from ..widgets import HTCarouselWidget
from ..widgets import HTCardWidget
from ..widgets import HTTracksListWidget
from ..widgets import HTAutoLoadWidget

from ..lib import utils

from ..disconnectable_iface import IDisconnectable

from gettext import gettext as _


class Page(Adw.NavigationPage, IDisconnectable):
    """Base class for all types of pages in the High Tide application.

    This class provides shared functionality for all page types, including
    UI loading, content management, and common widget creation methods.
    It handles the page lifecycle and provides utilities for displaying
    carousels, track listings, and other common UI elements.
    """

    __gtype_name__ = "Page"

    id = None

    @classmethod
    def new_from_id(cls, id):
        """Create a new Page instance from the id should be used only on pages that
        support it.

        Args:
            id: The page id

        Returns:
            Page: A new instance configured with the provided id
        """
        instance = cls()

        instance.id = id

        return instance

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
        """Load the page content asynchronously.

        Starts a background thread to fetch data via _load_async() and then updates
        the UI via _load_finish().
        Shows a loading state until content is ready.

        Returns:
            Page: Self for method chaining
        """

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

    def _load_async(self) -> None:
        """Fetch all data for the page in a background thread.

        This method should be overridden by subclasses to implement
        their specific data loading logic. Called from a background thread.

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def _load_finish(self) -> None:
        """Update the UI with loaded data.

        This method should be overridden by subclasses to implement
        their specific UI update logic. Called on the main thread after
        _load_async() completes successfully.

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def append(self, widget) -> None:
        """Append a widget to the page content.

        Automatically tracks disconnectable widgets for cleanup when the page
        is removed from navigation.

        Args:
            widget: The GTK widget to append to the page content
        """
        if isinstance(widget, IDisconnectable):
            self.disconnectables.append(widget)
        self.content.append(widget)

    def get_card(self, item) -> HTCardWidget:
        """Create a card widget for a TIDAL item.

        Args:
            item: A TIDAL object (Track, Album, Artist, Playlist, etc.)

        Returns:
            HTCardWidget: A card widget displaying the item
        """
        card = HTCardWidget(item)
        self.disconnectables.append(card)
        return card

    def on_play_button_clicked(self, btn) -> None:
        """Handle play button clicks by starting playback of the page's item.

        Args:
            btn: The play button widget that was clicked
        """
        utils.player_object.play_this(self.item)

    def on_shuffle_button_clicked(self, btn) -> None:
        """Handle shuffle button clicks by starting shuffled playback.

        Args:
            btn: The shuffle button widget that was clicked
        """
        utils.player_object.shuffle_this(self.item)

    def new_link_carousel_for(self, title, items) -> None:
        """Create a carousel of page link buttons.

        Creates a horizontal scrollable carousel containing buttons that link
        to other pages, commonly used for genre links and similar navigation.

        Args:
            title (str): The title to display above the carousel
            items: List of items with .title attribute and .get() method for navigation
        """

        # TODO make a separate widget for this

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

    def carousel_go_prev(self, btn, carousel) -> None:
        pos = carousel.get_position()
        if pos + 2 >= carousel.get_n_pages():
            if pos + 1 == carousel.get_n_pages():
                return
            else:
                next_page = carousel.get_nth_page(pos + 1)
        else:
            next_page = carousel.get_nth_page(pos + 1)
        if next_page is not None:
            carousel.scroll_to(next_page, True)

    def carousel_go_next(self, btn, carousel) -> None:
        pos = carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = carousel.get_nth_page(0)
        else:
            next_page = carousel.get_nth_page(pos - 1)

        carousel.scroll_to(next_page, True)

    def new_carousel_for(self, carousel_title, carousel_content, more_function=None):
        """Create and append a carousel widget with content.

        Args:
            carousel_title (str): The title to display for the carousel
            carousel_content: List of items to display in the carousel
            more_function: Optional function to call when "See More" is clicked
        """
        if len(carousel_content) == 0:
            return

        carousel = HTCarouselWidget(carousel_title)
        carousel.set_items(carousel_content)

        if more_function:
            carousel.set_more_function(more_function)

        self.append(carousel)

    def new_track_list_for(self, list_title, list_content, more_function=None):
        """Create and append a track list widget with content.

        Args:
            list_title (str): The title to display for the track list
            list_content: List of Track objects to display
            more_function: Optional function to call when "See More" is clicked
        """
        if len(list_content) == 0:
            return

        tracks_list_widget = HTTracksListWidget(list_title)
        tracks_list_widget.set_tracks_list(list_content)

        if more_function:
            tracks_list_widget.set_more_function(more_function)

        self.append(tracks_list_widget)

    def new_auto_load_for(self, list_title, list_content=None, more_function=None):
        """Create an auto-loading widget that loads more content on scroll.

        Args:
            list_title (str): The title for the auto-load widget
            list_content: Optional initial list of items to display
            more_function: Function to call to load more content
        """
        if len(list_content) == 0:
            return

        auto_load = HTAutoLoadWidget()
        auto_load.set_scrolled_window(self.scrolled_window)

        if more_function:
            auto_load.set_function(more_function)

        if list_content:
            auto_load.set_items(list_content)

    def get_page_link_card(self, page_link):
        """Create a button card for navigating to another page.

        Args:
            page_link: An object with .title attribute and .get() method

        Returns:
            Gtk.Button: A button configured to navigate to the linked page
        """

        # TODO make a separate widget for this

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
        """Handle page link button clicks by navigating to the linked page.

        Args:
            btn: The button that was clicked
            page_link: An object with a .get() method that returns page content
        """
        from .generic_page import HTGenericPage

        page = HTGenericPage.new_from_function(page_link.get).load()
        utils.navigation_view.push(page)
