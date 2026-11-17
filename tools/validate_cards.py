#!/usr/bin/env python3
"""Validate every material card + metadata pair in materials/.

Checks (no third-party deps so it runs in any CI image):
  * metadata.json present, required fields, allowed enums, semver version
  * changelog contains an entry for the current version
  * card.inp present, has exactly one *Material whose name == metadata id
  * released cards must have approved_by
  * --base REF: any card/metadata changed vs REF must bump its version
Exit code 1 on any error.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAT_DIR = os.path.join(ROOT, "materials")

REQUIRED = ["id", "name", "category", "version", "status", "units",
            "material_model", "source", "author", "date", "changelog"]
STATUS = {"draft", "released", "deprecated"}
UNITS = {"SI-mm", "SI-m", "US-in"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
MAT_KW = re.compile(r"^\*material\s*,\s*name\s*=\s*([^,\s]+)", re.I | re.M)


def card_dirs():
    for dirpath, _, files in os.walk(MAT_DIR):
        if "metadata.json" in files or "card.inp" in files:
            yield dirpath


def semver_tuple(v):
    return tuple(int(x) for x in v.split("."))


def check_dir(d):
    errs = []
    rel = os.path.relpath(d, ROOT)
    meta_p, card_p = os.path.join(d, "metadata.json"), os.path.join(d, "card.inp")
    if not os.path.isfile(meta_p):
        return ["%s: missing metadata.json" % rel], None
    if not os.path.isfile(card_p):
        errs.append("%s: missing card.inp" % rel)
    try:
        with open(meta_p) as f:
            meta = json.load(f)
    except ValueError as e:
        return ["%s: metadata.json is not valid JSON (%s)" % (rel, e)], None

    for k in REQUIRED:
        if k not in meta or meta[k] in ("", None, []):
            errs.append("%s: missing field '%s'" % (rel, k))
    if meta.get("status") not in STATUS:
        errs.append("%s: status must be one of %s" % (rel, sorted(STATUS)))
    if meta.get("units") not in UNITS:
        errs.append("%s: units must be one of %s" % (rel, sorted(UNITS)))
    v = meta.get("version", "")
    if not SEMVER.match(str(v)):
        errs.append("%s: version '%s' is not semver X.Y.Z" % (rel, v))
    if meta.get("status") == "released" and not meta.get("approved_by"):
        errs.append("%s: released card needs approved_by" % rel)
    if v and not any(c.get("version") == v for c in meta.get("changelog", [])):
        errs.append("%s: changelog has no entry for version %s" % (rel, v))
    if os.path.basename(d) != meta.get("id"):
        errs.append("%s: folder name must equal id '%s'" % (rel, meta.get("id")))

    if os.path.isfile(card_p):
        with open(card_p) as f:
            names = MAT_KW.findall(f.read())
        if len(names) != 1:
            errs.append("%s: card.inp must contain exactly one *Material (found %d)" % (rel, len(names)))
        elif names[0] != meta.get("id"):
            errs.append("%s: *Material name '%s' != id '%s'" % (rel, names[0], meta.get("id")))
    return errs, meta


def git(*args):
    return subprocess.check_output(["git"] + list(args), cwd=ROOT).decode()


def check_version_bumps(base):
    """Changed card/metadata must carry a higher version than on base ref."""
    errs = []
    changed = git("diff", "--name-only", base, "--", "materials").split()
    for d in sorted({os.path.dirname(p) for p in changed}):
        meta_rel = d + "/metadata.json"
        if not os.path.isfile(os.path.join(ROOT, meta_rel)):
            continue  # deleted card
        try:
            old = json.loads(git("show", "%s:%s" % (base, meta_rel)))
        except subprocess.CalledProcessError:
            continue  # new card
        with open(os.path.join(ROOT, meta_rel)) as f:
            new = json.load(f)
        try:
            if semver_tuple(new["version"]) <= semver_tuple(old["version"]):
                errs.append("%s changed but version not bumped (%s -> %s)"
                            % (d, old["version"], new["version"]))
        except (KeyError, ValueError):
            pass  # format errors are reported by check_dir
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="git ref to compare against for version-bump check")
    a = ap.parse_args()

    errors, ids = [], {}
    for d in card_dirs():
        e, meta = check_dir(d)
        errors += e
        if meta:
            if meta.get("id") in ids:
                errors.append("duplicate id %s in %s and %s" % (meta["id"], ids[meta["id"]], d))
            ids[meta.get("id")] = d
    if a.base:
        errors += check_version_bumps(a.base)

    for e in errors:
        print("ERROR:", e)
    print("%d cards checked, %d errors" % (len(ids), len(errors)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
