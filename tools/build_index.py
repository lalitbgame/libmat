#!/usr/bin/env python3
"""Build index.json: one entry per card with metadata + sha256 of card and metadata.

The Abaqus plugin downloads only index.json first, then fetches the cards whose
hash differs from its local cache, so sync is cheap.
"""
import datetime
import hashlib
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAT_DIR = os.path.join(ROOT, "materials")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return os.environ.get("CI_COMMIT_SHA", "unknown")


def main():
    entries = []
    for dirpath, _, files in sorted(os.walk(MAT_DIR)):
        if "metadata.json" not in files:
            continue
        meta_p, card_p = os.path.join(dirpath, "metadata.json"), os.path.join(dirpath, "card.inp")
        with open(meta_p) as f:
            meta = json.load(f)
        rel = os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        meta.update({
            "card_path": rel + "/card.inp",
            "metadata_path": rel + "/metadata.json",
            "card_sha256": sha256(card_p),
            "metadata_sha256": sha256(meta_p),
        })
        entries.append(meta)

    index = {
        "schema": 1,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_commit(),
        "materials": sorted(entries, key=lambda m: (m["category"], m["id"])),
    }
    with open(os.path.join(ROOT, "index.json"), "w") as f:
        json.dump(index, f, indent=2)
    print("index.json written with %d materials" % len(entries))


if __name__ == "__main__":
    main()
