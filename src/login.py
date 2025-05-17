# login.py
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
from gi.repository import Gdk

import tidalapi

from .lib import utils

@Gtk.Template(resource_path='/io/github/nokse22/HighTide/ui/login.ui')
class LoginDialog(Adw.Dialog):
    __gtype_name__ = 'LoginDialog'

    link_button = Gtk.Template.Child()
    code_label = Gtk.Template.Child()

    def __init__(self, _win, _session):
        super().__init__()

        self.session = _session
        self.win = _win

        self.code = ""

        login, future = self.session.login_oauth()

        uri = login.verification_uri_complete

        link = f"https://{uri}"

        self.code = uri[-5:]

        self.code_label.set_label(self.code)
        self.link_button.set_label(link)
        self.link_button.set_uri(link)

        GLib.timeout_add(600, self.check_login)

    def check_login(self):
        if self.session.check_login():
            self.win.secret_store.save()
            self.win.on_logged_in()
            self.close()
            return False
        return True

    @Gtk.Template.Callback("on_copy_code_button_clicked")
    def foo(self, btn):
        clipboard = Gdk.Display().get_default().get_clipboard()
        clipboard.set(self.code)
