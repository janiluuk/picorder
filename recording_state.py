#!/usr/bin/env python3
"""
Recording State Machine - Provides a clean state machine interface for recording operations
"""
import threading
import logging
import time
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Recording state enumeration"""
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"
    ERROR = "error"


class RecordingStateMachine:
    """
    State machine for recording operations.
    Provides atomic state transitions and clear state tracking.
    """
    
    def __init__(self, recording_manager):
        self._recording_manager = recording_manager
        self._lock = threading.Lock()
        self._state = RecordingState.IDLE
        self._state_history = []  # For debugging
        self._last_state_change = time.time()
        self._pending_operation = None  # "start" or "stop" or None
        
    def get_state(self) -> RecordingState:
        """Get current state (thread-safe)"""
        with self._lock:
            return self._state
    
    def get_state_dict(self) -> Dict[str, Any]:
        """Get full state information as a dictionary (non-blocking)"""
        # Don't hold lock while calling RecordingManager - it might block
        with self._lock:
            state_info = {
                'state': self._state.value,
                'last_change': self._last_state_change,
                'pending_operation': self._pending_operation,
            }
        
        # Get actual recording state from RecordingManager (outside lock to avoid deadlock)
        try:
            manager_state = self._recording_manager.get_recording_state(blocking=False)
            if manager_state:
                state_info.update(manager_state)
            else:
                # Fallback to cached state (read without lock - it's just a read)
                try:
                    state_info['is_recording'] = self._recording_manager._cached_is_recording
                    state_info['mode'] = self._recording_manager._cached_mode
                    state_info['start_time'] = self._recording_manager._cached_start_time
                except:
                    state_info['is_recording'] = False
                    state_info['mode'] = None
                    state_info['start_time'] = None
        except Exception as e:
            logger.debug(f"Error getting manager state: {e}")
            state_info['is_recording'] = False
            state_info['mode'] = None
            state_info['start_time'] = None
        
        return state_info
    
    def _transition(self, new_state: RecordingState, reason: str = ""):
        """Atomically transition to a new state"""
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                return  # No change needed
            
            # Validate transition
            valid_transitions = {
                RecordingState.IDLE: [RecordingState.STARTING, RecordingState.ERROR],
                RecordingState.STARTING: [RecordingState.RECORDING, RecordingState.IDLE, RecordingState.ERROR],
                RecordingState.RECORDING: [RecordingState.STOPPING, RecordingState.ERROR],
                RecordingState.STOPPING: [RecordingState.IDLE, RecordingState.ERROR],
                RecordingState.ERROR: [RecordingState.IDLE],
            }
            
            if new_state not in valid_transitions.get(old_state, []):
                logger.warning(f"Invalid state transition: {old_state.value} -> {new_state.value} (reason: {reason})")
                # Allow it anyway but log warning
            
            self._state = new_state
            self._last_state_change = time.time()
            self._state_history.append((old_state, new_state, reason, time.time()))
            
            # Keep only last 20 state changes
            if len(self._state_history) > 20:
                self._state_history.pop(0)
            
            logger.info(f"State transition: {old_state.value} -> {new_state.value} (reason: {reason})")
    
    def request_start(self, device: str, mode: str = "manual") -> bool:
        """
        Request to start recording.
        Returns True if request was accepted, False if rejected.
        """
        with self._lock:
            current_state = self._state
            
            # Can only start from IDLE or ERROR
            if current_state not in [RecordingState.IDLE, RecordingState.ERROR]:
                logger.debug(f"Cannot start recording: current state is {current_state.value}")
                return False
            
            # Check if there's already a pending start
            if self._pending_operation == "start":
                logger.debug("Start operation already pending")
                return False
            
            self._pending_operation = "start"
            self._transition(RecordingState.STARTING, f"Requested start ({mode})")
            return True
    
    def request_stop(self) -> bool:
        """
        Request to stop recording.
        Returns True if request was accepted, False if rejected.
        """
        with self._lock:
            current_state = self._state
            
            # Can stop from STARTING, RECORDING, or ERROR
            if current_state not in [RecordingState.STARTING, RecordingState.RECORDING, RecordingState.ERROR]:
                logger.debug(f"Cannot stop recording: current state is {current_state.value}")
                return False
            
            # Check if there's already a pending stop
            if self._pending_operation == "stop":
                logger.debug("Stop operation already pending")
                return False
            
            self._pending_operation = "stop"
            self._transition(RecordingState.STOPPING, "Requested stop")
            return True
    
    def on_start_success(self):
        """Called when recording successfully starts"""
        with self._lock:
            self._pending_operation = None
            self._transition(RecordingState.RECORDING, "Recording started successfully")
    
    def on_start_failure(self, error: str = ""):
        """Called when recording start fails"""
        with self._lock:
            self._pending_operation = None
            self._transition(RecordingState.IDLE, f"Start failed: {error}")
    
    def on_stop_success(self):
        """Called when recording successfully stops"""
        with self._lock:
            self._pending_operation = None
            self._transition(RecordingState.IDLE, "Recording stopped successfully")
    
    def on_stop_failure(self, error: str = ""):
        """Called when recording stop fails"""
        with self._lock:
            self._pending_operation = None
            # Even on failure, go to IDLE (process was killed)
            self._transition(RecordingState.IDLE, f"Stop completed (with errors: {error})")
    
    def sync_with_manager(self):
        """
        Sync state machine state with RecordingManager's actual state.
        This should be called periodically to ensure consistency.
        """
        try:
            manager_state = self._recording_manager.get_recording_state(blocking=False)
            if not manager_state:
                return
            
            is_recording = manager_state.get('is_recording', False)
            current_state = self.get_state()
            
            with self._lock:
                # If manager says recording but we're not in RECORDING state
                if is_recording and current_state not in [RecordingState.RECORDING, RecordingState.STARTING]:
                    logger.warning(f"State mismatch: manager says recording but state is {current_state.value}, syncing...")
                    self._transition(RecordingState.RECORDING, "Synced with manager state")
                    self._pending_operation = None
                
                # If manager says not recording but we're in RECORDING or STARTING
                elif not is_recording and current_state in [RecordingState.RECORDING, RecordingState.STARTING]:
                    logger.warning(f"State mismatch: manager says not recording but state is {current_state.value}, syncing...")
                    self._transition(RecordingState.IDLE, "Synced with manager state")
                    self._pending_operation = None
        except Exception as e:
            logger.debug(f"Error syncing state: {e}")
    
    def get_state_summary(self) -> str:
        """Get a human-readable state summary"""
        state_dict = self.get_state_dict()
        state = state_dict.get('state', 'unknown')
        is_recording = state_dict.get('is_recording', False)
        mode = state_dict.get('mode', 'unknown')
        pending = state_dict.get('pending_operation')
        
        summary = f"State: {state}"
        if pending:
            summary += f", Pending: {pending}"
        if is_recording:
            summary += f", Mode: {mode}"
        
        return summary

