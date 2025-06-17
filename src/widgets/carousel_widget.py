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
    __gtype_name__ = "HTCarouselWidget"

    """It is used to display multiple elements side by side with
    navigation arrows"""

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
        self.type = None

        self.items = []

    def set_more_function(self, _type, _function):
        self.more_button.set_visible(True)
        self.more_function = _function
        self.type = _type

    def append_card(self, card):
        self.disconnectables.append(card)
        self.carousel.append(card)
        self.n_pages = self.carousel.get_n_pages()

        if self.n_pages != 2:
            self.next_button.set_sensitive(True)

    def set_items(self, items_list, items_type):
        self.items = items_list
        self.type = items_type

        for index, item in enumerate(self.items):
            if index >= 8:
                self.more_button.set_visible(True)
                break
            self.append_card(HTCardWidget(item))

    def on_more_clicked(self, *args):
        from ..pages import fromFunctionPage

        if self.more_function is None:
            page = fromFunctionPage(self.type, self.title)
            page.set_items(self.items)
        else:
            page = fromFunctionPage(self.type, self.title)
            page.set_function(self.more_function)

        page.load()
        utils.navigation_view.push(page)

    def carousel_go_next(self, btn):
        pos = self.carousel.get_position()
        total_pages = self.carousel.get_n_pages()

        if pos + 3 >= total_pages:
            next_pos = max(0, total_pages - 2)
        else:
            next_pos = pos + 2

        next_page = self.carousel.get_nth_page(next_pos)
        if next_page is not None:
            self.carousel.scroll_to(next_page, True)

        self.prev_button.set_sensitive(next_pos > 0)
        self.next_button.set_sensitive(next_pos < total_pages - 2)

    def carousel_go_prev(self, btn):
        pos = self.carousel.get_position()
        total_pages = self.carousel.get_n_pages()

        if pos - 2 < 0:
            next_pos = 0
        else:
            next_pos = pos - 2

        next_page = self.carousel.get_nth_page(next_pos)
        if next_page is not None:
            self.carousel.scroll_to(next_page, True)

        # Update button sensitivity
        self.prev_button.set_sensitive(next_pos > 0)
        self.next_button.set_sensitive(next_pos < total_pages - 2)

    def __repr__(self, *args):
        return "<HTCarouselWidget>"
