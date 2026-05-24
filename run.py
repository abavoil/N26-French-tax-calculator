#!/usr/bin/env python3
"""
N26 Tax Calculator - Single entry point

Usage:
    python run.py              # Starts web server on http://localhost:5000
    python run.py --help       # Show help
    python run.py --version    # Show version
"""

import sys
import argparse
from pathlib import Path

from app.web import create_app


def main():
    parser = argparse.ArgumentParser(
        description="N26 French Tax Report Generator",
        epilog="Visit http://localhost:5000 in your browser after starting.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run on (default: 5000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (auto-reload on file changes). "
             "WARNING: --debug uses a process reloader that degrades the "
             "macOS Vision XPC connection (same root cause as threaded=False). "
             "Avoid when processing real documents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="n26-tax-calculator 1.0.0",
    )

    args = parser.parse_args()

    print("""
    ╔════════════════════════════════════════╗
    ║  N26 Tax Calculator                    ║
    ║  Starting web server...                ║
    ╚════════════════════════════════════════╝
    """)
    print(f"🌐 Open browser: http://{args.host}:{args.port}")
    print(f"📁 Uploads saved to: {Path.home() / '.n26-tax-calc' / 'uploads'}")
    print("🛑 Press Ctrl+C to stop\n")

    app = create_app()

    # Single-threaded mode: macOS Vision's livetext framework uses an XPC
    # service that stalls or fails when called from background threads.
    # The /process-progress polling endpoint cannot serve concurrently, so
    # the progress bar will stay at "Processing..." until OCR completes.
    # See ROADMAP.md "Known Issues" for details.
    #
    # The --debug flag has the same effect: Werkzeug's stat-reloader spawns
    # a subprocess via fork/exec, and the XPC connection does not survive
    # the exec boundary. OCR will likely fail on real documents even though
    # the pre-warm step (tiny 10x10 dummy image) reports success.
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=False,
    )


if __name__ == "__main__":
    main()