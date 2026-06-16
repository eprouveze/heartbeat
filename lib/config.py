"""config.py — heartbeat board paths and column defaults.

The board logic in board.py is generic; everything deployment-specific (where state
lives on disk, what the columns are named) is isolated here so an adopter changes one
file, not the engine. All paths derive from HEARTBEAT_HOME (default ~/.heartbeat),
which keeps board state OUT of ~/.claude so a dotfile sync can never clobber it.
"""
from __future__ import annotations

import os
from pathlib import Path

# Root for all heartbeat state. Override with HEARTBEAT_HOME (e.g. a git repo the loop
# pushes from, for durable ticks + the off-machine liveness watchdog).
HOME = Path(os.environ.get("HEARTBEAT_HOME", str(Path.home() / ".heartbeat")))

# Derived render artifact: the single-file kanban opened in a browser. The card files
# under CARDS_DIR are the source of truth; this HTML is recompiled after every write.
BOARD = HOME / "board.html"

# Source of truth: one JSON file per card. Concurrent writers touch DIFFERENT files,
# so a VCS merges them cleanly — clobber is impossible by construction.
CARDS_DIR = HOME / "cards"

# Board metadata (columns + last-updated), kept beside the card files.
META = CARDS_DIR / "_board.json"

# flock target for serializing board mutations.
LOCK = HOME / ".board.lock"

# Default column names, matching templates/heartbeat-board.html. Used only to seed a
# fresh board (migrate_to_files / first write); an existing board keeps its own columns.
DEFAULT_COLUMNS = [
    "Now (today)",
    "Next (this week)",
    "Waiting on owner",
    "On horizon",
    "Done (this week)",
]
