from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
# from gi.repository import GObject

import tidalapi

@Gtk.Template(resource_path='/io/github/nokse22/high-tide/login.ui')
class LoginWindow(Adw.Window):
    __gtype_name__ = 'LoginWindow'

    link_button = Gtk.Template.Child()
    code_label = Gtk.Template.Child()

    def __init__(self, _win, _session):
        super().__init__()

        self.session = _session
        self.win = _win

        login, future = self.session.login_oauth()

        link = f"https://{login.verification_uri_complete}"
        # code =

        self.code_label.set_label("ABCDEF")
        self.link_button.set_label(link)
        self.link_button.set_uri(link)

        GLib.timeout_add(600, self.check_login)

    def check_login(self):
        if self.session.check_login():
            self.destroy()
            self.win.load_home_page()
            self.win.save_token()
            return False
        return True

    @Gtk.Template.Callback("on_copy_code_button_clicked")
    def foo(self, btn):
        pass
