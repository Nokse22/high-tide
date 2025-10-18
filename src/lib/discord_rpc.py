import logging
import threading
import time
from enum import Enum

from tidalapi import Track

logger = logging.getLogger(__name__)

try:
    import pypresence

    has_pypresence = True
except ImportError:
    logger.warning("pypresence not found, skipping")
    has_pypresence = False


class State(Enum):
    DISCONNECTED = 0
    IDLE = 1
    PLAYING = 2


state: State = State.DISCONNECTED
disconnect_thread: threading.Thread | None = None


def connect() -> bool:
    """Connect to Discord Rich Presence IPC.

    Attempts to establish a connection to Discord's IPC server for
    Rich Presence functionality.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global state

    if not has_pypresence:
        return False

    try:
        rpc.connect()
    except Exception:
        logger.debug(
            "Can't connect to discord IPC; usually means that the RPC server is closed."
        )
        state = State.DISCONNECTED
        return False
    else:
        logger.info("Connected to discord IPC")
        state = State.IDLE
        return True


def disconnect() -> bool:
    """Disconnect from Discord Rich Presence IPC.

    Closes the connection to Discord's IPC server and updates the state.

    Returns:
        bool: True if disconnection successful, False otherwise
    """
    global state

    if not has_pypresence:
        return False

    try:
        rpc.close()
    except Exception:
        logger.debug("Can't disconnect from discord IPC")
        return False
    else:
        logger.info("Disconnected from discord IPC")
        state = State.DISCONNECTED
        return True


def set_activity(track: Track | None = None, offset_ms: int = 0) -> None:
    """Set the Discord Rich Presence activity status.

    Updates Discord with the current playing track information and playback position.

    Args:
        track: The currently playing Track object, or None to clear activity
        offset_ms: Current playback position in milliseconds (default: 0)
    """
    global state
    global disconnect_thread

    if not has_pypresence:
        return

    if state == State.DISCONNECTED:
        if not connect():
            return

    try:
        if track is None:
            rpc.update(
                details="High Tide",
                state="TIDAL gnome client",
                large_image="hightide_x1024",
                large_text="High Tide",
                buttons=[
                    {
                        "label": "Get High Tide",
                        "url": "https://github.com/nokse22/high-tide",
                    }
                ],
            )
            state = State.IDLE

            def disconnect_function() -> None:
                for _ in range(5 * 60):
                    time.sleep(1)
                    if state != State.IDLE:
                        return
                disconnect()

            disconnect_thread = threading.Thread(target=disconnect_function)
            disconnect_thread.start()
        else:
            artists = (
                [artist.name for artist in track.artists if artist.name is not None]
                if track.artists
                else None
            )
            if artists is not None and len(artists) == 0:
                artists = None

            rpc.update(
                details=track.name,
                state=", ".join(artists) if artists else "Unknown Artist",
                large_image=track.album.image() if track.album else "hightide_x1024",
                large_text=track.album.name if track.album else "High Tide",
                small_image="hightide_x1024" if track.album else None,
                small_text="High Tide" if track.album else None,
                start=int(time.time() * 1_000 - offset_ms),
                end=int(time.time() * 1_000 - offset_ms + track.duration * 1_000)
                if track.duration
                else None,
                buttons=[
                    {"label": "Listen to this song", "url": f"{track.share_url}?u"},
                    {
                        "label": "Get High Tide",
                        "url": "https://github.com/nokse22/high-tide",
                    },
                ],
            )
            state = State.PLAYING
    except pypresence.exceptions.PipeClosed:
        if connect():
            set_activity(track, offset_ms)
        else:
            state = State.DISCONNECTED
            logger.exception("Connection with discord IPC lost.")


if has_pypresence:
    rpc: pypresence.Presence = pypresence.Presence(client_id=1379096506065223680)
    connect()
