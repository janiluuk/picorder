from subprocess import Popen, PIPE, TimeoutExpired
from pygame.locals import KEYDOWN, K_ESCAPE
import pygame
import time
import os
import socket
import sys
import threading
import shutil
import json
import logging
from pathlib import Path
from ui import theme

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

# Setup logging - adapt path based on platform
try:
    if os.path.exists("/home/pi"):
        LOG_DIR = Path("/home/pi/logs")
    else:
        LOG_DIR = Path.home() / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / "picorder.log"
    handlers = [
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
except (OSError, PermissionError):
    # Fallback for test environments or when logs directory can't be created
    LOG_DIR = Path.cwd() / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / "picorder.log"
    handlers = [logging.StreamHandler()]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

if not GPIO_AVAILABLE:
    logger.warning("RPi.GPIO not available - GPIO features disabled")

# Detect platform (Raspberry Pi vs Desktop)
def is_raspberry_pi():
    """Detect if running on Raspberry Pi"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except (OSError, IOError):
        return False

IS_RASPBERRY_PI = is_raspberry_pi()

# Hardware configuration - adapt based on platform
if IS_RASPBERRY_PI:
    # Raspberry Pi configuration (TFT framebuffer)
    SCREEN_DEVICE = "/dev/fb1"
    TOUCH_DEVICE = "/dev/input/touchscreen"
    MOUSE_DRIVER = "TSLIB"
    FRAMEBUFFER = "/dev/fb1"
    # Use /home/pi paths on Raspberry Pi
    BASE_DIR = Path("/home/pi")
else:
    # Desktop configuration (X11)
    SCREEN_DEVICE = None  # Use default X11 display
    TOUCH_DEVICE = None  # Use default mouse
    MOUSE_DRIVER = None  # Use default mouse driver
    FRAMEBUFFER = None
    # Use user's home directory on desktop
    BASE_DIR = Path.home()

PAGE_01 = "01_menu_run.py"
PAGE_02 = "02_menu_system.py"
PAGE_03 = "03_menu_services.py"
PAGE_04 = "04_menu_stats.py"
PAGE_05 = "05_menu_library.py"
SCREEN_OFF = "menu_screenoff.py"

# Directory configuration
MENUDIR = BASE_DIR / "picorder"
RECORDING_DIR = BASE_DIR / "recordings"
CONFIG_FILE = MENUDIR / "config.json"
startpage = PAGE_01

# Recording state - use RecordingManager as single source of truth
from recording_manager import RecordingManager

# Create global RecordingManager instance
_recording_manager = RecordingManager(
    recording_dir=str(RECORDING_DIR),
    menu_dir=str(MENUDIR)
)

# Recording queue and worker thread - shared across all pages
# These must be in menu_settings.py so they persist when pages are loaded via exec()
from queue import Queue
import threading
_recording_queue = None  # Will be initialized on first use
_recording_thread = None  # Will be initialized on first use
_recording_operation_in_progress = None  # Will be initialized on first use
_recording_state_machine = None  # Will be initialized on first use  # Deprecated

# Current page tracking for on_touch() to know which menu is active
_current_page = None  # Will be set by go_to_page()

# Note: All recording state is now managed by RecordingManager (_recording_manager)
# Legacy global variables have been removed - use RecordingManager methods directly

# Activity tracking
last_activity_time = time.time()
SCREEN_TIMEOUT = 30  # seconds
SILENTJACK_SCRIPT = MENUDIR / "silentjack_monitor.sh"

# Constants
PROCESS_TERMINATE_TIMEOUT = 2  # seconds
PROCESS_KILL_DELAY = 0.5  # seconds
AUTO_RECORD_POLL_INTERVAL = 0.5  # seconds
DEVICE_VALIDATION_CACHE_TTL = 5.0  # seconds - cache device validation results
FILE_CHECK_INTERVAL = 1.0  # seconds - check files less frequently when idle

# Disk space and audio constants
MIN_FREE_DISK_SPACE_GB = 0.1  # Minimum free disk space required for recording (100MB)
AUDIO_SAMPLE_MAX = 32768  # 16-bit audio maximum value
SILENCE_THRESHOLD = 0.005  # Audio silence detection threshold
AUDIO_LEVEL_BOOST = 1.2  # Audio level display boost factor
AUDIO_METER_LOW_THRESHOLD = 0.5  # Audio meter color threshold for green
AUDIO_METER_HIGH_THRESHOLD = 0.8  # Audio meter color threshold for red

# Device name display length
MAX_DEVICE_NAME_LENGTH = 20

# Device validation cache
_device_validation_cache = {}
_device_cache_lock = threading.Lock()

# Config cache to reduce file I/O (CRITICAL FIX: Excessive load_config() calls)
_config_cache = None
_config_cache_time = 0
_config_cache_lock = threading.Lock()
CONFIG_CACHE_TTL = 1.0  # Cache config for 1 second to balance freshness and performance

################################################################################

def exit_menu():
    # exit
    pygame.quit()
    sys.exit()

def x(fb, f, a, exit_menu=True):
    if exit_menu:
        pygame.quit()
    ## Requires "Anybody" in dpkg-reconfigure x11-common if we have scrolled pages previously
    run_x = "/usr/bin/sudo FRAMEBUFFER=/dev/%s startx" % fb
    run_cmd(run_x)
    os.execv(f, a)

# Page router - keeps state across page navigation by using exec instead of execvp
def go_to_page(p):
    """Navigate to a different page (preserves state by using exec instead of execvp)"""
    # Use exec() to run the page code in the current process, preserving all state
    # This is safer than execvp() which replaces the process and loses state
    script_dir = Path(__file__).parent.absolute()
    page = script_dir / p
    if not page.exists():
        page = MENUDIR / p
    
    if not page.exists():
        logger.error(f"Page file not found: {p}")
        return
    
    # Read and execute the page file
    # Use an isolated namespace that imports from the current globals
    # This preserves RecordingManager and other shared state while preventing
    # pages from directly modifying each other's variables
    try:
        with open(page, 'r') as f:
            page_code = f.read()
        
        # Create an isolated namespace that has access to shared state
        # Pages can read shared state but cannot modify each other's variables
        # Import key modules and objects that pages need
        page_globals = {}
        
        # Copy essential builtins
        import builtins
        page_globals['__builtins__'] = builtins
        page_globals['__name__'] = '__main__'
        page_globals['__file__'] = str(page)
        
        # Import shared modules (pages can import from them)
        page_globals['menu_settings'] = sys.modules.get('menu_settings', __import__('menu_settings'))
        
        # Copy shared objects and functions that pages need
        # These are references, so pages can use them but changes to the objects
        # themselves will be visible to other pages (which is what we want for shared state)
        shared_items = [
            '_recording_manager',  # Shared RecordingManager instance
            'load_config', 'save_config',  # Config functions
            'get_audio_devices', 'get_disk_space', 'get_current_device_config',  # Device functions
            'run_cmd',  # Command execution
            'logger',  # Logger
            'init', 'update_activity',  # Display functions
            'draw_screen_border', 'populate_screen', 'make_button', 'on_touch',  # UI functions
            'go_to_page',  # Navigation function
            'screen',  # Display surface
            'black', 'white', 'red', 'green', 'tron_light', 'tron_inverse',  # Colors
            'PAGE_01', 'PAGE_02', 'PAGE_03', 'PAGE_04', 'PAGE_05', 'SCREEN_OFF',  # Page constants
            # Recording queue and thread - need to access the actual module's globals
            # These are in 01_menu_run.py's namespace, so we need to import them
        ]
        
        # Get items from menu_settings globals
        for item in shared_items:
            if item in globals():
                page_globals[item] = globals()[item]
        
        # Special handling for 'screen': it's defined in the calling page, not in menu_settings
        # Use inspect to get it from the caller's frame (could be module-level or function-level)
        if 'screen' not in page_globals:
            try:
                import inspect
                # Get the caller's frame (go_to_page is called from a page, so caller is the page)
                caller_frame = inspect.currentframe().f_back
                if caller_frame:
                    # First try caller's globals (if called from module level)
                    if 'screen' in caller_frame.f_globals:
                        page_globals['screen'] = caller_frame.f_globals['screen']
                        logger.debug("Retrieved 'screen' from caller's globals")
                    # Then try caller's locals (if called from a function)
                    elif 'screen' in caller_frame.f_locals:
                        page_globals['screen'] = caller_frame.f_locals['screen']
                        logger.debug("Retrieved 'screen' from caller's locals")
                    # Finally, try the caller's module globals (walk up the frame chain)
                    else:
                        # Walk up frames to find module-level screen
                        frame = caller_frame
                        while frame:
                            if 'screen' in frame.f_globals:
                                page_globals['screen'] = frame.f_globals['screen']
                                logger.debug("Retrieved 'screen' from frame chain")
                                break
                            frame = frame.f_back
            except Exception as e:
                logger.warning(f"Could not retrieve 'screen' from caller frame: {e}")
                # If screen is not available, the page will need to call init() itself
                # This is a fallback - pages should have screen already
        
        # Import pygame and other common modules
        page_globals['pygame'] = __import__('pygame')
        page_globals['os'] = __import__('os')
        page_globals['sys'] = sys
        page_globals['time'] = __import__('time')
        page_globals['Path'] = __import__('pathlib').Path
        
        # Set current page for on_touch() to know which menu is active
        global _current_page
        if p == PAGE_05:
            _current_page = "library"
        elif p == PAGE_01:
            _current_page = "main"
        elif p == PAGE_02:
            _current_page = "settings"
        else:
            _current_page = "other"
        
        # Execute in the isolated namespace
        # Pages can use 'from menu_settings import *' to get additional functions if needed
        exec(compile(page_code, str(page), 'exec'), page_globals)
    except Exception as e:
        logger.error(f"Error loading page {p}: {e}", exc_info=True)
        # Fallback to old method if exec fails
        pygame.quit()
        os.execvp("python3", ["python3", str(page)])
        sys.exit()

def get_hostname():
    # Use list to avoid shell interpretation (safer)
    hostname = run_cmd(["hostname"]).strip()
    # Add leading spaces for formatting (no need to remove last char since strip() handles newlines)
    return "  " + hostname

def get_ip():
    # Get Your External IP Address
    ip_msg = "Not connected"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(('<broadcast>', 0))
        ip_msg=" IP: " + s.getsockname()[0]
    except Exception:
        pass
    return ip_msg

def get_date():
    # Get time and date
    d = time.strftime("%a, %d %b %Y  %H:%M:%S", time.localtime())
    return d

def get_temp():
    # Get CPU temperature
    # Use list to avoid shell interpretation (safer)
    temp = run_cmd(["vcgencmd", "measure_temp"]).strip()
    temp = "Temp: " + temp[5:-1]
    return temp

def get_clock():
    # Use list to avoid shell interpretation (safer)
    clock = run_cmd(["vcgencmd", "measure_clock", "arm"]).strip()
    clock = clock.split("=")
    clock = int(clock[1][:-1]) / 1024 /1024
    clock = "Clock: " + str(clock) + "MHz"
    return clock

def get_volts():
    # Use list to avoid shell interpretation (safer)
    volts = run_cmd(["vcgencmd", "measure_volts"]).strip()
    volts = 'Core:   ' + volts[5:-1]
    return volts

def get_disk_space():
    """Get free disk space"""
    try:
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024**3)
        return "Free: {:.1f}GB".format(free_gb)
    except OSError as e:
        logger.error(f"Error getting disk space: {e}")
        return "Free: N/A"
    except Exception as e:
        logger.error(f"Unexpected error getting disk space: {e}", exc_info=True)
        return "Free: N/A"

def get_current_device_config():
    """Get current audio device and auto-record configuration with validation"""
    config = load_config()
    audio_device = config.get("audio_device", "")
    auto_record = config.get("auto_record", False)
    
    # Validate device - if invalid, disable auto-record
    # Use try-except to ensure validation doesn't hang the UI
    try:
        device_valid = audio_device and is_audio_device_valid(audio_device)
    except Exception as e:
        logger.debug(f"Error validating device during config check: {e}")
        device_valid = False
    
    if not device_valid and auto_record:
        config["auto_record"] = False
        save_config(config)
        auto_record = False
    
    return config, audio_device, auto_record, device_valid

def load_config(force_reload=False):
    """Load configuration from file with caching to reduce file I/O
    
    Args:
        force_reload: If True, bypass cache and reload from file
        
    Returns:
        dict: Configuration dictionary
    """
    global _config_cache, _config_cache_time
    
    default_config = {
        "audio_device": "plughw:0,0",
        "auto_record": True  # Default to True - all code uses True as default for consistency
    }
    
    # CRITICAL FIX: Use cached config if valid and not forcing reload
    current_time = time.time()
    with _config_cache_lock:
        if not force_reload and _config_cache is not None:
            age = current_time - _config_cache_time
            if age < CONFIG_CACHE_TTL:
                # Cache is still valid
                return _config_cache.copy()  # Return copy to prevent external modification
    
    # Cache expired or forced reload - load from file
    try:
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                result = {**default_config, **config}
        else:
            result = default_config.copy()
    except (OSError, IOError, json.JSONDecodeError) as e:
        logger.warning(f"Error loading config: {e}, using defaults")
        result = default_config.copy()
    except Exception as e:
        logger.error(f"Unexpected error loading config: {e}", exc_info=True)
        result = default_config.copy()
    
    # Update cache
    with _config_cache_lock:
        _config_cache = result.copy()
        _config_cache_time = current_time
    
    return result

def save_config(config):
    """Save configuration to file and invalidate cache"""
    global _config_cache
    try:
        config_path = Path(CONFIG_FILE)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # CRITICAL FIX: Invalidate cache after saving to ensure consistency
        with _config_cache_lock:
            _config_cache = None  # Invalidate cache so next load_config() reloads from file
            _config_cache_time = 0
    except (OSError, IOError) as e:
        logger.error(f"Error saving config: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving config: {e}", exc_info=True)

def get_auto_record_enabled():
    """Get auto_record setting from config (MEDIUM PRIORITY FIX: Code duplication #12)
    
    Returns:
        bool: True if auto_record is enabled, False otherwise
    """
    config = load_config()
    return config.get("auto_record", True)  # Consistent default with load_config()

def get_audio_device():
    """Get audio_device setting from config (MEDIUM PRIORITY FIX: Code duplication #12)
    
    Returns:
        str: Audio device string, empty string if not set
    """
    config = load_config()
    return config.get("audio_device", "plughw:0,0")

def get_audio_devices():
    """Get list of available audio input devices"""
    devices = [("", "None (Disabled)")]  # Add "None" option first
    try:
        # Use list to avoid shell interpretation (safer)
        output = run_cmd(["arecord", "-l"])
        for line in output.split('\n'):
            if 'card' in line.lower():
                # Extract card number and device name
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        for i, part in enumerate(parts):
                            if part == 'card' and i + 1 < len(parts):
                                card_num = parts[i+1].rstrip(':')
                                device_name = ' '.join(parts[parts.index('card'):])
                                device_id = "plughw:{},0".format(card_num)
                                # Validate device by testing if it can be opened (don't use cache for enumeration)
                                if validate_audio_device(device_id, use_cache=False):
                                    devices.append((device_id, device_name))
                                break
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Error parsing device line: {e}")
                        pass
        return devices
    except (OSError, ValueError) as e:
        logger.error(f"Error getting audio devices: {e}")
        return devices  # Return at least the "None" option
    except Exception as e:
        logger.error(f"Unexpected error getting audio devices: {e}", exc_info=True)
        return devices  # Return at least the "None" option

def validate_audio_device(device, use_cache=True):
    """Validate that an audio device is available and can be opened (with caching)"""
    if not device or device == "":
        return False
    
    # Check cache first
    if use_cache:
        with _device_cache_lock:
            if device in _device_validation_cache:
                cached_result, cached_time = _device_validation_cache[device]
                if time.time() - cached_time < DEVICE_VALIDATION_CACHE_TTL:
                    return cached_result
    
    # Perform actual validation
    try:
        # Try to list device capabilities (quick check)
        process = Popen(["arecord", "-D", device, "--dump-hw-params"], stdout=PIPE, stderr=PIPE)
        result = process.communicate(timeout=2)[0].decode('utf-8')
        # If device is valid, we should get hardware params, not an error
        is_valid = not ("Invalid" in result or "No such" in result or "cannot find" in result.lower())
        
        # Cache the result
        if use_cache:
            with _device_cache_lock:
                _device_validation_cache[device] = (is_valid, time.time())
        
        return is_valid
    except TimeoutExpired:
        # Device validation timed out - log at debug level to reduce noise
        # This is common on desktop systems without audio hardware
        logger.debug(f"Timeout validating device {device} (device may not be available)")
        return False
    except (OSError, ValueError) as e:
        logger.debug(f"Error validating device {device}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating device {device}: {e}", exc_info=True)
        return False

def is_audio_device_valid(device):
    """Check if the configured audio device is still valid (with caching)"""
    if not device or device == "":
        return False
    # Use cached validation - don't enumerate all devices every time
    return validate_audio_device(device, use_cache=True)

def detect_audio_signal(device, threshold=0.01, sample_duration=0.1):
    """Detect if there's audio signal (for silent jack detection)"""
    try:
        # Use arecord to capture a small sample and check for non-zero data
        # Use shell=True for pipeline command (safer than cmd.split() with pipes)
        # Note: Device is validated elsewhere, so injection risk is minimized
        cmd = "arecord -D {} -d {} -f cd -t raw 2>/dev/null | od -An -td2 | head -1".format(
            device, sample_duration)
        output = run_cmd(cmd)  # run_cmd will detect shell operators and use shell=True
        # Check if output contains non-zero values
        values = [int(x) for x in output.split() if x.isdigit() or (x.startswith('-') and x[1:].isdigit())]
        if values:
            max_val = max([abs(v) for v in values])
            return max_val > threshold * AUDIO_SAMPLE_MAX
        return False
    except (ValueError, OSError) as e:
        logger.debug(f"Error detecting audio signal: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error detecting audio signal: {e}", exc_info=True)
        return False

def get_audio_level(device, sample_duration=0.05):
    """Get current audio level as a normalized value (0.0 to 1.0)"""
    if not device or device == "":
        return 0.0
    
    try:
        # Capture a small audio sample
        process = Popen(
            ["arecord", "-D", device, "-d", str(sample_duration), "-f", "S16_LE", "-t", "raw"],
            stdout=PIPE, stderr=PIPE
        )
        audio_data, _ = process.communicate(timeout=1)
        
        if len(audio_data) < 2:
            return 0.0
        
        # Convert bytes to 16-bit signed integers
        import struct
        samples = struct.unpack('<' + 'h' * (len(audio_data) // 2), audio_data[:len(audio_data) - (len(audio_data) % 2)])
        
        # Calculate RMS (Root Mean Square) for better level representation
        if len(samples) == 0:
            return 0.0
        
        rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
        # Normalize to 0.0-1.0
        level = min(1.0, rms / AUDIO_SAMPLE_MAX)
        
        # Apply some smoothing and scaling for better visual feedback
        # Use logarithmic scaling for more natural meter response
        if level > 0:
            level = (level ** 0.5) * AUDIO_LEVEL_BOOST
            level = min(1.0, level)
        
        return level
    except Exception as e:
        logger.debug(f"Error getting audio level: {e}")
        return 0.0

def start_recording(device, mode="manual"):
    """Start audio recording (wrapper for RecordingManager)
    
    This is a thin wrapper that delegates to RecordingManager.
    All state is managed by RecordingManager - no legacy globals are updated.
    """
    # Skip device validation to avoid blocking - just check if device is configured
    if not device or device == "":
        logger.warning("Cannot start recording: no audio device selected")
        return False
    
    # Don't validate device here - it blocks! Just try to start recording
    # RecordingManager will handle errors gracefully and check disk space internally
    
    # Use RecordingManager to start recording (non-blocking, returns quickly)
    return _recording_manager.start_recording(device, mode)

def start_silentjack(device):
    """Start silentjack monitoring process (wrapper for RecordingManager)
    
    This is a thin wrapper that delegates to RecordingManager.
    All state is managed by RecordingManager.
    """
    return _recording_manager.start_silentjack(device)

def stop_silentjack():
    """Stop silentjack monitoring process (wrapper for RecordingManager)
    
    This is a thin wrapper that delegates to RecordingManager.
    All state is managed by RecordingManager.
    """
    return _recording_manager.stop_silentjack()

def create_silentjack_script(device):
    """Create script that silentjack will call when jack is inserted/removed (wrapper for RecordingManager)"""
    return _recording_manager._create_silentjack_script(device)

def stop_recording():
    """Stop audio recording and rename file with duration (wrapper for RecordingManager)
    
    This is a thin wrapper that delegates to RecordingManager.
    All state is managed by RecordingManager - no legacy globals are updated.
    """
    logger.info("stop_recording() wrapper called - about to call RecordingManager.stop_recording()")
    try:
        success = _recording_manager.stop_recording()
        logger.info(f"stop_recording() wrapper - RecordingManager returned: {success}")
        return success
    except Exception as e:
        logger.error(f"stop_recording() wrapper - Exception calling RecordingManager: {e}", exc_info=True)
        return False

def rename_with_duration(filename, duration_seconds):
    """Rename a recording file to include duration in the name (wrapper for RecordingManager)"""
    return _recording_manager._rename_with_duration(Path(filename), duration_seconds)

def get_recording_status():
    """Get recording status and duration (wrapper for RecordingManager)
    
    This is a thin wrapper that delegates to RecordingManager.
    All state is managed by RecordingManager - no legacy globals are updated.
    """
    return _recording_manager.get_recording_status()

def check_silence(device, duration=20):
    """Check if there's been silence for specified duration (for manual recording)"""
    # This is a simplified check - in practice you'd want to monitor audio levels
    # For now, we'll use a basic detection
    return not detect_audio_signal(device, threshold=SILENCE_THRESHOLD)

def update_activity():
    """Update last activity time (for screen timeout)"""
    global last_activity_time
    last_activity_time = time.time()

def should_screen_timeout():
    """
    Check if screen should timeout.
    
    Screen times out after SCREEN_TIMEOUT seconds of inactivity, but:
    - Never times out while recording (manual or auto)
    - Always checks current state (thread-safe)
    - On desktop, screen timeout is disabled (no GPIO backlight control)
    
    Returns:
        bool: True if screen should timeout, False otherwise
    """
    global last_activity_time
    # On desktop, don't timeout (no backlight to control)
    if not IS_RASPBERRY_PI:
        return False
    
    # Use RecordingManager to check recording state (thread-safe)
    # Screen should never timeout during active recording
    if _recording_manager.is_recording:
        return False
    
    # Check if idle time exceeds timeout threshold
    idle_time = time.time() - last_activity_time
    return idle_time > SCREEN_TIMEOUT

# Turn screen on
def screen_on():
    if GPIO_AVAILABLE and IS_RASPBERRY_PI:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(18, GPIO.OUT)
            backlight = GPIO.PWM(18, 1023)
            backlight.start(100)
            # Don't cleanup GPIO while PWM is active - it will stop the backlight
            # Store reference to keep it alive
            screen_on._backlight = backlight
            logger.debug("Screen turned on")
        except Exception as e:
            logger.error(f"Error turning screen on: {e}")
    # On desktop, screen_on just updates activity (no GPIO control)
    update_activity()
    go_to_page(PAGE_01)

# Turn screen off
def screen_off():
    if GPIO_AVAILABLE and IS_RASPBERRY_PI:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(18, GPIO.OUT)
            backlight = GPIO.PWM(18, 0.1)
            backlight.start(0)
            # Clean up previous backlight if it exists
            if hasattr(screen_on, '_backlight'):
                try:
                    screen_on._backlight.stop()
                except Exception as e:
                    logger.debug(f"Error stopping previous backlight: {e}")
            logger.debug("Screen turned off")
        except Exception as e:
            logger.error(f"Error turning screen off: {e}")
    # On desktop, screen_off is a no-op (screen stays visible)

def check_service(srvc):
    if not srvc:
        return False

    if srvc == "vnc":
        ps_output = run_cmd(['/bin/ps', '-ef'])
        if 'vnc :1' in ps_output:
            return True
        else:
            return False

    try:
        check = "/usr/sbin/service " + srvc + " status"
        status = run_cmd(check)
        if ("is running" in status) or ("active (running)") in status:
            return True
        else:
            return False
    except Exception as e:
        logger.debug(f"Error checking service {srvc}: {e}")
        return False

def s2c(srvc):
    # change service status to colour
    if check_service(srvc):
        return green
    else:
        return tron_light

def toggle_service(srvc):
    if srvc == "vnc":
        if check_service("vnc"):
            run_cmd("/usr/bin/sudo -u pi /usr/bin/vncserver -kill :1")
            return tron_light#True
        else:
            run_cmd("/usr/bin/sudo -u pi /usr/bin/vncserver :1")
            return green#False

    check = "/usr/bin/sudo /usr/sbin/service " + srvc + " status"
    start = "/usr/bin/sudo /usr/sbin/service " + srvc + " start"
    stop = "/usr/bin/sudo /usr/sbin/service " + srvc + " stop"
    status = run_cmd(check)
    if ("is running" in status) or ("active (running)") in status:
        run_cmd(stop)
        return tron_light#True
    else:
        run_cmd(start)
        return green#False
################################################################################

# Colours
# colors    R    G    B
white    = (255, 255, 255)
tron_whi = (189, 254, 255)
red      = (255,   0,   0)
green    = (  0, 255,   0)
blue     = (  0,   0, 255)
tron_blu = (  0, 219, 232)
black    = (  0,   0,   0)
cyan     = ( 50, 255, 255)
magenta  = (255,   0, 255)
yellow   = (255, 255,   0)
tron_yel = (255, 218,  10)
orange   = (255, 127,   0)
tron_ora = (255, 202,   0)

# Tron theme orange
tron_regular = tron_ora
tron_light   = tron_yel
tron_inverse = tron_whi

# Tron theme blue
##tron_regular = tron_blu
##tron_light   = tron_whi
##tron_inverse = tron_yel

################################################################################

label_pos_1 = (32, 30, 48)
label_pos_2 = (32, 105, 36)  # Smaller font for library items to fit on screen
label_pos_3 = (32, 180, 48)
button_pos_1 = (30, 105, 55, 210)
button_pos_2 = (260, 105, 55, 210)
button_pos_3 = (30, 180, 55, 210)
button_pos_4 = (260, 180, 55, 210)
button_pos_5 = (30, 255, 55, 210)
button_pos_6 = (260, 255, 55, 210)

size = width, height = theme.SCREEN_WIDTH, theme.SCREEN_HEIGHT

# Screen drawing constants
SCREEN_BORDER_OUTER = (0, 0, width - 1, height - 1)
SCREEN_BORDER_INNER = (2, 2, width - 5, height - 5)
SCREEN_BORDER_OUTER_WIDTH = 8
SCREEN_BORDER_INNER_WIDTH = 2

################################################################################
# Functions
def draw_screen_border(screen):
    """Draw standard screen border"""
    pygame.draw.rect(screen, tron_regular, SCREEN_BORDER_OUTER, SCREEN_BORDER_OUTER_WIDTH)
    pygame.draw.rect(screen, tron_light, SCREEN_BORDER_INNER, SCREEN_BORDER_INNER_WIDTH)

# define function for printing text in a specific place with a specific width
# and height with a specific colour and border
def make_button(text, pos, colour, screen, bg_color=None, pressed=False):
    """Draw a button with optional background color and pressed state"""
    xpo, ypo, height, width = pos
    
    # Draw background if provided (for active state)
    if bg_color:
        pygame.draw.rect(screen, bg_color, (xpo-10, ypo-10, width, height))
    
    # Draw border - make it brighter if pressed for visual feedback
    border_color = tron_light if pressed else tron_regular
    pygame.draw.rect(screen, border_color, (xpo-10,ypo-10,width,height),3)
    pygame.draw.rect(screen, tron_light, (xpo-9,ypo-9,width-1,height-1),1)
    pygame.draw.rect(screen, border_color, (xpo-8,ypo-8,width-2,height-2),1)
    
    font=pygame.font.Font(None,42)
    label=font.render(str(text).rjust(12), 1, (colour))
    screen.blit(label,(xpo,ypo))

# define function for printing text in a specific place with a specific colour
def make_label(text, pos, colour, screen):
    xpo, ypo, fontsize = pos
    font=pygame.font.Font(None,fontsize)
    label=font.render(str(text), 1, (colour))
    screen.blit(label,(xpo,ypo))

# define function that checks for touch location
def on_touch():
    # get the position that was touched
    try:
        touch_pos_raw = pygame.mouse.get_pos()
        # Ensure we have a tuple with two numeric values
        # Handle both tuple returns and mock objects in tests
        try:
            # If it's already a tuple/list, use it directly
            if isinstance(touch_pos_raw, (tuple, list)) and len(touch_pos_raw) >= 2:
                x = int(touch_pos_raw[0])
                y = int(touch_pos_raw[1])
                touch_pos = (x, y)
            else:
                # Try to access as indexable (handles mocks that return tuples)
                # Convert to tuple to ensure we have proper values
                touch_pos = tuple(touch_pos_raw)
                if len(touch_pos) >= 2:
                    x = int(touch_pos[0])
                    y = int(touch_pos[1])
                    touch_pos = (x, y)
                else:
                    return None
        except (TypeError, ValueError, IndexError, AttributeError):
            return None
    except (TypeError, IndexError, ValueError, AttributeError):
        # If get_pos() returns something unexpected, return None
        return None
    
    # button 1 event x_min, x_max, y_min, y_max
    # Only check library-specific buttons if we're in the library menu
    if _current_page == "library":
        # Check for up button in library (right side, moved up and bigger)
        if 410 <= touch_pos[0] <= 470 and 30 <= touch_pos[1] <= 70:
            return 1
        # Check for down button in library (right side, moved up and bigger)
        if 410 <= touch_pos[0] <= 470 and 75 <= touch_pos[1] <= 115:
            return 2
    
    # Original button 1 (left side, full size)
    if 30 <= touch_pos[0] <= 240 and 105 <= touch_pos[1] <=160:
        return 1
    # Original button 2 (right side, full size)
    if 260 <= touch_pos[0] <= 470 and 105 <= touch_pos[1] <=160:
        return 2
    # button 3 event
    if 30 <= touch_pos[0] <= 240 and 180 <= touch_pos[1] <=235:
        return 3
    # button 4 event
    if 260 <= touch_pos[0] <= 470 and 180 <= touch_pos[1] <=235:
        return 4
    # button 5 event
    if 30 <= touch_pos[0] <= 240 and 255 <= touch_pos[1] <=310:
        return 5
    # button 6 event
    if 260 <= touch_pos[0] <= 470 and 255 <= touch_pos[1] <=310:
        return 6

def run_cmd(cmd):
    """
    Run a command and return its output.
    
    Args:
        cmd: Either a string (will be split for simple commands) or a list of arguments.
             For shell commands with pipes/redirects, use shell=True explicitly.
    
    Returns:
        Decoded output string
    """
    # If cmd is already a list, use it directly (safe - no shell interpretation)
    if isinstance(cmd, list):
        try:
            process = Popen(cmd, stdout=PIPE, stderr=PIPE)
            output, _ = process.communicate()
            return output.decode('utf-8')
        except OSError as e:
            logger.error(f"Error running command {cmd}: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error running command {cmd}: {e}", exc_info=True)
            return ""
    
    # For string commands, check if they contain shell operators
    # If they do, we need shell=True (less safe but necessary for pipes/redirects)
    shell_operators = ['|', '>', '<', '&', ';', '&&', '||', '`', '$(']
    has_shell_ops = any(op in cmd for op in shell_operators) or cmd.strip().startswith('#')
    
    try:
        if has_shell_ops:
            # Shell command with operators - use shell=True but be careful
            process = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
            output, _ = process.communicate()
            return output.decode('utf-8')
        else:
            # Simple command - use shlex.split() to properly handle quoted arguments
            # This is safer than split() as it handles spaces in quoted strings correctly
            import shlex
            try:
                args = shlex.split(cmd)
                process = Popen(args, stdout=PIPE, stderr=PIPE)
                output, _ = process.communicate()
                return output.decode('utf-8')
            except ValueError as e:
                # Invalid quoting in command string
                logger.error(f"Error parsing command '{cmd}': {e}")
                return ""
    except OSError as e:
        logger.error(f"Error running command {cmd}: {e}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error running command {cmd}: {e}", exc_info=True)
        return ""

# Define each button press action
def button(number, _1, _2, _3, _4, _5, _6):
    if number == 1:
        _1()
        return
    if number == 2:
        _2()
        return
    if number == 3:
        _3()
        return
    if number == 4:
        _4()
        return
    if number == 5:
        _5()
        return
    if number == 6:
        _6()
        return

def init(draw=True):
    # init os environment - only set for Raspberry Pi framebuffer mode
    if IS_RASPBERRY_PI:
        if SCREEN_DEVICE:
            os.environ["SDL_FBDEV"] = SCREEN_DEVICE
        if TOUCH_DEVICE:
            os.environ["SDL_MOUSEDEV"] = TOUCH_DEVICE
        if MOUSE_DRIVER:
            os.environ["SDL_MOUSEDRV"] = MOUSE_DRIVER
        
        # Check if display device exists on Raspberry Pi
        if SCREEN_DEVICE and not os.path.exists(SCREEN_DEVICE) and not os.environ.get("DISPLAY"):
            logger.error(f"Display device {SCREEN_DEVICE} not found and no DISPLAY environment variable set.")
            logger.error("This application requires a physical display (TFT screen) or X11 forwarding.")
            raise RuntimeError(f"Display device {SCREEN_DEVICE} not available")
    else:
        # Desktop mode - check for X11 display
        if not os.environ.get("DISPLAY"):
            logger.error("No DISPLAY environment variable set. This application requires X11.")
            raise RuntimeError("No X11 display available")

    try:
        # Initialize pygame modules individually (to avoid ALSA errors)
        pygame.font.init()
        pygame.display.init()
        # Hide mouse cursor on Raspberry Pi, show on desktop
        pygame.mouse.set_visible(0 if IS_RASPBERRY_PI else 1)

        if draw:
            # Customise layout
            # Set size of the screen
            # On desktop, add RESIZABLE flag so window can be resized if needed
            flags = 0 if IS_RASPBERRY_PI else pygame.RESIZABLE
            screen = pygame.display.set_mode(size, flags)
            # Background Color
            screen.fill(black)
            # Draw border
            draw_screen_border(screen)
            # Update display to show initial screen
            pygame.display.update()
            # Set window title on desktop
            if not IS_RASPBERRY_PI:
                pygame.display.set_caption("Picorder - Audio Recorder")

            return screen
    except pygame.error as e:
        logger.error(f"Failed to initialize pygame display: {e}")
        if IS_RASPBERRY_PI:
            logger.error("This application requires a physical display (TFT screen).")
        else:
            logger.error("This application requires X11 display. Make sure DISPLAY is set.")
        raise RuntimeError(f"Failed to initialize display: {e}") from e

def draw_audio_meter(screen, level, x=400, y=30, width=20, height=60):
    """Draw a minimalistic vertical audio level meter"""
    # Draw background (dark)
    pygame.draw.rect(screen, black, (x, y, width, height))
    pygame.draw.rect(screen, tron_regular, (x, y, width, height), 1)
    
    # Calculate filled height based on level (0.0 to 1.0)
    filled_height = int(height * level)
    
    if filled_height > 0:
        # Draw filled portion with color gradient
        # Green for low levels, yellow for mid, red for high
        if level < AUDIO_METER_LOW_THRESHOLD:
            color = green
        elif level < AUDIO_METER_HIGH_THRESHOLD:
            color = tron_yel
        else:
            color = red
        
        # Draw from bottom up
        fill_y = y + height - filled_height
        pygame.draw.rect(screen, color, (x + 1, fill_y, width - 2, filled_height))
        
        # Add a subtle highlight
        if filled_height > 2:
            pygame.draw.line(screen, tron_light, (x + 1, fill_y), (x + width - 2, fill_y), 1)

def populate_screen(names, screen, service=["","","","","",""], label1=True,
        label2=False, label3=False, b12=True, b34=True, b56=True, show_audio_meter=False, audio_level=0.0,
        button_colors=None):
    """
    Populate screen with labels and buttons
    
    Args:
        button_colors: Dict mapping button index (1-6) to background color tuple (R, G, B)
    """
    if button_colors is None:
        button_colors = {}
    
    # Buttons and labels
    # First Row Label
    if label1:
        make_label(names[0], label_pos_1, tron_inverse, screen)
    # Second Row buttons 1 and 2
    if b12:
        bg1 = button_colors.get(1)
        bg2 = button_colors.get(2)
        make_button(names[1], button_pos_1, s2c(service[0]), screen, bg_color=bg1)
        make_button(names[2], button_pos_2, s2c(service[1]), screen, bg_color=bg2)
    elif label2:
        make_label(names[1], label_pos_2, tron_inverse, screen)
    # Third Row buttons 3 and 4
    if b34:
        bg3 = button_colors.get(3)
        bg4 = button_colors.get(4)
        make_button(names[3], button_pos_3, s2c(service[2]), screen, bg_color=bg3)
        make_button(names[4], button_pos_4, s2c(service[3]), screen, bg_color=bg4)
    elif label3:
        make_label(names[3], label_pos_3, tron_inverse, screen)
    # Fourth Row Buttons 5 and 6
    if b56:
        bg5 = button_colors.get(5)
        bg6 = button_colors.get(6)
        make_button(names[5], button_pos_5, s2c(service[4]), screen, bg_color=bg5)
        make_button(names[6], button_pos_6, s2c(service[5]), screen, bg_color=bg6)
    
    # Draw audio meter if requested
    if show_audio_meter:
        draw_audio_meter(screen, audio_level)

def main(buttons=None, update_callback=None, touch_handler=None, action_handlers=None):
    if buttons:
        [_1, _2, _3, _4, _5, _6] = buttons
        sleep_delay=0.1
    else:
        sleep_delay=0.4
    
    print(f"Main loop started (buttons={bool(buttons)}, callback={bool(update_callback)})", flush=True)
    
    # While loop to manage touch screen inputs
    # Note: pygame.event.get() is non-blocking, so timeout check happens every loop iteration
    loop_count = 0
    while 1:
        loop_count += 1
        if loop_count == 1:
            print("Main loop iteration 1", flush=True)
        if loop_count == 2:
            print("Main loop iteration 2", flush=True)
        if loop_count == 10:
            print("Main loop iteration 10", flush=True)
        if loop_count == 30:
            print("Main loop iteration 30 (callback should fire)", flush=True)
        
        # Check screen timeout before processing events
        # This ensures screen can timeout even if no events are received
        # Note: should_screen_timeout() checks recording state, so it's safe to call here
        if should_screen_timeout():
            screen_off()
            # Wait for touch to wake up screen
            # Keep checking for wake-up events, recording state, and audio input
            # Screen will wake if: touched, recording starts, or audio input detected
            # IMPORTANT: Check timeout at the start of the loop to handle timeout correctly
            audio_check_counter = 0  # Check audio every few iterations to reduce CPU usage
            while should_screen_timeout():
                # Process events first (non-blocking) to allow immediate wake on touch
                # This ensures screen can wake up immediately when touched, even during timeout
                events_processed = False
                for event in pygame.event.get():
                    events_processed = True
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        screen_on()
                        update_activity()  # Reset timeout timer
                        break
                
                # Check for audio input every 4 iterations (every ~2 seconds)
                # This reduces CPU usage while still being responsive to audio
                audio_check_counter += 1
                if audio_check_counter >= 4:
                    audio_check_counter = 0
                    try:
                        # Get configured audio device
                        config = load_config()
                        audio_device = config.get("audio_device", "")
                        
                        # Only check audio if device is configured - skip validation to avoid blocking
                        # Validation can block, so just check if device is configured
                        if audio_device:
                            # Check for audio input (threshold: 0.02 = 2% of max level)
                            audio_level = get_audio_level(audio_device, sample_duration=0.05)
                            if audio_level > 0.02:  # Audio detected above threshold
                                logger.debug(f"Audio input detected (level: {audio_level:.3f}), waking screen")
                                screen_on()
                                update_activity()  # Reset timeout timer
                                break
                    except Exception as e:
                        # Don't let audio detection errors prevent screen from working
                        logger.debug(f"Error checking audio input: {e}")
                
                # Short sleep to reduce CPU usage while screen is off
                # If recording starts while screen is off, it will wake automatically
                time.sleep(0.5)
        
        # Process all pending events (non-blocking)
        for event in pygame.event.get():
            if event.type == pygame.MOUSEBUTTONDOWN:
                update_activity()
                if touch_handler and action_handlers:
                    pos = pygame.mouse.get_pos()
                    action = touch_handler(pos)
                    if action and action in action_handlers:
                        action_handlers[action]()
                        pygame.event.pump()
                        pygame.display.update()
                        pygame.event.pump()
                elif buttons:
                    pos = (pygame.mouse.get_pos() [0], pygame.mouse.get_pos() [1])
                    b = on_touch()
                    if b:
                        # Execute button action immediately (non-blocking)
                        # The action will update the display
                        button(b, _1, _2, _3, _4, _5, _6)
                        # Process events immediately after button press to keep UI responsive
                        pygame.event.pump()
                        # Update display after button action (button handler should call update_display)
                        pygame.display.update()
                        # Process events again to ensure UI stays responsive
                        pygame.event.pump()
                else:
                    screen_on()

            #ensure there is always a safe way to end the program if the touch screen fails
            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    sys.exit()
        
        # Call update callback if provided (for dynamic content like recording status)
        # Only call it occasionally to avoid blocking (every 30 iterations = ~3 seconds)
        if update_callback:
            # Use a counter to throttle callback frequency
            if not hasattr(main, '_callback_counter'):
                main._callback_counter = 0
            main._callback_counter += 1
            if main._callback_counter >= 5:  # Call every 5 iterations (~0.5 second) for more responsive updates
                main._callback_counter = 0
                try:
                    # Process events before callback to keep UI responsive
                    pygame.event.pump()
                    # Call callback - wrap in try-except with timeout protection
                    # Use a simple timeout approach: if callback takes too long, skip it
                    import signal
                    def timeout_handler(signum, frame):
                        raise TimeoutError("Callback timeout")
                    
                    # On Unix, we could use signal.alarm, but that's complex
                    # Instead, just call it and hope it's fast
                    # If it blocks, the exception handler will catch it
                    update_callback()
                    # Process events immediately after callback to keep UI responsive
                    pygame.event.pump()
                except (Exception, KeyboardInterrupt) as e:
                    logger.debug(f"Error in update callback (non-fatal): {e}")
                    # Don't let callback errors break the main loop - just continue
                    # Process events even on error to keep UI responsive
                    try:
                        pygame.event.pump()
                    except:
                        pass
        
        if buttons:
            pygame.display.update()
            # Process events every loop iteration to keep UI responsive
            pygame.event.pump()
        ## Reduce CPU utilisation
        time.sleep(sleep_delay)

################################################################################
