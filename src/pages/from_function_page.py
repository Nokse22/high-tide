# single_type_page.py
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

from .page import Page

from ..disconnectable_iface import IDisconnectable

from ..widgets import HTAutoLoadWidget


class HTFromFunctionPage(Page):
    __gtype_name__ = "HTFromFunctionPage"

    """Used to display lists of albums/artists/mixes/playlists and tracks
    from a request function"""

    def __init__(self, _title=""):
        IDisconnectable.__init__(self)
        super().__init__()

        self.set_title(_title)

        self.auto_load = HTAutoLoadWidget(
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12
        )
        self.auto_load.set_scrolled_window(self.scrolled_window)

        self.append(self.auto_load)

    def _load_async(self):
        self.auto_load.th_load_items()

    def _load_finish(self):
        ...

    def set_function(self, function):
        self.auto_load.set_function(function)

    def set_items(self, items):
        self.auto_load.set_items(items)
