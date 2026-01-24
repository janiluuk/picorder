#!/usr/bin/env python3
"""
Comprehensive tests for RecordingManager and recording functionality.
Tests thread safety, error handling, and edge cases.
"""
import unittest
from unittest.mock import patch, MagicMock, Mock, mock_open
import sys
import os
import time
import threading
from pathlib import Path
import tempfile
import shutil

# Mock pygame before importing modules
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['pygame.font'] = MagicMock()
sys.modules['pygame.display'] = MagicMock()
sys.modules['pygame.mouse'] = MagicMock()
sys.modules['pygame.draw'] = MagicMock()

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recording_manager import RecordingManager


class TestRecordingManager(unittest.TestCase):
    """Test cases for RecordingManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)
        
        self.manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )

    def tearDown(self):
        """Clean up test fixtures"""
        # Stop any running processes
        if self.manager.is_recording:
            self.manager.stop_recording()
        self.manager.stop_silentjack()
        
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test RecordingManager initialization"""
        self.assertFalse(self.manager.is_recording)
        self.assertIsNone(self.manager.recording_mode)
        self.assertIsNone(self.manager.recording_start_time)
        self.assertEqual(self.manager.recording_dir, Path(self.recording_dir))

    def test_start_recording_success(self):
        """Test successful recording start"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            result = self.manager.start_recording("plughw:0,0", mode="manual")
            
            self.assertTrue(result)
            self.assertTrue(self.manager.is_recording)
            self.assertEqual(self.manager.recording_mode, "manual")
            mock_popen.assert_called_once()

    def test_start_recording_already_recording(self):
        """Test that starting recording when already recording returns False"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            # Start first recording
            self.manager.start_recording("plughw:0,0", mode="manual")
            
            # Try to start another
            result = self.manager.start_recording("plughw:0,0", mode="manual")
            
            self.assertFalse(result)
            # Should still be recording the first one
            self.assertTrue(self.manager.is_recording)

    def test_start_recording_os_error(self):
        """Test handling of OSError when starting recording"""
        with patch('subprocess.Popen', side_effect=OSError("Device not found")):
            result = self.manager.start_recording("invalid_device", mode="manual")
            
            self.assertFalse(result)
            self.assertFalse(self.manager.is_recording)

    def test_stop_recording_manual(self):
        """Test stopping a manual recording"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_popen.return_value = mock_process
            
            # Start recording
            self.manager.start_recording("plughw:0,0", mode="manual")
            time.sleep(0.1)  # Small delay to ensure state is set
            
            # Create a dummy recording file
            recording_file = Path(self.recording_dir) / "recording_20240101_120000.wav"
            recording_file.touch()
            
            # Mock the filename
            with patch.object(self.manager, '_recording_filename', recording_file):
                result = self.manager.stop_recording()
                
                self.assertTrue(result)
                self.assertFalse(self.manager.is_recording)
                mock_process.terminate.assert_called_once()

    def test_stop_recording_not_recording(self):
        """Test stopping when not recording"""
        result = self.manager.stop_recording()
        self.assertFalse(result)

    def test_get_recording_status_not_recording(self):
        """Test getting status when not recording"""
        status, duration = self.manager.get_recording_status()
        self.assertEqual(status, "Not Recording")
        self.assertEqual(duration, 0)

    def test_get_recording_status_manual(self):
        """Test getting status for manual recording"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            self.manager.start_recording("plughw:0,0", mode="manual")
            time.sleep(0.1)
            
            status, duration = self.manager.get_recording_status()
            self.assertIn("Manual", status)
            self.assertGreaterEqual(duration, 0)

    def test_thread_safety_concurrent_start(self):
        """Test thread safety with concurrent start attempts"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            results = []
            
            def start_recording():
                result = self.manager.start_recording("plughw:0,0", mode="manual")
                results.append(result)
            
            # Start multiple threads trying to record
            threads = [threading.Thread(target=start_recording) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # Only one should succeed
            self.assertEqual(sum(results), 1)
            self.assertTrue(self.manager.is_recording)

    def test_thread_safety_status_access(self):
        """Test thread safety when accessing status from multiple threads"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            self.manager.start_recording("plughw:0,0", mode="manual")
            
            statuses = []
            
            def get_status():
                status, duration = self.manager.get_recording_status()
                statuses.append((status, duration))
            
            # Access status from multiple threads
            threads = [threading.Thread(target=get_status) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # All should return valid status
            self.assertEqual(len(statuses), 10)
            for status, duration in statuses:
                self.assertIn("Manual", status)
                self.assertGreaterEqual(duration, 0)

    def test_rename_with_duration_seconds_only(self):
        """Test renaming with duration less than a minute"""
        filename = Path(self.recording_dir) / "recording_20240101_120000.wav"
        filename.touch()
        
        new_filename = self.manager._rename_with_duration(filename, 45)
        
        self.assertIsNotNone(new_filename)
        self.assertIn("45s", str(new_filename))
        self.assertNotIn("h", str(new_filename))

    def test_rename_with_duration_with_hours(self):
        """Test renaming with duration including hours"""
        filename = Path(self.recording_dir) / "recording_20240101_120000.wav"
        filename.touch()
        
        new_filename = self.manager._rename_with_duration(filename, 3665)  # 1h 1m 5s
        
        self.assertIsNotNone(new_filename)
        self.assertIn("01h", str(new_filename))
        self.assertIn("01m", str(new_filename))
        self.assertIn("05s", str(new_filename))

    def test_silentjack_script_creation(self):
        """Test silentjack script creation"""
        device = "plughw:0,0"
        result = self.manager._create_silentjack_script(device)
        
        self.assertTrue(result)
        self.assertTrue(self.manager.silentjack_script.exists())
        
        # Check script content
        script_content = self.manager.silentjack_script.read_text()
        self.assertIn(device, script_content)
        self.assertIn(self.recording_dir, script_content)
        
        # Check script is executable
        self.assertTrue(os.access(self.manager.silentjack_script, os.X_OK))

    def test_silentjack_script_variable_expansion(self):
        """Test that bash script has correct variable expansion"""
        device = "plughw:0,0"
        self.manager._create_silentjack_script(device)
        
        script_content = self.manager.silentjack_script.read_text()
        
        # Check for correct variable expansion (not $BASE_NAME_ but ${BASE_NAME}_)
        self.assertIn("${BASE_NAME}_${DUR_STR}", script_content)
        self.assertNotIn("$BASE_NAME_$DUR_STR", script_content)
        self.assertIn("${OLD_FILE%.wav}", script_content)

    def test_start_silentjack(self):
        """Test starting silentjack"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            result = self.manager.start_silentjack("plughw:0,0")
            
            self.assertTrue(result)
            mock_popen.assert_called_once()

    def test_stop_silentjack(self):
        """Test stopping silentjack"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_popen.return_value = mock_process
            
            self.manager.start_silentjack("plughw:0,0")
            result = self.manager.stop_silentjack()
            
            self.assertTrue(result)
            mock_process.terminate.assert_called_once()

    def test_stop_silentjack_not_running(self):
        """Test stopping silentjack when not running"""
        result = self.manager.stop_silentjack()
        self.assertFalse(result)

    def test_cleanup_silentjack_files(self):
        """Test cleanup of silentjack state files"""
        # Create dummy files
        self.manager.recording_pid_file.touch()
        self.manager.recording_file_file.touch()
        self.manager.recording_start_file.touch()
        
        self.manager._cleanup_silentjack_files()
        
        self.assertFalse(self.manager.recording_pid_file.exists())
        self.assertFalse(self.manager.recording_file_file.exists())
        self.assertFalse(self.manager.recording_start_file.exists())

    def test_check_silentjack_recording_active(self):
        """Test checking for active silentjack recording"""
        # Create state files
        with open(self.manager.recording_start_file, 'w') as f:
            f.write(str(time.time()))
        with open(self.manager.recording_pid_file, 'w') as f:
            f.write(str(os.getpid()))  # Use current process PID
        
        is_recording, start_time = self.manager.check_silentjack_recording()
        
        self.assertTrue(is_recording)
        self.assertIsNotNone(start_time)

    def test_check_silentjack_recording_inactive(self):
        """Test checking for inactive silentjack recording"""
        is_recording, start_time = self.manager.check_silentjack_recording()
        
        self.assertFalse(is_recording)
        self.assertIsNone(start_time)


class TestRecordingManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = os.path.join(self.temp_dir, "recordings")
        self.menu_dir = os.path.join(self.temp_dir, "picorder")
        os.makedirs(self.recording_dir, exist_ok=True)
        os.makedirs(self.menu_dir, exist_ok=True)
        
        self.manager = RecordingManager(
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )

    def tearDown(self):
        """Clean up test fixtures"""
        if self.manager.is_recording:
            self.manager.stop_recording()
        self.manager.stop_silentjack()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stop_recording_process_timeout(self):
        """Test handling of process that doesn't terminate"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.wait.side_effect = [TimeoutError(), None]  # First wait times out
            mock_popen.return_value = mock_process
            
            self.manager.start_recording("plughw:0,0", mode="manual")
            time.sleep(0.1)
            
            recording_file = Path(self.recording_dir) / "recording_test.wav"
            recording_file.touch()
            
            with patch.object(self.manager, '_recording_filename', recording_file):
                result = self.manager.stop_recording()
                
                # Should kill the process after timeout
                mock_process.kill.assert_called_once()

    def test_stop_recording_closes_file_handles_when_process_exists(self):
        """Test that file handles are closed when recording_process is not None"""
        with patch('recording_manager.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process
            
            # Start recording
            self.manager.start_recording("plughw:0,0", mode="manual")
            time.sleep(0.1)
            
            # Create a dummy recording file
            recording_file = Path(self.recording_dir) / "recording_test.wav"
            recording_file.touch()
            
            with patch.object(self.manager, '_recording_filename', recording_file):
                result = self.manager.stop_recording()
                
                self.assertTrue(result)
                # CRITICAL: File handles should be closed after stopping the process
                mock_process.stdout.close.assert_called_once()
                mock_process.stderr.close.assert_called_once()

    def test_stop_recording_none_process_no_attribute_error(self):
        """Test that stopping when recording_process is None doesn't cause AttributeError on file handles"""
        # Set up state to indicate we were recording, but process is None
        # This simulates the scenario where process was lost but state wasn't cleared
        with self.manager._lock:
            self.manager._is_recording = True
            self.manager._recording_process = None  # Process is None
            self.manager._recording_mode = "manual"
            self.manager._recording_start_time = time.time()
            # Create a recording file that exists
            recording_file = Path(self.recording_dir) / "recording_test.wav"
            recording_file.touch()
            self.manager._recording_filename = recording_file
        
        # CRITICAL: This should NOT raise an AttributeError when trying to close file handles
        # The bug was that file handle closing code was in the else block where recording_process is None
        # and it tried to access recording_process.stdout and recording_process.stderr, causing AttributeError
        try:
            result = self.manager.stop_recording()
            # Should complete without AttributeError
            self.assertFalse(self.manager.is_recording, "State should be cleared")
        except AttributeError as e:
            if "stdout" in str(e) or "stderr" in str(e):
                self.fail(f"Bug not fixed: AttributeError when accessing file handles on None process: {e}")
            else:
                raise  # Re-raise if it's a different AttributeError

    def test_rename_file_permission_error(self):
        """Test handling of permission error when renaming"""
        filename = Path(self.recording_dir) / "recording_test.wav"
        filename.touch()
        
        # Make directory read-only
        os.chmod(self.recording_dir, 0o555)
        
        try:
            new_filename = self.manager._rename_with_duration(filename, 60)
            # Should still return the new filename even if rename fails
            self.assertIsNotNone(new_filename)
        finally:
            # Restore permissions
            os.chmod(self.recording_dir, 0o755)

    def test_invalid_pid_file(self):
        """Test handling of invalid PID in file"""
        self.manager.recording_pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manager.recording_pid_file, 'w') as f:
            f.write("not_a_number")
        
        # Should not crash
        result = self.manager._stop_silentjack_recording()
        # May return False due to invalid PID, but shouldn't raise exception
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()

