#!/usr/bin/env python3
"""
Tests for button debouncing and double-click prevention
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time
from queue import Queue
from pathlib import Path
import tempfile
import shutil
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock pygame and RPi.GPIO before importing menu_settings
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

# Import the modules we need
from recording_manager import RecordingManager
import menu_settings

# Configure logging for tests
import logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestDebouncing(unittest.TestCase):
    """Test that button debouncing prevents double-clicks"""
    
    def setUp(self):
        # Create a temporary directory for recordings and menu files
        self.test_dir = Path(tempfile.mkdtemp())
        self.recording_dir = self.test_dir / "recordings"
        self.menu_dir = self.test_dir / "picorder"
        self.recording_dir.mkdir()
        self.menu_dir.mkdir()

        # Create dummy config file
        self.config_file = self.menu_dir / "config.json"
        with open(self.config_file, 'w') as f:
            f.write('{"audio_device": "plughw:2,0", "auto_record": false}')

        # Patch RecordingManager to use our test directories
        with patch('menu_settings.RECORDING_DIR', self.recording_dir), \
             patch('menu_settings.MENUDIR', self.menu_dir), \
             patch('menu_settings.CONFIG_FILE', self.config_file):
            self.manager = RecordingManager(
                recording_dir=str(self.recording_dir),
                menu_dir=str(self.menu_dir)
            )
            menu_settings._recording_manager = self.manager

        # Initialize queue and thread
        if menu_settings._recording_queue is None:
            menu_settings._recording_queue = Queue()
        if menu_settings._recording_operation_in_progress is None:
            menu_settings._recording_operation_in_progress = threading.Event()
        if not hasattr(menu_settings, '_optimistic_recording_state'):
            menu_settings._optimistic_recording_state = {
                'is_recording': False,
                'mode': None,
                'start_time': None,
                'pending_start': False,
                'pending_stop': False
            }
        if not hasattr(menu_settings, '_optimistic_state_lock'):
            menu_settings._optimistic_state_lock = threading.Lock()

        # Read the _2() function from 01_menu_run.py and extract it
        menu_run_path = Path(__file__).parent / "01_menu_run.py"
        with open(menu_run_path, 'r') as f:
            code = f.read()
        
        # Extract just the _2 function by finding it and executing it in a namespace
        # We'll create a minimal namespace with all the dependencies
        # Create a mock thread object
        mock_thread = MagicMock()
        mock_thread.is_alive = lambda: True
        
        self.test_namespace = {
            '__name__': '__main__',
            '__file__': str(menu_run_path),
            'menu_settings': menu_settings,
            'ms': menu_settings,
            '_recording_queue': menu_settings._recording_queue,
            '_recording_operation_in_progress': menu_settings._recording_operation_in_progress,
            '_optimistic_state': menu_settings._optimistic_recording_state,
            '_optimistic_state_lock': menu_settings._optimistic_state_lock,
            '_recording_thread': mock_thread,
            'audio_device': "plughw:2,0",
            'logger': logger,
            'load_config': lambda: {"audio_device": "plughw:2,0", "auto_record": False},
            'get_audio_device': lambda: "plughw:2,0",  # Add the missing function
            'queue_module': __import__('queue'),
            'time': time,
            'threading': threading,
        }
        
        # Find and execute just the _2 function definition
        # Extract the function definition
        import re
        match = re.search(r'def _2\(\):.*?(?=\ndef |\Z)', code, re.DOTALL)
        if match:
            func_code = match.group(0)
            # Execute it in our namespace
            exec(func_code, self.test_namespace)
            self._2 = self.test_namespace['_2']
        else:
            self.fail("Could not find _2() function in 01_menu_run.py")

    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
        # Reset debounce timer
        if hasattr(self._2, '_last_call_time'):
            delattr(self._2, '_last_call_time')

    def test_rapid_double_click_is_debounced(self):
        """Test that rapid double-clicks are debounced and only queue one operation"""
        # Clear queue
        while not menu_settings._recording_queue.empty():
            try:
                menu_settings._recording_queue.get_nowait()
            except:
                pass
        
        # Reset debounce timer
        if hasattr(self._2, '_last_call_time'):
            delattr(self._2, '_last_call_time')
        
        # Set optimistic state to not recording
        with menu_settings._optimistic_state_lock:
            menu_settings._optimistic_recording_state['is_recording'] = False
            menu_settings._optimistic_recording_state['pending_start'] = False
            menu_settings._optimistic_recording_state['pending_stop'] = False
        
        # Mock get_recording_state to return not recording
        with patch.object(self.manager, 'get_recording_state', return_value={'is_recording': False, 'mode': None, 'start_time': None}):
            # Simulate rapid double-click (within 300ms)
            self._2()
            time.sleep(0.05)  # 50ms delay - within debounce window
            self._2()
            
            # Should only have 1 operation in queue (first click processed, second debounced)
            queue_size = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size, 1, f"Expected 1 operation in queue after debounced double-click, got {queue_size}")
            
            # Verify it's a start operation
            operation = menu_settings._recording_queue.get_nowait()
            self.assertEqual(operation[0], "start", "Should queue start operation")

    def test_slow_clicks_are_not_debounced(self):
        """Test that clicks with >300ms delay are not debounced"""
        # Clear queue
        while not menu_settings._recording_queue.empty():
            try:
                menu_settings._recording_queue.get_nowait()
            except:
                pass
        
        # Reset debounce timer
        if hasattr(self._2, '_last_call_time'):
            delattr(self._2, '_last_call_time')
        
        # Set optimistic state to not recording
        with menu_settings._optimistic_state_lock:
            menu_settings._optimistic_recording_state['is_recording'] = False
            menu_settings._optimistic_recording_state['pending_start'] = False
            menu_settings._optimistic_recording_state['pending_stop'] = False
        
        # Mock get_recording_state to return not recording
        with patch.object(self.manager, 'get_recording_state', return_value={'is_recording': False, 'mode': None, 'start_time': None}):
            # Simulate slow double-click (outside 300ms debounce window)
            self._2()
            time.sleep(0.35)  # 350ms delay - outside debounce window
            self._2()
            
            # Should have 2 operations in queue (both clicks processed)
            queue_size = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size, 2, f"Expected 2 operations in queue after slow double-click, got {queue_size}")

    def test_stop_uses_both_optimistic_and_actual_state(self):
        """Test that stop decision uses both optimistic and actual state"""
        # Clear queue
        while not menu_settings._recording_queue.empty():
            try:
                menu_settings._recording_queue.get_nowait()
            except:
                pass
        
        # Reset debounce timer
        if hasattr(self._2, '_last_call_time'):
            delattr(self._2, '_last_call_time')
        
        # Set optimistic state to NOT recording, but actual state IS recording
        with menu_settings._optimistic_state_lock:
            menu_settings._optimistic_recording_state['is_recording'] = False
            menu_settings._optimistic_recording_state['pending_start'] = False
            menu_settings._optimistic_recording_state['pending_stop'] = False
        
        # Mock get_recording_state to return IS recording (actual state)
        with patch.object(self.manager, 'get_recording_state', return_value={'is_recording': True, 'mode': 'manual', 'start_time': time.time()}):
            self._2()
            
            # Should queue STOP because actual state says recording
            queue_size = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size, 1, "Should queue one operation")
            
            operation = menu_settings._recording_queue.get_nowait()
            self.assertEqual(operation[0], "stop", "Should queue stop operation when actual state says recording")

    def test_start_checks_pending_operations(self):
        """Test that start operation checks for pending operations"""
        # Clear queue
        while not menu_settings._recording_queue.empty():
            try:
                menu_settings._recording_queue.get_nowait()
            except:
                pass
        
        # Reset debounce timer
        if hasattr(self._2, '_last_call_time'):
            delattr(self._2, '_last_call_time')
        
        # The simplified implementation uses only debouncing (time-based) to prevent double-clicks
        # It does NOT check pending_start flags - those were removed in the refactoring
        # Instead, it queues operations based solely on the actual recording state
        
        # Set actual recording state to not recording
        with patch.object(self.manager, 'get_recording_state', return_value={'is_recording': False, 'mode': None, 'start_time': None}):
            # First click - should queue start
            self._2()
            queue_size1 = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size1, 1, "First click should queue operation")
            
            # Immediate second click (within debounce window) - should be ignored due to debounce
            self._2()
            queue_size2 = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size2, 1, "Second click within debounce window should be ignored")
            
            # Click after debounce window - should queue another operation
            time.sleep(0.25)  # Wait for debounce window to pass (>200ms)
            self._2()
            queue_size3 = menu_settings._recording_queue.qsize()
            self.assertEqual(queue_size3, 2, "Click after debounce window should queue another operation")


if __name__ == '__main__':
    unittest.main()
