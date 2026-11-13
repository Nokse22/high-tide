# cast.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Playing on Google Cast devices (Chromecast, Google TV, speakers with Chromecast
built-in) on the local network.

The device runs Google's Default Media Receiver and plays the FLAC file prepared
for it, from the same web server the DLNA devices use (see dlna.py).
"""

import json
import logging
import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MDNS_ADDRESS = ("224.0.0.251", 5353)
SERVICE = "_googlecast._tcp.local"
DEFAULT_MEDIA_RECEIVER = "CC1AD845"
NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection"
NS_HEARTBEAT = "urn:x-cast:com.google.cast.tp.heartbeat"
NS_RECEIVER = "urn:x-cast:com.google.cast.receiver"
NS_MEDIA = "urn:x-cast:com.google.cast.media"
SENDER = "sender-0"
TIMEOUT = 10


class CastError(Exception):
    pass


class TakenOver(CastError):
    """Another app is using the device now"""


# CastMessage protobuf, written and read by hand: 1 protocol_version, 2 source_id,
# 3 destination_id, 4 namespace, 5 payload_type (0 = string), 6 payload_utf8


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _encode(source: str, destination: str, namespace: str, payload: dict) -> bytes:
    def text(number, value):
        data = value.encode()
        return _varint(number << 3 | 2) + _varint(len(data)) + data

    message = (
        _varint(1 << 3) + _varint(0)
        + text(2, source)
        + text(3, destination)
        + text(4, namespace)
        + _varint(5 << 3) + _varint(0)
        + text(6, json.dumps(payload))
    )
    return struct.pack(">I", len(message)) + message


def _decode(data: bytes) -> dict:
    fields = {}
    i = 0
    while i < len(data):
        key = shift = 0
        while True:
            byte = data[i]
            i += 1
            key |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        number, wire = key >> 3, key & 7
        value = shift = 0
        if wire == 0:
            while True:
                byte = data[i]
                i += 1
                value |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            fields[number] = value
        elif wire == 2:
            length = shift = 0
            while True:
                byte = data[i]
                i += 1
                length |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            fields[number] = data[i : i + length]
            i += length
        else:
            raise CastError(f"Unexpected protobuf wire type {wire}")
    return {
        "source": fields.get(2, b"").decode(errors="replace"),
        "namespace": fields.get(4, b"").decode(errors="replace"),
        "payload": json.loads(fields.get(6, b"{}") or b"{}"),
    }


class _Connection:
    """One TLS connection to a device, with replies matched to requests"""

    def __init__(self, host: str, port: int) -> None:
        context = ssl.create_default_context()
        # Cast devices use self-signed certificates
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((host, port), timeout=TIMEOUT)
        self.sock = context.wrap_socket(raw)
        self.sock.settimeout(None)
        self.lock = threading.Lock()
        self.request_id = 0
        self.waiting: dict[int, list] = {}
        # The newest media session's status, and why the last one ended
        self.media_status: dict | None = None
        self.media_session_id = 0
        self.idle_reason: str | None = None
        self.receiver_status: dict | None = None
        self.closed = False
        self.connected_to: set[str] = set()
        self.send(NS_CONNECTION, "receiver-0", {"type": "CONNECT"})
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def send(self, namespace: str, destination: str, payload: dict) -> None:
        data = _encode(SENDER, destination, namespace, payload)
        with self.lock:
            self.sock.sendall(data)

    def request(self, namespace: str, destination: str, payload: dict) -> dict:
        with self.lock:
            self.request_id += 1
            request_id = self.request_id
        event = threading.Event()
        self.waiting[request_id] = [event, None]
        self.send(namespace, destination, {**payload, "requestId": request_id})
        if not event.wait(TIMEOUT):
            self.waiting.pop(request_id, None)
            raise CastError(f"{payload.get('type')} got no answer")
        reply = self.waiting.pop(request_id)[1]
        if reply.get("type") in ("LOAD_FAILED", "LOAD_CANCELLED", "INVALID_REQUEST"):
            raise CastError(f"{payload.get('type')} failed: {reply}")
        return reply

    def connect(self, destination: str) -> None:
        if destination not in self.connected_to:
            self.send(NS_CONNECTION, destination, {"type": "CONNECT"})
            self.connected_to.add(destination)

    def _receive_exactly(self, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("closed by the device")
            data += chunk
        return data

    def _read(self) -> None:
        try:
            while not self.closed:
                size = struct.unpack(">I", self._receive_exactly(4))[0]
                message = _decode(self._receive_exactly(size))
                payload = message["payload"]
                kind = payload.get("type")
                if message["namespace"] == NS_HEARTBEAT and kind == "PING":
                    self.send(NS_HEARTBEAT, message["source"], {"type": "PONG"})
                    continue
                if kind == "RECEIVER_STATUS":
                    self.receiver_status = payload.get("status")
                elif kind == "MEDIA_STATUS" and payload.get("status"):
                    status = payload["status"][0]
                    session_id = status.get("mediaSessionId", 0)
                    # A late status of an earlier session doesn't replace the newer one
                    if session_id >= self.media_session_id:
                        if session_id > self.media_session_id or status.get("idleReason"):
                            # Why the newest session ended, None while it plays
                            self.idle_reason = status.get("idleReason")
                        if (
                            session_id == self.media_session_id
                            and self.media_status
                            and "media" not in status
                        ):
                            # Updates leave out what didn't change
                            status = {**self.media_status, **status}
                        self.media_session_id = session_id
                        self.media_status = status
                elif kind == "MEDIA_STATUS":
                    self.media_status = None
                elif kind == "CLOSE":
                    self.connected_to.discard(message["source"])
                waiting = self.waiting.get(payload.get("requestId"))
                if waiting:
                    waiting[1] = payload
                    waiting[0].set()
        except Exception as e:
            if not self.closed:
                logger.info(f"Cast connection ended: {e}")
        self.closed = True
        for event, _reply in list(self.waiting.values()):
            event.set()

    def _heartbeat(self) -> None:
        while not self.closed:
            time.sleep(5)
            try:
                self.send(NS_HEARTBEAT, "receiver-0", {"type": "PING"})
            except OSError:
                self.closed = True

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


@dataclass(eq=False)
class CastDevice:
    """A Google Cast device, used like dlna.Renderer"""

    uuid: str
    name: str
    host: str
    port: int = 8009
    _connection: _Connection | None = field(default=None, repr=False)
    _transport: str | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # The media session of the track loaded here
    _media_session: int | None = field(default=None, repr=False)

    def __eq__(self, other) -> bool:
        return isinstance(other, CastDevice) and other.uuid == self.uuid

    def __hash__(self) -> int:
        return hash(self.uuid)

    def _session(self, launch=True) -> tuple[_Connection, str]:
        """Connection and media receiver session, started when needed.

        Without launch, raises TakenOver when another app replaced the media
        receiver this device was playing in.
        """
        with self._lock:
            if self._connection is None or self._connection.closed:
                self._connection = _Connection(self.host, self.port)
                if not launch and self._media_session is not None:
                    connection = self._connection
                    status = connection.request(
                        NS_RECEIVER, "receiver-0", {"type": "GET_STATUS"}
                    )
                    connection.receiver_status = status.get("status")
                    apps = (connection.receiver_status or {}).get("applications") or []
                    app = next((a for a in apps if a.get("transportId") == self._transport), None)
                    if not app:
                        raise TakenOver("Another app is playing")
                else:
                    self._transport = None
            connection = self._connection
            if self._transport:
                apps = (connection.receiver_status or {}).get("applications") or []
                if not any(a.get("transportId") == self._transport for a in apps):
                    if not launch and self._media_session is not None:
                        raise TakenOver("Another app is playing")
                    self._transport = None
            if not self._transport:
                status = connection.request(NS_RECEIVER, "receiver-0", {"type": "GET_STATUS"})
                apps = status.get("status", {}).get("applications") or []
                app = next(
                    (a for a in apps if a.get("appId") == DEFAULT_MEDIA_RECEIVER), None
                )
                if not app:
                    status = connection.request(
                        NS_RECEIVER,
                        "receiver-0",
                        {"type": "LAUNCH", "appId": DEFAULT_MEDIA_RECEIVER},
                    )
                    apps = status.get("status", {}).get("applications") or []
                    app = next(
                        (a for a in apps if a.get("appId") == DEFAULT_MEDIA_RECEIVER),
                        None,
                    )
                    if not app:
                        raise CastError("The media player didn't start on the device")
                self._transport = app["transportId"]
            connection.connect(self._transport)
            return connection, self._transport

    def _media(self, kind: str, **args) -> dict:
        connection, transport = self._session()
        status = connection.media_status
        if not status:
            raise CastError(f"{kind}: nothing loaded")
        return connection.request(
            NS_MEDIA,
            transport,
            {"type": kind, "mediaSessionId": status["mediaSessionId"], **args},
        )

    def load(self, url: str, mime: str, track) -> None:
        """Load a track paused, play() starts it"""
        from .utils import get_image_url

        metadata = {"metadataType": 3, "title": track.name}
        if getattr(track, "artist", None):
            metadata["artist"] = track.artist.name
        if getattr(track, "album", None):
            metadata["albumName"] = track.album.name
            try:
                image = get_image_url(track.album, 640)
                if image:
                    metadata["images"] = [{"url": image}]
            except Exception:
                pass
        connection, transport = self._session()
        connection.idle_reason = None
        reply = connection.request(
            NS_MEDIA,
            transport,
            {
                "type": "LOAD",
                "autoplay": False,
                "currentTime": 0,
                "media": {
                    "contentId": url,
                    "contentType": mime,
                    "streamType": "BUFFERED",
                    "duration": track.duration or None,
                    "metadata": metadata,
                },
            },
        )
        status = (reply.get("status") or [{}])[0]
        self._media_session = status.get("mediaSessionId", connection.media_session_id)

    def play(self) -> None:
        self._media("PLAY")

    def pause(self) -> None:
        self._media("PAUSE")

    def stop(self) -> None:
        if self._connection and not self._connection.closed and self._connection.media_status:
            try:
                self._media("STOP")
            except CastError as e:
                # Already ended on the device: nothing to stop
                if "INVALID_MEDIA_SESSION_ID" not in str(e):
                    raise

    def seek(self, seconds: float) -> None:
        self._media("SEEK", currentTime=seconds, resumeState="PLAYBACK_START")

    def seek_when_playing(self, seconds: float, timeout: float = 10) -> None:
        end = time.monotonic() + timeout
        while self.get_state() != "PLAYING" and time.monotonic() < end:
            time.sleep(0.25)
        self.seek(seconds)

    def _status(self) -> dict | None:
        connection, transport = self._session(launch=False)
        connection.request(NS_MEDIA, transport, {"type": "GET_STATUS"})
        return connection.media_status

    def get_state(self) -> str:
        """The same states as DLNA devices report, and TAKEN_OVER when another app
        loaded something else or stopped the track from elsewhere"""
        try:
            status = self._status()
        except TakenOver:
            return "TAKEN_OVER"
        connection = self._connection
        if self._media_session is not None and connection:
            if connection.media_session_id > self._media_session:
                return "TAKEN_OVER"
            idle = (status or {}).get("playerState") in (None, "IDLE")
            if idle and connection.idle_reason in ("CANCELLED", "INTERRUPTED"):
                return "TAKEN_OVER"
        if not status:
            return "NO_MEDIA_PRESENT"
        return {
            "PLAYING": "PLAYING",
            "BUFFERING": "TRANSITIONING",
            "PAUSED": "PAUSED_PLAYBACK",
        }.get(status.get("playerState"), "STOPPED")

    def get_position(self) -> tuple[float, float]:
        status = self._connection.media_status if self._connection else None
        if not status:
            return 0.0, 0.0
        duration = (status.get("media") or {}).get("duration") or 0.0
        return float(status.get("currentTime") or 0.0), float(duration)

    def get_volume(self) -> int | None:
        connection, _transport = self._session()
        status = connection.request(NS_RECEIVER, "receiver-0", {"type": "GET_STATUS"})
        level = status.get("status", {}).get("volume", {}).get("level")
        return None if level is None else round(level * 100)

    def set_volume(self, volume: int) -> None:
        connection, _transport = self._session()
        connection.request(
            NS_RECEIVER,
            "receiver-0",
            {"type": "SET_VOLUME", "volume": {"level": max(0, min(volume, 100)) / 100}},
        )

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None


def _read_name(data: bytes, i: int) -> tuple[str, int]:
    labels = []
    end = None
    for _ in range(128):
        length = data[i]
        if length & 0xC0 == 0xC0:
            if end is None:
                end = i + 2
            i = (length & 0x3F) << 8 | data[i + 1]
            continue
        i += 1
        if not length:
            break
        labels.append(data[i : i + length].decode(errors="replace"))
        i += length
    return ".".join(labels), end if end is not None else i


def parse_mdns(data: bytes) -> list[dict]:
    """Cast devices in an mDNS answer: name, uuid, host and port"""
    _id, _flags, questions, answers, authority, additional = struct.unpack(
        ">HHHHHH", data[:12]
    )
    i = 12
    for _ in range(questions):
        _name, i = _read_name(data, i)
        i += 4
    instances: dict[str, dict] = {}
    addresses: dict[str, str] = {}
    for _ in range(answers + authority + additional):
        name, i = _read_name(data, i)
        kind, _class, _ttl, length = struct.unpack(">HHIH", data[i : i + 10])
        i += 10
        rdata = data[i : i + length]
        if kind == 12 and name.lower() == SERVICE:  # PTR
            instances.setdefault(_read_name(data, i)[0], {})
        elif kind == 33:  # SRV
            port = struct.unpack(">H", rdata[4:6])[0]
            instances.setdefault(name, {}).update(
                port=port, target=_read_name(data, i + 6)[0]
            )
        elif kind == 16:  # TXT
            j = 0
            txt = {}
            while j < len(rdata):
                entry = rdata[j + 1 : j + 1 + rdata[j]].decode(errors="replace")
                j += 1 + rdata[j]
                key, _, value = entry.partition("=")
                txt[key] = value
            instances.setdefault(name, {}).update(txt=txt)
        elif kind == 1 and length == 4:  # A
            addresses[name.lower()] = socket.inet_ntoa(rdata)
        i += length
    devices = []
    for name, info in instances.items():
        if not name.lower().endswith(SERVICE):
            continue
        txt = info.get("txt", {})
        host = addresses.get((info.get("target") or "").lower())
        devices.append(
            {
                "uuid": txt.get("id") or name,
                "name": txt.get("fn") or name.split(".")[0],
                "host": host,
                "target": info.get("target"),
                "port": info.get("port"),
            }
        )
    return devices


def _query(name: str, kind: int) -> bytes:
    labels = b"".join(
        bytes([len(part)]) + part.encode() for part in name.split(".")
    ) + b"\0"
    return struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + labels + struct.pack(">HH", kind, 1)


def discover(timeout: float = 3.0) -> list[CastDevice]:
    """Find the Google Cast devices on the local network"""
    found: dict[str, dict] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.settimeout(0.5)
        end = time.monotonic() + timeout
        next_query = 0.0
        while time.monotonic() < end:
            if time.monotonic() >= next_query:
                # Sent from a port other than 5353, so devices answer this socket
                # directly (RFC 6762 6.7)
                try:
                    sock.sendto(_query(SERVICE, 12), MDNS_ADDRESS)
                    for device in found.values():
                        if not device.get("host") and device.get("target"):
                            sock.sendto(_query(device["target"], 1), MDNS_ADDRESS)
                except OSError as e:
                    logger.warning(f"Couldn't search for Cast devices: {e}")
                    return []
                next_query = time.monotonic() + 1
            try:
                data, address = sock.recvfrom(9000)
            except socket.timeout:
                continue
            try:
                devices = parse_mdns(data)
            except (IndexError, struct.error, UnicodeError):
                continue
            for device in devices:
                known = found.setdefault(device["uuid"], {})
                known.update({k: v for k, v in device.items() if v})
                # The answer comes from the device itself
                known.setdefault("source", address[0])
    devices = [
        CastDevice(
            uuid=d["uuid"],
            name=d.get("name") or d["uuid"],
            host=d.get("host") or d["source"],
            port=d.get("port") or 8009,
        )
        for d in found.values()
        if d.get("host") or d.get("source")
    ]
    return sorted(devices, key=lambda d: d.name.lower())
