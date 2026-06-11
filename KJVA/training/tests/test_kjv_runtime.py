#!/usr/bin/env python3
"""End-to-end checks for the retrieval-first KJV Tokenless runtime.

The server must already be running, for example:

  python3 training/scripts/serve_kjv_bundle.py \
    --bundle-dir "$TOKENLESS_HOME/exports/kjv_tokenless_v1_active" \
    --port 8091
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE = os.environ.get("TOKENLESS_KJV_BASE_URL", "http://127.0.0.1:8091")


def request_json(path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    url = BASE + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"content-type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def assert_ok(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return condition


def main() -> int:
    passed = True

    status, health = request_json("/healthz")
    passed &= assert_ok(
        "healthz",
        status == 200 and health.get("service") == "kjv-tokenless-bundle",
        f"status={status} service={health.get('service')!r}",
    )
    passed &= assert_ok(
        "healthz retrieval count",
        int(health.get("retrieval_docs") or 0) >= 36822,
        f"retrieval_docs={health.get('retrieval_docs')}",
    )

    ref = urllib.parse.quote("John 3:16")
    status, cite = request_json(f"/v1/cite?q={ref}")
    got_ids = [row.get("id") for row in cite.get("verses", [])]
    passed &= assert_ok(
        "direct citation",
        status == 200 and got_ids == ["JHN.3.16"],
        f"status={status} ids={got_ids}",
    )

    status, chat = request_json("/v1/chat", {"message": "God so loved the world", "top_k": 3})
    chat_ids = [row.get("id") for row in chat.get("citations", [])]
    passed &= assert_ok(
        "retrieval chat",
        status == 200 and "JHN.3.16" in chat_ids,
        f"status={status} citation_ids={chat_ids}",
    )

    status, apoc = request_json("/v1/chat", {"message": "love righteousness ye judges of the earth", "top_k": 3})
    apoc_ids = [row.get("id") for row in apoc.get("citations", [])]
    passed &= assert_ok(
        "apocrypha retrieval",
        status == 200 and "WIS.1.1" in apoc_ids,
        f"status={status} citation_ids={apoc_ids}",
    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
