"""SQLite persistence (stdlib sqlite3: no ORM, nothing to install). One connection guarded by a
lock; fine for a prototype, and the SQL is plain enough to port to Postgres.

Genotype rows are stored ONLY as AES-256-GCM ciphertext (app/core/crypto.py), bound to the
dataset id and donor id. The API layer never reads the genotypes table: only `load_dataset`
does, once at start-up, to build the in-memory Dataset.
"""

from __future__ import annotations

import io
import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.core import crypto
from app.core.audit_chain import GENESIS, entry_hash, jsonable
from app.core.consent import DonorView
from app.core.dataset import Dataset

SCHEMA = """
CREATE TABLE IF NOT EXISTS cohort_metadata(id INTEGER PRIMARY KEY CHECK(id=1), dataset_id TEXT NOT NULL, metadata_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS donors(id INTEGER PRIMARY KEY, cohort_id TEXT, population TEXT,
  consent_json TEXT, family_id INTEGER, withdrawn_at TEXT);
CREATE TABLE IF NOT EXISTS genotypes(donor_id INTEGER PRIMARY KEY, genotype_blob BLOB);
CREATE TABLE IF NOT EXISTS variants(id INTEGER PRIMARY KEY, chrom TEXT, pos INTEGER, ref TEXT,
  alt TEXT, maf REAL, is_rare INTEGER, planted INTEGER);
CREATE TABLE IF NOT EXISTS relationships(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_a INTEGER,
  donor_b INTEGER, relation TEXT, meioses INTEGER, shared_fraction REAL);
CREATE TABLE IF NOT EXISTS requesters(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, role TEXT,
  credential_level TEXT, institution TEXT, api_key_hash TEXT UNIQUE, created_at TEXT,
  frozen_at TEXT);
CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT, requester_id INTEGER,
  ts TEXT, purpose TEXT, disease TEXT, is_commercial INTEGER, data_level TEXT,
  cohort_filter_json TEXT, variant_filter_json TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER
  UNIQUE, outcome TEXT, reasons_json TEXT, risk_json TEXT, transform_json TEXT,
  explanation_text TEXT, needs_human INTEGER, reviewed_by TEXT, reviewed_at TEXT,
  private_json TEXT, release_json TEXT);
CREATE TABLE IF NOT EXISTS epsilon_ledger(requester_id INTEGER, dataset_id TEXT,
  epsilon_spent REAL, updated_at TEXT, PRIMARY KEY(requester_id, dataset_id));
CREATE TABLE IF NOT EXISTS audit_log(idx INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT,
  payload_json TEXT, prev_hash TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS donor_access(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER,
  request_id INTEGER, ts TEXT, purpose TEXT, disease TEXT, level TEXT, institution TEXT);
CREATE INDEX IF NOT EXISTS donor_access_donor ON donor_access(donor_id);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, requester_id INTEGER,
  ts TEXT, kind TEXT, score REAL, details_json TEXT, action_taken TEXT);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _blob(row: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, g=row.astype(np.int8))
    return buf.getvalue()


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ------------------------------------------------------------------ helpers
    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid or 0

    # ------------------------------------------------------------------ dataset
    def has_dataset(self) -> bool:
        return bool(self.one("SELECT 1 AS x FROM donors LIMIT 1"))

    def cohort_metadata(self) -> dict | None:
        row = self.one("SELECT dataset_id, metadata_json FROM cohort_metadata WHERE id=1")
        if not row:
            return None
        return {"dataset_id": row["dataset_id"], **json.loads(row["metadata_json"])}

    def save_cohort(self, cohort, master: bytes, dataset_id: str, metadata: dict | None = None) -> None:
        """Write a cohort and its provenance. Genotypes are encrypted before database storage."""
        v = cohort.variants
        planted = set(cohort.planted)
        with self.lock:
            d = self.db
            for t in ("genotypes", "donor_access", "donors", "variants", "relationships"):
                d.execute(f"DELETE FROM {t}")
            d.execute("DELETE FROM cohort_metadata")
            d.execute("INSERT INTO cohort_metadata(id,dataset_id,metadata_json) VALUES(1,?,?)",
                      (dataset_id, json.dumps(jsonable(metadata or {
                          "genotypes_real": False, "consent_simulated": True,
                          "source": "legacy-unspecified"
                      }))))
            d.executemany(
                "INSERT INTO variants VALUES(?,?,?,?,?,?,?,?)",
                [(i + 1, str(v["chrom"][i]), int(v["pos"][i]), str(v["ref"][i]), str(v["alt"][i]),
                  float(v["maf"][i]), int(v["is_rare"][i]), int(i in planted))
                 for i in range(len(v["pos"]))])
            for dn in cohort.donors:
                d.execute("INSERT INTO donors VALUES(?,?,?,?,?,?)",
                          (dn["id"], dn["cohort_id"], dn["population"], json.dumps(dn["consent"]),
                           dn["family_id"], "2026-01-01T00:00:00" if dn["withdrawn"] else None))
                blob = crypto.encrypt(master, dataset_id, dn["id"],
                                      _blob(cohort.genotypes[dn["id"] - 1]))
                d.execute("INSERT INTO genotypes VALUES(?,?)", (dn["id"], blob))
            d.executemany(
                "INSERT INTO relationships(donor_a,donor_b,relation,meioses,shared_fraction) "
                "VALUES(?,?,?,?,?)",
                [(r["donor_a"], r["donor_b"], r["relation"], r["meioses"], r["shared"])
                 for r in cohort.relationships])
            d.commit()

    def load_dataset(self, master: bytes, dataset_id: str) -> Dataset:
        donors_rows = self.q("SELECT * FROM donors ORDER BY id")
        donors = [DonorView(r["id"], r["population"], r["cohort_id"], r["family_id"],
                            json.loads(r["consent_json"]), r["withdrawn_at"] is not None)
                  for r in donors_rows]
        blobs = {r["donor_id"]: r["genotype_blob"]
                 for r in self.q("SELECT donor_id, genotype_blob FROM genotypes")}
        rows = []
        for d in donors:
            raw = crypto.decrypt(master, dataset_id, d.id, blobs[d.id])
            rows.append(np.load(io.BytesIO(raw))["g"])
        var = self.q("SELECT * FROM variants ORDER BY id")
        rels = [{"donor_a": r["donor_a"], "donor_b": r["donor_b"], "relation": r["relation"],
                 "meioses": r["meioses"], "shared": r["shared_fraction"]}
                for r in self.q("SELECT * FROM relationships")]
        coords = [(str(r["chrom"]), int(r["pos"]), r["ref"], r["alt"]) for r in var]
        return Dataset(np.vstack(rows).astype(np.int8), np.array([r["maf"] for r in var]),
                       donors, rels, [i for i, r in enumerate(var) if r["planted"]], dataset_id,
                       coords)

    # ------------------------------------------------------------------ requesters
    def add_requester(self, name: str, role: str, level: str, institution: str,
                      key_hash: str) -> int:
        return self.x("INSERT INTO requesters(name,role,credential_level,institution,"
                      "api_key_hash,created_at) VALUES(?,?,?,?,?,?)",
                      (name, role, level, institution, key_hash, now_iso()))

    def requester_by_key(self, key_hash: str) -> dict | None:
        return self.one("SELECT * FROM requesters WHERE api_key_hash=?", (key_hash,))

    # ------------------------------------------------------------------ donor ledger
    def add_donor_access(self, rows: list[tuple]) -> None:
        """rows: (donor_id, request_id, ts, purpose, disease, level, institution). One row per
        donor included in an AGGREGATE release; this is what a donor sees in their portal."""
        with self.lock:
            self.db.executemany(
                "INSERT INTO donor_access(donor_id,request_id,ts,purpose,disease,level,"
                "institution) VALUES(?,?,?,?,?,?,?)", rows)
            self.db.commit()

    def donor_access(self, donor_id: int, limit: int = 200) -> list[dict]:
        return self.q("SELECT request_id,ts,purpose,disease,level,institution FROM donor_access "
                      "WHERE donor_id=? ORDER BY id DESC LIMIT ?", (donor_id, limit))

    def set_donor_withdrawn(self, donor_id: int, ts: str | None) -> None:
        self.x("UPDATE donors SET withdrawn_at=? WHERE id=?", (ts, donor_id))

    def set_donor_consent(self, donor_id: int, consent: dict) -> None:
        self.x("UPDATE donors SET consent_json=? WHERE id=?", (json.dumps(consent), donor_id))

    def requester(self, rid: int) -> dict | None:
        return self.one("SELECT * FROM requesters WHERE id=?", (rid,))

    def requesters(self) -> list[dict]:
        return self.q("SELECT id,name,role,credential_level,institution,created_at,frozen_at "
                      "FROM requesters ORDER BY id")

    def set_frozen(self, rid: int, frozen: bool) -> None:
        self.x("UPDATE requesters SET frozen_at=? WHERE id=?", (now_iso() if frozen else None, rid))

    # ------------------------------------------------------------------ requests/decisions
    def add_request(self, rid: int, ts: str, req: dict) -> int:
        return self.x(
            "INSERT INTO requests(requester_id,ts,purpose,disease,is_commercial,data_level,"
            "cohort_filter_json,variant_filter_json,status) VALUES(?,?,?,?,?,?,?,?,?)",
            (rid, ts, req["purpose"], req.get("disease"), int(req.get("is_commercial", False)),
             req.get("data_level", "frequency"), json.dumps(req.get("cohort_filter") or {}),
             json.dumps(req.get("variant_filter") or {}), "pending"))

    def set_request_status(self, req_id: int, status: str) -> None:
        self.x("UPDATE requests SET status=? WHERE id=?", (status, req_id))

    def save_decision(self, req_id: int, d: dict) -> int:
        return self.x(
            "INSERT OR REPLACE INTO decisions(request_id,outcome,reasons_json,risk_json,"
            "transform_json,explanation_text,needs_human,private_json,release_json) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (req_id, d["outcome"], json.dumps(jsonable(d["reasons"])),
             json.dumps(jsonable(d["risk"])), json.dumps(jsonable(d["transform"])),
             d["explanation"], int(d["needs_human"]), json.dumps(jsonable(d.get("private") or {})),
             json.dumps(jsonable(d.get("release"))) if d.get("release") is not None else None))

    def update_decision(self, req_id: int, **fields: Any) -> None:
        cols = {"outcome": "outcome", "needs_human": "needs_human", "reviewed_by": "reviewed_by",
                "reviewed_at": "reviewed_at", "release": "release_json",
                "explanation": "explanation_text", "reasons": "reasons_json"}
        sets, args = [], []
        for k, v in fields.items():
            sets.append(f"{cols[k]}=?")
            args.append(json.dumps(jsonable(v)) if k in ("release", "reasons") else v)
        self.x(f"UPDATE decisions SET {', '.join(sets)} WHERE request_id=?", (*args, req_id))

    def _decision_view(self, r: dict, with_release: bool) -> dict:
        out = {
            "id": r["request_id"], "ts": r["ts"], "requester_id": r["requester_id"],
            "requester": r.get("requester_name"), "status": r["status"],
            "request": {"purpose": r["purpose"], "disease": r["disease"],
                        "is_commercial": bool(r["is_commercial"]), "data_level": r["data_level"],
                        "cohort_filter": json.loads(r["cohort_filter_json"]),
                        "variant_filter": json.loads(r["variant_filter_json"])},
            "outcome": r["outcome"], "reasons": json.loads(r["reasons_json"] or "[]"),
            "risk": json.loads(r["risk_json"] or "{}"),
            "transform": json.loads(r["transform_json"] or "{}"),
            "explanation": r["explanation_text"], "needs_human": bool(r["needs_human"]),
            "reviewed_by": r["reviewed_by"], "reviewed_at": r["reviewed_at"],
        }
        if with_release and r["status"] == "released" and r["release_json"]:
            out["release"] = json.loads(r["release_json"])
        return out

    _JOIN = ("SELECT q.*, d.outcome, d.reasons_json, d.risk_json, d.transform_json, "
             "d.explanation_text, d.needs_human, d.reviewed_by, d.reviewed_at, d.private_json, "
             "d.release_json, r.name AS requester_name, q.id AS request_id FROM requests q "
             "LEFT JOIN decisions d ON d.request_id=q.id "
             "LEFT JOIN requesters r ON r.id=q.requester_id ")

    def decision(self, req_id: int, with_release: bool = True) -> dict | None:
        r = self.one(self._JOIN + "WHERE q.id=?", (req_id,))
        return self._decision_view(r, with_release) if r and r["outcome"] else None

    def private(self, req_id: int) -> dict:
        r = self.one("SELECT private_json FROM decisions WHERE request_id=?", (req_id,))
        return json.loads(r["private_json"]) if r and r["private_json"] else {}

    def decisions(self, requester_id: int | None = None, limit: int = 200) -> list[dict]:
        sql = self._JOIN + "WHERE d.outcome IS NOT NULL "
        args: tuple = ()
        if requester_id is not None:
            sql += "AND q.requester_id=? "
            args = (requester_id,)
        rows = self.q(sql + "ORDER BY q.id DESC LIMIT ?", (*args, limit))
        return [self._decision_view(r, True) for r in rows]

    # ------------------------------------------------------------------ ledger/alerts
    def eps_spent(self, rid: int, dataset_id: str) -> float:
        r = self.one("SELECT epsilon_spent FROM epsilon_ledger WHERE requester_id=? AND "
                     "dataset_id=?", (rid, dataset_id))
        return float(r["epsilon_spent"]) if r else 0.0

    def set_eps_spent(self, rid: int, dataset_id: str, value: float) -> None:
        self.x("INSERT OR REPLACE INTO epsilon_ledger VALUES(?,?,?,?)",
               (rid, dataset_id, value, now_iso()))

    def add_alert(self, rid: int, kind: str, score: float, details: dict, action: str) -> int:
        return self.x("INSERT INTO alerts(requester_id,ts,kind,score,details_json,action_taken) "
                      "VALUES(?,?,?,?,?,?)",
                      (rid, now_iso(), kind, score, json.dumps(jsonable(details)), action))

    def alerts(self, limit: int = 200) -> list[dict]:
        rows = self.q("SELECT a.*, r.name AS requester FROM alerts a LEFT JOIN requesters r ON "
                      "r.id=a.requester_id ORDER BY a.id DESC LIMIT ?", (limit,))
        for r in rows:
            r["details"] = json.loads(r.pop("details_json"))
        return rows


class AuditStore:
    """audit_chain.Store implementation on the audit_log table."""

    def __init__(self, store: Store) -> None:
        self.s = store

    def all(self) -> list[dict]:
        return [{"idx": r["idx"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
                 "payload": json.loads(r["payload_json"]), "prev_hash": r["prev_hash"],
                 "hash": r["hash"]} for r in self.s.q("SELECT * FROM audit_log ORDER BY idx")]

    def last(self) -> dict | None:
        r = self.s.one("SELECT * FROM audit_log ORDER BY idx DESC LIMIT 1")
        if not r:
            return None
        return {"idx": r["idx"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
                "payload": json.loads(r["payload_json"]), "prev_hash": r["prev_hash"],
                "hash": r["hash"]}


    def append_atomic(self, actor: str, action: str, payload: Any, ts: str | None = None) -> dict:
        """Append under the store lock; PostgreSQL overrides this with a cross-process lock."""
        with self.s.lock:
            last = self.last()
            idx = int(last["idx"]) + 1 if last else 1
            previous = last["hash"] if last else GENESIS
            stamp = ts or now_iso()
            safe_payload = jsonable(payload)
            entry = {"idx": idx, "ts": stamp, "actor": actor, "action": action,
                     "payload": safe_payload, "prev_hash": previous,
                     "hash": entry_hash(idx, stamp, actor, action, safe_payload, previous)}
            self.add(entry)
            return entry

    def add(self, e: dict) -> None:
        self.s.x("INSERT INTO audit_log VALUES(?,?,?,?,?,?,?)",
                 (e["idx"], e["ts"], e["actor"], e["action"], json.dumps(e["payload"]),
                  e["prev_hash"], e["hash"]))

    def replace_payload(self, idx: int, payload: Any) -> None:
        self.s.x("UPDATE audit_log SET payload_json=? WHERE idx=?", (json.dumps(payload), idx))
