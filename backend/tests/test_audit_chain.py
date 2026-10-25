import copy
import random
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app.core.audit_chain import (
    GENESIS,
    AuditChain,
    MemoryStore,
    canonical_json,
    entry_hash,
    jsonable,
    verify,
)
from app.store import AuditStore, Store


def make_chain(n=12, allow_tamper=False):
    c = AuditChain(MemoryStore(), allow_tamper)
    for i in range(n):
        c.append(f"actor{i % 3}", ["request", "decision", "alert"][i % 3],
                 {"i": i, "nested": {"a": [1, 2, {"b": "x"}]}, "s": "héllo"},
                 ts=f"2026-10-20T08:00:{i:02d}.000000+00:00")
    return c


def test_canonical_json_is_stable_and_compact():
    a = canonical_json({"b": 1, "a": [True, None, "é"]})
    assert a == '{"a":[true,null,"\\u00e9"],"b":1}'
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_genesis_and_linking():
    c = make_chain(3)
    rows = c.entries()
    assert rows[0]["prev_hash"] == GENESIS and rows[0]["idx"] == 1
    assert rows[1]["prev_hash"] == rows[0]["hash"] and rows[2]["prev_hash"] == rows[1]["hash"]
    assert rows[0]["hash"] == entry_hash(1, rows[0]["ts"], "actor0", "request",
                                         rows[0]["payload"], GENESIS)


def test_untouched_chain_verifies_and_reports_head():
    c = make_chain(12)
    v = c.verify()
    assert v == {"ok": True, "length": 12, "head_hash": c.entries()[-1]["hash"],
                 "first_broken_index": None, "reason": None}
    assert c.head() == {"length": 12, "head_hash": v["head_hash"]}


def test_empty_chain_is_valid():
    v = AuditChain(MemoryStore()).verify()
    assert v["ok"] and v["length"] == 0 and v["head_hash"] == GENESIS


def mutate(entry, field, rng):
    """Return a copy of the entry with ONE field changed by a single character/byte/value."""
    e = copy.deepcopy(entry)
    if field == "payload":
        e["payload"]["i"] = e["payload"]["i"] + 1
    elif field in ("hash", "prev_hash"):
        s = e[field]
        k = rng.randrange(len(s))
        e[field] = s[:k] + ("0" if s[k] != "0" else "1") + s[k + 1:]
    elif field == "idx":
        e["idx"] += 1
    else:
        s = e[field]
        k = rng.randrange(len(s))
        e[field] = s[:k] + chr(ord(s[k]) ^ 1) + s[k + 1:]
    return e


def test_any_single_change_to_any_entry_is_detected_at_that_index():
    rng = random.Random(0)
    base = make_chain(15).entries()
    for i in range(len(base)):
        for field in ("payload", "hash", "prev_hash", "idx", "ts", "actor", "action"):
            rows = copy.deepcopy(base)
            rows[i] = mutate(rows[i], field, rng)
            v = verify(rows)
            assert not v["ok"], (i, field)
            assert v["first_broken_index"] == i + 1, (i, field, v)


def test_single_byte_flip_anywhere_in_serialised_entry_detected():
    base = make_chain(6).entries()
    for i, e in enumerate(base):
        raw = canonical_json(e)
        for pos in range(0, len(raw), 3):  # every 3rd byte keeps the test quick
            flipped = raw[:pos] + chr(ord(raw[pos]) ^ 1) + raw[pos + 1:]
            try:
                import json
                mutated = json.loads(flipped)
            except ValueError:
                continue  # not even valid JSON anymore: trivially rejected
            if mutated == e:
                continue
            rows = copy.deepcopy(base)
            rows[i] = mutated
            assert not verify(rows)["ok"], (i, pos)


def test_deletion_insertion_and_reordering_detected():
    base = make_chain(8).entries()
    deleted = base[:3] + base[4:]
    v = verify(deleted)
    assert not v["ok"] and v["first_broken_index"] == 4
    swapped = copy.deepcopy(base)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    assert not verify(swapped)["ok"]
    forged = copy.deepcopy(base)
    forged.insert(2, copy.deepcopy(base[2]))
    assert not verify(forged)["ok"]


def test_tamper_demo_gated_and_turns_chain_red_at_exact_index():
    c = make_chain(10, allow_tamper=False)
    try:
        c.tamper(5)
        raise AssertionError("must be refused")
    except PermissionError:
        pass
    assert c.verify()["ok"]
    c2 = make_chain(10, allow_tamper=True)
    c2.tamper(5)
    v = c2.verify()
    assert not v["ok"] and v["first_broken_index"] == 5 and v["reason"] == "hash_mismatch"


def test_truncation_and_full_rewrite_need_an_external_anchor():
    c = make_chain(10)
    anchor = c.head()  # published outside the system
    rows = c.entries()
    # 1. drop the newest entries: still a valid (shorter) chain by itself...
    assert verify(rows[:7])["ok"]
    # ...but the anchor catches it
    assert verify(rows[:7], anchor)["reason"] == "anchor_mismatch"
    # 2. attacker edits entry 4 AND recomputes every later hash: chain alone says "valid"
    forged = AuditChain(MemoryStore())
    for r in rows:
        p = dict(r["payload"])
        if r["idx"] == 4:
            p["i"] = 999
        forged.append(r["actor"], r["action"], p, ts=r["ts"])
    assert forged.verify()["ok"]  # the honest limitation
    assert not forged.verify(anchor)["ok"]  # ...fixed by the external anchor
    assert verify(rows, anchor)["ok"]  # untouched chain matches its own anchor


def test_jsonable_handles_numpy_sets_and_tuples():
    out = jsonable({"a": np.float64(1.5), "b": np.int64(3), "c": {3, 1, 2}, "d": (1, 2),
                    "e": np.array([1, 2])})
    assert out == {"a": 1.5, "b": 3, "c": [1, 2, 3], "d": [1, 2], "e": [1, 2]}
    c = AuditChain(MemoryStore())
    c.append("x", "y", {"v": np.float64(0.25), "ids": {2, 1}})
    assert c.verify()["ok"] and c.entries()[0]["payload"] == {"v": 0.25, "ids": [1, 2]}


def test_nan_rejected_so_hashes_stay_portable():
    c = AuditChain(MemoryStore())
    try:
        c.append("x", "y", {"v": float("nan")})
        raise AssertionError("NaN must be rejected")
    except ValueError:
        pass



def test_store_backed_concurrent_appends_keep_a_contiguous_chain():
    store = Store(":memory:")
    chain = AuditChain(AuditStore(store))
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda i: chain.append("worker", "test.concurrent", {"i": i}),
                          range(100)))
        result = chain.verify()
        assert result["ok"] is True
        assert result["length"] == 100
        assert [entry["idx"] for entry in chain.entries()] == list(range(1, 101))
    finally:
        store.db.close()
