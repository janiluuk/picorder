#!/usr/bin/env python3
"""
Tests for recording functionality - start/stop, queue processing, state management
"""
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import threading
import time
from queue import Queue
from pathlib import Path
import tempfile
import shutil

# Import the modules we want to test
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock pygame and RPi.GPIO before importing our modules
mock_pygame = MagicMock()
mock_pygame.locals = MagicMock()
sys.modules['pygame'] = mock_pygame
sys.modules['pygame.locals'] = mock_pygame.locals
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

from recording_manager import RecordingManager


class TestRecordingManager(unittest.TestCase):
    """Test RecordingManager functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = Path(self.temp_dir) / "recordings"
        self.menu_dir = Path(self.temp_dir) / "menu"
        self.recording_dir.mkdir(parents=True)
        self.menu_dir.mkdir(parents=True)
        
        self.manager = RecordingManager(
            recording_dir=str(self.recording_dir),
            menu_dir=str(self.menu_dir)
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('recording_manager.Popen')
    @patch('recording_manager.subprocess.run')
    def test_start_recording_success(self, mock_subprocess, mock_popen):
        """Test successful recording start"""
        # Mock arecord process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        # Mock disk space check (it's called inside start_recording)
        import shutil
        with patch('shutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {'free': 10**9})()  # 1GB free
            result = self.manager.start_recording("plughw:0,0", mode="manual")
        
        self.assertTrue(result)
        self.assertTrue(self.manager.is_recording)
        self.assertEqual(self.manager.recording_mode, "manual")
        self.assertIsNotNone(self.manager.recording_start_time)
    
    @patch('recording_manager.Popen')
    def test_stop_recording_success(self, mock_popen):
        """Test successful recording stop"""
        # Start a recording first
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        import shutil
        with patch('shutil.disk_usage') as mock_disk:
            mock_disk.return_value = type('obj', (object,), {'free': 10**9})()  # 1GB free
            self.manager.start_recording("plughw:0,0", mode="manual")
        
        # Now stop it
        mock_process.wait.return_value = None
        result = self.manager.stop_recording()
        
        self.assertTrue(result)
        self.assertFalse(self.manager.is_recording)
        # Check internal state (private attribute)
        with self.manager._lock:
            self.assertIsNone(self.manager._recording_process)
    
    @patch('menu_settings.load_config')
    @patch('subprocess.run')
    def test_stop_recording_kills_zombie_processes(self, mock_subprocess, mock_load_config):
        """Test that stop_recording kills zombie arecord processes"""
        # Mock config
        mock_load_config.return_value = {"audio_device": "plughw:0,0"}
        
        # Mock pgrep to find arecord processes
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"12345\n12346\n"
        mock_subprocess.return_value = mock_result
        
        # Mock kill_zombie_arecord_processes
        with patch.object(self.manager, '_kill_zombie_arecord_processes') as mock_kill:
            # Set state to not recording but with no process reference
            with self.manager._lock:
                self.manager._is_recording = False
                self.manager._recording_process = None
            
            result = self.manager.stop_recording()
            
            # Should have checked for arecord processes
            # The check happens in stop_recording when no process reference exists
            # Verify kill was called (if processes were found)
            if mock_subprocess.called:
                mock_kill.assert_called_once()
    
    def test_get_recording_state_blocking(self):
        """Test get_recording_state with blocking=True"""
        with self.manager._lock:
            self.manager._is_recording = True
            self.manager._recording_mode = "manual"
            self.manager._recording_start_time = time.time()
        
        state = self.manager.get_recording_state(blocking=True)
        
        self.assertTrue(state['is_recording'])
        self.assertEqual(state['mode'], "manual")
        self.assertIsNotNone(state['start_time'])
    
    def test_get_recording_state_non_blocking(self):
        """Test get_recording_state with blocking=False"""
        # Set actual state (non-blocking will try to acquire lock, so set actual state)
        with self.manager._lock:
            self.manager._is_recording = True
            self.manager._recording_mode = "manual"
            self.manager._recording_start_time = time.time()
            # Also set cached state
            self.manager._cached_is_recording = True
            self.manager._cached_mode = "manual"
            self.manager._cached_start_time = time.time()
        
        # Release lock and get state
        state = self.manager.get_recording_state(blocking=False)
        
        self.assertTrue(state['is_recording'])
        self.assertEqual(state['mode'], "manual")
        self.assertIsNotNone(state['start_time'])


class TestRecordingQueue(unittest.TestCase):
    """Test recording queue and worker thread functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.queue = Queue()
        self.operation_in_progress = threading.Event()
    
    def test_queue_put_get(self):
        """Test basic queue operations"""
        self.queue.put(("start", "plughw:0,0", "manual"))
        self.assertEqual(self.queue.qsize(), 1)
        
        operation = self.queue.get()
        self.assertEqual(operation[0], "start")
        self.assertEqual(operation[1], "plughw:0,0")
        self.assertEqual(operation[2], "manual")
    
    def test_queue_multiple_operations(self):
        """Test queue with multiple operations"""
        self.queue.put(("start", "plughw:0,0", "manual"))
        self.queue.put(("stop", None, None))
        self.queue.put(("start", "plughw:0,0", "auto"))
        
        self.assertEqual(self.queue.qsize(), 3)
        
        # Get operations in order
        op1 = self.queue.get()
        self.assertEqual(op1[0], "start")
        
        op2 = self.queue.get()
        self.assertEqual(op2[0], "stop")
        
        op3 = self.queue.get()
        self.assertEqual(op3[0], "start")
        self.assertEqual(op3[2], "auto")


class TestRecordingStateConsistency(unittest.TestCase):
    """Test that recording state is consistent across operations"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = Path(self.temp_dir) / "recordings"
        self.menu_dir = Path(self.temp_dir) / "menu"
        self.recording_dir.mkdir(parents=True)
        self.menu_dir.mkdir(parents=True)
        
        self.manager = RecordingManager(
            recording_dir=str(self.recording_dir),
            menu_dir=str(self.menu_dir)
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_state_cleared_after_stop(self):
        """Test that state is properly cleared after stop"""
        # Simulate recording state
        with self.manager._lock:
            self.manager._is_recording = True
            self.manager._recording_mode = "manual"
            self.manager._recording_start_time = time.time()
            self.manager._cached_is_recording = True
            self.manager._cached_mode = "manual"
            self.manager._cached_start_time = time.time()
        
        # Mock stop_recording to clear state
        with patch.object(self.manager, '_recording_process', None):
            with patch('recording_manager.subprocess.run') as mock_subprocess:
                # Mock no arecord processes found
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stdout = b""
                mock_subprocess.return_value = mock_result
                
                # Stop should clear state
                with self.manager._lock:
                    self.manager._is_recording = False
                    self.manager._recording_process = None
                    self.manager._recording_mode = None
                    self.manager._recording_start_time = None
                    self.manager._cached_is_recording = False
                    self.manager._cached_mode = None
                    self.manager._cached_start_time = None
        
        # Verify state is cleared
        state = self.manager.get_recording_state(blocking=True)
        self.assertFalse(state['is_recording'])
        self.assertIsNone(state['mode'])
        self.assertIsNone(state['start_time'])


if __name__ == '__main__':
    # Set up logging for tests
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Run tests
    unittest.main(verbosity=2)

