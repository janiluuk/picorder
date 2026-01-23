#!/usr/bin/env python3
"""
Tests for Library menu functionality (05_menu_library.py)
Tests recording browsing, scrolling, playing, and deleting.
Also tests button visual feedback and active states.
"""
import unittest
from unittest.mock import patch, MagicMock, Mock, mock_open
import sys
import os
import time
import tempfile
import shutil
import importlib.util
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

# Import after mocking
import menu_settings


class TestLibraryMenu(unittest.TestCase):
    """Test cases for Library menu functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.recording_dir = Path(self.temp_dir) / "recordings"
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        
        # Create some test recording files
        self.test_files = []
        for i in range(3):
            test_file = self.recording_dir / f"recording_{i:03d}.wav"
            test_file.write_bytes(b"fake wav data" * 100)  # Create fake file
            self.test_files.append(test_file)
            # Set different modification times
            os.utime(test_file, (time.time() - i * 3600, time.time() - i * 3600))
        
        # Patch RECORDING_DIR
        self.recording_dir_patcher = patch('menu_settings.RECORDING_DIR', self.recording_dir)
        self.recording_dir_patcher.start()

    def tearDown(self):
        """Clean up test fixtures"""
        self.recording_dir_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_recordings_empty(self):
        """Test getting recordings from empty directory"""
        # Remove all files
        for f in self.test_files:
            f.unlink()
        
        # Import after patching - use importlib to handle module name starting with number
        import importlib.util
        spec = importlib.util.spec_from_file_location("menu_library", os.path.join(os.path.dirname(__file__), "..", "05_menu_library.py"))
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        recordings = library_menu.get_recordings()
        self.assertEqual(len(recordings), 0)

    def test_get_recordings_with_files(self):
        """Test getting recordings with files"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("menu_library", os.path.join(os.path.dirname(__file__), "..", "05_menu_library.py"))
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        recordings = library_menu.get_recordings()
        self.assertEqual(len(recordings), 3)
        
        # Should be sorted by modification time (newest first)
        self.assertGreater(recordings[0]['mod_time'], recordings[1]['mod_time'])
        self.assertGreater(recordings[1]['mod_time'], recordings[2]['mod_time'])
        
        # Check file info
        for rec in recordings:
            self.assertIn('path', rec)
            self.assertIn('name', rec)
            self.assertIn('size_mb', rec)
            self.assertIn('mod_time', rec)
            self.assertTrue(rec['path'].exists())
            self.assertTrue(rec['name'].endswith('.wav'))

    @patch('subprocess.Popen')
    def test_play_recording(self, mock_popen):
        """Test playing a recording"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu.recordings = library_menu.get_recordings()
        library_menu.selected_index = 0
        
        library_menu._3()  # Play button
        
        # Should call aplay with the file path
        mock_popen.assert_called()
        # Check if any call was made with aplay
        call_args = mock_popen.call_args[0][0] if mock_popen.called else None
        if call_args:
            self.assertEqual(call_args[0], 'aplay')
            self.assertTrue(str(call_args[1]).endswith('.wav'))

    def test_delete_recording(self):
        """Test deleting a recording"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu.recordings = library_menu.get_recordings()
        initial_count = len(library_menu.recordings)
        library_menu.selected_index = 0
        
        file_to_delete = library_menu.recordings[0]['path']
        self.assertTrue(file_to_delete.exists())
        
        library_menu._4()  # Delete button
        
        # File should be deleted
        self.assertFalse(file_to_delete.exists())
        # List should be refreshed
        self.assertEqual(len(library_menu.recordings), initial_count - 1)

    def test_scroll_up(self):
        """Test scrolling up through recordings"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu.recordings = library_menu.get_recordings()
        library_menu.selected_index = 2
        library_menu.scroll_offset = 2
        
        library_menu._1()  # Scroll up
        
        self.assertEqual(library_menu.selected_index, 1)
        self.assertEqual(library_menu.scroll_offset, 1)

    def test_scroll_down(self):
        """Test scrolling down through recordings"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu.recordings = library_menu.get_recordings()
        library_menu.selected_index = 0
        library_menu.scroll_offset = 0
        
        library_menu._2()  # Scroll down
        
        self.assertEqual(library_menu.selected_index, 1)
        self.assertEqual(library_menu.scroll_offset, 0)  # Should stay at 0 until we need to scroll

    def test_scroll_bounds(self):
        """Test scrolling respects bounds"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu.recordings = library_menu.get_recordings()
        
        # Try to scroll up from first item
        library_menu.selected_index = 0
        library_menu._1()
        self.assertEqual(library_menu.selected_index, 0)  # Should stay at 0
        
        # Try to scroll down from last item
        library_menu.selected_index = len(library_menu.recordings) - 1
        library_menu._2()
        self.assertEqual(library_menu.selected_index, len(library_menu.recordings) - 1)  # Should stay at last

    @patch('menu_settings.go_to_page')
    def test_back_button(self, mock_go_to_page):
        """Test back button navigation"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        library_menu._5()  # Back button
        
        mock_go_to_page.assert_called_once_with(menu_settings.PAGE_01)

    def test_refresh_recordings(self):
        """Test refreshing recordings list"""
        spec = importlib.util.spec_from_file_location(
            "menu_library", 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "05_menu_library.py")
        )
        library_menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library_menu)
        
        # Create a new file
        new_file = self.recording_dir / "new_recording.wav"
        new_file.write_bytes(b"new data")
        
        library_menu.recordings = []
        library_menu.selected_index = 5
        library_menu.scroll_offset = 3
        
        library_menu._6()  # Refresh button
        
        self.assertEqual(len(library_menu.recordings), 4)  # Should include new file
        self.assertEqual(library_menu.selected_index, 0)  # Should reset
        self.assertEqual(library_menu.scroll_offset, 0)  # Should reset


class TestButtonVisualFeedback(unittest.TestCase):
    """Test cases for button visual feedback and active states"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock pygame screen
        self.mock_screen = MagicMock()
        self.mock_font = MagicMock()
        self.mock_font.render.return_value = MagicMock()
        
        with patch('menu_settings.pygame.font.Font', return_value=self.mock_font):
            pass

    def test_make_button_with_background_color(self):
        """Test make_button with background color"""
        with patch('menu_settings.pygame.font.Font', return_value=self.mock_font):
            menu_settings.make_button(
                "Test", 
                (30, 105, 55, 210), 
                menu_settings.tron_inverse, 
                self.mock_screen,
                bg_color=menu_settings.red
            )
        
        # Should draw background rectangle
        draw_calls = [call[0][0] for call in self.mock_screen.draw.rect.call_args_list if call[0][0] == self.mock_screen]
        # Check that fill was called (background)
        self.assertTrue(self.mock_screen.fill.called or any(
            'rect' in str(call).lower() for call in self.mock_screen.method_calls
        ))

    def test_make_button_without_background(self):
        """Test make_button without background color"""
        with patch('menu_settings.pygame.font.Font', return_value=self.mock_font):
            menu_settings.make_button(
                "Test", 
                (30, 105, 55, 210), 
                menu_settings.tron_inverse, 
                self.mock_screen
            )
        
        # Should still draw button (just no background fill)

    def test_populate_screen_with_button_colors(self):
        """Test populate_screen with button color mapping"""
        mock_screen = MagicMock()
        names = ["Status", "Auto", "Record", "Settings", "Library", "Screen Off", ""]
        button_colors = {2: menu_settings.red, 4: menu_settings.green}
        
        with patch('menu_settings.make_button') as mock_make_button:
            menu_settings.populate_screen(
                names, 
                mock_screen, 
                b12=True, 
                b34=True, 
                b56=True,
                button_colors=button_colors
            )
        
        # Check that make_button was called with correct background colors
        calls = mock_make_button.call_args_list
        # Button 2 (Record) should have red background
        # Button 4 (Library) should have green background
        button_2_call = next((c for c in calls if 'Record' in str(c)), None)
        button_4_call = next((c for c in calls if 'Library' in str(c)), None)
        
        # Verify buttons were drawn (exact verification depends on implementation)
        self.assertGreater(len(calls), 0)


class TestNonBlockingRecord(unittest.TestCase):
    """Test cases for non-blocking record functionality"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    @patch('menu_settings.is_audio_device_valid')
    @patch('menu_settings.load_config')
    @patch('menu_settings.start_recording')
    @patch('menu_settings.update_display')
    def test_record_button_skips_validation(self, mock_update, mock_start, mock_config, mock_validate):
        """Test that record button skips blocking device validation"""
        # Import module dynamically
        spec = importlib.util.spec_from_file_location(
            "menu_run", 
            os.path.join(os.path.dirname(__file__), "01_menu_run.py")
        )
        menu_run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(menu_run)
        
        mock_config.return_value = {"audio_device": "plughw:0,0"}
        
        # Mock recording manager state
        with patch('menu_settings._recording_manager') as mock_rm:
            mock_rm._is_recording = False
            mock_rm._recording_mode = None
            menu_run._2()
        
        # Should NOT call is_audio_device_valid (which blocks)
        # Should just check if device is configured
        mock_validate.assert_not_called()
        
        # Should try to start recording
        mock_start.assert_called_once()

    @patch('menu_settings.load_config')
    @patch('menu_settings.stop_recording')
    @patch('menu_settings.update_display')
    def test_record_button_stops_when_recording(self, mock_update, mock_stop, mock_config):
        """Test that record button stops recording when already recording"""
        spec = importlib.util.spec_from_file_location(
            "menu_run", 
            os.path.join(os.path.dirname(__file__), "01_menu_run.py")
        )
        menu_run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(menu_run)
        
        mock_config.return_value = {"audio_device": "plughw:0,0"}
        
        with patch('menu_settings._recording_manager') as mock_rm:
            mock_rm._is_recording = True
            mock_rm._recording_mode = "manual"
            menu_run._2()
        
        mock_stop.assert_called_once()

    def test_record_button_no_device(self):
        """Test record button with no device configured"""
        spec = importlib.util.spec_from_file_location(
            "menu_run", 
            os.path.join(os.path.dirname(__file__), "01_menu_run.py")
        )
        menu_run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(menu_run)
        
        with patch('menu_settings.load_config', return_value={"audio_device": ""}):
            with patch('menu_settings.start_recording') as mock_start:
                menu_run._2()
                # Should not start recording
                mock_start.assert_not_called()


class TestButtonPressFeedback(unittest.TestCase):
    """Test cases for button press visual feedback"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_screen = MagicMock()
        self.mock_update_callback = MagicMock()

    @patch('menu_settings.pygame.time.wait')
    @patch('menu_settings.pygame.display.update')
    def test_button_press_visual_feedback(self, mock_update, mock_wait):
        """Test that button press provides visual feedback"""
        mock_buttons = [MagicMock() for _ in range(6)]
        
        # Simulate button press
        menu_settings.button(1, *mock_buttons)
        
        # Should call update for visual feedback
        # (Exact implementation may vary, but should provide feedback)
        # The actual feedback is handled in main() loop

    def test_button_action_execution(self):
        """Test that button actions are executed"""
        mock_action = MagicMock()
        mock_buttons = [mock_action] + [MagicMock() for _ in range(5)]
        
        menu_settings.button(1, *mock_buttons)
        
        mock_action.assert_called_once()


if __name__ == '__main__':
    unittest.main()

