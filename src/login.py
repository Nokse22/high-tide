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
import io
import threading
from gettext import gettext as _
from typing import Any

import tidalapi

from .lib import utils
from gi.repository import Adw, Gdk, GLib, Gtk

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/login.ui")
class LoginDialog(Adw.Dialog):
    """Log in with a QR code (TIDAL's device login: approve on the phone or any
    browser signed in to TIDAL), or with the browser login (paste the address its
    "Page not found" page ends on)."""

    __gtype_name__ = "LoginDialog"

    navigation_view = Gtk.Template.Child()
    qr_stack = Gtk.Template.Child()
    qr_picture = Gtk.Template.Child()
    link_button = Gtk.Template.Child()
    code_label = Gtk.Template.Child()
    waiting_box = Gtk.Template.Child()
    qr_error_label = Gtk.Template.Child()
    browser_link_button = Gtk.Template.Child()
    redirect_url_entry = Gtk.Template.Child()
    login_button = Gtk.Template.Child()
    error_label = Gtk.Template.Child()

    def __init__(self, win: Any, session: tidalapi.Session) -> None:
        super().__init__()

        self.session = session
        self.win = win
        self.done = False

        self.browser_link_button.set_uri(self.session.pkce_login_url())
        self.connect("closed", self._on_closed)

        self._start_qr_login()

    def _on_closed(self, *_args) -> None:
        self.done = True

    # QR code login

    def _start_qr_login(self) -> None:
        self.qr_stack.set_visible_child_name("loading")
        threading.Thread(target=self._th_qr_login, daemon=True).start()

    def _th_qr_login(self) -> None:
        try:
            link_login, future = self.session.login_oauth()
        except Exception as exc:
            logger.exception("Could not start the QR code login")
            GLib.idle_add(self._on_qr_failure, str(exc))
            return
        GLib.idle_add(self._show_qr_code, link_login)
        try:
            # Polls TIDAL until the link is approved, or it expires
            future.result()
        except Exception:
            if not self.done:
                logger.info("The QR code login link expired, making a new one")
                GLib.idle_add(self._start_qr_login)
            return
        if self.done:
            return
        if self.session.check_login():
            GLib.idle_add(self._on_success, False)
        else:
            GLib.idle_add(self._on_qr_failure, _("Login was rejected by TIDAL."))

    def _show_qr_code(self, link_login) -> None:
        if self.done:
            return
        url = link_login.verification_uri_complete
        if not url.startswith("http"):
            url = "https://" + url
        self.link_button.set_uri(url)
        self.link_button.set_label(url.removeprefix("https://"))
        self.link_button.set_visible(True)
        self.code_label.set_label(link_login.user_code)
        self.code_label.set_visible(True)
        self.waiting_box.set_visible(True)
        self.qr_error_label.set_visible(False)

        texture = self._qr_texture(url)
        if texture is not None:
            self.qr_picture.set_paintable(texture)
            self.qr_stack.set_visible_child_name("code")
        else:
            self.qr_stack.set_visible(False)

    @staticmethod
    def _qr_texture(url: str) -> Gdk.Texture | None:
        try:
            import segno
        except ImportError:
            logger.warning("segno is missing: the login shows the link without a QR code")
            return None
        buffer = io.BytesIO()
        segno.make(url, error="m").save(
            buffer, kind="png", scale=8, border=2, dark="#000000", light="#ffffff"
        )
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(buffer.getvalue()))

    def _on_qr_failure(self, message: str) -> None:
        self.qr_stack.set_visible(False)
        self.waiting_box.set_visible(False)
        self.qr_error_label.set_label(_("Login failed: {error}").format(error=message))
        self.qr_error_label.set_visible(True)

    # Browser login

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
            GLib.idle_add(self._on_success, True)
        else:
            GLib.idle_add(self._on_failure, _("Login was rejected by TIDAL."))

    def _on_success(self, is_pkce: bool) -> None:
        if self.done:
            return
        self.done = True
        utils.device_login = not is_pkce
        try:
            self.win.secret_store.save(is_pkce=is_pkce)
            saved = True
        except Exception:
            # No usable keyring, e.g. no default collection outside a full
            # desktop (#228): the login still works until the app is closed
            logger.exception("Could not save the login to the keyring")
            saved = False
        self.win.on_logged_in()
        self.close()
        if not saved:
            utils.send_toast(
                _("Couldn't save your login to the keyring, so you'll need to log in again next time"),
                10,
            )

    def _on_failure(self, message: str) -> None:
        self.error_label.set_label(_("Login failed: {error}").format(error=message))
        self.error_label.set_visible(True)
        self.redirect_url_entry.set_sensitive(True)
        self.login_button.set_sensitive(True)
