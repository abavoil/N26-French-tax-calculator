import io
import json
import pytest
from pathlib import Path


def _parse_sse_events(text):
    """Parse SSE-formatted text into a list of {type, data} dicts."""
    events = []
    for block in text.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        evt_type = 'message'
        data_str = ''
        for line in lines:
            if line.startswith('event: '):
                evt_type = line[7:]
            elif line.startswith('data: '):
                data_str = line[6:]
        if data_str:
            events.append({"type": evt_type, "data": json.loads(data_str)})
    return events


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


def test_process_streaming_progress(client, monkeypatch):
    """/process yields SSE progress events via streaming."""
    def streaming_parse(pdf_paths, use_cache=True):
        for i in range(1, 4):
            yield ("progress", {"current": i, "total": 3, "file": f"file{i}.pdf"})
        yield ("result", {"assets": {}, "transactions": {}, "dividends": {}, "failed_files": []})
    monkeypatch.setattr("app.web.parse_documents_streaming", streaming_parse)
    monkeypatch.setattr("app.web.compute_tax_data", lambda a: ([], [], {}, {}))
    monkeypatch.setattr("app.web.export_to_excel", lambda *a, **kw: None)

    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pdfs"
    fixture_pdf = list(FIXTURE_DIR.glob("buy_order_*.pdf"))[0]
    pdf_bytes = fixture_pdf.read_bytes()

    init = client.post("/api/session/init")
    sid = init.get_json()["session_id"]

    client.post(
        f"/api/session/{sid}/upload-file",
        data={"file": (io.BytesIO(pdf_bytes), "buy_order_test.pdf")},
        content_type="multipart/form-data",
    )

    resp = client.post(f"/api/session/{sid}/process")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")

    events = _parse_sse_events(resp.data.decode())

    progress_events = [e for e in events if e["type"] == "progress"]
    assert len(progress_events) == 3
    assert progress_events[0]["data"]["current"] == 1
    assert progress_events[1]["data"]["current"] == 2
    assert progress_events[2]["data"]["current"] == 3

    complete_events = [e for e in events if e["type"] == "complete"]
    assert len(complete_events) == 1
    assert "session_id" in complete_events[0]["data"]
    assert "results_url" in complete_events[0]["data"]


def test_process_bad_pdf_file_error(client):
    """Uploading an unreadable PDF yields file_error and complete with failed_files."""
    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pdfs"
    black_pdf = FIXTURE_DIR / "black.pdf"
    assert black_pdf.exists(), "black.pdf fixture missing"
    pdf_bytes = black_pdf.read_bytes()

    init = client.post("/api/session/init")
    sid = init.get_json()["session_id"]

    client.post(
        f"/api/session/{sid}/upload-file",
        data={"file": (io.BytesIO(pdf_bytes), "black.pdf")},
        content_type="multipart/form-data",
    )

    resp = client.post(f"/api/session/{sid}/process")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")

    events = _parse_sse_events(resp.data.decode())

    file_error_events = [e for e in events if e["type"] == "file_error"]
    assert len(file_error_events) >= 1, f"No file_error events in {[e['type'] for e in events]}"
    black_errors = [e for e in file_error_events if "black.pdf" in e["data"]["file"]]
    assert len(black_errors) >= 1, f"black.pdf not in file_error events: {file_error_events}"

    complete_events = [e for e in events if e["type"] == "complete"]
    assert len(complete_events) == 1
    failed = complete_events[0]["data"].get("failed_files", [])
    assert any("black.pdf" in f.get("file", "") for f in failed), (
        f"black.pdf not in complete.failed_files: {failed}"
    )
    assert "results_url" in complete_events[0]["data"]

