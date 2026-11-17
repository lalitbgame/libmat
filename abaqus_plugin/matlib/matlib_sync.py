# -*- coding: utf-8 -*-
"""GitLab -> local cache sync for the material library.

Pure Python (no Abaqus, no third-party libs); works on Abaqus Python 2.7 and 3.x.

Cache layout (every version is kept, so old models stay reproducible):
    <cache>/index.json
    <cache>/cards/<id>/<version>/card.inp
    <cache>/cards/<id>/<version>/metadata.json
"""
from __future__ import print_function

import hashlib
import json
import os
import ssl

try:  # Py3
    from urllib.request import Request, urlopen
    from urllib.parse import quote
    from urllib.error import URLError, HTTPError
except ImportError:  # Py2 (Abaqus <= 2023)
    from urllib2 import Request, urlopen, URLError, HTTPError
    from urllib import quote

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "matlib_config.json")


def load_config():
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    cfg["cache_dir"] = os.path.expanduser(cfg.get("cache_dir", "~/.matlib"))
    return cfg


class GitLabSource(object):
    """Reads raw files from a GitLab project through the REST API v4."""

    def __init__(self, url, project, ref="main", token=None, verify_ssl=True, timeout=20):
        self.base = url.rstrip("/")
        self.project = quote(str(project), safe="")  # id or 'group/sub/project'
        self.ref = ref
        self.token = token
        self.timeout = timeout
        self.ctx = None if verify_ssl else ssl._create_unverified_context()

    def raw(self, path):
        url = "%s/api/v4/projects/%s/repository/files/%s/raw?ref=%s" % (
            self.base, self.project, quote(path, safe=""), quote(self.ref, safe=""))
        req = Request(url)
        if self.token:
            req.add_header("PRIVATE-TOKEN", self.token)
        kw = {"timeout": self.timeout}
        if self.ctx is not None:
            kw["context"] = self.ctx
        return urlopen(req, **kw).read()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, data):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def card_dir(cache_dir, mat_id, version):
    return os.path.join(cache_dir, "cards", mat_id, version)


def sync(cfg=None, source=None, log=print):
    """Pull index.json, then download any card whose hash is new or changed.

    Returns (index_dict, n_downloaded, online_flag). Falls back to the cached
    index when GitLab is unreachable so users can still work offline.
    """
    cfg = cfg or load_config()
    cache = cfg["cache_dir"]
    if source is None:
        source = GitLabSource(cfg["gitlab_url"], cfg["project"], cfg.get("ref", "main"),
                              os.environ.get(cfg.get("token_env", "MATLIB_TOKEN")),
                              cfg.get("verify_ssl", True))
    try:
        raw_index = source.raw("index.json")
        index = json.loads(raw_index.decode("utf-8"))
    except (URLError, HTTPError, IOError, ValueError) as e:
        log("MATLIB: GitLab unreachable (%s); using cached library." % e)
        return load_cached_index(cache), 0, False

    n = 0
    for m in index["materials"]:
        d = card_dir(cache, m["id"], m["version"])
        card_p, meta_p = os.path.join(d, "card.inp"), os.path.join(d, "metadata.json")
        if os.path.isfile(card_p) and _sha(open(card_p, "rb").read()) == m["card_sha256"]:
            continue
        card = source.raw(m["card_path"])
        meta = source.raw(m["metadata_path"])
        if _sha(card) != m["card_sha256"]:
            raise RuntimeError("Hash mismatch for %s v%s - index and card out of sync"
                               % (m["id"], m["version"]))
        _write(card_p, card)
        _write(meta_p, meta)
        n += 1
        log("MATLIB: downloaded %s v%s" % (m["id"], m["version"]))

    _write(os.path.join(cache, "index.json"), raw_index)
    log("MATLIB: library in sync (commit %s, %d new/updated cards)"
        % (index.get("commit", "?")[:8], n))
    return index, n, True


def load_cached_index(cache_dir):
    p = os.path.join(cache_dir, "index.json")
    if not os.path.isfile(p):
        return {"materials": [], "commit": "none"}
    with open(p) as f:
        return json.load(f)


def list_choices(index, include_drafts=False):
    """Entries shown in the dialog. Deprecated cards are always hidden."""
    out = []
    for m in index.get("materials", []):
        if m["status"] == "deprecated":
            continue
        if m["status"] == "draft" and not include_drafts:
            continue
        out.append(m)
    return out


def choice_label(m):
    return "%s | v%s | %s | %s" % (m["id"], m["version"], m["status"], m["units"])


def parse_label(label):
    parts = [p.strip() for p in label.split("|")]
    return parts[0], parts[1].lstrip("v")
