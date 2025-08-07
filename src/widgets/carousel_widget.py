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

from gi.repository import Gtk

from ..widgets import HTCardWidget
from ..lib import utils

from ..disconnectable_iface import IDisconnectable


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
    next_button = Gtk.Template.Child()
    prev_button = Gtk.Template.Child()
    carousel = Gtk.Template.Child()
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

        self.n_pages = 0

        self.title = _title
        self.title_label.set_label(self.title)

        self.more_function = None

        self.items = []

    def set_more_function(self, _function):
        """Set the function to call when the "See More" button is clicked.

        Args:
            _function: A callable that returns page content
        """
        self.more_button.set_visible(True)
        self.more_function = _function

    def set_items(self, items_list):
        """Set the list of items to display in the carousel.

        Creates card widgets for each item in the list and adds them to the carousel.

        Args:
            items_list: List of TIDAL objects to display as cards
        """
        self.items = items_list

        for index, item in enumerate(self.items):
            if index >= 8:
                self.more_button.set_visible(True)
                break
            card = HTCardWidget(item)
            self.disconnectables.append(card)
            self.carousel.append(card)
            self.n_pages = self.carousel.get_n_pages()

            if self.n_pages != 2:
                self.next_button.set_sensitive(True)

    def on_more_clicked(self, *args):
        """Handle "See More" button clicks by navigating to a detailed page"""
        from ..pages import HTFromFunctionPage

        if self.more_function is None:
            page = HTFromFunctionPage(self.title)
            page.set_items(self.items)
        else:
            page = HTFromFunctionPage(self.title)
            page.set_function(self.more_function)

        page.load()
        utils.navigation_view.push(page)

    def carousel_go_next(self, btn):
        """Navigate to the next page in the carousel"""
        pos = self.carousel.get_position()
        total_pages = self.carousel.get_n_pages()

        if pos + 2 >= total_pages:
            next_pos = total_pages - 1
        else:
            next_pos = pos + 2

        next_page = self.carousel.get_nth_page(next_pos)
        if next_page is not None:
            self.carousel.scroll_to(next_page, True)

        self.prev_button.set_sensitive(next_pos > 1)
        self.next_button.set_sensitive(next_pos < total_pages - 2)

    def carousel_go_prev(self, btn):
        """Navigate to the previous page in the carousel"""
        pos = self.carousel.get_position()
        total_pages = self.carousel.get_n_pages()

        if pos - 2 < 0:
            prev_pos = 0
        else:
            prev_pos = pos - 2

        prev_page = self.carousel.get_nth_page(prev_pos)
        if prev_page is not None:
            self.carousel.scroll_to(prev_page, True)

        self.prev_button.set_sensitive(prev_pos > 1)
        self.next_button.set_sensitive(prev_pos < total_pages - 2)

    def __repr__(self, *args):
        return "<HTCarouselWidget>"
