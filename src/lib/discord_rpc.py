from tidalapi.media import Track
import time
try:
    import pypresence
except ImportError:
    print("pypresence not found, skipping")
    pypresence = None

if pypresence:
    rpc = pypresence.Presence(client_id=1379096506065223680)
    rpc.connect()
    set_activity()

def set_activity(track: Track|None = None, offset_ms: int = 0):
    if pypresence is None:
        print("[pypresence] library not installed, skipping")
        return

    if track is None:
        rpc.update(
            activity_type=pypresence.ActivityType.LISTENING,
            details="High Tide",
            state="TIDAL gnome client",
            large_image="hightide_x1024",
            large_text="High Tide",
            buttons=[
                {
                    "label": "Get High Tide",
                    "url": "https://github.com/nokse22/high-tide"
                }
            ]
        )
    else:
        rpc.update(
            activity_type=pypresence.ActivityType.LISTENING,
            details=track.name,
            state=f"By {track.artist.name}",
            large_image=track.album.image() if track.album else "hightide_x1024",
            large_text=track.album.name if track.album else "High Tide",
            small_image="hightide_x1024" if track.album else None,
            small_text="High Tide" if track.album else None,
            start=int(time.time() * 1_000 - offset_ms),
            buttons=[
                {
                    "label": "Listen to this song",
                    "url": f"{track.share_url}?u"
                },
                {
                    "label": "Get High Tide",
                    "url": "https://github.com/nokse22/high-tide"
                }
            ],
        )