"""Tamper-EVIDENT audit log (section 7.5): a SHA-256 hash chain.

    hash_i = SHA256( canonical_json({idx, ts, actor, action, payload, prev_hash}) )
    prev_hash of the first entry = 64 zeros;  idx starts at 1.

Canonical JSON = sorted keys, no whitespace, ASCII only, so the same entry always hashes to the
same bytes on any machine.

What this gives you:  editing, deleting, inserting or reordering any entry breaks the chain at a
specific index, which `verify` reports.

What it does NOT give you (say this plainly):
  * It does not make tampering impossible, only DETECTABLE.
  * Someone with full write access to the database can rewrite an entry AND recompute every later
    hash; the result still verifies. Likewise, deleting the newest entries leaves a valid shorter
    chain. The defence is to publish the head hash (and length) somewhere outside the system
    (README, a slide, an email to yourself) and pass it to `verify(anchor=...)`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Protocol

GENESIS = "0" * 64


def jsonable(obj: Any) -> Any:
    """Convert numpy scalars/arrays, sets, tuples and datetimes into plain JSON types."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(v) for v in obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "tolist"):  # numpy scalar or array
        return jsonable(obj.tolist())
    return obj


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=True)


def entry_hash(idx: int, ts: str, actor: str, action: str, payload: Any, prev_hash: str) -> str:
    body = {"idx": idx, "ts": ts, "actor": actor, "action": action, "payload": payload,
            "prev_hash": prev_hash}
    return hashlib.sha256(canonical_json(body).encode("ascii")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Store(Protocol):
    def all(self) -> list[dict]: ...
    def last(self) -> dict | None: ...
    def add(self, entry: dict) -> None: ...
    def replace_payload(self, idx: int, payload: Any) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def all(self) -> list[dict]:
        return [dict(r) for r in self.rows]

    def last(self) -> dict | None:
        return dict(self.rows[-1]) if self.rows else None

    def add(self, entry: dict) -> None:
        self.rows.append(dict(entry))

    def replace_payload(self, idx: int, payload: Any) -> None:
        self.rows[idx - 1]["payload"] = payload


def verify(entries: list[dict], anchor: dict | None = None) -> dict:
    """Recompute the whole chain. Returns
    {ok, length, head_hash, first_broken_index, reason}.
    `anchor` = {"length": int, "head_hash": str} published earlier outside the system: it also
    catches truncation and full-chain rewrites, which the chain alone cannot."""
    prev = GENESIS
    for i, e in enumerate(entries):
        want_idx = i + 1
        try:
            if e["idx"] != want_idx:
                return _bad(entries, want_idx, "idx_out_of_sequence")
            if e["prev_hash"] != prev:
                return _bad(entries, want_idx, "prev_hash_mismatch")
            h = entry_hash(e["idx"], e["ts"], e["actor"], e["action"], e["payload"],
                           e["prev_hash"])
            stored = e["hash"]
        except (KeyError, TypeError, ValueError):
            return _bad(entries, want_idx, "malformed_entry")
        if h != stored:
            return _bad(entries, want_idx, "hash_mismatch")
        prev = stored
    out = {"ok": True, "length": len(entries), "head_hash": prev, "first_broken_index": None,
           "reason": None}
    if anchor is not None and (anchor["length"] > len(entries) or (
            anchor["length"] <= len(entries) and anchor["length"] > 0
            and entries[anchor["length"] - 1]["hash"] != anchor["head_hash"])):
        out.update(ok=False, first_broken_index=min(anchor["length"], len(entries)) or 1,
                   reason="anchor_mismatch")
    return out


def _bad(entries: list[dict], idx: int, reason: str) -> dict:
    head = GENESIS
    if entries:
        last = entries[-1]
        head = last.get("hash", GENESIS) if isinstance(last, dict) else GENESIS
    return {"ok": False, "length": len(entries), "head_hash": head, "first_broken_index": idx,
            "reason": reason}


class AuditChain:
    """Append-only log on top of a Store."""

    def __init__(self, store: Store, allow_tamper: bool = False) -> None:
        self.store = store
        self.allow_tamper = allow_tamper

    def append(self, actor: str, action: str, payload: Any, ts: str | None = None) -> dict:
        last = self.store.last()
        prev = last["hash"] if last else GENESIS
        idx = (last["idx"] + 1) if last else 1
        ts = ts or _now()
        payload = jsonable(payload)
        entry = {"idx": idx, "ts": ts, "actor": actor, "action": action, "payload": payload,
                 "prev_hash": prev,
                 "hash": entry_hash(idx, ts, actor, action, payload, prev)}
        self.store.add(entry)
        return entry

    def entries(self) -> list[dict]:
        return self.store.all()

    def head(self) -> dict:
        last = self.store.last()
        return {"length": last["idx"] if last else 0,
                "head_hash": last["hash"] if last else GENESIS}

    def verify(self, anchor: dict | None = None) -> dict:
        return verify(self.store.all(), anchor)

    def tamper(self, idx: int) -> None:
        """DEMO ONLY: change one entry's payload without fixing the hashes, so the chain turns
        red at exactly this index. Refuses unless allow_tamper (GG_ALLOW_TAMPER_DEMO=true)."""
        if not self.allow_tamper:
            raise PermissionError("tamper demo is disabled")
        rows = self.store.all()
        if not 1 <= idx <= len(rows):
            raise IndexError(idx)
        payload = rows[idx - 1]["payload"]
        new = dict(payload) if isinstance(payload, dict) else {"value": payload}
        new["_tampered"] = True
        self.store.replace_payload(idx, new)
