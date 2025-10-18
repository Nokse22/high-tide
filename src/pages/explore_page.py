# explore_page.py
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

from gettext import gettext as _

from gi.repository import Gtk

from ..lib import utils
from .generic_page import HTGenericPage
from .search_page import HTSearchPage

import logging
logger = logging.getLogger(__name__)


class HTExplorePage(HTGenericPage):
    """A page to display the explore page"""

    __gtype_name__ = "HTExplorePage"

    tries = 0

    def _load_async(self) -> None:
        try:
            self.page = utils.session.explore()
        except Exception:
            logger.exception("Error while loading Explore page")
            self.tries += 1
            if self.tries < 5:
                self._load_async()
            return

    def _load_finish(self) -> None:
        self.set_tag("explore")
        self.set_title(_("Explore"))

        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/search_entry.ui"
        )
        search_entry = builder.get_object("search_entry")
        self.signals.append((
            search_entry,
            search_entry.connect("activate", self.on_search_activated),
        ))

        self.append(search_entry)

        HTGenericPage._load_finish(self)

    def on_search_activated(self, entry) -> None:
        query = entry.get_text()
        page = HTSearchPage(query).load()
        utils.navigation_view.push(page)
