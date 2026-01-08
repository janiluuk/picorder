#!/usr/bin/env python3
from menu_settings import *

################################################################################
def _1():
    """Button 1 handler - stats display buttons have no actions (display only)"""
    pass

def _2():
    """Button 2 handler - stats display buttons have no actions (display only)"""
    pass

def _3():
    """Button 3 handler - stats display buttons have no actions (display only)"""
    pass

def _4():
    """Button 4 handler - stats display buttons have no actions (display only)"""
    pass

def _5():
    # next page
    go_to_page(PAGE_03)
def _6():
    # Refresh
    pygame.quit()
    os.execv(__file__, sys.argv)
################################################################################

temp, clock, volts = get_temp(), get_clock(), get_volts()
names = [temp, clock, "", volts, "", "<<<", "Refresh"]

screen = init()
populate_screen(names, screen, label2=True, label3=True, b12=False, b34=False)
main([_1, _2, _3, _4, _5, _6])
