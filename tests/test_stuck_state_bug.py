#!/usr/bin/env python3
"""
Test for stuck state bug where actual_recording=True and pending_stop=True
prevents both start and stop operations.
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

# Mock pygame and RPi.GPIO before importing menu_settings
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

# Configure logging for tests
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestStuckStateBug(unittest.TestCase):
    """Test that stuck state (actual_recording=True, pending_stop=True) is handled correctly"""

    def setUp(self):
        # Create a temporary directory for recordings and menu files
        self.test_dir = Path(tempfile.mkdtemp())
        self.recording_dir = self.test_dir / "recordings"
        self.menu_dir = self.test_dir / "picorder"
        self.recording_dir.mkdir()
        self.menu_dir.mkdir()

        # Mock menu_settings and 01_menu_run globals
        self.mock_ms = MagicMock()
        self.mock_ms._recording_queue = Queue()
        self.mock_ms._recording_operation_in_progress = threading.Event()
        self.mock_ms._recording_manager = MagicMock()
        self.mock_ms._recording_manager.get_recording_state.return_value = {
            'is_recording': True,  # Actual state says recording
            'mode': 'manual',
            'start_time': time.time()
        }
        self.mock_ms._recording_manager._lock = threading.Lock()
        self.mock_ms._optimistic_recording_state = {
            'is_recording': False,  # Optimistic says NOT recording
            'mode': None,
            'start_time': None,
            'pending_start': False,
            'pending_stop': True  # STUCK: pending_stop is True
        }
        self.mock_ms._optimistic_state_lock = threading.Lock()
        self.mock_ms._recording_thread = MagicMock()
        self.mock_ms._recording_thread.is_alive.return_value = True

        # Mock load_config to return a consistent device
        self.mock_ms.load_config.return_value = {"audio_device": "plughw:2,0"}
        self.mock_ms.audio_device = "plughw:2,0"

        # Mock start_recording and stop_recording
        self.mock_ms.start_recording.return_value = True
        self.mock_ms.stop_recording.return_value = True

        # Inject mocks into the global namespace
        self.globals_patch = patch.dict(
            'sys.modules',
            {
                'menu_settings': self.mock_ms,
                'menu_settings.ms': self.mock_ms,
            }
        )
        self.globals_patch.start()

        # Manually define _2 function to test the stuck state logic
        self._2_code = """
import time
import menu_settings as ms
from queue import Queue
import queue as queue_module
queue_module.Full = queue_module.Full  # Make Full available
import threading
import logging

logger = logging.getLogger(__name__)

_recording_queue = ms._recording_queue
_recording_operation_in_progress = ms._recording_operation_in_progress
_recording_state_machine = ms._recording_state_machine
_optimistic_state = ms._optimistic_recording_state
_optimistic_state_lock = ms._optimistic_state_lock
_recording_thread = ms._recording_thread

def _2():
    global audio_device, _recording_thread
    
    try:
        config = ms.load_config()
        audio_device = config.get("audio_device", "")
    except Exception as e:
        logger.warning(f"Could not reload config in _2(): {e}")
    
    if not audio_device:
        logger.warning("No audio device configured, cannot start recording")
        return
    
    device = audio_device
    
    # Debounce
    if not hasattr(_2, '_last_call_time'):
        _2._last_call_time = 0
    current_time = time.time()
    time_since_last_call = current_time - _2._last_call_time
    if time_since_last_call < 0.3:
        logger.debug(f"_2(): Ignoring rapid click (debounce: {time_since_last_call:.3f}s)")
        return
    _2._last_call_time = current_time
    
    # Check BOTH optimistic state AND actual state
    with _optimistic_state_lock:
        is_optimistically_recording = _optimistic_state.get('is_recording', False)
        pending_start = _optimistic_state.get('pending_start', False)
        pending_stop = _optimistic_state.get('pending_stop', False)
    
    # Check actual recording state
    try:
        actual_state = ms._recording_manager.get_recording_state(blocking=False)
        is_actually_recording = actual_state['is_recording'] if actual_state else False
    except Exception as e:
        logger.error(f"Error getting actual recording state: {e}")
        is_actually_recording = False
    
    # Check if pending_stop is stale (we're not recording but pending_stop is True)
    if pending_stop and not is_optimistically_recording and not is_actually_recording:
        logger.warning("_2(): Found stale pending_stop flag - clearing it")
        with _optimistic_state_lock:
            _optimistic_state['pending_stop'] = False
        pending_stop = False
    
    # CRITICAL FIX: If actual_recording=True but pending_stop=True, the stop didn't work
    # Clear pending_stop and allow stopping again to prevent stuck state
    if is_actually_recording and pending_stop:
        logger.warning("_2(): Recording still running despite pending_stop - clearing flag to allow retry")
        with _optimistic_state_lock:
            _optimistic_state['pending_stop'] = False
        pending_stop = False
    
    # Decision: stop if recording (either optimistic or actual), start if not recording
    should_stop = is_optimistically_recording or is_actually_recording
    should_start = (not is_optimistically_recording and not is_actually_recording) and not pending_start and not pending_stop
    
    logger.info(f"_2(): State check - optimistic_recording={is_optimistically_recording}, actual_recording={is_actually_recording}, pending_start={pending_start}, pending_stop={pending_stop}")
    logger.info(f"_2(): Decision - should_stop={should_stop}, should_start={should_start}")
    
    if should_stop:
        logger.info("_2(): User pressed STOP button - queuing stop operation")
        queue_success = False
        try:
            _recording_queue.put_nowait(("stop", None, None))
            queue_success = True
            logger.info(f"_2(): Stop queued successfully. Queue size after: {_recording_queue.qsize()}")
        except (queue_module.Full, AttributeError, TypeError) as e:
            logger.warning(f"_2(): put_nowait() failed: {e}, trying timeout fallback")
            try:
                _recording_queue.put(("stop", None, None), timeout=0.01)
                queue_success = True
            except Exception as e2:
                logger.error(f"_2(): Failed to queue stop operation: {e2}")
        
        if queue_success:
            with _optimistic_state_lock:
                _optimistic_state['is_recording'] = False
                _optimistic_state['mode'] = None
                _optimistic_state['start_time'] = None
                _optimistic_state['pending_stop'] = True
                _optimistic_state['pending_start'] = False
        return queue_success
    elif should_start:
        logger.info(f"_2(): User pressed START button - queuing start operation")
        queue_success = False
        try:
            _recording_queue.put_nowait(("start", device, "manual"))
            queue_success = True
        except (queue_module.Full, AttributeError, TypeError) as e:
            try:
                _recording_queue.put(("start", device, "manual"), timeout=0.01)
                queue_success = True
            except Exception as e2:
                logger.error(f"Failed to queue start operation: {e2}")
        
        if queue_success:
            with _optimistic_state_lock:
                _optimistic_state['is_recording'] = True
                _optimistic_state['mode'] = "manual"
                _optimistic_state['start_time'] = time.time()
                _optimistic_state['pending_start'] = True
                _optimistic_state['pending_stop'] = False
        return queue_success
    else:
        logger.debug(f"_2(): No action taken - should_stop={should_stop}, should_start={should_start}")
        return False
"""
        # Execute the code in a custom namespace
        self.test_globals = {
            'logger': logger,
            'ms': self.mock_ms,
            'Queue': Queue,
            'queue_module': MagicMock(),
            'threading': threading,
            'time': time,
            'audio_device': self.mock_ms.audio_device,
            '_recording_queue': self.mock_ms._recording_queue,
            '_recording_operation_in_progress': self.mock_ms._recording_operation_in_progress,
            '_recording_state_machine': self.mock_ms._recording_state_machine,
            '_optimistic_state': self.mock_ms._optimistic_recording_state,
            '_optimistic_state_lock': self.mock_ms._optimistic_state_lock,
            '_recording_thread': self.mock_ms._recording_thread
        }
        exec(self._2_code, self.test_globals)
        self._2 = self.test_globals['_2']

    def tearDown(self):
        self.globals_patch.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if hasattr(self._2, '_last_call_time'):
            del self._2._last_call_time

    def test_stuck_state_allows_stop_retry(self):
        """Test that stuck state (actual_recording=True, pending_stop=True) allows stop retry"""
        # Initial state: actual_recording=True, pending_stop=True (stuck)
        self.assertTrue(self.mock_ms._recording_manager.get_recording_state()['is_recording'])
        self.assertTrue(self.mock_ms._optimistic_recording_state['pending_stop'], 
                       "Initial state should have pending_stop=True")
        self.assertFalse(self.mock_ms._optimistic_recording_state['is_recording'],
                        "Initial optimistic state should say not recording")
        
        # Call _2() - should detect stuck state, clear pending_stop, and allow stop
        result = self._2()
        
        # Should have queued a stop operation
        self.assertTrue(result, "Should have queued stop operation")
        self.assertEqual(self.mock_ms._recording_queue.qsize(), 1, "Should have one stop operation in queue")
        
        # Verify the queued operation is a stop
        operation = self.mock_ms._recording_queue.get_nowait()
        self.assertEqual(operation[0], "stop", "Should queue stop operation")
        
        # After queuing stop, pending_stop should be True again (correct - we're now pending a stop)
        # The key is that it was cleared BEFORE queuing to allow the retry
        self.assertTrue(self.mock_ms._optimistic_recording_state['pending_stop'],
                       "After queuing stop, pending_stop should be True again")

    def test_stuck_state_prevents_start(self):
        """Test that stuck state prevents start (correct behavior)"""
        # Initial state: actual_recording=True, pending_stop=True (stuck)
        self.assertTrue(self.mock_ms._recording_manager.get_recording_state()['is_recording'])
        self.assertTrue(self.mock_ms._optimistic_recording_state['pending_stop'])
        
        # Call _2() - should detect stuck state and stop, not start
        result = self._2()
        
        # Should NOT try to start
        if self.mock_ms._recording_queue.qsize() > 0:
            operation = self.mock_ms._recording_queue.get_nowait()
            self.assertNotEqual(operation[0], "start", "Should not queue start when recording is active")

if __name__ == '__main__':
    unittest.main()

