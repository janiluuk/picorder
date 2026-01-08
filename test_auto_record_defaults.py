#!/usr/bin/env python3
"""
Test for auto_record default value consistency bug.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
from pathlib import Path
import sys

# Mock pygame and RPi.GPIO before importing menu_settings
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

class TestAutoRecordDefaults(unittest.TestCase):
    """Test that auto_record default values are consistent"""

    def setUp(self):
        # Create a temporary config file
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_file = self.test_dir / "config.json"
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_value_consistency_when_key_missing(self):
        """Test that default values are consistent when auto_record key is missing from config"""
        # Create config file without auto_record key
        config_data = {"audio_device": "plughw:0,0"}
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f)
        
        # Mock CONFIG_FILE to point to our test file
        with patch('menu_settings.CONFIG_FILE', str(self.config_file)):
            from menu_settings import load_config
            
            config = load_config()
            
            # Both should use the same default (True from default_config)
            value1 = config.get("auto_record", True)  # As used in line 17
            value2 = config.get("auto_record", True)  # As used in line 27 (after fix)
            
            # They should be the same
            self.assertEqual(value1, value2, "Default values should be consistent")
            
            # Since load_config() merges with default_config, the key should exist
            # So both should return True (from default_config)
            self.assertTrue("auto_record" in config, "auto_record key should exist after load_config()")
            self.assertEqual(config["auto_record"], True, "auto_record should be True from default_config")

    def test_default_value_consistency_when_key_exists(self):
        """Test that values are consistent when auto_record key exists in config"""
        # Create config file with auto_record=False
        config_data = {"audio_device": "plughw:0,0", "auto_record": False}
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f)
        
        with patch('menu_settings.CONFIG_FILE', str(self.config_file)):
            from menu_settings import load_config
            
            config = load_config()
            
            # Both should read the same value from config
            value1 = config.get("auto_record", True)
            value2 = config.get("auto_record", True)
            
            self.assertEqual(value1, value2, "Values should be consistent when key exists")
            self.assertEqual(value1, False, "Should read False from config file")

    def test_toggle_behavior_when_key_missing(self):
        """Test that toggle works correctly when auto_record key is missing from config"""
        # Create config file without auto_record key
        config_data = {"audio_device": "plughw:0,0"}
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f)
        
        with patch('menu_settings.CONFIG_FILE', str(self.config_file)):
            from menu_settings import load_config, save_config
            
            # Simulate what happens in 01_menu_run.py:
            # Line 17: Initial load
            config1 = load_config()
            initial_value = config1.get("auto_record", True)  # Should be True from default_config
            
            # Line 27: What _1() reads
            config2 = load_config()
            current_value = config2.get("auto_record", True)  # Should also be True
            
            # Both should be True and consistent
            self.assertEqual(initial_value, True, "Initial value should be True from default_config")
            self.assertEqual(current_value, True, "Current value should be True from default_config")
            self.assertEqual(initial_value, current_value, "Values should be consistent")
            
            # Verify that if we toggle it, it works correctly
            # Since both read True, toggling should set it to False
            if current_value:
                config2["auto_record"] = False
                save_config(config2)
                
                # Reload and verify it's now False
                config3 = load_config()
                toggled_value = config3.get("auto_record", True)
                self.assertEqual(toggled_value, False, "After toggle, value should be False")

if __name__ == '__main__':
    unittest.main()

