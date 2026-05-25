# N26 Tax Calculator

Simple web app to generate French tax reports from N26 investment statements. Everything runs locally on your machine — no data is uploaded anywhere (only ISINs are sent to Yahoo Finance to resolve ticker names).

## Quick Start

### Requirements
- Python 3.14 or later
- macOS only (requires Apple Vision OCR framework; Windows is not supported)
- See the [Help page](http://localhost:5000/help) for detailed usage instructions

### Installation & Run

```bash
git clone https://github.com/abavoil/n26-tax-calculator
cd n26-tax-calculator
brew install uv
uv run run.py
```

Then open **http://localhost:5000**

Additional options: `--port`, `--host`, `--debug` (see `uv run run.py --help`).

## Usage

1. **Download PDFs from N26**
   - Mobile app → Profile → Support Center → Messages
   - Look for: `buy_order_*.pdf`, `sell_order_*.pdf`, `income_distribution_*.pdf`
   - Samples in `tests/fixtures/pdfs/`

2. **Upload to the web app**
   - Drag-and-drop or click to browse (select all at once)
   - Click "Analyze Documents"

3. **Download tax report**
   - **ZIP archive** containing all result files for the session
   - **Per-year Excel workbooks** (`tax_report_2025.xlsx`, etc.) — ready for filing (forms 2042, 2047, 2074)
   - **`transactions.csv`** — detailed audit trail of every operation

## Output Files

The ZIP download includes:

- **`tax_report_YYYY.xlsx`** (one per tax year) — Excel workbook with:
  - Declarations sheet (tax form boxes for 2042, 2047, 2074)
  - Capital gains/losses summary
  - Dividend income by country
  - Remaining positions (open positions carried to next year)
  - Full transaction breakdown (buys, sells, dividends)

- **`transactions.csv`** — detailed log of every operation: date, type, asset, quantity, price, fees, PMP, gain/loss. Use this to cross-check against your N26 annual statement.

- **`meta.json`** — session metadata (file count, tax years covered)

## Privacy

- **Your files are processed entirely on your computer.**
- PDFs are never uploaded to any external server.
- ISINs are sent to Yahoo Finance to resolve ticker names — no other data leaves your machine.
- All data stored under `~/.n26-tax-calc/` — easily removable.
- No tracking, no analytics.

## Technical Details

### Configuration

The app stores data in `~/.n26-tax-calc/` by default (override with `N26_APP_DIR` env var). Key locations:

| Path | Purpose |
|---|---|
| `~/.n26-tax-calc/uploads/` | Temporary uploads during processing |
| `~/.n26-tax-calc/output/` | Processed results (sessions, auto-cleaned after 7 days) |
| `~/.n26-tax-calc/app.log` | Application log (rotates at 10 MB) |

### ISIN → Ticker Resolution

When processing buy/sell orders, the app extracts ISIN codes and resolves them to ticker symbols via the Yahoo Finance API. Results are cached locally so repeated processing of the same ISINs requires no network calls.

### Threading Note

The app runs in single-threaded mode due to a limitation of macOS's Vision framework (`ocrmac` uses XPC services that stall on background threads). Debug mode (`--debug`) has the same issue — avoid when processing real documents.

## Troubleshooting

See the **Help** page in the app (`/help`) for detailed troubleshooting.

### Common Issues

**"OCR Failed"** — PDF might be corrupted. Try re-downloading from N26.

**"Data Not Found"** — Unusual document format. Verify it's a standard N26 statement.

**"No Valid Documents Found"** — Files must be named: `buy_order_`, `sell_order_`, or `income_distribution_`.

## License

Apache 2.0 — See LICENSE file

## Contributing

Bug reports and suggestions welcome! Open an issue on GitHub.
