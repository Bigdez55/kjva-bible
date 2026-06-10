#!/usr/bin/env python3
"""push_to_hf.py — publish a Tokenless model bundle to a PRIVATE Hugging Face repo.

PRIVATE BY DEFAULT (proprietary IP). The repo is created with private=True and the
script VERIFIES privacy after upload. It will NOT create or convert a public repo
unless you pass --allow-public (which prints a loud warning). This is the safety
rail so the architecture/weights can never leak to the public Hub by accident.

Usage:
  python3 push_to_hf.py --repo tokenless-base-v1 \
      --card "../BASE_MODEL_CARD.md" \
      --files runs/byte_proof/model_config.json runs/byte_proof/byte_vocab.json
  # domain model:
  python3 push_to_hf.py --repo transitgpt --card docs/domains/transitgpt_MODEL_CARD.md \
      --files gguf/transitgpt.gguf
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, whoami

_FRONTMATTER = """---
license: other
license_name: proprietary-all-rights-reserved
tags:
  - tokenless
  - byte-level
  - private
  - proprietary
library_name: custom
inference: false
---

> **PROPRIETARY AND CONFIDENTIAL — ALL RIGHTS RESERVED.** Private repository. No license
> or rights are granted. Unauthorized access, use, or disclosure is prohibited.

"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="repo name under your account (e.g. tokenless-base-v1)")
    ap.add_argument("--card", type=Path, default=None, help="markdown model card -> README.md")
    ap.add_argument("--files", nargs="*", type=Path, default=[], help="files to upload (config/vocab/gguf/safetensors)")
    ap.add_argument("--subdir", default="", help="optional path-in-repo prefix for --files")
    ap.add_argument("--allow-public", action="store_true", help="DANGER: create a PUBLIC repo (exposes IP)")
    args = ap.parse_args()

    api = HfApi()
    try:
        user = whoami()["name"]
    except Exception:
        print("[hf] NOT logged in. Run: huggingface-cli login", file=sys.stderr)
        return 1
    repo_id = f"{user}/{args.repo}"
    private = not args.allow_public
    if args.allow_public:
        print("!!! WARNING: --allow-public set — this repo will be PUBLIC and expose proprietary IP.", file=sys.stderr)

    api.create_repo(repo_id, repo_type="model", private=private, exist_ok=True)
    print(f"[hf] repo: {repo_id}  (private={private})")

    if args.card and args.card.exists():
        # Prepend HF frontmatter + confidentiality banner to the card.
        body = args.card.read_text(encoding="utf-8")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
            tf.write(_FRONTMATTER + body)
            readme = tf.name
        api.upload_file(path_or_fileobj=readme, path_in_repo="README.md",
                        repo_id=repo_id, repo_type="model")
        print("[hf] uploaded README.md (model card + confidentiality banner)")

    for f in args.files:
        if not f.exists():
            print(f"[hf] skip (not found): {f}")
            continue
        dest = (args.subdir.rstrip("/") + "/" + f.name) if args.subdir else f.name
        api.upload_file(path_or_fileobj=str(f), path_in_repo=dest,
                        repo_id=repo_id, repo_type="model")
        print(f"[hf] uploaded {dest}")

    # VERIFY privacy after upload — hard guard.
    info = api.repo_info(repo_id, repo_type="model")
    print(f"[hf] VERIFY: private={info.private}  url=https://huggingface.co/{repo_id}")
    if not info.private and not args.allow_public:
        print("[hf] FATAL: repo is PUBLIC but --allow-public was not set!", file=sys.stderr)
        return 2
    print("[hf] OK — bundle is on the private Hub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
