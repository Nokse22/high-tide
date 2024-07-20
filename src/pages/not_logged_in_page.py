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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gdk

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.user import Favorites

from ..lib import utils

import threading
import requests
import random

from .page import Page

from ..lib import variables

class notLoggedInPage(Page):
    __gtype_name__ = 'notLoggedInPage'

    def _th_load_page(self):
        self.set_title("Not Logged In")

        descr = '''To be able to use this app you need to login with your TIDAL account.'''

        login_button = Gtk.Button(
            label="Login",
            css_classes=["pill", "suggested-action"],
            action_name="app.log-in",
            halign=Gtk.Align.CENTER
        )
        status_page = Adw.StatusPage(
            title="Login first",
            description=descr,
            icon_name="face-wink-symbolic",
            child=login_button,
            valign=Gtk.Align.CENTER,
            vexpand=True
        )

        self.page_content.append(status_page)
        self._page_loaded()
