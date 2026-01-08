#!/bin/bash
##############################################
##                                          ##
##  Desktop Menu Launcher                   ##
##  Launches menu on Linux desktop          ##
##  Uses pygame with X11 display            ##
##                                          ##
##############################################

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if DISPLAY is set
if [ -z "$DISPLAY" ]; then
    echo "Error: No DISPLAY environment variable set."
    echo "This script requires X11 to run."
    echo "Make sure you're running this in a graphical environment."
    exit 1
fi

# Change to the script directory
cd "$SCRIPT_DIR" || exit 1

# Debug: Show environment info
echo "Starting Picorder on desktop..."
echo "DISPLAY=$DISPLAY"
echo "Working directory: $SCRIPT_DIR"

# Run the menu application
python3 "$SCRIPT_DIR/01_menu_run.py" 2>&1

# If we get here, the application exited
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Application exited with code: $EXIT_CODE"
    exit $EXIT_CODE
fi

