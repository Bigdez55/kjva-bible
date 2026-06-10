#!/usr/bin/env python3
"""Minimal retrieval-first HTTP runtime for a KJV Tokenless export bundle."""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from kjv_retrieval import KJVRetriever  # noqa


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def resolve_corpus_dir(bundle_dir: Path) -> Path:
    for candidate in [
        bundle_dir,
        bundle_dir / "corpus",
        bundle_dir / "retrieval",
    ]:
        if (candidate / "retrieval_index.json").exists() or (candidate / "verses.jsonl").exists():
            return candidate
    raise FileNotFoundError(f"no KJV retrieval artifacts found under {bundle_dir}")


class KJVHandler(BaseHTTPRequestHandler):
    retriever: KJVRetriever
    manifest: dict
    model_config: dict
    model_id: str

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path in {"/healthz", "/status"}:
            self._send_json(200, health_payload(
                self.retriever, self.manifest, self.model_config, self.model_id
            ))
            return
        if parsed.path == "/v1/cite":
            query = (params.get("q") or params.get("ref") or [""])[0]
            self._send_json(200, self.retriever.cite(query))
            return
        if parsed.path == "/v1/chat":
            query = (params.get("q") or params.get("message") or params.get("prompt") or [""])[0]
            self._send_json(200, self.retriever.chat(query))
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return
        if parsed.path == "/v1/cite":
            query = body.get("ref") or body.get("query") or body.get("q") or ""
            self._send_json(200, self.retriever.cite(query))
            return
        if parsed.path == "/v1/chat":
            query = body.get("message") or body.get("prompt") or body.get("query") or body.get("q") or ""
            top_k = int(body.get("top_k", 3))
            self._send_json(200, self.retriever.chat(query, top_k=top_k))
            return
        self._send_json(404, {"error": "not_found"})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)


def health_payload(retriever: KJVRetriever, manifest: dict,
                   model_config: dict, model_id: str) -> dict:
    return {
        "status": "ok",
        "service": "kjv-tokenless-bundle",
        "model_id": model_id,
        "parameter_count": manifest.get("n_parameters"),
        "corpus_id": manifest.get("corpus_id") or retriever.corpus_id,
        "retrieval_docs": retriever.retrieval_docs,
        "tokenization": manifest.get("tokenization"),
        "max_seq_len": model_config.get("max_seq_len"),
        "attestation": manifest.get("tokenless_attestation") or manifest.get("attestation"),
        "exact_citation_without_generation": True,
    }


def build_handler(bundle_dir: Path, model_id: str | None) -> type[KJVHandler]:
    corpus_dir = resolve_corpus_dir(bundle_dir)
    retriever = KJVRetriever(corpus_dir)
    manifest = load_json(bundle_dir / "manifest.json")
    if not manifest and (corpus_dir / "manifest.json").exists():
        manifest = load_json(corpus_dir / "manifest.json")
    model_config = load_json(bundle_dir / "model_config.json")
    handler_model_id = (
        model_id
        or manifest.get("model_id")
        or manifest.get("export_id")
        or bundle_dir.name
    )

    class Handler(KJVHandler):
        pass

    Handler.retriever = retriever
    Handler.manifest = manifest
    Handler.model_config = model_config
    Handler.model_id = handler_model_id
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--model-id", default=None)
    args = parser.parse_args()

    handler = build_handler(Path(args.bundle_dir), args.model_id)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"KJV Tokenless runtime listening on http://{args.host}:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
