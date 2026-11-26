# Checks that High Tide's Discord status reaches Discord: a stand-in for Discord's
# Rich Presence socket gets the status of a made-up song from the app's own Discord
# code, with the pypresence the bundle ships. Discord errors are only logged by the
# app, so without this a pypresence that doesn't fit the app's code goes unnoticed.
# Used by the Flatpak workflow, inside the sandbox:
#   python3 discord-check.py [package dir]   (default /app/share/high-tide)

import importlib.util
import json
import logging
import os
import socket
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace

package_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/share/high-tide"

# Our own socket folder, so a real Discord is never reached
runtime_dir = tempfile.mkdtemp()
os.environ["XDG_RUNTIME_DIR"] = runtime_dir

activities = []
got_activity = threading.Event()


def recv_frame(conn):
    head = b""
    while len(head) < 8:
        chunk = conn.recv(8 - len(head))
        if not chunk:
            return None, None
        head += chunk
    op, length = struct.unpack("<II", head)
    body = b""
    while len(body) < length:
        body += conn.recv(length - len(body))
    return op, json.loads(body)


def send_frame(conn, op, payload):
    data = json.dumps(payload).encode()
    conn.sendall(struct.pack("<II", op, len(data)) + data)


def serve(conn):
    with conn:
        op, _ = recv_frame(conn)  # handshake
        if op is None:
            return
        send_frame(conn, 1, {"cmd": "DISPATCH", "evt": "READY", "data": {"v": 1}})
        while True:
            op, message = recv_frame(conn)
            if op is None:
                return
            if message.get("cmd") == "SET_ACTIVITY":
                activities.append((message.get("args") or {}).get("activity"))
                got_activity.set()
            send_frame(
                conn,
                1,
                {
                    "cmd": message.get("cmd"),
                    "evt": None,
                    "nonce": message.get("nonce"),
                    "data": {},
                },
            )


def accept_loop(server):
    while True:
        conn, _ = server.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(os.path.join(runtime_dir, "discord-ipc-0"))
server.listen(4)
threading.Thread(target=accept_loop, args=(server,), daemon=True).start()

errors = []


class ErrorHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            errors.append(record.getMessage())


logging.basicConfig(level=logging.INFO)
logging.getLogger("discord_rpc").addHandler(ErrorHandler())

# Only the Discord module, not the whole app
path = os.path.join(package_dir, "high_tide", "lib", "discord_rpc.py")
spec = importlib.util.spec_from_file_location("discord_rpc", path)
discord_rpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discord_rpc)

track = SimpleNamespace(
    name="Check Song",
    artists=[SimpleNamespace(name="Check Artist")],
    album=SimpleNamespace(
        name="Check Album", image=lambda *args: "https://example.com/cover.jpg"
    ),
    duration=200,
)
discord_rpc.set_activity(track, 0)
got_activity.wait(15)

activity = activities[0] if activities else None
ok = (
    bool(activity)
    and activity.get("details") == track.name
    and activity.get("assets", {}).get("large_text") == track.album.name
    and not errors
)
print(
    f"Discord check {'passed' if ok else 'failed'}: status sent: "
    f"{json.dumps(activity)}, errors: {errors or 'none'}",
    flush=True,
)
os._exit(0 if ok else 1)
