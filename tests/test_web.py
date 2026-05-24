import io
import json
import time
import threading
import pytest
from pathlib import Path


@pytest.fixture
def client():
    from app.web import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_help_returns_200(client):
    resp = client.get("/help")
    assert resp.status_code == 200


def test_history_returns_200(client):
    resp = client.get("/history")
    assert resp.status_code == 200


def test_init_session(client):
    resp = client.post("/api/session/init")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "session_id" in data


def test_upload_no_file(client):
    resp = client.post("/api/session/test-id/upload-file")
    assert resp.status_code == 400


def test_upload_bad_extension(client):
    data = {"file": (io.BytesIO(b"not a pdf"), "test.txt")}
    resp = client.post(
        "/api/session/test-id/upload-file",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_process_empty_session(client):
    resp = client.post("/api/session/nonexistent/process")
    assert resp.status_code == 400


def test_results_not_found(client):
    resp = client.get("/results/nonexistent")
    assert resp.status_code == 302


def test_download_hidden_file_check(client):
    resp = client.get("/download/test/.hidden")
    assert resp.status_code == 400


def test_download_not_found(client):
    resp = client.get("/download/test/missing.csv")
    assert resp.status_code == 404


def test_cleanup(client):
    resp = client.post("/api/cleanup")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"


def test_process_progress_polling(client, monkeypatch):
    """Polling /process-progress during /process sees intermediate states."""
    from app.web import create_app

    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pdfs"
    fixture_pdf = list(FIXTURE_DIR.glob("buy_order_*.pdf"))[0]
    pdf_bytes = fixture_pdf.read_bytes()

    def slow_parse(pdf_paths, use_cache=True, progress_callback=None):
        for i in range(1, 4):
            if progress_callback:
                progress_callback(i, 3, f"file{i}.pdf")
            time.sleep(0.5)
        return {}, [], []
    monkeypatch.setattr("app.web.parse_documents", slow_parse)
    monkeypatch.setattr("app.web.compute_tax_data", lambda a: ([], [], {}, {}))
    monkeypatch.setattr("app.web.export_to_excel", lambda *a, **kw: None)

    init = client.post("/api/session/init")
    sid = init.get_json()["session_id"]

    client.post(
        f"/api/session/{sid}/upload-file",
        data={"file": (io.BytesIO(pdf_bytes), "buy_order_test.pdf")},
        content_type="multipart/form-data",
    )

    progress_states = []

    def poll():
        poll_app = create_app()
        with poll_app.test_client() as poll_client:
            for _ in range(15):
                r = poll_client.get(f"/api/session/{sid}/process-progress")
                progress_states.append(r.get_json())
                time.sleep(0.2)

    t = threading.Thread(target=poll, daemon=True)
    t.start()

    client.post(f"/api/session/{sid}/process")
    t.join()

    currents = [p.get("current", 0) for p in progress_states if p.get("phase") == "ocr"]
    assert any(c == 1 for c in currents), f"Never saw current=1 in {currents}"
    assert any(c == 2 for c in currents), f"Never saw current=2 in {currents}"
    assert any(c == 3 for c in currents), f"Never saw current=3 in {currents}"

