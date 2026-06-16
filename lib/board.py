"""board.py — the single, lock-guarded read/write path for the heartbeat board.

Storage model:
  SOURCE OF TRUTH = one file per card: $HEARTBEAT_HOME/cards/<id>.json, plus cards/_board.json
  (columns + updated). Concurrent writers touch DIFFERENT files, so a VCS merges them cleanly
  — clobber is impossible by construction. The board.html blob is a DERIVED render artifact,
  recompiled from the card files after every write (so opening board.html still works locally).

  Backward-compatible: if cards/ is empty (pre-migration), everything falls back to reading
  and writing the embedded board.html blob — so deploying this module is a no-op until
  migrate_to_files() flips the source. All mutations are flock-guarded + atomic either way.

Paths and default columns live in config.py — this engine is deployment-agnostic.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from config import BOARD, CARDS_DIR, DEFAULT_COLUMNS, LOCK, META

DATA_RE = re.compile(r'(<script id="data" type="application/json">)(.*?)(</script>)', re.S)


@contextmanager
def board_lock():
    """Exclusive flock over all board mutations. Blocking (low-contention board)."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def files_mode() -> bool:
    """True once the per-card files exist (post-migration); else blob-mode (legacy fallback)."""
    return META.exists()


def card_id(card: dict) -> str:
    """Stable id derived from title+owner (used when a card lacks an explicit id/key)."""
    base = f"{card.get('title', '')}|{card.get('owner', '')}".encode("utf-8")
    return "c-" + hashlib.sha1(base).hexdigest()[:8]


def _blob_read() -> dict:
    m = DATA_RE.search(BOARD.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("heartbeat board data block not found")
    return json.loads(m.group(2))


def _atomic_write(path: Path, text: str):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _dump(obj: dict) -> str:
    """Canonical on-disk form for card / meta JSON files: deterministic AND
    POSIX-terminated (single trailing newline).

    The trailing newline matters: without it a writer that emits no newline while the
    committed file has one rewrites every card on every save → phantom "modified" files
    → autostash collisions on every pull/push across sessions and machines. Emit the
    newline everywhere so the bytes round-trip and a VCS sees a save as a no-op."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _write_if_changed(path: Path, text: str) -> bool:
    """Write only when the canonical bytes differ from what's on disk. This is the
    'change-only' half of the design: the file-per-card layout is meant to let concurrent
    writers touch DISJOINT files, but a save that rewrote all cards on every mutation
    would dirty the whole board on a one-card upsert. Skipping unchanged files means an
    upsert touches exactly the cards it edits."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    _atomic_write(path, text)
    return True


def compile_blob(data: dict):
    """Regenerate the board.html data block from `data` (keeps the hand-authored template)."""
    html = BOARD.read_text(encoding="utf-8")
    m = DATA_RE.search(html)
    if not m:
        raise RuntimeError("heartbeat board data block not found (compile)")
    new_html = html[: m.start(2)] + json.dumps(data, ensure_ascii=False, indent=2) + html[m.end(2):]
    _atomic_write(BOARD, new_html)


def load() -> dict:
    """Point-in-time read. Files-mode assembles from cards/*.json; else parses the blob."""
    if not files_mode():
        return _blob_read()
    meta = json.loads(META.read_text(encoding="utf-8"))
    cards = []
    for p in sorted(CARDS_DIR.glob("*.json")):
        if p.name == "_board.json":
            continue
        cards.append(json.loads(p.read_text(encoding="utf-8")))
    cards.sort(key=lambda c: (c.get("col", 99), c.get("id", "")))
    return {
        "columns": meta.get("columns", list(DEFAULT_COLUMNS)),
        "updated": meta.get("updated", ""),
        "cards": cards,
    }


def save_data(data: dict):
    """Persist the full board `data`. Files-mode: write each card file, delete orphans, write
    meta, recompile the blob. Blob-mode: write the embedded blob. Caller holds board_lock()."""
    if not files_mode():
        compile_blob(data)
        return
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    live_ids = set()
    for card in data.get("cards", []):
        cid = card.get("id") or card_id(card)
        card["id"] = cid
        live_ids.add(cid)
        _write_if_changed(CARDS_DIR / f"{cid}.json", _dump(card))  # change-only + canonical
    # remove orphan card files (cards deleted from data)
    for p in CARDS_DIR.glob("*.json"):
        if p.name != "_board.json" and p.stem not in live_ids:
            p.unlink()
    _write_if_changed(META, _dump(
        {"columns": data.get("columns", list(DEFAULT_COLUMNS)), "updated": data.get("updated", "")}))
    compile_blob(data)  # keep the render artifact current


def migrate_to_files() -> int:
    """One-time: split the current blob into per-card files + meta. Idempotent-ish (re-runs
    overwrite). Returns the number of cards written. Caller holds board_lock()."""
    data = _blob_read()
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    # ensure ids before filing (a card with no id can't have a stable filename)
    seen = set()
    for c in data.get("cards", []):
        if not c.get("id"):
            cid = card_id(c)
            while cid in seen:
                cid += "x"
            c["id"] = cid
        seen.add(c["id"])
    _atomic_write(META, _dump(
        {"columns": data.get("columns", list(DEFAULT_COLUMNS)), "updated": data.get("updated", "")}))
    for c in data.get("cards", []):
        _atomic_write(CARDS_DIR / f"{c['id']}.json", _dump(c))
    return len(data.get("cards", []))


# ---- read-only helper ----

def get(cid: str) -> dict | None:
    return next((c for c in load().get("cards", []) if c.get("id") == cid), None)


# ---- mutations (all lock-guarded; go through load()/save_data() so they work in either mode) ----

def ensure_ids() -> int:
    with board_lock():
        data = load()
        n = 0
        seen = set()
        for c in data.get("cards", []):
            if not c.get("id"):
                cid = card_id(c)
                while cid in seen:
                    cid += "x"
                c["id"] = cid
                n += 1
            seen.add(c["id"])
        if n:
            save_data(data)
        return n


def _guard_provenance(existing: dict, incoming: dict) -> None:
    """Provenance ratchet: a card once stamped untrusted (provenance.origin == "ai" — set
    by an auto-producer on scraped content) can NEVER be silently downgraded to trusted by
    a later upsert/set. This protects the heartbeat auto-land gate from being bypassed by a
    follow-up write that drops or rewrites provenance. Mutates `incoming` in place.
    Review entries may still be appended; origin/basis stay pinned to the untrusted values."""
    ep = existing.get("provenance")
    if not (isinstance(ep, dict) and ep.get("origin") == "ai"):
        return
    ip = incoming.get("provenance")
    if not isinstance(ip, dict):
        incoming["provenance"] = ep  # absent or null → preserve the untrusted stamp
        return
    ip["origin"] = "ai"              # never downgrade away from untrusted
    ip.setdefault("basis", ep.get("basis"))


def can_auto_land(card: dict, *, producer_actor: str | None = None) -> tuple[bool, str]:
    """The auto-land gate — the code that makes "AI cannot approve its own work" real.

    An autonomous loop that adds any auto-land action (auto-merge a PR, auto-deploy) MUST
    call this first and act only when it returns (True, …). Returns (ok, reason):

    - Untrusted origin (provenance.origin == "ai", an auto-producer scrape) is NEVER
      auto-landable — that is the whole point of the producer stamp + ratchet.
    - Otherwise the card needs at least one review entry whose actor is DISTINCT from
      `producer_actor` (the loop/actor that created the card). The producer reviewing its
      own work does not count — a separate context (the adversarial reviewer or the human
      owner) must have added the entry. An empty review stack is never landable.

    This closes the delete+re-add laundering path too: a card removed and re-added (even
    relabelled origin="human") starts with an empty review stack, so it is not landable
    until a distinct actor reviews it.
    """
    prov = card.get("provenance")
    if not isinstance(prov, dict):
        return False, "no provenance stamp"
    if prov.get("origin") == "ai":
        return False, "untrusted origin (scraped) — never auto-land"
    review = prov.get("review") or []
    reviewers = {
        r.get("actor") for r in review
        if isinstance(r, dict) and r.get("action") and r.get("actor")
    }
    if not (reviewers - {producer_actor}):
        return False, "no review by an actor distinct from the producer"
    return True, "ok"


def upsert(card: dict) -> str:
    """Add a card, or merge fields into the existing card with the same id. Returns the id."""
    with board_lock():
        data = load()
        cid = card.get("id") or card_id(card)
        card = {**card, "id": cid}
        for c in data.setdefault("cards", []):
            if c.get("id") == cid:
                _guard_provenance(c, card)
                c.update(card)
                break
        else:
            data["cards"].append(card)
        save_data(data)
        return cid


def move(cid: str, col: int) -> bool:
    with board_lock():
        data = load()
        for c in data.get("cards", []):
            if c.get("id") == cid:
                c["col"] = int(col)
                save_data(data)
                return True
        return False


def remove(cid: str) -> bool:
    with board_lock():
        data = load()
        cards = data.get("cards", [])
        kept = [c for c in cards if c.get("id") != cid]
        if len(kept) == len(cards):
            return False
        data["cards"] = kept
        save_data(data)
        return True
