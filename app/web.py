"""
Flask web application.
"""

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import logging
import uuid
import json
from datetime import datetime
import zipfile
import io
import os

from core.parser import parse_documents
from core.calculator import compute_tax_data
from core.exporter import export_to_excel
from utils.errors import TaxCalcError
from utils.logger import setup_logging
from config import OUTPUT_DIR, LOG_FILE, LOG_LEVEL

logger = logging.getLogger(__name__)


def _cleanup_old_sessions():
    """Remove session outputs older than OUTPUT_RETENTION_DAYS."""
    from config import OUTPUT_DIR, OUTPUT_RETENTION_DAYS
    import shutil
    from datetime import timedelta

    now = datetime.now()
    cutoff = now - timedelta(days=OUTPUT_RETENTION_DAYS)
    removed = 0
    if OUTPUT_DIR.exists():
        for item in OUTPUT_DIR.iterdir():
            if item.is_dir():
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    if mtime < cutoff:
                        shutil.rmtree(item)
                        removed += 1
                except Exception:
                    pass
    if removed:
        logger.info(f"Cleaned up {removed} expired session(s) older than {OUTPUT_RETENTION_DAYS} days")


def _prewarm_ocr():
    """Run a dummy OCR call to initialize the Apple Vision XPC service connection."""
    try:
        from PIL import Image
        from ocrmac import ocrmac
        dummy = Image.new("RGB", (10, 10), color="black")
        ocrmac.OCR(dummy, framework="livetext").recognize()
        logger.info("OCR Vision framework pre-warmed successfully")
    except Exception as e:
        logger.debug(f"OCR pre-warm skipped (non-macOS or Vision unavailable): {e}")


def create_app():
    """
    Create and configure Flask app.
    """
    from config import LOG_FILE, LOG_LEVEL
    setup_logging(LOG_FILE, LOG_LEVEL)

    from config import ensure_dirs
    ensure_dirs()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )
    app.secret_key = 'dev-key-change-in-production'
    
    # Session cleanup on startup: delete outputs older than retention period
    _cleanup_old_sessions()
    
    # Pre-warm the macOS Vision framework for OCR to avoid sandbox issues
    # with XPC service connections when called from background threads.
    _prewarm_ocr()
    
    # Error handlers
    @app.errorhandler(TaxCalcError)
    def handle_calc_error(error):
        """Handle tax calculator errors gracefully, showing stack traces in debug mode."""
        if app.debug:
            logger.exception(f"TaxCalcError raised: {error.title} - {error.message}")
        else:
            logger.warning(f"{error.title}: {error.message}")
            
        if request.is_json or request.path.startswith('/api/'):
            return jsonify(error.to_dict()), 400
        else:
            flash(f"❌ {error.title}: {error.message}", category="error")
            flash(f"💡 {error.suggestion}", category="warning")
            return redirect(url_for('index'))
    
    @app.errorhandler(Exception)
    def handle_error(error):
        """Handle unexpected errors."""
        logger.exception("Unexpected error")
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                "title": "Unexpected Error",
                "message": "Something went wrong. Please try again.",
                "suggestion": "If this persists, check the logs or contact support.",
            }), 500
        else:
            flash("❌ An unexpected error occurred. Please try again.", category="error")
            return redirect(url_for('index')), 500
    
    # Routes
    @app.route('/')
    def index():
        """Home page with upload form."""
        return render_template('index.html')
    
    @app.route('/help')
    def help_page():
        """Help and documentation page."""
        return render_template('help.html')
    
    @app.route('/history')
    def history():
        """List previous processing results."""
        results = []
        for result_dir in sorted(OUTPUT_DIR.glob('*'), reverse=True)[:10]:
            meta_file = result_dir / 'meta.json'
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        meta = json.load(f)
                    results.append(meta)
                except Exception as e:
                    logger.warning(f"Could not load meta from {result_dir}: {e}")
        return render_template('history.html', results=results)
    
    @app.route('/api/session/init', methods=['POST'])
    def init_session():
        """Initialize a new processing session and return the session_id."""
        session_id = str(uuid.uuid4())
        session_dir = OUTPUT_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / 'upload_temp').mkdir(exist_ok=True)
        
        logger.info(f"Initialized session: {session_id}")
        return jsonify({"status": "success", "session_id": session_id})

    @app.route('/api/session/<session_id>/upload-file', methods=['POST'])
    def upload_single_file(session_id):
        """Upload and parse a single file, validating it instantly."""
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['file']
        if not file or not file.filename.endswith('.pdf'):
            return jsonify({"error": f"Invalid file format: {file.filename}"}), 400

        session_dir = OUTPUT_DIR / session_id
        upload_temp_dir = session_dir / 'upload_temp'
        
        # Save the file
        filepath = upload_temp_dir / file.filename
        file.save(filepath)

        try:
            # Lightweight validation: check the PDF is openable (no OCR yet)
            import pymupdf
            doc = pymupdf.open(filepath)
            page_count = len(doc)
            doc.close()
            if page_count == 0:
                raise TaxCalcError("Empty PDF", f"PDF '{file.filename}' has no pages", "Check the file is not corrupted.")
            logger.info(f"Session {session_id}: Successfully validated {file.filename}")
            return jsonify({"status": "success", "filename": file.filename})
        except TaxCalcError as e:
            if filepath.exists():
                filepath.unlink()
            return jsonify(e.to_dict()), 400
        except Exception as e:
            if filepath.exists():
                filepath.unlink()
            logger.exception(f"Unexpected parser failure on {file.filename}")
            return jsonify({"error": f"Failed to parse {file.filename}: {e}"}), 500

    @app.route('/api/session/<session_id>/process-progress')
    def get_process_progress(session_id):
        """Poll progress of an active process session."""
        from config import OUTPUT_DIR
        prog = OUTPUT_DIR / session_id / "progress.json"
        if prog.exists():
            try:
                return jsonify(json.loads(prog.read_text()))
            except Exception:
                pass
        return jsonify({"phase": "waiting", "current": 0, "total": 0, "file": ""})

    @app.route('/api/session/<session_id>/process', methods=['POST'])
    def process_session(session_id):
        """Run calculations, generate the Excel sheet, and finalize the session."""
        session_dir = OUTPUT_DIR / session_id
        upload_temp_dir = session_dir / 'upload_temp'
        
        pdf_paths = list(upload_temp_dir.glob('*.pdf'))
        if not pdf_paths:
            return jsonify({"error": "No files found to process"}), 400

        def _write_progress(phase, current=0, total=0, file=""):
            try:
                tmp = session_dir / ".progress.tmp"
                tmp.write_text(json.dumps({
                    "phase": phase, "current": current, "total": total, "file": file
                }))
                tmp.rename(session_dir / "progress.json")
            except Exception:
                pass

        def _ocr_progress(current, total, filename):
            _write_progress("ocr", current, total, filename)

        try:
            logger.info(f"Session {session_id}: Computing tax returns for {len(pdf_paths)} documents")
            _write_progress("ocr", 0, len(pdf_paths), "")
            
            # 1. Parse all valid documents together to build the full dataset
            assets, transactions, dividends = parse_documents(pdf_paths, progress_callback=_ocr_progress)
            
            # 2. Compute taxes
            _write_progress("calc", 0, 0, "")
            audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)
            
            # 3. Export one Excel per year
            excel_files = []
            for dash in dashboards:
                year = dash.year
                positions = positions_by_year.get(year, {})
                year_events_list = events_by_year.get(year, [])
                fname = f'tax_report_{year}.xlsx'
                export_to_excel(assets, session_dir / fname, dashboards, audit_rows, positions, year_events_list, year)
                excel_files.append(fname)
            
            # 4. Save audit trail CSV
            csv_path = session_dir / 'transactions.csv'
            if audit_rows:
                import csv
                with open(csv_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=audit_rows[0].keys())
                    writer.writeheader()
                    writer.writerows(audit_rows)
            
            # 5. Build per-year data for meta.json
            years_data = []
            for dash in dashboards:
                positions_list = []
                for isin, pos in (positions_by_year.get(dash.year, {}) or {}).items():
                    if hasattr(pos, "total_quantity") and pos.total_quantity > 0:
                        asset = assets.get(isin)
                        positions_list.append({
                            "ticker": asset.ticker if asset else "",
                            "isin": isin,
                            "quantity": float(round(pos.total_quantity, 2)),
                            "total_cost": float(round(pos.total_cost, 2)),
                        })
                years_data.append({
                    "year": dash.year,
                    "declarations": [
                        {"form": d.form, "box": d.box, "description": d.description, "value": d.value}
                        for d in dash.declarations
                    ],
                    "form_2047_details": dash.form_2047_details,
                    "positions": sorted(positions_list, key=lambda x: x["ticker"]),
                })
            
            latest_year = years_data[-1]["year"] if years_data else datetime.now().year
            
            meta = {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
                "transaction_count": len(transactions),
                "dividend_count": len(dividends),
                "asset_count": len(assets),
                "latest_year": latest_year,
                "years": years_data,
                "excel_files": excel_files,
            }
            with open(session_dir / 'meta.json', 'w') as f:
                json.dump(meta, f, indent=2)
                
            _write_progress("done", 0, 0, "")
            return jsonify({"status": "success", "session_id": session_id})
            
        except TaxCalcError as e:
            return jsonify(e.to_dict()), 400
        except Exception as e:
            logger.exception(f"Processing failed for session {session_id}")
            return jsonify({"error": f"Tax compilation failed: {e}"}), 500

    @app.route('/api/session/<session_id>/exists')
    def session_exists(session_id):
        """Check if a session's meta.json exists."""
        from config import OUTPUT_DIR
        meta_file = OUTPUT_DIR / session_id / 'meta.json'
        return jsonify({"exists": meta_file.exists()})

    @app.route('/api/cleanup', methods=['POST'])
    def cleanup_environment():
        """Clean all temporary directories, processed session outputs, and OCR cache."""
        import shutil
        from config import OCR_CACHE_FILE, UPLOAD_DIR
        
        cleaned_items = []
        errors = []

        # 1. Clear OCR Cache file
        if OCR_CACHE_FILE.exists():
            try:
                OCR_CACHE_FILE.unlink()
                cleaned_items.append("OCR Cache File")
            except Exception as e:
                errors.append(f"Cache file: {e}")

        # 2. Clear Session Outputs Directory
        if OUTPUT_DIR.exists():
            for item in OUTPUT_DIR.glob('*'):
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    errors.append(f"Output directory item '{item.name}': {e}")
            cleaned_items.append("Session Outputs")

        # 3. Clear Temporary Uploads Directory
        if UPLOAD_DIR.exists():
            for item in UPLOAD_DIR.glob('*'):
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    errors.append(f"Upload directory item '{item.name}': {e}")
            cleaned_items.append("Temporary Uploads")

        if errors:
            logger.warning(f"Cleanup finished with partial errors: {errors}")
            return jsonify({
                "status": "partial_success",
                "message": "Some directories could not be fully cleared.",
                "details": errors
            }), 207

        logger.info("System cleanup executed: Environment reset successfully.")
        return jsonify({
            "status": "success",
            "message": f"Successfully cleared: {', '.join(cleaned_items)}"
        })
    
    @app.route('/results/<session_id>')
    def results(session_id):
        """Display processing results."""
        session_dir = OUTPUT_DIR / session_id
        meta_file = session_dir / 'meta.json'
        
        if not meta_file.exists():
            flash("❌ Results not found", category="error")
            return redirect(url_for('index'))
        
        try:
            with open(meta_file) as f:
                summary = json.load(f)
            
            # Load transactions for display
            transactions = []
            csv_path = session_dir / 'transactions.csv'
            if csv_path.exists():
                import csv
                with open(csv_path) as f:
                    reader = csv.DictReader(f)
                    transactions = list(reader)
            
            return render_template(
                'results.html',
                session_id=session_id,
                summary=summary,
                transactions=transactions,
                years=summary.get("years", []),
                latest_year=summary.get("latest_year"),
                excel_files=summary.get("excel_files", []),
                generated_at=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error loading results for {session_id}: {e}")
            flash("❌ Could not load results", category="error")
            return redirect(url_for('index'))
    
    @app.route('/download/<session_id>/<filename>')
    def download(session_id, filename):
        """Download a result file."""
        # Validate filename to prevent directory traversal
        if '/' in filename or filename.startswith('.'):
            return "Invalid filename", 400
        
        filepath = OUTPUT_DIR / session_id / filename
        if not filepath.exists():
            return "File not found", 404
        
        logger.info(f"Downloading: {filepath}")
        return send_file(filepath, as_attachment=True)
    
    @app.route('/download-all/<session_id>', methods=['POST'])
    def download_all(session_id):
        """Download all files as ZIP."""
        session_dir = OUTPUT_DIR / session_id
        if not session_dir.exists():
            return "Session not found", 404
        
        # Create ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in session_dir.glob('*'):
                if file.is_file() and not file.name.startswith('.'):
                    zipf.write(file, arcname=file.name)
        
        zip_buffer.seek(0)
        logger.info(f"Downloading all files for session {session_id}")
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'n26_tax_report_{session_id[:8]}.zip'
        )
    
    return app
