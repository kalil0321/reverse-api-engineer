#!/bin/bash
# Clean build script - removes all build artifacts and caches before building

set -e  # Exit on error

echo "🧹 Cleaning build artifacts..."

# Remove Python cache files
echo "  → Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove build directories
echo "  → Removing build directories..."
rm -rf dist/ build/ *.egg-info src/*.egg-info 2>/dev/null || true

# Remove any .pyc files in src
echo "  → Removing compiled Python files in src/..."
find src -type f -name "*.pyc" -delete 2>/dev/null || true

echo "✅ Clean complete!"
echo ""
echo "🏗️  Building package..."
uv build

echo ""
echo "✅ Build complete!"
echo ""
echo "📦 Built files:"
ls -lh dist/
