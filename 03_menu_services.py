#!/usr/bin/env python3
from sys import argv as __argv__
from menu_settings import *

################################################################################
def _1():
    # Apache
    # Transmission
    c = toggle_service(services[0])
    make_button(names[1], button_pos_1, c, screen)
def _2():
    """Button 2 handler - currently unused (no service configured)"""
    pass

def _3():
    """Button 3 handler - currently unused (no service configured)"""
    pass

def _4():
    """Button 4 handler - currently unused (no service configured)"""
    pass
def _5():
    # Previous page
    go_to_page(PAGE_02)
def _6():
    # Next page
    go_to_page(PAGE_04)
################################################################################

date = get_date()
# Services menu - currently only Transmission is configured
names = [date, "Transmission", "", "", "", "<<<", ">>>"]
services = ["transmission-daemon", "", "", "", "", ""]

screen = init()
populate_screen(names, screen, service=services, b34=False)
main([_1, _2, _3, _4, _5, _6])
