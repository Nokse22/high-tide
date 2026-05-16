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

import logging
import threading
from gettext import gettext as _
from typing import Any

import tidalapi
from gi.repository import Adw, GLib, Gtk

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/login.ui")
class LoginDialog(Adw.Dialog):
    __gtype_name__ = "LoginDialog"

    link_button = Gtk.Template.Child()
    redirect_url_entry = Gtk.Template.Child()
    login_button = Gtk.Template.Child()
    error_label = Gtk.Template.Child()

    def __init__(self, win: Any, session: tidalapi.Session) -> None:
        super().__init__()

        self.session = session
        self.win = win

        login_url: str = self.session.pkce_login_url()
        self.link_button.set_uri(login_url)

    @Gtk.Template.Callback("on_redirect_url_changed")
    def on_redirect_url_changed(self, entry: Adw.EntryRow) -> None:
        self.login_button.set_sensitive(bool(entry.get_text().strip()))
        self.error_label.set_visible(False)

    @Gtk.Template.Callback("on_login_button_clicked")
    def on_login_button_clicked(self, *_args) -> None:
        redirect_url: str = self.redirect_url_entry.get_text().strip()
        if not redirect_url:
            return

        self.login_button.set_sensitive(False)
        self.redirect_url_entry.set_sensitive(False)
        self.error_label.set_visible(False)

        threading.Thread(
            target=self._exchange_token, args=(redirect_url,), daemon=True
        ).start()

    def _exchange_token(self, redirect_url: str) -> None:
        try:
            token_json = self.session.pkce_get_auth_token(redirect_url)
            self.session.process_auth_token(token_json, is_pkce_token=True)
        except Exception as exc:
            logger.exception("PKCE token exchange failed")
            GLib.idle_add(self._on_failure, str(exc))
            return

        if self.session.check_login():
            GLib.idle_add(self._on_success)
        else:
            GLib.idle_add(self._on_failure, _("Login was rejected by Tidal."))

    def _on_success(self) -> None:
        self.win.secret_store.save(is_pkce=True)
        self.win.on_logged_in()
        self.close()

    def _on_failure(self, message: str) -> None:
        self.error_label.set_label(_("Login failed: {error}").format(error=message))
        self.error_label.set_visible(True)
        self.redirect_url_entry.set_sensitive(True)
        self.login_button.set_sensitive(True)
