# home_page.py
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

from tidalapi.page import PageItem, PageLink, ShortcutList, TrackList

from .page import Page

from ..lib import utils

from gettext import gettext as _


class HTHomePage(Page):
    __gtype_name__ = "HTHomePage"

    home = None

    def _load_async(self):
        self.home = utils.session.home()

    def _load_finish(self):
        self.set_tag("home")
        self.set_title(_("Home"))

        for index, category in enumerate(self.home.categories):
            try:
                if isinstance(category.items[0], PageItem) or isinstance(
                    category.items[0], PageLink
                ):
                    continue

                if isinstance(category.items[0], Track):
                    self.new_track_list_for(category.title, category.items)
                else:
                    self.new_carousel_for(category.title, category.items)
            except Exception as e:
                print(e)
