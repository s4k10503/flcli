"""Domain value object: GM drum-name → MIDI pitch map.

Pure musical knowledge — which note number is "kick", which is "snare",
etc.  Belongs in the domain because it describes the music, not the
wire format.  The piano-roll realtime path looks the friendly name up
here when the user types ``--drum kick`` instead of ``--pitch 36``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

#: GM drum pitches keyed by friendly short name.
DRUMS: Final[Mapping[str, int]] = {
    "kick": 36,
    "snare": 38,
    "clap": 39,
    "chh": 42,
    "ohh": 46,
}
