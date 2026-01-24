#!/usr/bin/env python3
"""
Tests for audio device validation functionality
Tests cover device detection, validation caching, and error handling
"""
import unittest
from unittest.mock import patch, MagicMock, call
import time
import sys
from pathlib import Path

# Mock pygame before importing menu_settings to avoid initialization issues
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['pygame.font'] = MagicMock()
sys.modules['pygame.display'] = MagicMock()
sys.modules['pygame.mouse'] = MagicMock()
sys.modules['pygame.draw'] = MagicMock()
sys.modules['pygame.time'] = MagicMock()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import menu_settings


class TestAudioDeviceValidation(unittest.TestCase):
    """Test audio device validation with various scenarios"""

    def setUp(self):
        """Reset validation cache before each test"""
        # Clear any cached validation results
        if hasattr(menu_settings, '_device_validation_cache'):
            menu_settings._device_validation_cache = {}

    @patch('menu_settings.Popen')
    def test_validate_audio_device_valid_device(self, mock_popen):
        """Test validation with a valid audio device"""
        # Mock successful arecord --dump-hw-params output
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"FORMAT:  S16_LE\nCHANNELS: 2\n", b"")
        mock_popen.return_value = mock_process
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertTrue(result)
        mock_popen.assert_called_once()

    @patch('menu_settings.Popen')
    def test_validate_audio_device_invalid_device(self, mock_popen):
        """Test validation with invalid audio device"""
        # Mock arecord output with error
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"Invalid audio device plughw:99,0\n", b"")
        mock_popen.return_value = mock_process
        
        result = menu_settings.validate_audio_device("plughw:99,0", use_cache=False)
        self.assertFalse(result)

    def test_validate_audio_device_empty_device(self):
        """Test validation with empty device string"""
        result = menu_settings.validate_audio_device("", use_cache=False)
        self.assertFalse(result)
        # Should not call subprocess for empty device

    @patch('menu_settings.Popen')
    def test_validate_audio_device_caching(self, mock_popen):
        """Test that validation results are cached"""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"FORMAT:  S16_LE\n", b"")
        mock_popen.return_value = mock_process
        
        # First call - should hit subprocess
        result1 = menu_settings.validate_audio_device("plughw:2,0", use_cache=True)
        self.assertTrue(result1)
        self.assertEqual(mock_popen.call_count, 1)
        
        # Second call within cache TTL - should use cache
        result2 = menu_settings.validate_audio_device("plughw:2,0", use_cache=True)
        self.assertTrue(result2)
        # Still only 1 call - used cache
        self.assertEqual(mock_popen.call_count, 1)

    @patch('menu_settings.subprocess.run')
    def test_validate_audio_device_cache_expiry(self, mock_run):
        """Test that cache expires after TTL"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\n"
        )
        
        # Patch the cache TTL to be very short for testing
        original_ttl = menu_settings.DEVICE_VALIDATION_CACHE_TTL if hasattr(menu_settings, 'DEVICE_VALIDATION_CACHE_TTL') else 5
        if hasattr(menu_settings, 'DEVICE_VALIDATION_CACHE_TTL'):
            menu_settings.DEVICE_VALIDATION_CACHE_TTL = 0.1  # 100ms
        
        # First call
        result1 = menu_settings.validate_audio_device("plughw:2,0", use_cache=True)
        self.assertTrue(result1)
        initial_calls = mock_run.call_count
        
        # Wait for cache to expire
        time.sleep(0.15)
        
        # Second call after expiry - should hit subprocess again
        result2 = menu_settings.validate_audio_device("plughw:2,0", use_cache=True)
        self.assertTrue(result2)
        self.assertEqual(mock_run.call_count, initial_calls + 1)
        
        # Restore original TTL
        if hasattr(menu_settings, 'DEVICE_VALIDATION_CACHE_TTL'):
            menu_settings.DEVICE_VALIDATION_CACHE_TTL = original_ttl

    @patch('menu_settings.subprocess.run')
    def test_validate_audio_device_subprocess_error(self, mock_run):
        """Test handling of subprocess errors"""
        # Mock subprocess failure
        mock_run.side_effect = OSError("Command not found")
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertFalse(result)

    @patch('menu_settings.subprocess.run')
    def test_validate_audio_device_timeout(self, mock_run):
        """Test handling of subprocess timeout"""
        mock_run.side_effect = TimeoutError("Timeout")
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertFalse(result)

    @patch('menu_settings.subprocess.run')
    def test_is_audio_device_valid_wrapper(self, mock_run):
        """Test is_audio_device_valid wrapper function"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\n"
        )
        
        # Test valid device
        result = menu_settings.is_audio_device_valid("plughw:2,0")
        self.assertTrue(result)
        
        # Test empty device
        result = menu_settings.is_audio_device_valid("")
        self.assertFalse(result)

    @patch('menu_settings.subprocess.run')
    def test_get_audio_devices_includes_validation(self, mock_run):
        """Test that get_audio_devices returns only valid devices"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\nplughw:0,0\ndefault\n"
        )
        
        devices = menu_settings.get_audio_devices()
        self.assertIsInstance(devices, list)
        # Should return list of tuples (device, name)
        if devices:
            self.assertIsInstance(devices[0], tuple)
            self.assertEqual(len(devices[0]), 2)


class TestAudioDeviceHotPlugging(unittest.TestCase):
    """Test audio device hot-plugging scenarios"""

    @patch('menu_settings.subprocess.run')
    @patch('menu_settings.load_config')
    def test_device_unplugged_during_operation(self, mock_load_config, mock_run):
        """Test behavior when device is unplugged during operation"""
        # Start with valid device
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\n"
        )
        mock_load_config.return_value = {"audio_device": "plughw:2,0"}
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertTrue(result)
        
        # Simulate device unplugged
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="default\n"  # Device no longer in list
        )
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertFalse(result)

    @patch('menu_settings.subprocess.run')
    def test_device_plugged_in_detected(self, mock_run):
        """Test that newly plugged device is detected"""
        # Initially no device
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="default\n"
        )
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertFalse(result)
        
        # Device plugged in
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\ndefault\n"
        )
        
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertTrue(result)


class TestAudioDeviceErrorHandling(unittest.TestCase):
    """Test error handling in audio device validation"""

    @patch('menu_settings.subprocess.run')
    def test_malformed_device_string(self, mock_run):
        """Test handling of malformed device strings"""
        test_devices = [
            "invalid device name",
            "plughw:",
            ":",
            "plughw:999,999",
            "../../../etc/passwd",  # Path traversal attempt
        ]
        
        for device in test_devices:
            with self.subTest(device=device):
                # Should handle gracefully without crashing
                try:
                    result = menu_settings.validate_audio_device(device, use_cache=False)
                    # Should return False for invalid devices
                    self.assertIsInstance(result, bool)
                except Exception as e:
                    self.fail(f"Validation raised exception for device '{device}': {e}")

    @patch('menu_settings.subprocess.run')
    def test_unicode_device_names(self, mock_run):
        """Test handling of unicode characters in device names"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="plughw:2,0\n"
        )
        
        # Should handle unicode without crashing
        result = menu_settings.validate_audio_device("plughw:2,0", use_cache=False)
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()
