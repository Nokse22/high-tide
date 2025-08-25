# shortcuts_widget.py
#
# Copyright 2025 Nokse <nokse@posteo.com>
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
from gettext import gettext as _
from typing import List, Union

from gi.repository import GLib, Gtk
from tidalapi import Album, Artist, Mix, MixV2, Playlist

from ..disconnectable_iface import IDisconnectable
from ..lib import utils


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/shortcut_widget.ui"
)
class HTShorcutWidget(Gtk.FlowBoxChild, IDisconnectable):
    """A widget to display a shortcut on the home page"""

    __gtype_name__ = "HTShorcutWidget"

    title_label = Gtk.Template.Child()
    subtitle_label = Gtk.Template.Child()
    image = Gtk.Template.Child()
    click_gesture = Gtk.Template.Child()

    def __init__(self, item: Union[Mix, MixV2, Album, Artist, Playlist]) -> None:
        IDisconnectable.__init__(self)
        super().__init__()

        self.action: str | None = None
        self.item: Union[Mix, MixV2, Album, Artist, Playlist] = item

        self.signals.append((
            self.click_gesture,
            self.click_gesture.connect("released", self._on_click),
        ))

        if isinstance(self.item, Mix) or isinstance(self.item, MixV2):
            self.title_label.set_label(self.item.title)
            self.subtitle_label.set_label(self.item.sub_title)
            self.action = "win.push-mix-page"
        elif isinstance(self.item, Album):
            self.title_label.set_label(self.item.name)
            self.subtitle_label.set_label(self.item.artist.name)
            self.action = "win.push-album-page"
        elif isinstance(self.item, Artist):
            self.title_label.set_label(self.item.name)
            self.subtitle_label.set_label(_("Artist"))
            self.action = "win.push-artist-page"
        elif isinstance(self.item, Playlist):
            self.title_label.set_label(self.item.name)
            creator_name = "TIDAL"
            if self.item.creator is not None and self.item.creator.name is not None:
                creator_name = self.item.creator.name
            self.subtitle_label.set_label(_("By {}").format(creator_name))
            self.action = "win.push-playlist-page"

        threading.Thread(target=utils.add_image, args=(self.image, self.item)).start()

    def _on_click(self, *args) -> None:
        if self.action is None:
            return

        self.activate_action(self.action, GLib.Variant("s", str(self.item.id)))


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/shortcuts_widget.ui"
)
class HTShorcutsWidget(Gtk.Box, IDisconnectable):
    """A widget to display all shortcuts on the home page"""

    __gtype_name__ = "HTShorcutsWidget"

    shorcuts_flow_box = Gtk.Template.Child()

    def __init__(
        self, items: List[Union[Mix, MixV2, Album, Artist, Playlist]] | None = None
    ) -> None:
        IDisconnectable.__init__(self)
        super().__init__()

        self.set_items(items)

    def set_items(
        self, items_list: List[Union[Mix, MixV2, Album, Artist, Playlist]] | None
    ) -> None:
        if items_list is None:
            return
        for item in items_list:
            self.shorcuts_flow_box.append(HTShorcutWidget(item))
