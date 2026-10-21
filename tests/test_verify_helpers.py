"""Verification helpers must finish startup and observe real page hydration."""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ROOT / ".cursor/skills/verify-nfl-lab/helpers"


def test_documented_server_launch_returns_while_server_is_running(tmp_path):
    env = {**os.environ, "VERIFY_RUN_DIR": str(tmp_path)}
    try:
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", '''
                eval "$(.cursor/skills/verify-nfl-lab/helpers/serve.sh start | tee /dev/stderr | grep -E '^VERIFY_')"
                export VERIFY_RUN_DIR VERIFY_URL
                curl --fail --silent "${VERIFY_URL}/index.html"
            '''],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=8,
        )
        assert proc.returncode == 0, proc.stderr
        assert 'id="home-title"' in proc.stdout
        os.kill(int((tmp_path / "serve.pid").read_text()), 0)
    finally:
        subprocess.run(
            ["bash", str(HELPERS / "serve.sh"), "stop"],
            env=env, capture_output=True, check=True, timeout=5,
        )


def chrome_path():
    candidates = [os.environ.get("CHROME_PATH")]
    candidates += [shutil.which(name) for name in (
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    )]
    candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for candidate in candidates:
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    pytest.fail("Chrome/Chromium is required for browser verification tests")


@contextmanager
def published_site(api_path=None, mode=None):
    """Serve committed files unchanged, with controlled transport delays/failures."""
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == api_path:
                if mode == "delay":
                    time.sleep(2)
                elif mode == "fail":
                    self.send_error(503)
                    return
            super().do_GET()

        def log_message(self, *_args):
            pass

    handler = functools.partial(Handler, directory=str(ROOT / "public"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def browser_shot(base_url, page, out_dir):
    return subprocess.run(
        ["node", str(HELPERS / "browser_shot.mjs"), base_url, f"/{page}.html", str(out_dir)],
        env={**os.environ, "CHROME_PATH": chrome_path()},
        capture_output=True, text=True, timeout=25,
    )


@pytest.mark.parametrize("page, api_path", [
    ("ledger", "/api/baseline.json"),
    ("model", "/api/picks.json"),
])
def test_browser_waits_for_delayed_published_data(tmp_path, page, api_path):
    with published_site(api_path, "delay") as url:
        proc = browser_shot(url, page, tmp_path)
    assert proc.returncode == 0, proc.stderr
    snap = json.loads((tmp_path / "snapshot.json").read_text())
    assert snap["ready"] is True
    assert (tmp_path / "page.png").stat().st_size > 0
    if page == "ledger":
        assert "48.8" in snap["spread"]
        assert "51.0" in snap["total"]
        assert snap["live"] not in ("", "…")
        assert snap["tiles"] == 2
    else:
        assert snap["charts"]["ratings"] == 32
        assert snap["charts"]["games"] > 0
        assert snap["charts"]["winrate"] and snap["charts"]["mae"]


@pytest.mark.parametrize("page, api_path", [
    ("ledger", "/api/report_card.json"),
    ("ledger", "/api/baseline.json"),
    ("model", "/api/model.json"),
    ("model", "/api/picks.json"),
])
def test_browser_rejects_failed_published_data(tmp_path, page, api_path):
    with published_site(api_path, "fail") as url:
        proc = browser_shot(url, page, tmp_path)
    assert proc.returncode != 0, proc.stdout
    assert "page never hydrated" in proc.stderr
    assert not (tmp_path / "page.png").exists()
    assert not (tmp_path / "snapshot.json").exists()


def test_browser_still_captures_hydrated_home(tmp_path):
    with published_site() as url:
        proc = browser_shot(url, "index", tmp_path)
    assert proc.returncode == 0, proc.stderr
    snap = json.loads((tmp_path / "snapshot.json").read_text())
    assert snap["ready"] is True
    assert snap["title"] and "Loading" not in snap["title"]
