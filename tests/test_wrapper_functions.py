#!/usr/bin/env python3
"""
Tests for wrapper functions in menu_settings.py that use RecordingManager.
Tests the integration layer between legacy code and RecordingManager.
"""
import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
import os
import time
import tempfile
import shutil
from pathlib import Path

# Mock pygame before importing modules
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['pygame.font'] = MagicMock()
sys.modules['pygame.display'] = MagicMock()
sys.modules['pygame.mouse'] = MagicMock()
sys.modules['pygame.draw'] = MagicMock()

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import menu_settings
from recording_manager import RecordingManager


class TestWrapperFunctions(unittest.TestCase):
    """Test wrapper functions that use RecordingManager"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)
        
        # Create a new RecordingManager instance for testing
        self.test_manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        # Replace the global manager
        menu_settings._recording_manager = self.test_manager

    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_manager.is_recording:
            self.test_manager.stop_recording()
        self.test_manager.stop_silentjack()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('menu_settings.is_audio_device_valid')
    @patch('menu_settings._recording_manager')
    def test_start_recording_wrapper_validates_device(self, mock_manager, mock_validate):
        """Test that start_recording wrapper validates device"""
        mock_validate.return_value = True
        mock_manager.start_recording.return_value = True
        mock_manager.recording_start_time = time.time()
        mock_manager.is_recording = False
        
        # Test with invalid device
        mock_validate.return_value = False
        result = menu_settings.start_recording("invalid_device", mode="manual")
        self.assertFalse(result)
        mock_manager.start_recording.assert_not_called()
        
        # Test with valid device
        mock_validate.return_value = True
        mock_manager.start_recording.reset_mock()
        result = menu_settings.start_recording("plughw:0,0", mode="manual")
        self.assertTrue(result)
        # Check that it was called (may be called with mode as positional or keyword arg)
        mock_manager.start_recording.assert_called_once()
        call_args = mock_manager.start_recording.call_args
        self.assertEqual(call_args[0][0], "plughw:0,0")
        self.assertEqual(call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('mode', 'manual'), "manual")

    @patch('menu_settings._recording_manager')
    def test_stop_recording_wrapper(self, mock_manager):
        """Test stop_recording wrapper"""
        mock_manager.stop_recording.return_value = True
        mock_manager.is_recording = False
        mock_manager.recording_mode = None
        mock_manager.recording_start_time = None
        
        result = menu_settings.stop_recording()
        
        self.assertTrue(result)
        mock_manager.stop_recording.assert_called_once()
        
        # Verify legacy globals are updated
        self.assertFalse(menu_settings.is_recording)
        self.assertIsNone(menu_settings.recording_mode)

    @patch('menu_settings._recording_manager')
    def test_get_recording_status_wrapper(self, mock_manager):
        """Test get_recording_status wrapper"""
        mock_manager.get_recording_status.return_value = ("Manual: 05:30", 330)
        mock_manager.is_recording = True
        mock_manager.recording_mode = "manual"
        mock_manager.recording_start_time = time.time() - 330
        
        status, duration = menu_settings.get_recording_status()
        
        self.assertEqual(status, "Manual: 05:30")
        self.assertEqual(duration, 330)
        mock_manager.get_recording_status.assert_called_once()
        
        # Verify legacy globals are updated
        self.assertTrue(menu_settings.is_recording)
        self.assertEqual(menu_settings.recording_mode, "manual")

    @patch('menu_settings._recording_manager')
    def test_start_silentjack_wrapper(self, mock_manager):
        """Test start_silentjack wrapper"""
        mock_manager.start_silentjack.return_value = True
        mock_process = MagicMock()
        mock_manager._silentjack_process = mock_process
        
        result = menu_settings.start_silentjack("plughw:0,0")
        
        self.assertTrue(result)
        mock_manager.start_silentjack.assert_called_once_with("plughw:0,0")
        # Verify legacy global is updated
        self.assertEqual(menu_settings.silentjack_process, mock_process)

    @patch('menu_settings._recording_manager')
    def test_stop_silentjack_wrapper(self, mock_manager):
        """Test stop_silentjack wrapper"""
        mock_manager.stop_silentjack.return_value = True
        
        result = menu_settings.stop_silentjack()
        
        self.assertTrue(result)
        mock_manager.stop_silentjack.assert_called_once()
        # Verify legacy global is cleared
        self.assertIsNone(menu_settings.silentjack_process)

    @patch('menu_settings._recording_manager')
    def test_rename_with_duration_wrapper(self, mock_manager):
        """Test rename_with_duration wrapper"""
        from pathlib import Path
        mock_manager._rename_with_duration.return_value = Path("/test/new_name.wav")
        
        result = menu_settings.rename_with_duration("/test/old_name.wav", 3665)
        
        self.assertIsNotNone(result)
        mock_manager._rename_with_duration.assert_called_once()
        args = mock_manager._rename_with_duration.call_args[0]
        self.assertEqual(str(args[0]), "/test/old_name.wav")
        self.assertEqual(args[1], 3665)


class TestBackwardCompatibility(unittest.TestCase):
    """Test that legacy globals are properly maintained for backward compatibility"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)
        
        self.test_manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        menu_settings._recording_manager = self.test_manager

    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_manager.is_recording:
            self.test_manager.stop_recording()
        self.test_manager.stop_silentjack()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('recording_manager.MIN_FREE_DISK_SPACE_GB', 0.0001)  # Set very low threshold
    @patch('shutil.disk_usage')
    @patch('recording_manager.Popen')
    @patch('menu_settings.is_audio_device_valid')
    def test_legacy_globals_updated_on_start(self, mock_validate, mock_popen, mock_disk):
        """Test that legacy globals are updated when starting recording"""
        mock_validate.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_disk.return_value = MagicMock(free=1024**3)  # 1GB free
        
        result = menu_settings.start_recording("plughw:0,0", mode="manual")
        
        self.assertTrue(result)
        self.assertTrue(menu_settings.is_recording)
        self.assertEqual(menu_settings.recording_mode, "manual")
        self.assertIsNotNone(menu_settings.recording_start_time)

    @patch('recording_manager.MIN_FREE_DISK_SPACE_GB', 0.0001)  # Set very low threshold
    @patch('shutil.disk_usage')
    @patch('recording_manager.Popen')
    @patch('menu_settings.is_audio_device_valid')
    def test_legacy_globals_updated_on_stop(self, mock_validate, mock_popen, mock_disk):
        """Test that legacy globals are updated when stopping recording"""
        mock_validate.return_value = True
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process
        mock_disk.return_value = MagicMock(free=1024**3)  # 1GB free
        
        # Start recording
        menu_settings.start_recording("plughw:0,0", mode="manual")
        
        # Stop recording
        recording_file = Path(self.recording_dir) / "recording_test.wav"
        recording_file.touch()
        self.test_manager._recording_filename = recording_file
        
        result = menu_settings.stop_recording()
        
        self.assertTrue(result)
        self.assertFalse(menu_settings.is_recording)
        self.assertIsNone(menu_settings.recording_mode)
        self.assertIsNone(menu_settings.recording_start_time)


if __name__ == '__main__':
    unittest.main()

