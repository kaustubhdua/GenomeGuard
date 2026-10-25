"""Check whether a synthetic request survives a redeploy.

Use only against the public synthetic demo. The default expectation is that a known
pre-redeploy request ID is absent after restart because this free service has no disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get(base: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
    request = Request(base.rstrip("/") + "/" + path.lstrip("/"),
                      headers={"Accept": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--request-id", type=int, required=True,
                        help="ID confirmed to exist before the redeploy")
    args = parser.parse_args()
    status, demo = get(args.base, "/demo/requesters")
    if status != 200 or not demo.get("admin_key"):
        print("[FAIL] cannot retrieve synthetic-demo admin credential")
        return 1
    status, _ = get(args.base, f"/requests/{args.request_id}",
                    {"X-Admin-Key": demo["admin_key"]})
    if status == 404:
        print(f"[PASS] pre-redeploy synthetic request {args.request_id} is absent after redeploy")
        print("CONFIRMED: the free deployment did not preserve the SQLite request record.")
        return 0
    if status == 200:
        print(f"[FAIL] pre-redeploy request {args.request_id} still exists; investigate storage behavior")
    else:
        print(f"[FAIL] unexpected HTTP {status} while checking request {args.request_id}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
