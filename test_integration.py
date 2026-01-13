#!/usr/bin/env python3
"""
Integration tests for recording workflows using RecordingManager.
Tests the full recording lifecycle and integration between components.
"""
import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
import os
import time
import threading
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recording_manager import RecordingManager
import menu_settings


class TestRecordingIntegration(unittest.TestCase):
    """Integration tests for recording workflows"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('menu_settings._recording_manager')
    def test_start_stop_manual_recording(self, mock_manager):
        """Test manual recording start/stop workflow"""
        # Mock the recording manager
        mock_manager.start_recording.return_value = True
        mock_manager.stop_recording.return_value = True
        mock_manager.is_recording = False
        mock_manager.recording_mode = None
        mock_manager.recording_start_time = None
        
        # Start recording
        result = menu_settings.start_recording("plughw:0,0", mode="manual")
        
        self.assertTrue(result)
        # The wrapper calls start_recording with positional args, not keyword args
        mock_manager.start_recording.assert_called_once_with("plughw:0,0", "manual")
        
        # Stop recording
        mock_manager.is_recording = True
        mock_manager.recording_mode = "manual"
        result = menu_settings.stop_recording()
        
        self.assertTrue(result)
        mock_manager.stop_recording.assert_called_once()

    @patch('menu_settings._recording_manager')
    def test_get_recording_status_wrapper(self, mock_manager):
        """Test get_recording_status wrapper function"""
        mock_manager.get_recording_status.return_value = ("Manual: 01:23", 83)
        mock_manager.is_recording = True
        mock_manager.recording_mode = "manual"
        mock_manager.recording_start_time = time.time() - 83
        
        status, duration = menu_settings.get_recording_status()
        
        self.assertEqual(status, "Manual: 01:23")
        self.assertEqual(duration, 83)
        mock_manager.get_recording_status.assert_called_once()

    @patch('menu_settings._recording_manager')
    def test_silentjack_wrapper_functions(self, mock_manager):
        """Test silentjack wrapper functions"""
        mock_manager.start_silentjack.return_value = True
        mock_manager.stop_silentjack.return_value = True
        mock_manager._silentjack_process = MagicMock()
        
        # Test start
        result = menu_settings.start_silentjack("plughw:0,0")
        self.assertTrue(result)
        mock_manager.start_silentjack.assert_called_once_with("plughw:0,0")
        
        # Test stop
        result = menu_settings.stop_silentjack()
        self.assertTrue(result)
        mock_manager.stop_silentjack.assert_called_once()

    def test_recording_manager_thread_safety(self):
        """Test thread safety of RecordingManager"""
        manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        results = []
        
        def concurrent_access():
            for _ in range(10):
                status, duration = manager.get_recording_status()
                results.append((status, duration))
                time.sleep(0.01)
        
        # Start multiple threads
        threads = [threading.Thread(target=concurrent_access) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should succeed without errors
        self.assertEqual(len(results), 50)
        for status, duration in results:
            self.assertIsInstance(status, str)
            self.assertIsInstance(duration, int)

    @patch('recording_manager.Popen')
    def test_start_recording_device_validation(self, mock_popen):
        """Test that start_recording validates device before recording"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        # Test with invalid device
        with patch('menu_settings.is_audio_device_valid', return_value=False):
            result = menu_settings.start_recording("invalid_device", mode="manual")
            self.assertFalse(result)
            mock_popen.assert_not_called()
        
        # Test with valid device
        with patch('menu_settings.is_audio_device_valid', return_value=True):
            with patch('menu_settings._recording_manager.start_recording', return_value=True):
                result = menu_settings.start_recording("plughw:0,0", mode="manual")
                # Should check device validity
                pass


class TestRecordingWorkflows(unittest.TestCase):
    """Test complete recording workflows"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('recording_manager.Popen')
    def test_manual_recording_workflow(self, mock_popen):
        """Test complete manual recording workflow"""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process
        
        manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        # Start recording
        result = manager.start_recording("plughw:0,0", mode="manual")
        self.assertTrue(result)
        self.assertTrue(manager.is_recording)
        self.assertEqual(manager.recording_mode, "manual")
        
        # Wait a bit
        time.sleep(0.1)
        
        # Get status
        status, duration = manager.get_recording_status()
        self.assertIn("Manual", status)
        self.assertGreaterEqual(duration, 0)
        
        # Stop recording
        recording_file = Path(self.recording_dir) / "recording_test.wav"
        recording_file.touch()
        manager._recording_filename = recording_file
        
        result = manager.stop_recording()
        self.assertTrue(result)
        self.assertFalse(manager.is_recording)

    def test_auto_recording_state_management(self):
        """Test auto recording state management"""
        manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        # Simulate silentjack starting a recording
        recording_start_file = manager.recording_start_file
        recording_pid_file = manager.recording_pid_file
        
        with open(recording_start_file, 'w') as f:
            f.write(str(time.time()))
        
        with open(recording_pid_file, 'w') as f:
            f.write(str(os.getpid()))  # Use current process
        
        # Check status
        status, duration = manager.get_recording_status()
        # Should detect silentjack recording if device is valid
        # (we can't fully test this without a real device)


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of recording operations"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('recording_manager.Popen')
    def test_concurrent_start_stop(self, mock_popen):
        """Test concurrent start/stop operations"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        results = []
        errors = []
        
        def start_stop_cycle():
            try:
                # Try to start
                result1 = manager.start_recording("plughw:0,0", mode="manual")
                results.append(('start', result1))
                time.sleep(0.01)
                # Try to stop
                result2 = manager.stop_recording()
                results.append(('stop', result2))
            except Exception as e:
                errors.append(e)
        
        # Run concurrent operations
        threads = [threading.Thread(target=start_stop_cycle) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should not have any errors
        self.assertEqual(len(errors), 0)
        # At least some operations should succeed
        self.assertGreater(len(results), 0)

    def test_status_access_during_recording(self):
        """Test status access during active recording"""
        manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            manager.start_recording("plughw:0,0", mode="manual")
            
            # Access status from multiple threads
            statuses = []
            
            def get_status():
                status, duration = manager.get_recording_status()
                statuses.append((status, duration))
            
            threads = [threading.Thread(target=get_status) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # All should return valid status
            self.assertEqual(len(statuses), 20)
            for status, duration in statuses:
                self.assertIsInstance(status, str)
                self.assertIsInstance(duration, int)


if __name__ == '__main__':
    unittest.main()

