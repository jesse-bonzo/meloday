# Get the base directory of the script
import os

import yaml
from plexapi.library import LibrarySection
from plexapi.playlist import Playlist
from plexapi.server import PlexServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config(filepath="config.yml"):
    with open(os.path.join(BASE_DIR, filepath), "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

config = load_config()

MIRROR_CONFIG = config.get("plex_mirror")
MIRROR_ENABLED = bool(MIRROR_CONFIG and MIRROR_CONFIG.get("enabled"))
mirror_plex: PlexServer | None = None
mirror_lib: LibrarySection | None = None
if MIRROR_ENABLED:
    try:
        mirror_token = os.environ.get("MELODAY_MIRROR_PLEX_TOKEN") or MIRROR_CONFIG.get("token")
        if not mirror_token:
            raise RuntimeError("Mirror Plex token not set: define MELODAY_MIRROR_PLEX_TOKEN env var or plex_mirror.token in config.yml")
        mirror_plex = PlexServer(MIRROR_CONFIG["url"], mirror_token, timeout=60)
        if mirror_plex:
            mirror_lib = mirror_plex.library.section(MIRROR_CONFIG["music_library"])
    except Exception as e:
        print(f"Mirror server unreachable, disabling mirror: {e}")
        MIRROR_ENABLED = False


def mirror_playlist(name, tracks, description, cover_path):
    """Recreates the playlist on the mirror server, matching tracks by metadata
    since ratingKeys aren't shared across servers."""
    if not MIRROR_ENABLED:
        return
    if not mirror_plex or not mirror_lib:
        print(f"Mirror: unable to connect to mirror server for '{name}'")
        return
    try:
        matched = []
        for t in tracks:
            try:
                candidates = mirror_lib.searchTracks(title=t.title)
            except Exception:
                continue
            match = next(
                (c for c in candidates
                 if c.title == t.title
                 and getattr(c, "grandparentTitle", None) == getattr(t, "grandparentTitle", None)
                 and getattr(c, "parentTitle", None) == getattr(t, "parentTitle", None)),
                None
            )
            if match:
                matched.append(match)

        if not matched:
            print(f"Mirror: no matching tracks found on mirror server for '{name}'")
            return

        existing_mirror_playlist: Playlist | None = None
        playlist: Playlist
        for playlist in mirror_plex.playlists():
            if playlist and playlist.title.startswith("Meloday for "):
                existing_mirror_playlist = playlist
                break

        if existing_mirror_playlist:
            existing_mirror_playlist.removeItems(existing_mirror_playlist.items())
            existing_mirror_playlist.addItems(matched)
            existing_mirror_playlist.editTitle(name)
            existing_mirror_playlist.editSummary(description)
        else:
            existing_mirror_playlist = mirror_plex.createPlaylist(name, items=matched)
            if existing_mirror_playlist:
                existing_mirror_playlist.editSummary(description)

        if cover_path and os.path.exists(cover_path) and existing_mirror_playlist:
            existing_mirror_playlist.uploadPoster(filepath=cover_path)

        print(f"Mirror: matched {len(matched)}/{len(tracks)} tracks for '{name}'")
    except Exception as ex:
        print(f"Mirror failed for '{name}': {ex}")
