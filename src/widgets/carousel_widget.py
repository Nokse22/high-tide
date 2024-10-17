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
from ..lib import variables

@Gtk.Template(resource_path='/io/github/nokse22/HighTide/ui/widgets/carousel_widget.ui')
class HTCarouselWidget(Gtk.Box):
    __gtype_name__ = 'HTCarouselWidget'

    """It is used to display multiple elements side by side with navigation arrows"""

    title_label = Gtk.Template.Child()
    next_button = Gtk.Template.Child()
    prev_button = Gtk.Template.Child()
    carousel = Gtk.Template.Child()
    more_button = Gtk.Template.Child()

    def __init__(self, _title=""):
        super().__init__()

        self.signals = []

        self.signals.append(
            (self, self.connect("unrealize", self.__on_unrealized))
        )

        self.signals.append(
            (self.next_button, self.next_button.connect("clicked", self.carousel_go_next))
        )

        self.signals.append(
            (self.prev_button, self.prev_button.connect("clicked", self.carousel_go_prev))
        )

        self.signals.append(
            (self.more_button, self.more_button.connect("clicked", self.on_more_clicked))
        )

        self.n_pages = 0

        self.title = _title
        self.title_label.set_label(self.title)

        self.more_function = None
        self.type = None

        self.items = []

        # self.card_width = 0
        # self.connect("notify::width", self._width_changed)

    def set_more_function(self, _type, _function):
        self.more_button.set_visible(True)
        self.more_function = _function
        self.type = _type

    def append_card(self, card):
        self.carousel.append(card)
        self.n_pages = self.carousel.get_n_pages()

        if self.n_pages != 2:
            self.next_button.set_sensitive(True)

    def set_items(self, items_list, items_type):
        self.items = items_list
        self.type = items_type

        for index, item in enumerate(self.items):
            if index > 8:
                self.more_button.set_visible(True)
                break
            self.append_card(HTCardWidget(item))

    def on_more_clicked(self, *args):
        from ..pages import fromFunctionPage

        if self.more_function == None:
            page = fromFunctionPage(self.type, self.title)
            page.set_items(self.items)
        else:
            page = fromFunctionPage(self.type, self.title)
            page.set_function(self.more_function)

        print(f"clicked more, items len:{len(self.items)}")

        page.load()
        variables.navigation_view.push(page)

    def carousel_go_next(self, btn):
        pos = self.carousel.get_position()
        if pos + 2 >= self.carousel.get_n_pages():
            if pos + 1 == self.carousel.get_n_pages():
                return
            else:
                next_page = self.carousel.get_nth_page(pos + 1)
        else:
            next_page = self.carousel.get_nth_page(pos + 2)

        if next_page != None:
            self.carousel.scroll_to(next_page, True)

        self.prev_button.set_sensitive(True)

    def carousel_go_prev(self, btn):
        pos = self.carousel.get_position()
        if pos - 2 < 0:
            if pos - 1 < 0:
                return
            else:
                next_page = self.carousel.get_nth_page(0)
        else:
            next_page = self.carousel.get_nth_page(pos - 2)

        self.carousel.scroll_to(next_page, True)

        if pos - 2 <= 0:
            self.prev_button.set_sensitive(False)

    def delete_signals(self):
        disconnected_signals = 0
        for obj, signal_id in self.signals:
            disconnected_signals += 1
            obj.disconnect(signal_id)

            self.signals = []
        print(f"disconnected {disconnected_signals} signals from {self}")

    def __repr__(self, *args):
        return "<HTCarouselWidget>"

    def __on_unrealized(self, *args):
        self.delete_signals()

    def __del__(self, *args):
        print(f"DELETING {self}")

