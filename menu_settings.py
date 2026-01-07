from subprocess import Popen, PIPE, call, getoutput
from pygame.locals import KEYDOWN, K_ESCAPE
import pygame
import time
import os
import socket
import sys
import threading
import shutil
import json

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except:
    print("No GPIO package")
    GPIO_AVAILABLE = False

# Hardware
SCREEN_DEVICE = "/dev/fb1"
TOUCH_DEVICE = "/dev/input/touchscreen"
MOUSE_DRIVER = "TSLIB"

PAGE_01 = "01_menu_run.py"
PAGE_02 = "02_menu_system.py"
PAGE_03 = "03_menu_services.py"
PAGE_04 = "04_menu_stats.py"
SCREEN_OFF = "menu_screenoff.py"

# bash export
FRAMEBUFFER = "/dev/fb1"
MENUDIR = "/home/pi/picorder/"
RECORDING_DIR = "/home/pi/recordings/"
CONFIG_FILE = MENUDIR + "config.json"
startpage = PAGE_01

# Recording state
recording_process = None
silentjack_process = None
recording_start_time = None
recording_filename = None
recording_mode = None  # "auto" or "manual"
is_recording = False
last_activity_time = time.time()
SCREEN_TIMEOUT = 30  # seconds
SILENTJACK_SCRIPT = MENUDIR + "silentjack_monitor.sh"

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

def go_to_page(p):
    # next page
    pygame.quit()
    ##startx only works when we don't use subprocess here, don't know why
    page = MENUDIR + p
    os.execvp("python3", ["python3", page])
    sys.exit()

def get_hostname():
    hostname = run_cmd("hostname")
    hostname = "  " + hostname[:-1]
    return hostname

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
    temp = run_cmd("vcgencmd measure_temp")
    temp = "Temp: " + temp[5:-1]
    return temp

def get_clock():
    clock = run_cmd("vcgencmd measure_clock arm")
    clock = clock.split("=")
    clock = int(clock[1][:-1]) / 1024 /1024
    clock = "Clock: " + str(clock) + "MHz"
    return clock

def get_volts():
    volts = run_cmd("vcgencmd measure_volts")
    volts = 'Core:   ' + volts[5:-1]
    return volts

def get_disk_space():
    """Get free disk space"""
    try:
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024**3)
        return "Free: {:.1f}GB".format(free_gb)
    except:
        return "Free: N/A"

def load_config():
    """Load configuration from file"""
    default_config = {
        "audio_device": "plughw:0,0",
        "auto_record": True
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
    except:
        pass
    return default_config

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except:
        pass

def get_audio_devices():
    """Get list of available audio input devices"""
    devices = [("", "None (Disabled)")]  # Add "None" option first
    try:
        output = run_cmd("arecord -l")
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
                                # Validate device by testing if it can be opened
                                if validate_audio_device(device_id):
                                    devices.append((device_id, device_name))
                                break
                    except Exception:
                        pass
        return devices
    except Exception:
        return devices  # Return at least the "None" option

def validate_audio_device(device):
    """Validate that an audio device is available and can be opened"""
    if not device or device == "":
        return False
    try:
        # Try to list device capabilities (quick check)
        cmd = "arecord -D {} --dump-hw-params 2>&1".format(device)
        result = run_cmd(cmd)
        # If device is valid, we should get hardware params, not an error
        if "Invalid" in result or "No such" in result or "cannot find" in result.lower():
            return False
        return True
    except Exception:
        return False

def is_audio_device_valid(device):
    """Check if the configured audio device is still valid"""
    if not device or device == "":
        return False
    devices = get_audio_devices()
    device_ids = [d[0] for d in devices]
    return device in device_ids and validate_audio_device(device)

def detect_audio_signal(device, threshold=0.01, sample_duration=0.1):
    """Detect if there's audio signal (for silent jack detection)"""
    try:
        # Use arecord to capture a small sample and check for non-zero data
        cmd = "arecord -D {} -d {} -f cd -t raw 2>/dev/null | od -An -td2 | head -1".format(
            device, sample_duration)
        output = run_cmd(cmd)
        # Check if output contains non-zero values
        values = [int(x) for x in output.split() if x.isdigit() or (x.startswith('-') and x[1:].isdigit())]
        if values:
            max_val = max([abs(v) for v in values])
            return max_val > threshold * 32768  # 16-bit audio threshold
        return False
    except:
        return False

def start_recording(device, mode="manual"):
    """Start audio recording"""
    global recording_process, recording_start_time, recording_mode, is_recording, recording_filename
    
    if is_recording:
        return
    
    # Create recordings directory if it doesn't exist
    os.makedirs(RECORDING_DIR, exist_ok=True)
    
    # Generate filename with date and time (duration will be added when stopping)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    recording_filename = RECORDING_DIR + "recording_{}.wav".format(timestamp)
    
    # Start arecord process
    cmd = "arecord -D {} -f cd -t wav {}".format(device, recording_filename)
    recording_process = Popen(cmd.split(), stdout=PIPE, stderr=PIPE)
    recording_start_time = time.time()
    recording_mode = mode
    is_recording = True

def start_silentjack(device):
    """Start silentjack monitoring process"""
    global silentjack_process
    
    if silentjack_process is not None:
        # Check if still running
        if silentjack_process.poll() is None:
            return  # Already running
        else:
            silentjack_process = None
    
    # Create monitor script if it doesn't exist
    if not os.path.exists(SILENTJACK_SCRIPT):
        create_silentjack_script(device)
    
    # Start silentjack with monitor script
    # silentjack will call the script when jack is inserted/removed
    cmd = "silentjack -i {} -o {}".format(device, SILENTJACK_SCRIPT)
    silentjack_process = Popen(cmd.split(), stdout=PIPE, stderr=PIPE)

def stop_silentjack():
    """Stop silentjack monitoring process"""
    global silentjack_process
    
    if silentjack_process is not None:
        try:
            silentjack_process.terminate()
            silentjack_process.wait(timeout=2)
        except:
            try:
                silentjack_process.kill()
            except:
                pass
        silentjack_process = None

def create_silentjack_script(device):
    """Create script that silentjack will call when jack is inserted/removed"""
    # Ensure recordings directory exists
    os.makedirs(RECORDING_DIR, exist_ok=True)
    
    script_content = """#!/bin/bash
# Script called by silentjack when jack state changes
# $1 = "in" (plugged) or "out" (unplugged)
# $2 = device name

STATE="$1"
DEVICE="{}"
RECORDING_DIR="{}"
MENUDIR="{}"

# Ensure recordings directory exists
mkdir -p "$RECORDING_DIR"

if [ "$STATE" = "in" ]; then
    # Jack plugged in - start recording
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FILENAME="$RECORDING_DIR/recording_$TIMESTAMP.wav"
    arecord -D "$DEVICE" -f cd -t wav "$FILENAME" &
    echo $! > "$MENUDIR/.recording_pid"
    echo "$FILENAME" > "$MENUDIR/.recording_file"
    echo "$(date +%s)" > "$MENUDIR/.recording_start"
else
    # Jack unplugged - stop recording and rename with duration
    if [ -f "$MENUDIR/.recording_pid" ]; then
        PID=$(cat "$MENUDIR/.recording_pid")
        START_TIME=$(cat "$MENUDIR/.recording_start")
        OLD_FILE=$(cat "$MENUDIR/.recording_file")
        
        # Stop the recording
        kill $PID 2>/dev/null
        sleep 0.5
        
        # Calculate duration and rename
        if [ -f "$OLD_FILE" ]; then
            END_TIME=$(date +%s)
            DURATION=$((END_TIME - START_TIME))
            HOURS=$((DURATION / 3600))
            MINUTES=$(((DURATION % 3600) / 60))
            SECONDS=$((DURATION % 60))
            
            if [ $HOURS -gt 0 ]; then
                DUR_STR=$(printf "%02dh%02dm%02ds" $HOURS $MINUTES $SECONDS)
            else
                DUR_STR=$(printf "%02dm%02ds" $MINUTES $SECONDS)
            fi
            
            BASE_NAME="${OLD_FILE%.wav}"
            NEW_FILE="${BASE_NAME}_${DUR_STR}.wav"
            mv "$OLD_FILE" "$NEW_FILE" 2>/dev/null
        fi
        
        # Clean up
        rm -f "$MENUDIR/.recording_pid" "$MENUDIR/.recording_file" "$MENUDIR/.recording_start"
    fi
fi
""".format(device, RECORDING_DIR, MENUDIR)
    
    with open(SILENTJACK_SCRIPT, 'w') as f:
        f.write(script_content)
    os.chmod(SILENTJACK_SCRIPT, 0o755)

def stop_recording():
    """Stop audio recording and rename file with duration"""
    global recording_process, recording_start_time, recording_mode, is_recording, recording_filename
    
    # If it's a silentjack recording, stop it via the PID file and rename
    if recording_mode == "auto" and os.path.exists(MENUDIR + ".recording_pid"):
        try:
            with open(MENUDIR + ".recording_pid", 'r') as f:
                pid = int(f.read().strip())
            
            # Get start time and filename
            start_time = None
            old_filename = None
            if os.path.exists(MENUDIR + ".recording_start"):
                with open(MENUDIR + ".recording_start", 'r') as f:
                    start_time = float(f.read().strip())
            if os.path.exists(MENUDIR + ".recording_file"):
                with open(MENUDIR + ".recording_file", 'r') as f:
                    old_filename = f.read().strip()
            
            # Stop the process
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(0.5)  # Wait for process to stop
            except:
                pass
            
            # Rename file with duration if we have the info
            if old_filename and start_time and os.path.exists(old_filename):
                duration = int(time.time() - start_time)
                new_filename = rename_with_duration(old_filename, duration)
                if new_filename and os.path.exists(old_filename):
                    try:
                        os.rename(old_filename, new_filename)
                    except:
                        pass
            
            # Clean up files
            for f in [".recording_pid", ".recording_file", ".recording_start"]:
                try:
                    os.remove(MENUDIR + f)
                except:
                    pass
        except:
            pass
    
    # Stop our own recording process
    if recording_process is not None:
        try:
            recording_process.terminate()
            recording_process.wait(timeout=2)
        except:
            try:
                recording_process.kill()
            except:
                pass
        
        # Rename file with duration
        if recording_filename and os.path.exists(recording_filename):
            duration = int(time.time() - recording_start_time)
            new_filename = rename_with_duration(recording_filename, duration)
            if new_filename:
                try:
                    os.rename(recording_filename, new_filename)
                except:
                    pass
        
        recording_process = None
        recording_filename = None
    
    recording_start_time = None
    recording_mode = None
    is_recording = False

def rename_with_duration(filename, duration_seconds):
    """Rename a recording file to include duration in the name"""
    try:
        # Parse duration into hours, minutes, seconds
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        
        # Create duration string
        if hours > 0:
            duration_str = "{:02d}h{:02d}m{:02d}s".format(hours, minutes, seconds)
        else:
            duration_str = "{:02d}m{:02d}s".format(minutes, seconds)
        
        # Extract directory and base filename
        dir_path = os.path.dirname(filename)
        base_name = os.path.basename(filename)
        
        # Remove .wav extension
        if base_name.endswith('.wav'):
            base_name = base_name[:-4]
        
        # Create new filename with duration
        new_filename = os.path.join(dir_path, "{}_{}.wav".format(base_name, duration_str))
        
        return new_filename
    except:
        return None

def get_recording_status():
    """Get recording status and duration"""
    global is_recording, recording_start_time, recording_mode
    
    # Check if silentjack is recording (for auto mode)
    silentjack_recording = False
    silentjack_start = None
    if os.path.exists(MENUDIR + ".recording_start"):
        try:
            with open(MENUDIR + ".recording_start", 'r') as f:
                silentjack_start = float(f.read().strip())
            # Check if process is still running
            if os.path.exists(MENUDIR + ".recording_pid"):
                try:
                    with open(MENUDIR + ".recording_pid", 'r') as f:
                        pid = int(f.read().strip())
                    # Check if process exists
                    try:
                        os.kill(pid, 0)  # Signal 0 just checks if process exists
                        silentjack_recording = True
                    except:
                        # Process doesn't exist, clean up
                        for f in [".recording_pid", ".recording_file", ".recording_start"]:
                            try:
                                os.remove(MENUDIR + f)
                            except:
                                pass
                except:
                    pass
        except:
            pass
    
    # Determine current recording state
    if silentjack_recording and recording_mode == "auto":
        # Silentjack is handling the recording
        duration = int(time.time() - silentjack_start)
        minutes = duration // 60
        seconds = duration % 60
        status = "Auto: {:02d}:{:02d}".format(minutes, seconds)
        return status, duration
    elif is_recording:
        # Manual recording or our process
        duration = int(time.time() - recording_start_time)
        minutes = duration // 60
        seconds = duration % 60
        mode_str = "Auto" if recording_mode == "auto" else "Manual"
        status = "{}: {:02d}:{:02d}".format(mode_str, minutes, seconds)
        return status, duration
    else:
        return "Not Recording", 0

def check_silence(device, duration=20):
    """Check if there's been silence for specified duration (for manual recording)"""
    # This is a simplified check - in practice you'd want to monitor audio levels
    # For now, we'll use a basic detection
    return not detect_audio_signal(device, threshold=0.005)

def update_activity():
    """Update last activity time (for screen timeout)"""
    global last_activity_time
    last_activity_time = time.time()

def should_screen_timeout():
    """Check if screen should timeout (30s idle, but not when recording)"""
    global is_recording, last_activity_time
    if is_recording:
        return False
    return (time.time() - last_activity_time) > SCREEN_TIMEOUT

# Turn screen on
def screen_on():
    if GPIO_AVAILABLE:
        try:
            backlight = GPIO.PWM(18, 1023)
            backlight.start(100)
            GPIO.cleanup()
        except:
            pass
    update_activity()
    go_to_page(PAGE_01)

# Turn screen off
def screen_off():
    if GPIO_AVAILABLE:
        try:
            backlight = GPIO.PWM(18, 0.1)
            backlight.start(0)
        except:
            pass

def check_service(srvc):
    if not srvc:
        return False

    if srvc == "vnc":
        if 'vnc :1' in getoutput('/bin/ps -ef'):
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
    except:
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
label_pos_2 = (32, 105, 48)
label_pos_3 = (32, 180, 48)
button_pos_1 = (30, 105, 55, 210)
button_pos_2 = (260, 105, 55, 210)
button_pos_3 = (30, 180, 55, 210)
button_pos_4 = (260, 180, 55, 210)
button_pos_5 = (30, 255, 55, 210)
button_pos_6 = (260, 255, 55, 210)

size = width, height = 480, 320

################################################################################
# Functions
# define function for printing text in a specific place with a specific width
# and height with a specific colour and border
def make_button(text, pos, colour, screen):
    xpo, ypo, height, width = pos
    pygame.draw.rect(screen, tron_regular, (xpo-10,ypo-10,width,height),3)
    pygame.draw.rect(screen, tron_light, (xpo-9,ypo-9,width-1,height-1),1)
    pygame.draw.rect(screen, tron_regular, (xpo-8,ypo-8,width-2,height-2),1)
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
    touch_pos = pygame.mouse.get_pos()
    touch_pos = (touch_pos[0], touch_pos[1])
    # button 1 event x_min, x_max, y_min, y_max
    if 30 <= touch_pos[0] <= 240 and 105 <= touch_pos[1] <=160:
        return 1
    # button 2 event
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
    process = Popen(cmd.split(), stdout=PIPE)
    output = process.communicate()[0]
    return output.decode('utf-8')

def run_proc(proc, f, a):
    pygame.quit()
    process = call(proc, shell=True)
    os.execv(f, a)

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
    # init os environment
    os.environ["SDL_FBDEV"] = SCREEN_DEVICE
    os.environ["SDL_MOUSEDEV"] = TOUCH_DEVICE
    os.environ["SDL_MOUSEDRV"] = MOUSE_DRIVER

    # Initialize pygame modules individually (to avoid ALSA errors) and hide mouse
    pygame.font.init()
    pygame.display.init()
    pygame.mouse.set_visible(0)

    if draw:
        # Customise layout
        # Set size of the screen
        screen = pygame.display.set_mode(size)
        # Background Color
        screen.fill(black)
        # Outer Border
        pygame.draw.rect(screen, tron_regular, (0,0,479,319),8)
        pygame.draw.rect(screen, tron_light, (2,2,479-4,319-4),2)

        return screen

def populate_screen(names, screen, service=["","","","","",""], label1=True,
        label2=False, label3=False, b12=True, b34=True, b56=True):
    # Buttons and labels
    # First Row Label
    if label1:
        make_label(names[0], label_pos_1, tron_inverse, screen)
    # Second Row buttons 3 and 4
    if b12:
        make_button(names[1], button_pos_1, s2c(service[0]), screen)
        make_button(names[2], button_pos_2, s2c(service[1]), screen)
    elif label2:
        make_label(names[1], label_pos_2, tron_inverse, screen)
    # Third Row buttons 5 and 6
    if b34:
        make_button(names[3], button_pos_3, s2c(service[2]), screen)
        make_button(names[4], button_pos_4, s2c(service[3]), screen)
    elif label3:
        make_label(names[3], label_pos_3, tron_inverse, screen)
    # Fourth Row Buttons
    if b56:
        make_button(names[5], button_pos_5, s2c(service[4]), screen)
        make_button(names[6], button_pos_6, s2c(service[5]), screen)

def main(buttons=[], update_callback=None):
    if buttons:
        [_1, _2, _3, _4, _5, _6] = buttons
        sleep_delay=0.1
    else:
        sleep_delay=0.4
    #While loop to manage touch screen inputs
    while 1:
        # Check screen timeout
        if should_screen_timeout():
            screen_off()
            # Wait for touch to wake up
            while should_screen_timeout():
                for event in pygame.event.get():
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        screen_on()
                        break
                time.sleep(0.5)
        
        for event in pygame.event.get():
            if event.type == pygame.MOUSEBUTTONDOWN:
                update_activity()
                if buttons:
                    pos = (pygame.mouse.get_pos() [0], pygame.mouse.get_pos() [1])
                    b = on_touch()
                    if b:
                        button(b, _1, _2, _3, _4, _5, _6)
                else:
                    screen_on()

            #ensure there is always a safe way to end the program if the touch screen fails
            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    sys.exit()
        
        # Call update callback if provided (for dynamic content like recording status)
        if update_callback and buttons:
            try:
                update_callback()
            except:
                pass
        
        if buttons:
            pygame.display.update()
        ## Reduce CPU utilisation
        time.sleep(sleep_delay)

################################################################################
