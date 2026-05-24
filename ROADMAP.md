# N26 Tax Calculator - Implementation Roadmap

## Phase 1: Foundation (CURRENT - In Progress)

### Completed ✅
- [x] Project structure refactoring
- [x] Config auto-setup (no manual files)
- [x] Custom error handling system
- [x] Logging infrastructure
- [x] Web routes and error handlers
- [x] Templates (upload, results, history, help)
- [x] JavaScript drag-drop file upload
- [x] Installation script (bash)
- [x] Documentation (README, contributing)
- [x] Asset/Transaction/Dividend data models (`core/models.py`)
- [x] PDF parsing wired to return real transaction/dividend data
- [x] FIFO cost basis tracking & capital gains computation
- [x] French tax declarations (2042, 2047, 2074 boxes)
- [x] Multi-sheet Excel export (Déclarations, Achats, Ventes, Dividendes, Actifs_Restants, Détails_2047)
- [x] Session cleanup on startup (30-day retention)
- [x] Unit tests (35 tests: parser, calculator, exporter, web)

### In Progress 🔄
- [ ] End-to-end testing (full upload → process → download flow)
- [x] macOS sandbox OCR issue (threaded=False — single-threaded server)

### Next 📋
- [ ] Fix any runtime issues discovered during real-PDF testing
- [ ] Merge to main branch

---

## Phase 2: Polish & Testing

- [ ] Fix any bugs from Phase 1
- [ ] Performance optimization (OCR is main bottleneck)
- [ ] Investigate multiprocessing for OCR — macOS sandbox blocks threaded XPC, but separate processes may work
- [ ] Better progress indication during processing (SSE or polling)
- [ ] Improve error messages based on user feedback
- [ ] Integration tests with sample PDF files
- [ ] macOS sandbox: investigate subprocess isolation or pre-warm OCR service

---

## Phase 3: Future Enhancements (Not in Scope)

- [ ] Multi-country tax support (UK, Germany, Spain, Italy)
- [ ] Alternative OCR providers (PaddleOCR, EasyOCR)
- [ ] Email export feature
- [ ] Browser caching of results
- [ ] Analytics (anonymous usage stats)
- [ ] Dark mode toggle

---

## Current Architecture

```
copilot-refactor (this branch)
├── app/               Web layer (Flask)
├── core/              Business logic
├── utils/             Shared utilities
├── run.py             Entry point
├── config.py          Settings
├── install.sh         Setup script
└── README.md          User documentation
```

**Key design decisions:**
- Single entry point (`run.py`)
- Auto-creating config (no manual setup)
- Web-first (no CLI complexity)
- Clean separation of concerns
- Simple, readable code over fancy features

---

## Testing Checklist

Before merging to main:

- [ ] Installation works on clean system (macOS)
- [ ] App starts without errors: `python run.py`
- [ ] Web UI loads at http://localhost:5000
- [ ] File upload form displays correctly
- [ ] Can select and upload PDF files
- [ ] Error messages are user-friendly
- [ ] Results page displays correctly
- [ ] Can download generated files
- [ ] Help page is clear and useful
- [ ] History page lists previous results
- [ ] No Python exceptions in logs

---

## Known Issues

- **`--debug` flag breaks OCR**: Werkzeug's `--debug` mode uses a stat
  reloader that spawns a child process via fork/exec.  macOS Vision's XPC
  service connection does not survive this boundary, so OCR returns 0
  annotations on real documents.  The pre-warm step (tiny 10×10 dummy
  image) succeeds, giving a false sense of health, but full-page OCR
  silently fails.  Always run without `--debug` when processing real data.
- **OCR returns 0 annotations on some sell_order PDFs**: The macOS Vision
  livetext framework sometimes returns empty on certain N26 PDF layouts.
  The file is then rejected with "Could not extract text". Added per-file
  annotation-count logging in `annotate_page()` so the operator can tell
  whether OCR produced nothing at all, or text that was filtered out by
  the y ≥ 0.10 threshold.
- **Single-threaded server (`threaded=False`)**: macOS Vision's livetext
  framework uses an XPC service that stalls or fails when called from
  background threads.  The Flask dev server therefore runs with
  `threaded=False`.  A consequence is that the `/process-progress` polling
  endpoint cannot serve during a `/process` request — the progress bar
  stays at "Processing..." until OCR finishes.  The Flask test_client()
  is immune because it calls app.wsgi_app inline, bypassing the threading
  layer.

---

## Questions?

See README.md or open a GitHub issue.
