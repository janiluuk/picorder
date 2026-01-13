#!/usr/bin/env python3
"""
Screen Off Mode - Power saving mode for Raspberry Pi
Turns off the backlight to save power (Raspberry Pi only)
"""
import RPi.GPIO as GPIO
from menu_settings import *

init(draw=False)
# Initialise GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)

#While loop to manage touch screen inputs
screen_off()
main()
