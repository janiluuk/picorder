#!/usr/bin/env python3
"""
Recording Manager - Handles all recording operations with thread safety
"""
import os
import time
import threading
import logging
from subprocess import Popen, PIPE
from pathlib import Path

# Setup logging
logger = logging.getLogger(__name__)

# Constants
PROCESS_TERMINATE_TIMEOUT = 2  # seconds
PROCESS_KILL_DELAY = 0.5  # seconds
MIN_FREE_DISK_SPACE_GB = 0.1  # Minimum free disk space required for recording (100MB)


class RecordingManager:
    """Manages audio recording operations with thread safety"""
    
    def __init__(self, recording_dir="/home/pi/recordings/", menu_dir="/home/pi/picorder/"):
        self.recording_dir = Path(recording_dir)
        self.menu_dir = Path(menu_dir)
        # Try to create directory, but don't fail if we can't (e.g., in test environment)
        try:
            self.recording_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not create recording directory {self.recording_dir}: {e}")
        
        self._lock = threading.Lock()
        self._recording_process = None
        self._silentjack_process = None
        self._recording_start_time = None
        self._recording_filename = None
        self._recording_mode = None  # "auto" or "manual"
        self._is_recording = False
        
        self.silentjack_script = self.menu_dir / "silentjack_monitor.sh"
        self.recording_pid_file = self.menu_dir / ".recording_pid"
        self.recording_file_file = self.menu_dir / ".recording_file"
        self.recording_start_file = self.menu_dir / ".recording_start"
    
    @property
    def is_recording(self):
        """Check if currently recording"""
        with self._lock:
            return self._is_recording
    
    @property
    def recording_mode(self):
        """Get current recording mode"""
        with self._lock:
            return self._recording_mode
    
    @property
    def recording_start_time(self):
        """Get recording start time"""
        with self._lock:
            return self._recording_start_time
    
    def start_recording(self, device, mode="manual"):
        """Start audio recording"""
        import shutil
        with self._lock:
            if self._is_recording:
                return False
            
            try:
                # Check disk space before recording
                try:
                    stat = shutil.disk_usage(self.recording_dir)
                    free_gb = stat.free / (1024**3)
                    if free_gb < MIN_FREE_DISK_SPACE_GB:
                        logger.error("Insufficient disk space for recording")
                        return False
                except OSError as e:
                    logger.error(f"Error checking disk space: {e}")
                    return False
                
                # Generate filename with timestamp
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                self._recording_filename = self.recording_dir / f"recording_{timestamp}.wav"
                
                # Start arecord process
                cmd = ["arecord", "-D", device, "-f", "cd", "-t", "wav", str(self._recording_filename)]
                self._recording_process = Popen(cmd, stdout=PIPE, stderr=PIPE)
                self._recording_start_time = time.time()
                self._recording_mode = mode
                self._is_recording = True
                logger.info(f"Started {mode} recording: {self._recording_filename}")
                return True
            except OSError as e:
                logger.error(f"OS error starting recording: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error starting recording: {e}", exc_info=True)
                return False
    
    def stop_recording(self):
        """Stop audio recording and rename file with duration"""
        with self._lock:
            if not self._is_recording:
                return False
            
            success = True
            
            # Handle silentjack recordings
            if self._recording_mode == "auto" and self.recording_pid_file.exists():
                success = self._stop_silentjack_recording()
            
            # Stop our own recording process
            if self._recording_process is not None:
                try:
                    self._recording_process.terminate()
                    self._recording_process.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                    logger.debug("Recording process terminated gracefully")
                except TimeoutError:
                    logger.warning("Recording process did not terminate, killing...")
                    try:
                        self._recording_process.kill()
                        self._recording_process.wait()
                    except Exception as e:
                        logger.error(f"Error killing recording process: {e}")
                except Exception as e:
                    logger.error(f"Error terminating recording process: {e}")
                
                # Rename file with duration
                if self._recording_filename and self._recording_filename.exists():
                    duration = int(time.time() - self._recording_start_time)
                    new_filename = self._rename_with_duration(self._recording_filename, duration)
                    if new_filename:
                        try:
                            self._recording_filename.rename(new_filename)
                            logger.info(f"Renamed recording file to: {new_filename}")
                        except OSError as e:
                            logger.error(f"OS error renaming file {self._recording_filename}: {e}")
                        except Exception as e:
                            logger.error(f"Unexpected error renaming file: {e}", exc_info=True)
                
                # Close file handles before clearing
                if self._recording_process is not None:
                    try:
                        if self._recording_process.stdout:
                            self._recording_process.stdout.close()
                        if self._recording_process.stderr:
                            self._recording_process.stderr.close()
                    except Exception:
                        pass
                self._recording_process = None
                self._recording_filename = None
            
            self._recording_start_time = None
            self._recording_mode = None
            self._is_recording = False
            return success
    
    def _stop_silentjack_recording(self):
        """Stop a silentjack-initiated recording"""
        try:
            if not self.recording_pid_file.exists():
                return False
            
            with open(self.recording_pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Get start time and filename
            start_time = None
            old_filename = None
            if self.recording_start_file.exists():
                with open(self.recording_start_file, 'r') as f:
                    start_time = float(f.read().strip())
            if self.recording_file_file.exists():
                with open(self.recording_file_file, 'r') as f:
                    old_filename = Path(f.read().strip())
            
            # Stop the process
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(0.5)
            except Exception:
                pass
            
            # Rename file with duration
            if old_filename and start_time and old_filename.exists():
                duration = int(time.time() - start_time)
                new_filename = self._rename_with_duration(old_filename, duration)
                if new_filename:
                    try:
                        old_filename.rename(new_filename)
                    except Exception:
                        pass
            
            # Clean up files
            for f in [self.recording_pid_file, self.recording_file_file, self.recording_start_file]:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
            
            logger.info("Stopped silentjack recording")
            return True
        except ValueError as e:
            logger.error(f"Invalid PID in silentjack recording file: {e}")
            return False
        except OSError as e:
            logger.error(f"OS error stopping silentjack recording: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error stopping silentjack recording: {e}", exc_info=True)
            return False
    
    def _rename_with_duration(self, filename, duration_seconds):
        """Rename a recording file to include duration"""
        try:
            # Parse duration
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            
            # Create duration string
            if hours > 0:
                duration_str = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
            else:
                duration_str = f"{minutes:02d}m{seconds:02d}s"
            
            # Create new filename
            base_name = filename.stem
            new_filename = filename.parent / f"{base_name}_{duration_str}.wav"
            return new_filename
        except (ValueError, OSError) as e:
            logger.error(f"Error creating duration filename: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating duration filename: {e}", exc_info=True)
            return None
    
    def get_recording_status(self):
        """Get recording status and duration"""
        with self._lock:
            # Check silentjack recording
            silentjack_recording = False
            silentjack_start = None
            if self.recording_start_file.exists():
                try:
                    with open(self.recording_start_file, 'r') as f:
                        silentjack_start = float(f.read().strip())
                    if self.recording_pid_file.exists():
                        try:
                            with open(self.recording_pid_file, 'r') as f:
                                pid = int(f.read().strip())
                            try:
                                os.kill(pid, 0)  # Check if process exists
                                silentjack_recording = True
                            except Exception:
                                # Process doesn't exist, clean up
                                self._cleanup_silentjack_files()
                        except Exception:
                            pass
                except Exception:
                    pass
            
            # Determine current recording state
            if silentjack_recording and self._recording_mode == "auto":
                duration = int(time.time() - silentjack_start)
                minutes = duration // 60
                seconds = duration % 60
                status = f"Auto: {minutes:02d}:{seconds:02d}"
                return status, duration
            elif self._is_recording:
                duration = int(time.time() - self._recording_start_time)
                minutes = duration // 60
                seconds = duration % 60
                mode_str = "Auto" if self._recording_mode == "auto" else "Manual"
                status = f"{mode_str}: {minutes:02d}:{seconds:02d}"
                return status, duration
            else:
                return "Not Recording", 0
    
    def _cleanup_silentjack_files(self):
        """Clean up silentjack state files"""
        for f in [self.recording_pid_file, self.recording_file_file, self.recording_start_file]:
            try:
                f.unlink(missing_ok=True)
            except OSError as e:
                logger.debug(f"Error cleaning up silentjack file {f}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error cleaning up silentjack file {f}: {e}", exc_info=True)
    
    def start_silentjack(self, device):
        """Start silentjack monitoring process"""
        with self._lock:
            if self._silentjack_process is not None:
                if self._silentjack_process.poll() is None:
                    return True  # Already running
                else:
                    self._silentjack_process = None
            
            try:
                # Create monitor script if needed
                if not self.silentjack_script.exists():
                    self._create_silentjack_script(device)
                
                # Start silentjack
                cmd = ["silentjack", "-i", device, "-o", str(self.silentjack_script)]
                self._silentjack_process = Popen(cmd, stdout=PIPE, stderr=PIPE)
                logger.info(f"Started silentjack monitoring for device: {device}")
                return True
            except OSError as e:
                logger.error(f"OS error starting silentjack: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error starting silentjack: {e}", exc_info=True)
                return False
    
    @property
    def is_silentjack_running(self):
        """Check if silentjack is currently running"""
        with self._lock:
            if self._silentjack_process is None:
                return False
            # Check if process is still running (poll() returns None if running)
            try:
                return self._silentjack_process.poll() is None
            except (OSError, ProcessLookupError):
                return False
    
    def stop_silentjack(self):
        """Stop silentjack monitoring process"""
        with self._lock:
            if self._silentjack_process is not None:
                try:
                    self._silentjack_process.terminate()
                    self._silentjack_process.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                    logger.debug("Silentjack process terminated gracefully")
                except TimeoutError:
                    logger.warning("Silentjack process did not terminate, killing...")
                    try:
                        self._silentjack_process.kill()
                        self._silentjack_process.wait()
                    except Exception as e:
                        logger.error(f"Error killing silentjack process: {e}")
                except Exception as e:
                    logger.error(f"Error terminating silentjack process: {e}")
                self._silentjack_process = None
                return True
            return False
    
    def _create_silentjack_script(self, device):
        """Create script that silentjack will call when jack is inserted/removed"""
        # Use .format() instead of f-string to avoid issues with bash ${} syntax
        script_content = """#!/bin/bash
# Script called by silentjack when jack state changes
# $1 = "in" (plugged) or "out" (unplugged)
# $2 = device name

STATE="$1"
DEVICE="{device}"
RECORDING_DIR="{recording_dir}"
MENUDIR="{menu_dir}"

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
        
        # Calculate duration and rename with error checking
        if [ -f "$OLD_FILE" ]; then
            END_TIME=$(date +%s)
            DURATION=$((END_TIME - START_TIME))
            
            # Only rename if duration is valid (greater than 0)
            if [ $DURATION -gt 0 ]; then
                HOURS=$((DURATION / 3600))
                MINUTES=$(((DURATION % 3600) / 60))
                SECONDS=$((DURATION % 60))
                
                if [ $HOURS -gt 0 ]; then
                    DUR_STR=$(printf "%02dh%02dm%02ds" $HOURS $MINUTES $SECONDS)
                else
                    DUR_STR=$(printf "%02dm%02ds" $MINUTES $SECONDS)
                fi
                
                # Extract base filename without .wav extension
                # Use double braces {{}} to escape in Python format() - generates single braces {{}} in bash
                BASE_NAME="${{OLD_FILE%.wav}}"
                # Combine base name and duration with proper variable expansion
                # Double braces {{}} in Python template become single braces {{}} in bash
                # This ensures bash correctly expands both variables as ${{BASE_NAME}} and ${{DUR_STR}}
                # Without braces, bash would interpret $BASE_NAME_ as a single variable name
                NEW_FILE="${{BASE_NAME}}_${{DUR_STR}}.wav"
                
                # Rename with error checking - verify source exists and rename succeeds
                if [ -f "$OLD_FILE" ]; then
                    if mv "$OLD_FILE" "$NEW_FILE" 2>/dev/null && [ -f "$NEW_FILE" ]; then
                        # Successfully renamed - file exists at new location
                        :
                    else
                        # Rename failed - log error (to stderr which silentjack may capture)
                        echo "Error: Failed to rename recording file" >&2
                        # Keep original file to avoid data loss
                    fi
                fi
            fi
        fi
        
        # Clean up
        rm -f "$MENUDIR/.recording_pid" "$MENUDIR/.recording_file" "$MENUDIR/.recording_start"
    fi
fi
""".format(
            device=device,
            recording_dir=self.recording_dir,
            menu_dir=self.menu_dir
        )
        try:
            with open(self.silentjack_script, 'w') as f:
                f.write(script_content)
            os.chmod(self.silentjack_script, 0o755)
            logger.info(f"Created silentjack script: {self.silentjack_script}")
            return True
        except OSError as e:
            logger.error(f"OS error creating silentjack script: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating silentjack script: {e}", exc_info=True)
            return False
    
    def check_silentjack_recording(self):
        """Check if silentjack has started a recording"""
        if not self.recording_start_file.exists():
            return False, None
        
        try:
            with open(self.recording_start_file, 'r') as f:
                start_time = float(f.read().strip())
            
            if not self.recording_pid_file.exists():
                return False, None
            
            with open(self.recording_pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            try:
                os.kill(pid, 0)  # Check if process exists
                return True, start_time
            except Exception:
                self._cleanup_silentjack_files()
                return False, None
        except Exception:
            return False, None

