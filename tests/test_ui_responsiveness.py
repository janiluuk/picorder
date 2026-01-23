#!/usr/bin/env python3
"""
Tests for UI responsiveness - ensure button handlers don't block
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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock pygame and RPi.GPIO before importing menu_settings
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

# Import the modules we want to test
from recording_manager import RecordingManager
import menu_settings

# Import 01_menu_run.py (name starts with number, need special handling)
import importlib.util
menu_run_path = Path(__file__).parent / "01_menu_run.py"
spec = importlib.util.spec_from_file_location("menu_run", menu_run_path)
menu_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu_run)

# Configure logging for tests
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestUIResponsiveness(unittest.TestCase):
    """Test that UI operations are non-blocking and responsive"""
    
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
            # Re-initialize the global manager in menu_settings to use our mocked paths
            menu_settings._recording_manager = self.manager
            # Reload config in menu_run to pick up new paths
            menu_run.config = menu_settings.load_config()
            menu_run.audio_device = menu_run.config.get("audio_device", "")

        # Ensure the worker thread is started for queue tests
        if not menu_run._recording_thread.is_alive():
            menu_run._recording_thread.start()
        
        # Clear the queue before each test
        while not menu_run._recording_queue.empty():
            try:
                menu_run._recording_queue.get_nowait()
            except:
                pass
        menu_run._recording_operation_in_progress.clear()
        
        # Initialize optimistic state
        if not hasattr(menu_settings, '_optimistic_recording_state'):
            menu_settings._optimistic_recording_state = {
                'is_recording': False,
                'mode': None,
                'start_time': None,
                'pending_start': False,
                'pending_stop': False
            }
        menu_run._optimistic_state = menu_settings._optimistic_recording_state
        
        # Reset optimistic state
        menu_run._optimistic_state['is_recording'] = False
        menu_run._optimistic_state['mode'] = None
        menu_run._optimistic_state['start_time'] = None
        menu_run._optimistic_state['pending_start'] = False
        menu_run._optimistic_state['pending_stop'] = False

    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
        # Ensure the manager state is reset
        with self.manager._lock:
            self.manager._is_recording = False
            self.manager._recording_process = None
            self.manager._recording_filename = None
            self.manager._recording_start_time = None
            self.manager._recording_mode = None
            self.manager._cached_is_recording = False
            self.manager._cached_mode = None
            self.manager._cached_start_time = None
            self.manager._starting_recording = False

    def test_button_handler_returns_quickly(self):
        """Test that _2() button handler returns quickly without blocking"""
        # Mock pygame to avoid display operations
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Measure execution time
            start_time = time.time()
            menu_run._2()
            execution_time = time.time() - start_time
            
            # Should return in less than 50ms (very fast)
            self.assertLess(execution_time, 0.05, 
                          f"Button handler took {execution_time*1000:.2f}ms, should be < 50ms")
            logger.info(f"Button handler execution time: {execution_time*1000:.2f}ms")

    def test_button_handler_queues_operation(self):
        """Test that _2() queues an operation without blocking"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Clear queue
            while not menu_run._recording_queue.empty():
                try:
                    menu_run._recording_queue.get_nowait()
                except:
                    pass
            
            # Call button handler
            menu_run._2()
            
            # Verify operation was queued
            self.assertFalse(menu_run._recording_queue.empty(), 
                           "Operation should be queued")
            
            # Verify it's a start operation (since optimistic state says not recording)
            operation = menu_run._recording_queue.get_nowait()
            self.assertEqual(operation[0], "start", "Should queue start operation")
            self.assertEqual(operation[2], "manual", "Should be manual mode")

    def test_optimistic_state_updated_immediately(self):
        """Test that optimistic state is updated immediately when button is pressed"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Initially not recording
            self.assertFalse(menu_run._optimistic_state['is_recording'])
            
            # Press record button
            menu_run._2()
            
            # Optimistic state should be updated immediately
            self.assertTrue(menu_run._optimistic_state['is_recording'], 
                          "Optimistic state should be updated immediately")
            self.assertEqual(menu_run._optimistic_state['mode'], "manual")
            self.assertTrue(menu_run._optimistic_state['pending_start'])
            self.assertIsNotNone(menu_run._optimistic_state['start_time'])

    def test_stop_button_updates_optimistic_state(self):
        """Test that pressing stop updates optimistic state immediately"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Set optimistic state to recording
            menu_run._optimistic_state['is_recording'] = True
            menu_run._optimistic_state['mode'] = "manual"
            menu_run._optimistic_state['start_time'] = time.time()
            
            # Press stop button (should toggle to stop)
            menu_run._2()
            
            # Optimistic state should be updated immediately
            self.assertFalse(menu_run._optimistic_state['is_recording'],
                           "Optimistic state should show not recording")
            self.assertTrue(menu_run._optimistic_state['pending_stop'])
            
            # Verify stop operation was queued
            operation = menu_run._recording_queue.get_nowait()
            self.assertEqual(operation[0], "stop", "Should queue stop operation")

    def test_multiple_rapid_presses_dont_block(self):
        """Test that multiple rapid button presses don't cause blocking"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Simulate 10 rapid button presses
            start_time = time.time()
            for i in range(10):
                menu_run._2()
                # Small delay to simulate rapid pressing
                time.sleep(0.001)
            total_time = time.time() - start_time
            
            # All 10 presses should complete quickly
            self.assertLess(total_time, 0.1, 
                          f"10 rapid presses took {total_time*1000:.2f}ms, should be < 100ms")
            
            # Queue should have operations (may have duplicates, but that's OK)
            queue_size = menu_run._recording_queue.qsize()
            self.assertGreater(queue_size, 0, "Operations should be queued")
            logger.info(f"10 rapid presses queued {queue_size} operations in {total_time*1000:.2f}ms")

    def test_button_handler_no_display_operations(self):
        """Test that button handler doesn't perform any display operations"""
        # Mock pygame and display functions
        with patch('_01_menu_run.pygame') as mock_pygame, \
             patch('_01_menu_run.update_display') as mock_update_display, \
             patch('_01_menu_run.populate_screen') as mock_populate_screen, \
             patch('_01_menu_run.draw_screen_border') as mock_draw_border:
            
            mock_pygame.event.pump = Mock()
            mock_pygame.display.update = Mock()
            
            # Call button handler
            menu_run._2()
            
            # Verify no display operations were called
            mock_update_display.assert_not_called()
            mock_populate_screen.assert_not_called()
            mock_draw_border.assert_not_called()
            mock_pygame.display.update.assert_not_called()

    def test_button_handler_handles_missing_config_gracefully(self):
        """Test that button handler handles missing config gracefully"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Set audio_device to empty (simulating missing config)
            original_device = menu_run.audio_device
            menu_run.audio_device = ""
            
            try:
                # Should return immediately without error
                start_time = time.time()
                menu_run._2()
                execution_time = time.time() - start_time
                
                # Should return quickly even with missing config
                self.assertLess(execution_time, 0.05)
            finally:
                menu_run.audio_device = original_device

    def test_optimistic_state_syncs_with_actual_state(self):
        """Test that optimistic state eventually syncs with actual state"""
        # Mock pygame
        with patch('_01_menu_run.pygame') as mock_pygame:
            mock_pygame.event.pump = Mock()
            
            # Press record - optimistic state should update
            menu_run._2()
            self.assertTrue(menu_run._optimistic_state['is_recording'])
            
            # Simulate worker completing the operation successfully
            with patch('recording_manager.Popen') as mock_popen, \
                 patch('recording_manager.shutil.disk_usage') as mock_disk:
                mock_disk.return_value.free = 10 * 1024 * 1024 * 1024  # 10GB free
                mock_process = MagicMock()
                mock_process.poll.return_value = None  # Process is running
                mock_popen.return_value = mock_process
                
                # Start recording (simulating worker thread)
                result = self.manager.start_recording("plughw:2,0", "manual")
                self.assertTrue(result)
                
                # Clear pending flag (simulating worker thread)
                menu_run._optimistic_state['pending_start'] = False
                
                # Now optimistic state should match actual state
                # (In real code, update_display() would sync them)
                actual_state = self.manager.get_recording_state(blocking=False)
                if actual_state and actual_state['is_recording']:
                    # Sync optimistic state
                    menu_run._optimistic_state['is_recording'] = True
                    menu_run._optimistic_state['mode'] = actual_state['mode']
                    menu_run._optimistic_state['start_time'] = actual_state['start_time']
                
                # States should match
                self.assertEqual(menu_run._optimistic_state['is_recording'], 
                               actual_state['is_recording'])


if __name__ == '__main__':
    unittest.main()

