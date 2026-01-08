#!/bin/bash
##############################################
##                                          ##
##  Menu                                    ##
##  Launches menu                           ##
##  Best autostarted through ~/.profile     ##
##                                          ##
##############################################

# Check if display is available (required for pygame)
if [ ! -e /dev/fb1 ] && [ -z "$DISPLAY" ]; then
    echo "Error: No display available. This menu requires a physical display."
    echo "The menu must be run on the Raspberry Pi with the TFT display connected."
    echo "Cannot run over SSH without X11 forwarding or a physical display."
    exit 1
fi

# Check if running over SSH
if [ -n "$SSH_CONNECTION" ] && [ -z "$DISPLAY" ] && [ ! -e /dev/fb1 ]; then
    echo "Warning: Running over SSH without display. The menu requires a physical display."
    echo "The menu should be run locally on the Raspberry Pi."
    exit 1
fi

# Note: logout only works in login shells, so we skip it if not in a login shell
# The menu will run regardless
sudo /usr/bin/env python3 /home/pi/picorder/01_menu_run.py 2>&1
