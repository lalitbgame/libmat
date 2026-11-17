"""End-to-end test of matlib_sync against a local mock of the GitLab files API.

Run:  python3 tests/test_sync.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "abaqus_plugin", "matlib"))
import matlib_sync  # noqa: E402

REPO = None  # directory the mock server serves from
TOKEN = "test-token"


class MockGitLab(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("PRIVATE-TOKEN") != TOKEN:
            self.send_response(401); self.end_headers(); return
        # /api/v4/projects/<proj>/repository/files/<path>/raw?ref=main
        parts = urlparse(self.path).path.split("/")
        fpath = unquote(parts[parts.index("files") + 1])
        full = os.path.join(REPO, fpath)
        if not os.path.isfile(full):
            self.send_response(404); self.end_headers(); return
        data = open(full, "rb").read()
        self.send_response(200); self.end_headers(); self.wfile.write(data)


def main():
    global REPO
    REPO = tempfile.mkdtemp()
    cache = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, "materials"), os.path.join(REPO, "materials"))
    shutil.copy(os.path.join(ROOT, "index.json"), REPO)

    srv = HTTPServer(("127.0.0.1", 0), MockGitLab)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_port
    cfg = {"cache_dir": cache}
    src = matlib_sync.GitLabSource(url, "cae/material-cards", token=TOKEN)

    # 1. first sync downloads everything
    idx, n, online = matlib_sync.sync(cfg, src)
    assert online and n == 3, n
    # 2. second sync downloads nothing
    _, n, _ = matlib_sync.sync(cfg, src)
    assert n == 0, n
    # 3. drafts hidden by default
    labels = [matlib_sync.choice_label(m) for m in matlib_sync.list_choices(idx)]
    assert not any("PA66" in l for l in labels), labels
    assert matlib_sync.parse_label(labels[0])[1].count(".") == 2
    # 4. new version of a card on the server -> only that card pulled, old version kept
    idx_srv = json.load(open(os.path.join(REPO, "index.json")))
    s355 = [m for m in idx_srv["materials"] if m["id"] == "S355"][0]
    card = os.path.join(REPO, s355["card_path"])
    with open(card, "a") as f:
        f.write(" 540.0, 0.250\n")
    s355["version"] = "1.2.0"
    s355["card_sha256"] = matlib_sync._sha(open(card, "rb").read())
    json.dump(idx_srv, open(os.path.join(REPO, "index.json"), "w"))
    _, n, _ = matlib_sync.sync(cfg, src)
    assert n == 1, n
    assert os.path.isdir(matlib_sync.card_dir(cache, "S355", "1.1.0"))
    assert os.path.isdir(matlib_sync.card_dir(cache, "S355", "1.2.0"))
    # 5. offline -> falls back to cache
    srv.shutdown(); srv.server_close()
    idx_off, n, online = matlib_sync.sync(cfg, src, log=lambda m: None)
    assert not online and len(idx_off["materials"]) == 3
    print("ALL SYNC TESTS PASSED")
    shutil.rmtree(REPO); shutil.rmtree(cache)


if __name__ == "__main__":
    main()
