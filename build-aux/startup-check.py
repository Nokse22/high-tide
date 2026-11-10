# Starts High Tide and checks that its main window is up after a few seconds,
# without uncaught exceptions. Used by the Flatpak workflow, inside the sandbox:
#   python3 startup-check.py [script [args...]]   (default /app/bin/high-tide)

import os
import runpy
import sys

from gi.repository import Gio, GLib

script = sys.argv[1] if len(sys.argv) > 1 else "/app/bin/high-tide"
sys.argv = [script] + sys.argv[2:]
errors = []
default_excepthook = sys.excepthook


def excepthook(exc_type, value, tb):
    errors.append(exc_type.__name__)
    default_excepthook(exc_type, value, tb)


def check():
    app = Gio.Application.get_default()
    window = app.props.active_window if app else None
    name = type(window).__name__ if window else None
    ok = name == "HighTideWindow" and not errors
    print(
        f"Startup check {'passed' if ok else 'failed'}: window {name}, "
        f"uncaught exceptions: {', '.join(errors) or 'none'}",
        flush=True,
    )
    os._exit(0 if ok else 1)


sys.excepthook = excepthook
GLib.timeout_add_seconds(15, check)
runpy.run_path(script, run_name="__main__")
print("Startup check failed: High Tide quit before the check", flush=True)
sys.exit(1)
