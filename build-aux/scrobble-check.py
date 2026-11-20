# Checks that High Tide's scrobbles reach Last.fm and ListenBrainz: stand-ins for
# both services get "now playing" and the scrobble of a made-up song, played through
# the app's own scrobbling code on a stand-in player. The app only logs scrobbling
# errors, so without this a broken scrobble goes unnoticed.
# Used by the Flatpak workflow, inside the sandbox:
#   python3 scrobble-check.py [package dir]   (default /app/share/high-tide)

import hashlib
import importlib
import json
import logging
import os
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlparse

import gi

gi.require_version("Secret", "1")
from gi.repository import GObject  # noqa: E402

package_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/share/high-tide"
os.environ["NO_PROXY"] = "127.0.0.1"

LASTFM_SESSION = "check-session-key"
LISTENBRAINZ_TOKEN = "check-token"

requests_seen = []
problems = []
lock = threading.Lock()


class FakeServices(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        path = urlparse(self.path).path
        if path.startswith("/lastfm"):
            self.lastfm(dict(parse_qsl(body)))
        elif path.startswith("/listenbrainz"):
            self.listenbrainz(path, json.loads(body or "null"))
        else:
            self.reply(404, {})

    def lastfm(self, params):
        # Last.fm's signing: every parameter but format and api_sig, sorted, then
        # the secret
        signed = "".join(
            f"{key}{params[key]}"
            for key in sorted(params)
            if key not in ("format", "api_sig")
        )
        expected = hashlib.md5(
            (signed + lastfm.API_SECRET).encode(), usedforsecurity=False
        ).hexdigest()
        method = params.get("method")
        with lock:
            requests_seen.append(("Last.fm", method, params))
        if params.get("api_sig") != expected or params.get("sk") != LASTFM_SESSION:
            self.reply(403, {"error": 13, "message": "Invalid method signature"})
        elif method == "track.updateNowPlaying":
            self.reply(200, {"nowplaying": {}})
        elif method == "track.scrobble":
            self.reply(200, {"scrobbles": {"@attr": {"accepted": 1, "ignored": 0}}})
        else:
            self.reply(400, {"error": 3, "message": "Invalid method"})

    def listenbrainz(self, path, body):
        kind = body.get("listen_type") if isinstance(body, dict) else None
        with lock:
            requests_seen.append(("ListenBrainz", kind, body))
        if self.headers.get("Authorization") != f"Token {LISTENBRAINZ_TOKEN}":
            self.reply(401, {"code": 401, "error": "Invalid authorization token."})
        elif path.endswith("/submit-listens") and kind in ("playing_now", "single"):
            self.reply(200, {"status": "ok"})
        else:
            self.reply(400, {"code": 400, "error": "Invalid JSON document submitted."})


server = ThreadingHTTPServer(("127.0.0.1", 0), FakeServices)
threading.Thread(target=server.serve_forever, daemon=True).start()
base_url = f"http://127.0.0.1:{server.server_address[1]}"


class ProblemHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            problems.append(record.getMessage())


logging.basicConfig(level=logging.INFO)
logging.getLogger("lib").addHandler(ProblemHandler())

# Only the scrobbling modules, not the whole app (lib/__init__.py loads it all)
lib = types.ModuleType("lib")
lib.__path__ = [os.path.join(package_dir, "high_tide", "lib")]
sys.modules["lib"] = lib
scrobbling = importlib.import_module("lib.scrobbling")
lastfm = importlib.import_module("lib.lastfm")
listenbrainz = importlib.import_module("lib.listenbrainz")

lastfm.LastFmClient.API_URL = f"{base_url}/lastfm/2.0/"
listenbrainz.API_URL = f"{base_url}/listenbrainz/1"

# Listening time is counted with time.monotonic(); this clock is moved by hand
clock = [1000.0]
scrobbling.time = SimpleNamespace(time=time.time, monotonic=lambda: clock[0])


class FakePlayer(GObject.Object):
    __gsignals__ = {
        "update-slider": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "song-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }
    playing = GObject.Property(type=bool, default=False)

    def __init__(self):
        super().__init__()
        self.playing_track = None
        self.position = 0.0

    def query_position(self, default=0):
        return int(self.position * 1_000_000_000)


track = SimpleNamespace(
    id=1,
    name="Check Song",
    artist=SimpleNamespace(name="Check Artist"),
    artists=[SimpleNamespace(name="Check Artist")],
    album=SimpleNamespace(name="Check Album"),
    duration=40,
    track_num=1,
    isrc="",
    share_url="",
)

queue_dir = Path(tempfile.mkdtemp())
player = FakePlayer()
lastfm_client = lastfm.LastFmClient(
    SimpleNamespace(data={"session-key": LASTFM_SESSION, "username": "check"})
)
listenbrainz_client = listenbrainz.ListenBrainzClient(
    SimpleNamespace(data={"token": LISTENBRAINZ_TOKEN, "username": "check"}),
    "check",
)
scrobblers = [
    lastfm.LastFmScrobbler(
        player, lastfm_client, lastfm.LastFmQueue(lastfm_client, queue_dir / "lfm")
    ),
    listenbrainz.ListenBrainzScrobbler(
        player,
        listenbrainz_client,
        listenbrainz.ListenBrainzQueue(listenbrainz_client, queue_dir / "lb"),
    ),
]

# Play the 40 s song for 24 s (more than half of it), a tick every 2 s
player.playing_track = track
player.playing = True
player.emit("song-changed")
for _ in range(12):
    clock[0] += 2
    player.position += 2
    player.emit("update-slider")

wanted = {
    ("Last.fm", "track.updateNowPlaying"),
    ("Last.fm", "track.scrobble"),
    ("ListenBrainz", "playing_now"),
    ("ListenBrainz", "single"),
}
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    with lock:
        seen = {(service, kind) for service, kind, _ in requests_seen}
    if wanted <= seen:
        break
    time.sleep(0.2)
time.sleep(1)  # let the replies be handled, so their errors are logged

with lock:
    seen = [(service, kind) for service, kind, _ in requests_seen]
missing = sorted(wanted - set(seen))
for service, kind, payload in requests_seen:
    names = json.dumps(payload) if service == "ListenBrainz" else payload
    if "Check Song" not in str(names) or "Check Artist" not in str(names):
        problems.append(f"{service} {kind} lacks the song or artist: {names}")

ok = not missing and not problems
print(
    f"Scrobble check {'passed' if ok else 'failed'}: requests: {seen}, "
    f"missing: {missing or 'none'}, problems: {problems or 'none'}",
    flush=True,
)
os._exit(0 if ok else 1)
