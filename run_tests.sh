#!/bin/bash
# Run recording functionality tests

cd "$(dirname "$0")"

echo "Running recording functionality tests..."
echo ""

python3 tests/test_recording_functionality.py -v

echo ""
echo "Tests complete!"

