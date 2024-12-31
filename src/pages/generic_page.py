# generic_page.py
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


from tidalapi.page import PageItem, PageLink
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist

from .page import Page
from ..widgets import HTCarouselWidget
from ..widgets import HTTracksListWidget


class genericPage(Page):
    __gtype_name__ = 'genericPage'

    """It is used for explore page categories page"""

    def _th_load_page(self):
        generic_content = self.item.get()

        for index, category in enumerate(generic_content.categories):
            if isinstance(category, PageItem):
                continue
            items = []

            if isinstance(category.items[0], Track):
                tracks_list_widget = HTTracksListWidget(category.title)
                tracks_list_widget.set_tracks_list(category.items)
                self.page_content.append(tracks_list_widget)
            else:
                carousel = HTCarouselWidget(category.title)
                self.disconnectables.append(carousel)
                self.page_content.append(carousel)

                for item in category.items:
                    if isinstance(item, PageItem):  # Featured
                        button = self.get_page_item_card(item)
                        carousel.append_card(button)
                    elif isinstance(item, PageLink):  # Generes and moods
                        items.append("\t" + item.title)
                        button = self.get_page_link_card(item)
                        carousel.append_card(button)
                    elif isinstance(item, Mix):  # Mixes and for you
                        button = self.get_mix_card(item)
                        carousel.append_card(button)
                    elif isinstance(item, Album):
                        album_card = self.get_album_card(item)
                        carousel.append_card(album_card)
                    elif isinstance(item, Artist):
                        button = self.get_artist_card(item)
                        carousel.append_card(button)
                    elif isinstance(item, Playlist):
                        button = self.get_playlist_card(item)
                        carousel.append_card(button)

        self._page_loaded()
