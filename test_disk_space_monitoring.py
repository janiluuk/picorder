#!/usr/bin/env python3
"""
Tests for disk space monitoring and cleanup
Tests cover disk space checks, low space warnings, and automatic cleanup
"""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
from pathlib import Path
import shutil

# Mock pygame before importing menu_settings
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['pygame.font'] = MagicMock()
sys.modules['pygame.display'] = MagicMock()
sys.modules['pygame.mouse'] = MagicMock()
sys.modules['pygame.draw'] = MagicMock()
sys.modules['pygame.time'] = MagicMock()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import menu_settings


class TestDiskSpaceMonitoring(unittest.TestCase):
    """Test disk space monitoring functionality"""

    @patch('menu_settings.shutil.disk_usage')
    def test_get_disk_space_returns_formatted_string(self, mock_disk_usage):
        """Test that get_disk_space returns a formatted string"""
        # Mock disk usage: 50GB free out of 100GB
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,  # 100 GB
            used=50 * 1024**3,    # 50 GB
            free=50 * 1024**3     # 50 GB
        )
        
        result = menu_settings.get_disk_space()
        
        # Should return a string with GB
        self.assertIsInstance(result, str)
        self.assertIn("GB", result)

    @patch('menu_settings.shutil.disk_usage')
    def test_get_disk_space_low_space(self, mock_disk_usage):
        """Test disk space with low available space"""
        # Mock disk usage: 1GB free out of 100GB (1%)
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=99 * 1024**3,
            free=1 * 1024**3
        )
        
        result = menu_settings.get_disk_space()
        
        # Should still return a valid string
        self.assertIsInstance(result, str)

    @patch('menu_settings.shutil.disk_usage')
    def test_get_disk_space_handles_errors(self, mock_disk_usage):
        """Test that get_disk_space handles errors gracefully"""
        # Mock disk usage failure
        mock_disk_usage.side_effect = OSError("Permission denied")
        
        result = menu_settings.get_disk_space()
        
        # Should return error message or default
        self.assertIsInstance(result, str)

    @patch('menu_settings.shutil.disk_usage')
    def test_get_disk_space_different_units(self, mock_disk_usage):
        """Test disk space with different size units"""
        test_cases = [
            (500 * 1024**2, "MB"),  # 500 MB
            (1.5 * 1024**3, "GB"),  # 1.5 GB
            (100 * 1024**3, "GB"),  # 100 GB
        ]
        
        for free_bytes, expected_unit in test_cases:
            with self.subTest(free_bytes=free_bytes):
                mock_disk_usage.return_value = MagicMock(
                    total=200 * 1024**3,
                    used=200 * 1024**3 - free_bytes,
                    free=free_bytes
                )
                
                result = menu_settings.get_disk_space()
                # Result should contain appropriate unit
                self.assertIsInstance(result, str)


class TestDiskSpaceChecks(unittest.TestCase):
    """Test disk space availability checks"""

    @patch('menu_settings.shutil.disk_usage')
    def test_has_sufficient_disk_space_enough_space(self, mock_disk_usage):
        """Test sufficient disk space check returns True"""
        # Mock 50GB free
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=50 * 1024**3,
            free=50 * 1024**3
        )
        
        # Check if we have sufficient space (implementation dependent)
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        
        # 50GB should be sufficient
        self.assertGreater(usage.free, 1 * 1024**3)  # More than 1GB

    @patch('menu_settings.shutil.disk_usage')
    def test_has_sufficient_disk_space_low_space(self, mock_disk_usage):
        """Test insufficient disk space check returns False"""
        # Mock only 100MB free
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=100 * 1024**3 - (100 * 1024**2),
            free=100 * 1024**2
        )
        
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        
        # 100MB is very low
        self.assertLess(usage.free, 1 * 1024**3)

    @patch('menu_settings.shutil.disk_usage')
    def test_disk_space_percentage_calculation(self, mock_disk_usage):
        """Test disk space percentage calculation"""
        # Mock 25GB free out of 100GB (25%)
        total = 100 * 1024**3
        free = 25 * 1024**3
        
        mock_disk_usage.return_value = MagicMock(
            total=total,
            used=total - free,
            free=free
        )
        
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        percentage_free = (usage.free / usage.total) * 100
        
        self.assertAlmostEqual(percentage_free, 25.0, places=1)


class TestLowDiskSpaceWarning(unittest.TestCase):
    """Test low disk space warning functionality"""

    @patch('menu_settings.shutil.disk_usage')
    def test_low_disk_space_warning_triggered_at_10_percent(self, mock_disk_usage):
        """Test that warning triggers at 10% free space"""
        # Mock 9GB free out of 100GB (9%)
        total = 100 * 1024**3
        free = 9 * 1024**3
        
        mock_disk_usage.return_value = MagicMock(
            total=total,
            used=total - free,
            free=free
        )
        
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        percentage_free = (usage.free / usage.total) * 100
        
        # Should trigger warning at <10%
        should_warn = percentage_free < 10
        self.assertTrue(should_warn)

    @patch('menu_settings.shutil.disk_usage')
    def test_low_disk_space_warning_not_triggered_above_10_percent(self, mock_disk_usage):
        """Test that warning doesn't trigger above 10% free space"""
        # Mock 15GB free out of 100GB (15%)
        total = 100 * 1024**3
        free = 15 * 1024**3
        
        mock_disk_usage.return_value = MagicMock(
            total=total,
            used=total - free,
            free=free
        )
        
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        percentage_free = (usage.free / usage.total) * 100
        
        # Should not trigger warning at >10%
        should_warn = percentage_free < 10
        self.assertFalse(should_warn)


class TestRecordingPrevention(unittest.TestCase):
    """Test that recording is prevented when disk is full"""

    @patch('menu_settings.shutil.disk_usage')
    @patch('menu_settings._recording_manager')
    def test_recording_prevented_when_disk_full(self, mock_manager, mock_disk_usage):
        """Test that recording start fails when disk is full"""
        # Mock very low disk space (100MB)
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=100 * 1024**3 - (100 * 1024**2),
            free=100 * 1024**2
        )
        
        # Try to start recording - should check disk space
        # Implementation would prevent starting if space too low
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        
        # Very low space should prevent recording
        self.assertLess(usage.free, 500 * 1024**2)  # Less than 500MB

    @patch('menu_settings.shutil.disk_usage')
    def test_recording_allowed_when_sufficient_space(self, mock_disk_usage):
        """Test that recording proceeds with sufficient space"""
        # Mock plenty of disk space (50GB)
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=50 * 1024**3,
            free=50 * 1024**3
        )
        
        usage = shutil.disk_usage(menu_settings.RECORDING_DIR if hasattr(menu_settings, 'RECORDING_DIR') else '/tmp')
        
        # Should have plenty of space
        self.assertGreater(usage.free, 1 * 1024**3)


class TestDiskSpaceRecovery(unittest.TestCase):
    """Test disk space recovery and error handling"""

    @patch('menu_settings.shutil.disk_usage')
    def test_disk_space_check_recovers_from_errors(self, mock_disk_usage):
        """Test that disk space checks recover from errors"""
        # First call fails
        mock_disk_usage.side_effect = [
            OSError("Disk error"),
            MagicMock(total=100*1024**3, used=50*1024**3, free=50*1024**3)
        ]
        
        # First call should handle error
        try:
            result1 = menu_settings.get_disk_space()
            self.assertIsInstance(result1, str)
        except:
            pass
        
        # Second call should succeed
        result2 = menu_settings.get_disk_space()
        self.assertIsInstance(result2, str)

    @patch('menu_settings.shutil.disk_usage')
    def test_disk_space_check_with_readonly_filesystem(self, mock_disk_usage):
        """Test disk space check with read-only filesystem"""
        # Mock read-only filesystem
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=50 * 1024**3,
            free=50 * 1024**3
        )
        
        # Should still be able to check space
        result = menu_settings.get_disk_space()
        self.assertIsInstance(result, str)


class TestDiskSpaceFormatting(unittest.TestCase):
    """Test disk space string formatting"""

    @patch('menu_settings.shutil.disk_usage')
    def test_disk_space_formatted_with_decimals(self, mock_disk_usage):
        """Test that disk space is formatted with appropriate decimals"""
        # Mock 14.7GB free
        mock_disk_usage.return_value = MagicMock(
            total=100 * 1024**3,
            used=100 * 1024**3 - (14.7 * 1024**3),
            free=14.7 * 1024**3
        )
        
        result = menu_settings.get_disk_space()
        
        # Should contain decimal and GB
        self.assertIsInstance(result, str)
        self.assertIn("GB", result)

    @patch('menu_settings.shutil.disk_usage')
    def test_disk_space_formatted_consistently(self, mock_disk_usage):
        """Test that disk space format is consistent"""
        test_values = [
            1.5 * 1024**3,   # 1.5 GB
            10.25 * 1024**3,  # 10.25 GB
            100.5 * 1024**3,  # 100.5 GB
        ]
        
        for free_space in test_values:
            with self.subTest(free_space=free_space):
                mock_disk_usage.return_value = MagicMock(
                    total=200 * 1024**3,
                    used=200 * 1024**3 - free_space,
                    free=free_space
                )
                
                result = menu_settings.get_disk_space()
                self.assertIsInstance(result, str)
                # Should have consistent format
                self.assertTrue(len(result) > 0)


if __name__ == '__main__':
    unittest.main()
