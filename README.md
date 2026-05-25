# N26 Tax Calculator

Simple web app to generate French tax reports from N26 investment statements.

## Quick Start

### Requirements
- Python 3.11 or later
- macOS only (requires Apple Vision OCR framework; Windows is not supported)

### Installation

**macOS (only):**
```bash
git clone https://github.com/abavoil/n26-tax-calculator
cd n26-tax-calculator
brew install uv  # Python package manager
```

### Start the App

```bash
uv run python run.py
```

Then open your browser to: **http://localhost:5000**

## Usage

1. **Download documents from N26**
   - Mobile app → Profile → Support Center → Messages
   - Look for: `buy_order_*.pdf`, `sell_order_*.pdf`, `income_distribution_*.pdf`
   - a sample can be found in `tests/fixtures/pdfs/`

2. **Upload to the web app**
   - Drag-and-drop files or click to browse (Select all files at once)
   - Click "Analyze Documents"

3. **Download tax report**
   - `tax_report.xlsx` - Ready for filing (forms 2042, 2047, 2074)
   - `transactions.csv` - Detailed audit trail

## Output Files

- **tax_report.xlsx** - Excel workbook with:
  - Tax form declarations (2042, 2047, 2074)
  - Transaction breakdown
  - Capital gains/losses summary
  - Dividend income by country

- **transactions.csv** - Detailed log for verification

## ❓ Troubleshooting

See the **Help** page in the app or visit `/help` for detailed troubleshooting.

### Common Issues

**"OCR Failed"** - PDF might be corrupted. Try re-downloading from N26.

**"Data Not Found"** - Document might be unusual format. Verify it's a standard N26 statement.

**"No Valid Documents Found"** - Files must be named: `buy_order_`, `sell_order_`, or `income_distribution_`

## Privacy

- Your files are processed locally on your computer
- Nothing is uploaded to external servers
- All data is stored in `~/.n26-tax-calc/` only
- No tracking or analytics

## Before Filing

⚠️ **Always verify** the report matches your N26 annual tax statement before filing your taxes.

- Check all transaction dates and amounts
- Verify dividend amounts by country
- Consult with a tax advisor if unsure

## License

Apache 2.0 - See LICENSE file

## Contributing

Bug reports and suggestions welcome! Open an issue on GitHub.
