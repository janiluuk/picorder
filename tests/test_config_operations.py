#!/usr/bin/env python3
"""
Tests for config file operations
Tests cover concurrent access, corruption recovery, caching, and migrations
"""
import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import tempfile
import os
import sys
import threading
import time
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


class TestConfigFileOperations(unittest.TestCase):
    """Test config file loading, saving, and error handling"""

    def setUp(self):
        """Create a temporary config file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = os.path.join(self.temp_dir, "config.json")
        self.original_config_file = menu_settings.CONFIG_FILE
        menu_settings.CONFIG_FILE = Path(self.temp_config)
        
        # Reset config cache
        if hasattr(menu_settings, '_config_cache'):
            menu_settings._config_cache = None
        if hasattr(menu_settings, '_config_cache_time'):
            menu_settings._config_cache_time = 0

    def tearDown(self):
        """Clean up temporary files"""
        menu_settings.CONFIG_FILE = self.original_config_file
        if os.path.exists(self.temp_config):
            os.remove(self.temp_config)
        os.rmdir(self.temp_dir)

    def test_load_config_valid_file(self):
        """Test loading a valid config file"""
        test_config = {
            "audio_device": "plughw:2,0",
            "auto_record": True,
            "screen_timeout": 30
        }
        
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f)
        
        config = menu_settings.load_config(force_reload=True)
        self.assertEqual(config["audio_device"], "plughw:2,0")
        self.assertTrue(config["auto_record"])
        self.assertEqual(config["screen_timeout"], 30)

    def test_load_config_missing_file(self):
        """Test loading when config file doesn't exist"""
        # Don't create the file
        config = menu_settings.load_config(force_reload=True)
        
        # Should return default config
        self.assertIsInstance(config, dict)
        self.assertIn("audio_device", config)

    def test_load_config_corrupted_json(self):
        """Test loading corrupted JSON config"""
        # Write invalid JSON
        with open(self.temp_config, 'w') as f:
            f.write("{invalid json content")
        
        # Should handle gracefully and return default config
        config = menu_settings.load_config(force_reload=True)
        self.assertIsInstance(config, dict)

    def test_load_config_empty_file(self):
        """Test loading empty config file"""
        # Create empty file
        open(self.temp_config, 'w').close()
        
        config = menu_settings.load_config(force_reload=True)
        self.assertIsInstance(config, dict)

    def test_load_config_caching(self):
        """Test that config is cached and not reloaded unnecessarily"""
        test_config = {"audio_device": "plughw:2,0"}
        
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f)
        
        # First load
        config1 = menu_settings.load_config(force_reload=True)
        
        # Modify file
        test_config["audio_device"] = "plughw:0,0"
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f)
        
        # Second load without force_reload - should use cache
        config2 = menu_settings.load_config(force_reload=False)
        
        # Should still have old value from cache
        self.assertEqual(config2["audio_device"], "plughw:2,0")
        
        # Third load with force_reload - should read new value
        config3 = menu_settings.load_config(force_reload=True)
        self.assertEqual(config3["audio_device"], "plughw:0,0")

    def test_save_config_creates_file(self):
        """Test that save_config creates the file if it doesn't exist"""
        test_config = {
            "audio_device": "plughw:2,0",
            "auto_record": False
        }
        
        menu_settings.save_config(test_config)
        
        self.assertTrue(os.path.exists(self.temp_config))
        
        # Verify content
        with open(self.temp_config, 'r') as f:
            saved_config = json.load(f)
        
        self.assertEqual(saved_config["audio_device"], "plughw:2,0")
        self.assertFalse(saved_config["auto_record"])

    def test_save_config_overwrites_existing(self):
        """Test that save_config overwrites existing config"""
        initial_config = {"audio_device": "plughw:0,0"}
        
        with open(self.temp_config, 'w') as f:
            json.dump(initial_config, f)
        
        new_config = {"audio_device": "plughw:2,0", "new_key": "new_value"}
        menu_settings.save_config(new_config)
        
        # Verify overwrite
        with open(self.temp_config, 'r') as f:
            saved_config = json.load(f)
        
        self.assertEqual(saved_config["audio_device"], "plughw:2,0")
        self.assertEqual(saved_config["new_key"], "new_value")

    def test_save_config_preserves_formatting(self):
        """Test that saved config is properly formatted"""
        test_config = {
            "audio_device": "plughw:2,0",
            "nested": {"key": "value"}
        }
        
        menu_settings.save_config(test_config)
        
        # Read raw file
        with open(self.temp_config, 'r') as f:
            content = f.read()
        
        # Should be valid JSON
        parsed = json.loads(content)
        self.assertEqual(parsed["audio_device"], "plughw:2,0")


class TestConcurrentConfigAccess(unittest.TestCase):
    """Test concurrent config file access"""

    def setUp(self):
        """Create a temporary config file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = os.path.join(self.temp_dir, "config.json")
        self.original_config_file = menu_settings.CONFIG_FILE
        menu_settings.CONFIG_FILE = Path(self.temp_config)
        
        # Initialize with test config
        test_config = {"counter": 0}
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f)

    def tearDown(self):
        """Clean up temporary files"""
        menu_settings.CONFIG_FILE = self.original_config_file
        if os.path.exists(self.temp_config):
            os.remove(self.temp_config)
        os.rmdir(self.temp_dir)

    def test_concurrent_reads(self):
        """Test multiple concurrent reads don't cause errors"""
        errors = []
        
        def read_config():
            try:
                config = menu_settings.load_config(force_reload=True)
                self.assertIsInstance(config, dict)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=read_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0, f"Errors during concurrent reads: {errors}")

    def test_concurrent_writes(self):
        """Test multiple concurrent writes are handled"""
        errors = []
        
        def write_config(value):
            try:
                config = menu_settings.load_config(force_reload=True)
                config["test_value"] = value
                menu_settings.save_config(config)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=write_config, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should not crash, though final value may vary
        self.assertEqual(len(errors), 0, f"Errors during concurrent writes: {errors}")
        
        # Verify file is still valid JSON
        config = menu_settings.load_config(force_reload=True)
        self.assertIsInstance(config, dict)


class TestConfigMigration(unittest.TestCase):
    """Test config file migration and version handling"""

    def setUp(self):
        """Create a temporary config file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = os.path.join(self.temp_dir, "config.json")
        self.original_config_file = menu_settings.CONFIG_FILE
        menu_settings.CONFIG_FILE = Path(self.temp_config)

    def tearDown(self):
        """Clean up temporary files"""
        menu_settings.CONFIG_FILE = self.original_config_file
        if os.path.exists(self.temp_config):
            os.remove(self.temp_config)
        os.rmdir(self.temp_dir)

    def test_old_config_format_handling(self):
        """Test handling of old config format (if migration exists)"""
        # Old format without some new keys
        old_config = {
            "audio_device": "plughw:2,0"
            # Missing new keys like auto_record, screen_timeout
        }
        
        with open(self.temp_config, 'w') as f:
            json.dump(old_config, f)
        
        config = menu_settings.load_config(force_reload=True)
        
        # Should have old keys
        self.assertEqual(config["audio_device"], "plughw:2,0")
        
        # Should have default values for new keys
        self.assertIn("auto_record", config)

    def test_extra_keys_preserved(self):
        """Test that unknown keys in config are preserved"""
        config_with_extra = {
            "audio_device": "plughw:2,0",
            "unknown_future_key": "some_value"
        }
        
        with open(self.temp_config, 'w') as f:
            json.dump(config_with_extra, f)
        
        config = menu_settings.load_config(force_reload=True)
        
        # Save and reload
        menu_settings.save_config(config)
        config2 = menu_settings.load_config(force_reload=True)
        
        # Extra key should be preserved
        self.assertEqual(config2.get("unknown_future_key"), "some_value")


class TestConfigCacheInvalidation(unittest.TestCase):
    """Test config cache invalidation behavior"""

    def setUp(self):
        """Create a temporary config file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = os.path.join(self.temp_dir, "config.json")
        self.original_config_file = menu_settings.CONFIG_FILE
        menu_settings.CONFIG_FILE = Path(self.temp_config)
        
        test_config = {"audio_device": "plughw:2,0"}
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f)

    def tearDown(self):
        """Clean up temporary files"""
        menu_settings.CONFIG_FILE = self.original_config_file
        if os.path.exists(self.temp_config):
            os.remove(self.temp_config)
        os.rmdir(self.temp_dir)

    def test_cache_invalidated_on_save(self):
        """Test that cache is invalidated when config is saved"""
        # Load config into cache
        config1 = menu_settings.load_config(force_reload=True)
        self.assertEqual(config1["audio_device"], "plughw:2,0")
        
        # Modify and save
        config1["audio_device"] = "plughw:0,0"
        menu_settings.save_config(config1)
        
        # Load again - should get new value
        config2 = menu_settings.load_config(force_reload=False)
        self.assertEqual(config2["audio_device"], "plughw:0,0")


if __name__ == '__main__':
    unittest.main()
