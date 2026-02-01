import logging
import threading
import time
from enum import Enum

from tidalapi.media import Track

from pypresence.presence import Presence
from pypresence.types import ActivityType

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

    if track is None:
        try:
            if state != State.DISCONNECTED:
                rpc.clear()
                rpc.close()
        except Exception:
            pass
        state = State.DISCONNECTED
        return

    if state == State.DISCONNECTED:
        if not connect():
            return

    try:
        if track is not None:
            artists = (
                [artist.name for artist in track.artists if artist.name is not None]
                if track.artists
                else None
            )
            if artists is not None and len(artists) == 0:
                artists = None

            rpc.update(
                activity_type=ActivityType.LISTENING,
                details=track.name,
                name=", ".join(artists) if artists else "Unknown Artist",
                state=", ".join(artists) if artists else "Unknown Artist",
                large_image=track.album.image() if track.album else "hightide_x1024",
                small_text="High Tide" if track.album else None,
                start=int(time.time() - offset_ms),
                end=int(time.time() - offset_ms + track.duration),
            )
            state = State.PLAYING
    except pypresence.exceptions.PipeClosed:
        if connect():
            set_activity(track, offset_ms)
        else:
            state = State.DISCONNECTED
            logger.exception("Connection with discord IPC lost.")


if has_pypresence:
    rpc: Presence = Presence(client_id=1379096506065223680)
    connect()
