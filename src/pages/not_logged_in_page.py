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

from .page import Page
from gettext import gettext as _


class HTNotLoggedInPage(Page):
    __gtype_name__ = "HTNotLoggedInPage"

    def _load_async(self):
        pass

    def _load_finish(self):
        self.set_title("Not Logged In")

        login_button = Gtk.Button(
            label=_("Login"),
            css_classes=["pill", "suggested-action"],
            action_name="app.log-in",
            halign=Gtk.Align.CENTER,
        )
        self.append(Adw.StatusPage(
            title=_("Login first"),
            description=_(
                "To be able to use this app you need to login with your TIDAL account."
            ),
            icon_name="key-login-symbolic",
            child=login_button,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        ))
