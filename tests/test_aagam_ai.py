"""Local AI against a stand-in for Ollama's API, and once against the real one when it is running."""

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from helpers import write_notice_pdf, write_pdf

from aagam import ai, library
from aagam.config import AagamSettings
from aagam.db import open_db


class FakeOllama(BaseHTTPRequestHandler):
    models = ["qwen3:4b"]
    answer: dict = {}
    reject_think = False
    requests: list = []

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"models": [{"name": m} for m in self.models]})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(request)
        if self.reject_think and "think" in request:
            return self._send(400, {"error": f'"{request["model"]}" does not support thinking'})
        self._send(200, {"message": {"role": "assistant", "content": json.dumps(self.answer)}})


@pytest.fixture
def ollama():
    FakeOllama.requests = []
    FakeOllama.reject_think = False
    FakeOllama.models = ["qwen3:4b"]
    FakeOllama.answer = {
        "summary": "Notice of the 10th AGM of Acme Widgets Limited on 30 September 2026, with special resolutions under s.185 and s.186.",
        "key_points": ["Loans up to Rs. 25 crore under s.185", "Rs. 100 crore over the s.186 limit"],
        "document_type": "notice",
        "tags": ["Group Loans", "agm"],
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def aagam(settings, url, model="qwen3:4b"):
    return AagamSettings(core=settings, local_ai_url=url, local_ai_model=model)


def test_status_says_what_is_missing(ollama):
    assert ai.LocalAI(ollama, "qwen3:4b").status()["message"] == "Ready."
    assert "ollama pull llama9" in ai.LocalAI(ollama, "llama9").status()["message"]
    assert ai.LocalAI("http://127.0.0.1:9", "qwen3:4b").status()["running"] is False


def test_the_queue_writes_summaries_and_suggestions(settings, ollama, tmp_path):
    with open_db(settings.db_path) as vault:
        notice = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"))
        scan = library.add_document(vault, settings, write_pdf(tmp_path / "scan.pdf", [""]))
    config = aagam(settings, ollama)
    assert ai.run_queue(config, ai.LocalAI.from_settings(config)) == 2
    with open_db(settings.db_path) as vault:
        doc = library.document(vault, notice["document_id"])
        jobs = {j["document_id"]: j for j in vault._rows("SELECT * FROM ai_jobs")}
    assert doc["summary"].startswith("Notice of the 10th AGM") and doc["summary_by"] == "local:qwen3:4b"
    assert doc["key_points"][1] == "Rs. 100 crore over the s.186 limit"
    assert doc["suggested_tags"] == ["group loans"]  # "agm" is already a tag; suggestions aren't applied
    assert jobs[notice["document_id"]]["status"] == "done"
    assert jobs[scan["document_id"]]["status"] == "skipped" and "Claude Desktop" in jobs[scan["document_id"]]["note"]
    request = FakeOllama.requests[0]
    assert request["format"] == ai.SUMMARY_SCHEMA and request["think"] is False and request["stream"] is False
    assert "--- page 2 ---" in request["messages"][1]["content"]


def test_a_model_without_thinking_is_asked_again(settings, ollama, tmp_path):
    FakeOllama.reject_think = True
    with open_db(settings.db_path) as vault:
        notice = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"))
    config = aagam(settings, ollama)
    ai.run_queue(config, ai.LocalAI.from_settings(config))
    with open_db(settings.db_path) as vault:
        assert library.document(vault, notice["document_id"])["summary_by"] == "local:qwen3:4b"
    assert "think" not in FakeOllama.requests[-1]


def test_failures_are_recorded_and_the_queue_moves_on(settings, ollama, tmp_path):
    FakeOllama.answer = {"summary": "", "key_points": [], "document_type": "notice", "tags": []}
    with open_db(settings.db_path) as vault:
        library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"))
    config = aagam(settings, ollama)
    assert ai.run_queue(config, ai.LocalAI.from_settings(config)) == 1
    with open_db(settings.db_path) as vault:
        job = vault._rows("SELECT status, note FROM ai_jobs")[0]
    assert job == {"status": "failed", "note": "Local AI returned an empty summary."}


def test_her_summary_is_kept(settings, ollama, tmp_path):
    with open_db(settings.db_path) as vault:
        notice = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"))
        library.save_summary(vault, notice["document_id"], "Mine.", "her")
    config = aagam(settings, ollama)
    ai.run_queue(config, ai.LocalAI.from_settings(config))
    with open_db(settings.db_path) as vault:
        assert library.document(vault, notice["document_id"])["summary"] == "Mine."
        assert vault._rows("SELECT status FROM ai_jobs")[0]["status"] == "failed"


def _real_ollama_model():
    model = os.environ.get("AAGAM_TEST_MODEL", "gemma3:1b")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            names = [m["name"] for m in json.load(response)["models"]]
    except OSError:
        return None
    return model if model in names else None


@pytest.mark.local_ai
@pytest.mark.skipif(_real_ollama_model() is None, reason="needs Ollama running with AAGAM_TEST_MODEL (default gemma3:1b)")
def test_with_the_real_local_model(settings, tmp_path):
    model = _real_ollama_model()
    with open_db(settings.db_path) as vault:
        notice = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"))
    config = aagam(settings, "http://127.0.0.1:11434", model)
    assert ai.run_queue(config, ai.LocalAI.from_settings(config)) == 1
    with open_db(settings.db_path) as vault:
        doc = library.document(vault, notice["document_id"])
    assert doc["summary"] and doc["summary_by"] == f"local:{model}", vault._rows("SELECT * FROM ai_jobs")
