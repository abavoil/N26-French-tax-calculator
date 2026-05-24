# Refactored N26 Tax Calculator - Copilot Branch

This branch contains the refactored version with:

✅ Better web interface (drag-drop, results display)  
✅ Easier setup (single command to install)  
✅ Better error messages (user-friendly)  
✅ Cleaner code structure (separated concerns)  

## What's New

### Project Structure
```
app/              - Flask web application
core/             - Business logic (no web dependencies)
utils/            - Utility modules (errors, logging)
run.py            - Single entry point
config.py         - Auto-configuration
```

### Key Improvements

1. **Single Entry Point** (`run.py`)
   - No more separate `main.py` and `app.py`
   - Simple command: `python run.py`

2. **Auto Config**
   - No manual `config.py` creation
   - Directories auto-created on first run
   - Settings at `~/.n26-tax-calc/`

3. **Better UI**
   - Drag-drop file upload
   - Progress indicator
   - Clear results page
   - File download management

4. **Error Handling**
   - User-friendly messages
   - Actionable suggestions
   - No cryptic Python exceptions

5. **Logging**
   - Organized logging module
   - File and console output
   - Rotating file handler

## Getting Started

```bash
bash install.sh        # macOS/Linux
install.bat            # Windows

python run.py          # Start the app
```

Then visit: http://localhost:5000

## Current Status

- ✅ Project structure initialized
- ✅ Web routes and templates created
- ✅ Error handling system in place
- ✅ File upload interface working
- ⚠️ PDF parsing needs data model implementation
- ⚠️ Tax calculations need completion
- ⚠️ Excel export needs data wiring

## Next Steps

1. Implement Asset/Transaction/Dividend data classes
2. Complete PDF field extraction
3. Implement tax calculations (capital gains, dividends)
4. Wire Excel export with actual data
5. Add session cleanup (delete old results)
6. Test end-to-end workflow

## Notes

This is a work in progress. The structure is solid, but core business logic still needs implementation.
