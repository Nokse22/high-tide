# dlna.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Playing on DLNA (UPnP AV) speakers, TVs and streamers on the local network.

The speaker can't play TIDAL's streams itself, so each track is turned into a
FLAC file, served from a small web server here, and the speaker is told to play
that file's address.
"""

import html
import logging
import os
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

SSDP_ADDRESS = ("239.255.255.250", 1900)
RENDERER_TYPE = "urn:schemas-upnp-org:device:MediaRenderer:1"
AV_TRANSPORT = "urn:schemas-upnp-org:service:AVTransport"
RENDERING_CONTROL = "urn:schemas-upnp-org:service:RenderingControl"
DEVICE_NS = "{urn:schemas-upnp-org:device-1-0}"
TIMEOUT = 5


class DlnaError(Exception):
    pass


@dataclass
class Renderer:
    """A device that can play audio from an address it's given"""

    udn: str
    name: str
    location: str
    av_transport_url: str
    rendering_control_url: str | None

    @property
    def host(self) -> str:
        return urllib.parse.urlparse(self.location).hostname or ""

    def _call(self, url: str, service: str, action: str, args: dict) -> dict:
        arguments = "".join(
            f"<{name}>{html.escape(str(value), quote=False)}</{name}>"
            for name, value in args.items()
        )
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{service}">{arguments}</u:{action}>'
            "</s:Body></s:Envelope>"
        ).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPACTION": f'"{service}#{action}"',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                reply = response.read()
        except urllib.error.HTTPError as e:
            reply = e.read()
            code = re.search(rb"<errorCode>(\d+)</errorCode>", reply)
            text = re.search(rb"<errorDescription>([^<]*)<", reply)
            raise DlnaError(
                f"{action} failed: {code.group(1).decode() if code else e.code} "
                f"{text.group(1).decode() if text else ''}".strip()
            ) from e
        except OSError as e:
            raise DlnaError(f"{action} failed: {e}") from e
        result = {}
        for element in ET.fromstring(reply).iter():
            if element.tag.endswith(f"{action}Response"):
                for child in element:
                    result[child.tag.split("}")[-1]] = child.text or ""
        return result

    def _transport(self, action: str, **args) -> dict:
        service = f"{AV_TRANSPORT}:1"
        return self._call(
            self.av_transport_url, service, action, {"InstanceID": 0, **args}
        )

    def set_uri(self, url: str, metadata: str) -> None:
        self._transport("SetAVTransportURI", CurrentURI=url, CurrentURIMetaData=metadata)

    def load(self, url: str, mime: str, track) -> None:
        """Load a track, play() starts it"""
        self.set_uri(url, track_metadata(track, url, mime))

    def play(self) -> None:
        self._transport("Play", Speed=1)

    def pause(self) -> None:
        self._transport("Pause")

    def stop(self) -> None:
        self._transport("Stop")

    def seek(self, seconds: float) -> None:
        self._transport("Seek", Unit="REL_TIME", Target=format_time(seconds))

    def get_state(self) -> str:
        """PLAYING, PAUSED_PLAYBACK, STOPPED, TRANSITIONING or NO_MEDIA_PRESENT"""
        return self._transport("GetTransportInfo").get("CurrentTransportState", "")

    def seek_when_playing(self, seconds: float, timeout: float = 10) -> None:
        """Seek once playback has started, devices ignore a seek before that.

        Some say they're playing before the track has started, so wait until they
        know its duration, and seek again if the position didn't move.
        """
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.get_state() == "PLAYING" and self.get_position()[1] > 0:
                break
            time.sleep(0.25)
        for _attempt in range(3):
            self.seek(seconds)
            time.sleep(1)
            if self.get_position()[0] >= seconds - 1:
                return
        logger.warning(f"The DLNA device didn't seek to {seconds:.0f} s")

    def get_position(self) -> tuple[float, float]:
        """Position and duration of the current track in seconds"""
        info = self._transport("GetPositionInfo")
        return parse_time(info.get("RelTime")), parse_time(info.get("TrackDuration"))

    def get_volume(self) -> int | None:
        """The device's volume from 0 to 100, None if it has none"""
        if not self.rendering_control_url:
            return None
        reply = self._call(
            self.rendering_control_url,
            f"{RENDERING_CONTROL}:1",
            "GetVolume",
            {"InstanceID": 0, "Channel": "Master"},
        )
        try:
            return int(reply.get("CurrentVolume", ""))
        except ValueError:
            return None

    def set_volume(self, volume: int) -> None:
        if not self.rendering_control_url:
            return
        self._call(
            self.rendering_control_url,
            f"{RENDERING_CONTROL}:1",
            "SetVolume",
            {"InstanceID": 0, "Channel": "Master", "DesiredVolume": volume},
        )

    @classmethod
    def from_location(cls, location: str) -> "Renderer | None":
        """Read a device's description, None if it can't play media"""
        with urllib.request.urlopen(location, timeout=TIMEOUT) as response:
            root = ET.fromstring(response.read())
        base = root.findtext(f"{DEVICE_NS}URLBase") or location
        for device in root.iter(f"{DEVICE_NS}device"):
            if not (device.findtext(f"{DEVICE_NS}deviceType") or "").startswith(
                RENDERER_TYPE[:-1]
            ):
                continue
            urls = {}
            for service in device.iter(f"{DEVICE_NS}service"):
                service_type = service.findtext(f"{DEVICE_NS}serviceType") or ""
                control = service.findtext(f"{DEVICE_NS}controlURL") or ""
                for name in (AV_TRANSPORT, RENDERING_CONTROL):
                    if service_type.startswith(name) and name not in urls:
                        urls[name] = urllib.parse.urljoin(base, control)
            if AV_TRANSPORT not in urls:
                continue
            return cls(
                udn=device.findtext(f"{DEVICE_NS}UDN") or location,
                name=device.findtext(f"{DEVICE_NS}friendlyName") or location,
                location=location,
                av_transport_url=urls[AV_TRANSPORT],
                rendering_control_url=urls.get(RENDERING_CONTROL),
            )
        return None


def discover(timeout: float = 3.0) -> list[Renderer]:
    """Find the devices on the local network that can play media"""
    search = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDRESS[0]}:{SSDP_ADDRESS[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        f"ST: {RENDERER_TYPE}\r\n\r\n"
    ).encode()
    locations = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(0.5)
        end = time.monotonic() + timeout
        next_search = 0.0
        while time.monotonic() < end:
            if time.monotonic() >= next_search:
                # Sent a few times, as UDP can get lost
                try:
                    sock.sendto(search, SSDP_ADDRESS)
                except OSError as e:
                    logger.warning(f"Couldn't search for DLNA devices: {e}")
                    return []
                next_search = time.monotonic() + 1
            try:
                data, _address = sock.recvfrom(8192)
            except socket.timeout:
                continue
            match = re.search(rb"(?im)^location:\s*(\S+)", data)
            if match:
                locations.add(match.group(1).decode(errors="replace"))

    def describe(location):
        try:
            return Renderer.from_location(location)
        except Exception as e:
            logger.info(f"Couldn't read the DLNA device at {location}: {e}")
            return None

    renderers = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for renderer in pool.map(describe, sorted(locations)):
            if renderer:
                renderers.setdefault(renderer.udn, renderer)
    return sorted(renderers.values(), key=lambda r: r.name.lower())


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def parse_time(text: str | None) -> float:
    if not text or text == "NOT_IMPLEMENTED":
        return 0.0
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return 0.0
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def local_address_for(host: str) -> str:
    """The address of this computer that the device at host can reach"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, 1900))
        return sock.getsockname()[0]


def track_metadata(track, url: str, mime: str) -> str:
    """DIDL-Lite description of a track, shown by devices with a screen"""
    from .utils import get_image_url

    def text(value):
        return html.escape(value or "", quote=False)

    artist = track.artist.name if getattr(track, "artist", None) else ""
    album = track.album.name if getattr(track, "album", None) else ""
    cover = ""
    try:
        cover_url = get_image_url(track.album, 640) if track.album else None
        if cover_url:
            cover = f"<upnp:albumArtURI>{text(cover_url)}</upnp:albumArtURI>"
    except Exception:
        pass
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        f'<item id="{track.id}" parentID="0" restricted="1">'
        f"<dc:title>{text(track.name)}</dc:title>"
        f"<dc:creator>{text(artist)}</dc:creator>"
        f"<upnp:artist>{text(artist)}</upnp:artist>"
        f"<upnp:album>{text(album)}</upnp:album>{cover}"
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        f'<res protocolInfo="http-get:*:{mime}:*" '
        f'duration="{format_time(track.duration or 0)}.000">{text(url)}</res>'
        "</item></DIDL-Lite>"
    )


class MediaServer:
    """Serves the prepared files to the devices on the local network"""

    def __init__(self) -> None:
        self._files: dict[str, tuple[Path, str]] = {}
        self._lock = threading.Lock()
        files = self._files
        lock = self._lock

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                logger.debug("DLNA server: " + format % args)

            def do_HEAD(self):
                self._send(head=True)

            def do_GET(self):
                self._send(head=False)

            def _send(self, head):
                key = self.path.lstrip("/").split("/")[0].split(".")[0]
                with lock:
                    entry = files.get(key)
                if not entry or not entry[0].exists():
                    self.send_error(404)
                    return
                path, mime = entry
                size = path.stat().st_size
                start, end = 0, size - 1
                match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
                if match and (match.group(1) or match.group(2)):
                    if match.group(1):
                        start = int(match.group(1))
                        if match.group(2):
                            end = min(int(match.group(2)), size - 1)
                    else:
                        start = max(0, size - int(match.group(2)))
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                else:
                    self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("transferMode.dlna.org", "Streaming")
                self.send_header(
                    "contentFeatures.dlna.org",
                    "DLNA.ORG_OP=01;DLNA.ORG_CI=0;"
                    "DLNA.ORG_FLAGS=01700000000000000000000000000000",
                )
                self.end_headers()
                if head:
                    return
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    try:
                        while left > 0:
                            chunk = f.read(min(65536, left))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            left -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                # Devices drop connections all the time, e.g. when seeking
                logger.debug(f"DLNA server: connection from {client_address} ended")

        self._server = Server(("0.0.0.0", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        logger.info(f"DLNA media server on port {self.port}")

    def add(self, path: Path, mime: str, host: str, extension: str) -> str:
        """Serve a file, returns its address as seen from host"""
        key = secrets.token_hex(8)
        with self._lock:
            self._files[key] = (path, mime)
        return f"http://{local_address_for(host)}:{self.port}/{key}.{extension}"

    def remove_all_but(self, paths: list[Path]) -> None:
        """Stop serving the other files and delete them"""
        with self._lock:
            for key, (path, _mime) in list(self._files.items()):
                if path not in paths:
                    del self._files[key]
                    try:
                        os.unlink(path)
                    except OSError:
                        pass


def prepare_flac(source_uri: str, destination: Path) -> None:
    """Decode a track (a DASH manifest, stream address or file) into a FLAC file.

    FLAC is lossless and what nearly every DLNA device plays, whatever TIDAL sent.
    """
    from gi.repository import Gst

    tmp = destination.with_suffix(".tmp")
    pipeline = Gst.Pipeline.new("dlna-prepare")
    decode = Gst.ElementFactory.make("uridecodebin", None)
    convert = Gst.ElementFactory.make("audioconvert", None)
    encode = Gst.ElementFactory.make("flacenc", None)
    sink = Gst.ElementFactory.make("filesink", None)
    decode.set_property("uri", source_uri)
    sink.set_property("location", str(tmp))
    for element in (decode, convert, encode, sink):
        pipeline.add(element)
    convert.link(encode)
    encode.link(sink)

    def on_pad_added(_decode, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        sink_pad = convert.get_static_pad("sink")
        if caps.to_string().startswith("audio/") and not sink_pad.is_linked():
            pad.link(sink_pad)

    decode.connect("pad-added", on_pad_added)
    pipeline.set_state(Gst.State.PLAYING)
    bus = pipeline.get_bus()
    try:
        message = bus.timed_pop_filtered(
            10 * 60 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR
        )
    finally:
        pipeline.set_state(Gst.State.NULL)
    if not message or message.type == Gst.MessageType.ERROR:
        tmp.unlink(missing_ok=True)
        error = message.parse_error()[0].message if message else "timed out"
        raise DlnaError(f"Couldn't prepare the track: {error}")
    tmp.rename(destination)
