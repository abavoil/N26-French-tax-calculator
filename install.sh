#!/bin/bash
set -e

echo "🚀 Installing N26 Tax Calculator..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

echo "Syncing environment and dependencies..."
uv sync

echo "✓ Environment ready"

echo ""
echo "════════════════════════════════════════"
echo "✅ Installation complete!"
echo "════════════════════════════════════════"
echo ""
echo "To start the app:"
echo "  uv run python run.py"
echo ""
echo "Then open: http://localhost:5000"
echo ""
