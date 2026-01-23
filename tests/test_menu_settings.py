#!/usr/bin/env python3
"""
Basic unit tests for menu_settings module.
Tests functions that don't require hardware (GPIO, display, etc.)
"""
import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
import os

# Mock pygame before importing menu_settings to avoid initialization issues
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['pygame.font'] = MagicMock()
sys.modules['pygame.display'] = MagicMock()
sys.modules['pygame.mouse'] = MagicMock()
sys.modules['pygame.draw'] = MagicMock()

# Add the current directory to the path so we can import menu_settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import menu_settings
from ui import nav, theme


class TestMenuSettings(unittest.TestCase):
    """Test cases for menu_settings module"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def test_get_date(self):
        """Test get_date returns a formatted date string"""
        date = menu_settings.get_date()
        self.assertIsInstance(date, str)
        self.assertGreater(len(date), 0)
        # Should contain day, date, and time components
        self.assertIn(":", date)  # Should have time

    @patch('menu_settings.run_cmd')
    def test_get_hostname(self, mock_run_cmd):
        """Test get_hostname returns formatted hostname"""
        mock_run_cmd.return_value = "test-hostname\n"
        hostname = menu_settings.get_hostname()
        self.assertIsInstance(hostname, str)
        self.assertTrue(hostname.startswith("  "))
        self.assertEqual(hostname, "  test-hostname")

    @patch('socket.socket')
    def test_get_ip_connected(self, mock_socket):
        """Test get_ip when connected"""
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ('192.168.1.100', 0)
        mock_socket.return_value = mock_sock
        
        ip = menu_settings.get_ip()
        self.assertIsInstance(ip, str)
        self.assertIn("IP:", ip)
        self.assertIn("192.168.1.100", ip)

    @patch('socket.socket')
    def test_get_ip_not_connected(self, mock_socket):
        """Test get_ip when not connected"""
        mock_socket.side_effect = Exception("Connection failed")
        
        ip = menu_settings.get_ip()
        self.assertEqual(ip, "Not connected")

    @patch('menu_settings.run_cmd')
    def test_get_temp(self, mock_run_cmd):
        """Test get_temp returns formatted temperature"""
        mock_run_cmd.return_value = "temp=45.6'C\n"
        temp = menu_settings.get_temp()
        self.assertIsInstance(temp, str)
        self.assertTrue(temp.startswith("Temp:"))
        self.assertIn("45.6", temp)

    @patch('menu_settings.run_cmd')
    def test_get_clock(self, mock_run_cmd):
        """Test get_clock returns formatted clock speed"""
        mock_run_cmd.return_value = "frequency(48)=1500000000\n"
        clock = menu_settings.get_clock()
        self.assertIsInstance(clock, str)
        self.assertTrue(clock.startswith("Clock:"))
        self.assertIn("MHz", clock)

    @patch('menu_settings.run_cmd')
    def test_get_volts(self, mock_run_cmd):
        """Test get_volts returns formatted voltage"""
        mock_run_cmd.return_value = "volt=1.20V\n"
        volts = menu_settings.get_volts()
        self.assertIsInstance(volts, str)
        self.assertTrue(volts.startswith("Core:"))
        self.assertIn("1.20", volts)

    def test_check_service_empty(self):
        """Test check_service with empty service name"""
        result = menu_settings.check_service("")
        self.assertFalse(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_vnc_running(self, mock_run_cmd):
        """Test check_service for VNC when running"""
        mock_run_cmd.return_value = "pi 1234 vnc :1"
        result = menu_settings.check_service("vnc")
        self.assertTrue(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_vnc_not_running(self, mock_run_cmd):
        """Test check_service for VNC when not running"""
        mock_run_cmd.return_value = "pi 1234 other process"
        result = menu_settings.check_service("vnc")
        self.assertFalse(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_running(self, mock_run_cmd):
        """Test check_service for regular service when running"""
        mock_run_cmd.return_value = "service is running"
        result = menu_settings.check_service("apache2")
        self.assertTrue(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_active_running(self, mock_run_cmd):
        """Test check_service for systemd service when active"""
        mock_run_cmd.return_value = "active (running)"
        result = menu_settings.check_service("apache2")
        self.assertTrue(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_not_running(self, mock_run_cmd):
        """Test check_service for service when not running"""
        mock_run_cmd.return_value = "service is stopped"
        result = menu_settings.check_service("apache2")
        self.assertFalse(result)

    @patch('menu_settings.run_cmd')
    def test_check_service_exception(self, mock_run_cmd):
        """Test check_service handles exceptions"""
        mock_run_cmd.side_effect = Exception("Command failed")
        result = menu_settings.check_service("apache2")
        self.assertFalse(result)

    @patch('menu_settings.check_service')
    def test_s2c_service_running(self, mock_check):
        """Test s2c returns green when service is running"""
        mock_check.return_value = True
        color = menu_settings.s2c("apache2")
        self.assertEqual(color, menu_settings.green)

    @patch('menu_settings.check_service')
    def test_s2c_service_stopped(self, mock_check):
        """Test s2c returns tron_light when service is stopped"""
        mock_check.return_value = False
        color = menu_settings.s2c("apache2")
        self.assertEqual(color, menu_settings.tron_light)

    def test_button_routing(self):
        """Test button function routes to correct handler"""
        call_order = []
        
        def handler1():
            call_order.append(1)
        def handler2():
            call_order.append(2)
        def handler3():
            call_order.append(3)
        def handler4():
            call_order.append(4)
        def handler5():
            call_order.append(5)
        def handler6():
            call_order.append(6)
        
        menu_settings.button(1, handler1, handler2, handler3, handler4, handler5, handler6)
        self.assertEqual(call_order, [1])
        
        call_order.clear()
        menu_settings.button(3, handler1, handler2, handler3, handler4, handler5, handler6)
        self.assertEqual(call_order, [3])
        
        call_order.clear()
        menu_settings.button(6, handler1, handler2, handler3, handler4, handler5, handler6)
        self.assertEqual(call_order, [6])

    def test_nav_hit_test(self):
        """Test nav_hit_test returns the correct tab"""
        # Calculate y coordinate within nav bar (scaled for current environment)
        # Use a small offset (10px) from the top of the nav bar to ensure we're within it
        nav_y = theme.SCREEN_HEIGHT - theme.NAV_BAR_HEIGHT + 10
        button_count = len(nav.NAV_TABS)
        button_width = theme.SCREEN_WIDTH // button_count
        
        # Test each button at its center x position
        self.assertEqual(nav.nav_hit_test(button_width // 2, nav_y), "home")
        self.assertEqual(nav.nav_hit_test(button_width + button_width // 2, nav_y), "library")
        self.assertEqual(nav.nav_hit_test(2 * button_width + button_width // 2, nav_y), "stats")
        self.assertEqual(nav.nav_hit_test(3 * button_width + button_width // 2, nav_y), "settings")
        self.assertIsNone(nav.nav_hit_test(10, 10))

    @patch('menu_settings.Popen')
    def test_run_cmd(self, mock_popen):
        """Test run_cmd executes command and returns decoded output"""
        mock_process = MagicMock()
        # Mock the communicate method to return test output
        mock_process.communicate.return_value = (b"test output\n", b"")
        mock_popen.return_value = mock_process
        
        # Test with list input (safest, no shell interpretation)
        result = menu_settings.run_cmd(["echo", "test"])
        # The output should be decoded and returned
        self.assertEqual(result, "test output\n")
        # Should be called with the list directly
        mock_popen.assert_called_once()
        # Verify it was called with the list
        call_args = mock_popen.call_args[0][0]
        self.assertIsInstance(call_args, list)
        self.assertEqual(call_args, ["echo", "test"])

    def test_color_constants(self):
        """Test color constants are tuples of 3 integers"""
        colors = [
            menu_settings.white,
            menu_settings.red,
            menu_settings.green,
            menu_settings.blue,
            menu_settings.black,
            menu_settings.tron_regular,
            menu_settings.tron_light,
            menu_settings.tron_inverse,
        ]
        for color in colors:
            self.assertIsInstance(color, tuple)
            self.assertEqual(len(color), 3)
            for component in color:
                self.assertIsInstance(component, int)
                self.assertGreaterEqual(component, 0)
                self.assertLessEqual(component, 255)


if __name__ == '__main__':
    unittest.main()
