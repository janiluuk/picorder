#!/bin/bash
##############################################
##                                          ##
##  Menu                                    ##
##  Launches menu                           ##
##  Best autostarted through ~/.profile     ##
##                                          ##
##############################################

# Note: logout only works in login shells, so we skip it if not in a login shell
# The menu will run regardless
sudo /usr/bin/env python3 /home/pi/picorder/01_menu_run.py
