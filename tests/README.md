# Tests Directory

This directory contains all unit and integration tests for the Picorder project.

## Running Tests

### Run all tests
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### Run a specific test module
```bash
python3 -m unittest tests.test_menu_settings -v
```

### Run recording functionality tests (via script)
```bash
./run_tests.sh
```

## Test Structure

- `test_audio_device_validation.py` - Audio device validation tests
- `test_auto_record_defaults.py` - Auto-record default value tests
- `test_config_operations.py` - Configuration file operations tests
- `test_debouncing.py` - Button debouncing tests
- `test_disk_space_monitoring.py` - Disk space monitoring tests
- `test_integration.py` - Integration tests for recording workflows
- `test_library_menu.py` - Library menu functionality tests
- `test_menu_settings.py` - Menu settings module tests
- `test_recording_functionality.py` - Recording start/stop and state management tests
- `test_recording_manager.py` - Recording manager tests
- `test_screen_management.py` - Screen management and timeout tests
- `test_stuck_state_bug.py` - Tests for stuck state bug fixes
- `test_ui_helpers.py` - UI helper function tests
- `test_ui_responsiveness.py` - UI responsiveness tests
- `test_wrapper_functions.py` - Wrapper function tests

## CI/CD

Tests are automatically run on push and pull requests via GitHub Actions. See `.github/workflows/tests.yml` for configuration.
