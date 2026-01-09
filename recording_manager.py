#!/usr/bin/env python3
"""
Recording Manager - Handles all recording operations with thread safety
"""
import os
import time
import threading
import logging
import subprocess
from subprocess import Popen, PIPE, TimeoutExpired
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
        self._starting_recording = False  # Flag to prevent concurrent start attempts
        
        # Cached state for non-blocking reads (updated atomically with lock)
        # These are updated whenever _is_recording changes, allowing fast reads without lock
        self._cached_is_recording = False
        self._cached_mode = None
        self._cached_start_time = None
        
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
    
    def get_recording_state(self, blocking=True):
        """Get all recording state in one lock acquisition (faster than multiple property calls)
        
        Args:
            blocking: If False, returns cached state if lock is held (non-blocking)
        """
        if blocking:
            with self._lock:
                # Update cache while we have the lock
                self._cached_is_recording = self._is_recording
                self._cached_mode = self._recording_mode
                self._cached_start_time = self._recording_start_time
                return {
                    'is_recording': self._is_recording,
                    'mode': self._recording_mode,
                    'start_time': self._recording_start_time
                }
        else:
            # Non-blocking: try to acquire lock, return cached state if held
            if self._lock.acquire(blocking=False):
                try:
                    # Update cache while we have the lock
                    self._cached_is_recording = self._is_recording
                    self._cached_mode = self._recording_mode
                    self._cached_start_time = self._recording_start_time
                    return {
                        'is_recording': self._is_recording,
                        'mode': self._recording_mode,
                        'start_time': self._recording_start_time
                    }
                finally:
                    self._lock.release()
            else:
                # Lock is held - return cached state (may be slightly stale but won't block)
                # Also check if arecord process is actually running as a fallback
                cached_state = {
                    'is_recording': self._cached_is_recording,
                    'mode': self._cached_mode,
                    'start_time': self._cached_start_time
                }
                # If cache says not recording, double-check with process check
                if not self._cached_is_recording:
                    # Quick check if arecord is running (non-blocking)
                    try:
                        import subprocess
                        # Try to get device from config to check more specifically
                        try:
                            from menu_settings import load_config
                            config = load_config()
                            audio_device = config.get("audio_device", "")
                            if audio_device:
                                # Check for arecord with this specific device
                                result = subprocess.run(["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                                        capture_output=True, timeout=0.05)
                                if result.returncode == 0 and result.stdout.strip():
                                    # arecord is running but cache says not recording - return corrected state
                                    logger.debug("Found arecord process but cache says not recording - cache may be stale")
                                    # Try to estimate start time from file modification time
                                    start_time_estimate = None
                                    try:
                                        from pathlib import Path
                                        recordings_dir = Path(self.recording_dir)
                                        if recordings_dir.exists():
                                            wav_files = list(recordings_dir.glob("recording_*.wav"))
                                            if wav_files:
                                                # Get most recent file
                                                wav_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                                                most_recent = wav_files[0]
                                                # Estimate start time from file modification time
                                                start_time_estimate = most_recent.stat().st_mtime
                                    except:
                                        pass
                                    if start_time_estimate is None:
                                        import time
                                        start_time_estimate = time.time()
                                    # Return corrected state with estimated start time
                                    return {
                                        'is_recording': True,
                                        'mode': 'manual',  # Default to manual if unknown
                                        'start_time': start_time_estimate
                                    }
                        except:
                            pass
                    except:
                        pass
                return cached_state
    
    def _kill_zombie_arecord_processes(self, device):
        """Kill any zombie arecord processes that might be holding the device"""
        # Use a very short timeout to avoid blocking the UI
        # If cleanup takes too long, just skip it and try anyway
        try:
            import shlex
            # Escape device for shell safety
            device_escaped = shlex.quote(device)
            cmd = f"pgrep -f 'arecord.*-D.*{device_escaped}'"
            # Use very short timeout - if it takes longer, skip cleanup
            # Reduced to 0.05s to minimize blocking
            result = subprocess.run(cmd, shell=True, capture_output=True, timeout=0.05, text=True)
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                logger.warning(f"Found {len(pids)} zombie arecord process(es) for device {device}, killing...")
                # Kill all processes immediately without waiting
                for pid_str in pids:
                    try:
                        pid = int(pid_str.strip())
                        # Send SIGKILL immediately (no SIGTERM, no wait)
                        try:
                            os.kill(pid, 9)  # SIGKILL - immediate kill
                        except ProcessLookupError:
                            pass  # Already dead
                        except PermissionError:
                            pass  # Can't kill (might be different user)
                    except (ValueError, ProcessLookupError, PermissionError):
                        pass  # PID invalid or already dead
                # No sleep - device should be released immediately after SIGKILL
        except subprocess.TimeoutExpired:
            # Timeout is OK - just continue without cleanup
            logger.debug("Timeout checking for zombie processes, continuing...")
        except Exception as e:
            logger.debug(f"Error killing zombie arecord processes: {e}")
    
    def start_recording(self, device, mode="manual"):
        """Start audio recording"""
        import shutil
        with self._lock:
            # Check if already recording or in the process of starting
            if self._is_recording or self._starting_recording:
                return False
            
            # Check disk space before recording (quick check)
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
            recording_filename = self.recording_dir / f"recording_{timestamp}.wav"
            
            # Prepare command
            cmd = ["arecord", "-D", device, "-f", "cd", "-t", "wav", str(recording_filename)]
            
            # Set flag to prevent concurrent start attempts before releasing lock
            self._starting_recording = True
        
        # Release lock before starting process (don't do cleanup upfront - only if needed)
        # Note: _starting_recording flag is set to prevent race conditions
        try:
            # Start arecord process (non-blocking)
            recording_process = Popen(cmd, stdout=PIPE, stderr=PIPE)
            
            # Give it a very brief moment to fail if device is invalid or busy (non-blocking check)
            # This allows arecord to fail immediately if device doesn't exist or is busy
            time.sleep(0.005)  # 5ms - minimal delay, just enough for immediate failures
            
            # Check if process already failed (non-blocking poll)
            return_code = recording_process.poll()
            if return_code is not None:
                # Process already failed - read error message
                stderr_output = b""
                try:
                    # Try to read stderr (non-blocking, may fail if pipe closed)
                    import select
                    if select.select([recording_process.stderr], [], [], 0)[0]:
                        stderr_output = recording_process.stderr.read(1024)
                except:
                    pass
                
                error_msg = stderr_output.decode('utf-8', errors='ignore').strip()
                
                # Check if it's a "device busy" error - try cleanup and retry once
                if "Device or resource busy" in error_msg or "device busy" in error_msg.lower():
                    logger.warning(f"Device busy, attempting cleanup and retry...")
                    # Clean up the failed process first
                    try:
                        recording_process.terminate()
                        try:
                            recording_process.wait(timeout=0.1)
                        except:
                            recording_process.kill()
                    except:
                        pass
                    
                    # Only now do we try to kill zombie processes (lazy cleanup)
                    # Use a very short timeout to avoid blocking
                    self._kill_zombie_arecord_processes(device)
                    time.sleep(0.02)  # Reduced from 0.05s - minimal delay (20ms)
                    
                    # Try once more
                    recording_process = Popen(cmd, stdout=PIPE, stderr=PIPE)
                    time.sleep(0.005)
                    return_code = recording_process.poll()
                    if return_code is not None:
                        # Still failed after retry
                        stderr_output = b""
                        try:
                            import select
                            if select.select([recording_process.stderr], [], [], 0)[0]:
                                stderr_output = recording_process.stderr.read(1024)
                        except:
                            pass
                        error_msg = stderr_output.decode('utf-8', errors='ignore').strip()
                        logger.error(f"arecord failed after retry (exit code {return_code}): {error_msg}")
                        try:
                            recording_process.terminate()
                            try:
                                recording_process.wait(timeout=0.1)
                            except:
                                recording_process.kill()
                        except:
                            pass
                        # Clear the starting flag on failure
                        with self._lock:
                            self._starting_recording = False
                        return False
                    # Retry succeeded - fall through to success case
                else:
                    # Other error (not device busy)
                    logger.error(f"arecord failed immediately (exit code {return_code}): {error_msg}")
                    try:
                        recording_process.terminate()
                        try:
                            recording_process.wait(timeout=0.5)
                        except:
                            recording_process.kill()
                    except:
                        pass
                    # Clear the starting flag on failure
                    with self._lock:
                        self._starting_recording = False
                    return False
            
            # Process started successfully - update state (re-acquire lock)
            with self._lock:
                self._recording_process = recording_process
                self._recording_filename = recording_filename
                self._recording_start_time = time.time()
                self._recording_mode = mode
                self._is_recording = True
                self._cached_is_recording = True
                self._cached_mode = mode
                self._cached_start_time = self._recording_start_time
                self._starting_recording = False  # Clear the starting flag
                logger.info(f"Started {mode} recording: {self._recording_filename}")
                return True
                
        except OSError as e:
            logger.error(f"OS error starting recording: {e}")
            # Clear the starting flag on error
            with self._lock:
                self._starting_recording = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting recording: {e}", exc_info=True)
            # Clear the starting flag on error
            with self._lock:
                self._starting_recording = False
            return False
    
    def stop_recording(self):
        """Stop audio recording and rename file with duration"""
        logger.info("RecordingManager.stop_recording() called - entering function")
        # Get process and state while holding lock (quick operations only)
        recording_process = None
        recording_filename = None
        recording_start_time = None
        recording_mode = None
        needs_silentjack_stop = False
        
        logger.info("RecordingManager.stop_recording() - about to acquire lock")
        with self._lock:
            logger.info(f"RecordingManager.stop_recording() - inside lock: _is_recording={self._is_recording}, _recording_process={self._recording_process is not None}")
            # Capture any process that exists, even if _is_recording is False
            # This handles cases where state is out of sync
            recording_process = self._recording_process
            recording_filename = self._recording_filename
            recording_start_time = self._recording_start_time
            recording_mode = self._recording_mode
            
            if not self._is_recording:
                logger.warning("stop_recording() called but _is_recording is False")
                # Even if _is_recording is False, if there's a process, we should kill it
                if recording_process is not None:
                    logger.warning("stop_recording() called but _is_recording is False, but _recording_process exists - will kill process anyway")
                    # Clear the process reference
                    self._recording_process = None
                    self._recording_filename = None
                    self._recording_start_time = None
                    self._recording_mode = None
                    # Set needs_silentjack_stop to False since we don't know the mode
                    needs_silentjack_stop = False
                    # Don't return here - continue to kill the process below
                else:
                    # No process reference, but check if arecord is actually running
                    # This handles cases where state is out of sync
                    logger.warning("stop_recording() called but _is_recording is False and no process reference")
                    logger.info("Checking for running arecord processes as fallback...")
                    # We'll check for arecord processes outside the lock
                    # Set a flag to indicate we should check
                    should_check_arecord = True
                    # Don't return yet - we'll check arecord processes below
            else:
                logger.info(f"Stopping recording (mode: {self._recording_mode}, filename: {self._recording_filename})")
                # Check if we need to stop silentjack (quick check)
                needs_silentjack_stop = (recording_mode == "auto" and self.recording_pid_file.exists())
                
                # Clear state immediately (before waiting for process)
                self._recording_process = None
                self._recording_filename = None
                self._recording_start_time = None
                self._recording_mode = None
                self._is_recording = False
                self._cached_is_recording = False
                self._cached_mode = None
                self._cached_start_time = None
                logger.info("State cleared in stop_recording()")
        
        # Release lock before blocking operations
        
        # If we didn't have a process reference but _is_recording was False,
        # check for arecord processes as a fallback
        if recording_process is None and not self._is_recording:
            logger.info("No process reference and state says not recording, checking for arecord processes...")
            # Get the device from config to check for arecord processes
            try:
                from menu_settings import load_config
                config = load_config()
                audio_device = config.get("audio_device", "")
                if audio_device:
                    # Check for arecord processes
                    import subprocess
                    result = subprocess.run(["pgrep", "-f", f"arecord.*-D.*{audio_device}"], 
                                          capture_output=True, timeout=0.1)
                    if result.returncode == 0 and result.stdout.strip():
                        logger.warning(f"Found arecord process running but no process reference - killing it")
                        # Kill the arecord processes
                        self._kill_zombie_arecord_processes(audio_device)
                        # Clear BOTH cached state AND actual state since we just killed the process
                        with self._lock:
                            # Clear actual state
                            self._is_recording = False
                            self._recording_process = None
                            self._recording_filename = None
                            self._recording_start_time = None
                            self._recording_mode = None
                            # Clear cached state
                            self._cached_is_recording = False
                            self._cached_mode = None
                            self._cached_start_time = None
                            logger.info("Cleared both actual and cached state after killing arecord processes")
                        # Try to find the most recent recording file and rename it if possible
                        # This is best-effort since we don't have the filename
                        try:
                            from pathlib import Path
                            recordings_dir = Path(self.recording_dir)
                            if recordings_dir.exists():
                                # Find the most recent .wav file that starts with "recording_"
                                wav_files = list(recordings_dir.glob("recording_*.wav"))
                                if wav_files:
                                    # Sort by modification time, most recent first
                                    wav_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                                    most_recent = wav_files[0]
                                    # Try to get duration from file size or use a default
                                    # For now, just log it
                                    logger.info(f"Most recent recording file: {most_recent}")
                        except:
                            pass
                        return True  # Consider it successful if we killed the process
                    else:
                        logger.info("No arecord processes found - nothing to stop")
                        return False
            except Exception as e:
                logger.error(f"Error checking for arecord processes: {e}", exc_info=True)
                return False
        
        success = True
        
        # Handle silentjack recordings (outside lock)
        if needs_silentjack_stop:
            success = self._stop_silentjack_recording()
        
        # Stop our own recording process (outside lock to avoid blocking)
        if recording_process is not None:
            logger.info(f"Terminating recording process (PID: {recording_process.pid if hasattr(recording_process, 'pid') else 'unknown'})")
            try:
                recording_process.terminate()
                logger.info("Sent terminate signal to recording process")
                recording_process.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                logger.info("Recording process terminated gracefully")
            except TimeoutExpired:
                logger.warning("Recording process did not terminate within timeout, killing...")
                try:
                    recording_process.kill()
                    logger.info("Sent kill signal to recording process")
                    recording_process.wait(timeout=PROCESS_KILL_DELAY)
                    logger.info("Recording process killed")
                except TimeoutExpired:
                    logger.warning("Process did not die after kill, continuing...")
                except Exception as e:
                    logger.error(f"Error killing recording process: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Error terminating recording process: {e}", exc_info=True)
            
            # Close file handles (outside lock)
            # CRITICAL FIX: File handle closing must be inside the if block where recording_process is not None
            try:
                if recording_process.stdout:
                    recording_process.stdout.close()
                if recording_process.stderr:
                    recording_process.stderr.close()
            except Exception as e:
                logger.debug(f"Error closing file handles: {e}")
        else:
            logger.warning("No recording process to stop (recording_process is None)")
        
        # Rename file with duration (outside lock)
        # This can happen in both cases (process exists or not) if we have a filename
        if recording_filename and recording_filename.exists():
            if recording_start_time:
                duration = int(time.time() - recording_start_time)
                new_filename = self._rename_with_duration(recording_filename, duration)
                if new_filename:
                    try:
                        recording_filename.rename(new_filename)
                        logger.info(f"Renamed recording file to: {new_filename}")
                    except OSError as e:
                        logger.error(f"OS error renaming file {recording_filename}: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error renaming file: {e}", exc_info=True)
        
        # Give device a brief moment to be fully released after stopping
        # This helps prevent "device busy" errors when starting a new recording immediately
        # Reduced delay to improve responsiveness
        time.sleep(0.05)  # Reduced from 0.2s to 0.05s
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
                except TimeoutExpired:
                    logger.warning("Silentjack process did not terminate, killing...")
                    try:
                        self._silentjack_process.kill()
                        self._silentjack_process.wait(timeout=PROCESS_KILL_DELAY)
                    except TimeoutExpired:
                        logger.warning("Silentjack process did not die after kill, continuing...")
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
                    # Verify source file exists and is readable before attempting rename
                    if [ ! -r "$OLD_FILE" ]; then
                        echo "Error: Source file is not readable: $OLD_FILE" >&2
                    elif mv "$OLD_FILE" "$NEW_FILE" 2>/dev/null; then
                        # Verify rename succeeded by checking new file exists
                        if [ -f "$NEW_FILE" ]; then
                            # Successfully renamed - file exists at new location
                            :
                        else
                            # Rename appeared to succeed but new file doesn't exist
                            echo "Error: Rename appeared to succeed but new file not found: $NEW_FILE" >&2
                            # Try to recover original file if possible
                            if [ ! -f "$OLD_FILE" ]; then
                                echo "Error: Original file also missing after failed rename!" >&2
                            fi
                        fi
                    else
                        # Rename failed - log error (to stderr which silentjack may capture)
                        echo "Error: Failed to rename recording file from $OLD_FILE to $NEW_FILE" >&2
                        # Keep original file to avoid data loss
                        if [ ! -f "$OLD_FILE" ]; then
                            echo "Error: Original file missing after failed rename attempt!" >&2
                        fi
                    fi
                else
                    # Source file doesn't exist - log error
                    echo "Error: Source file does not exist: $OLD_FILE" >&2
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

