from typing import Tuple, Any, Optional
from .handler import AbletonOSCHandler
import logging

logger = logging.getLogger("abletonosc")


class AutomationHandler(AbletonOSCHandler):
    """Handles clip automation envelopes.

    Allows creating, reading, and writing automation breakpoints
    for any device parameter on any clip.
    """

    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "automation"

    def init_api(self):
        self.osc_server.add_handler("/live/clip/insert_automation_step", self._insert_step)
        self.osc_server.add_handler("/live/clip/insert_automation_steps", self._insert_steps)
        self.osc_server.add_handler("/live/clip/get_automation_value", self._get_value)
        self.osc_server.add_handler("/live/clip/clear_automation", self._clear_envelope)
        self.osc_server.add_handler("/live/clip/clear_all_automation", self._clear_all)

    def _get_clip_and_param(self, track_idx, clip_idx, device_idx, param_idx):
        """Helper to resolve clip and parameter objects."""
        track = self.song.tracks[track_idx]
        clip_slot = track.clip_slots[clip_idx]
        if not clip_slot.clip:
            logger.error("No clip at track %d, slot %d" % (track_idx, clip_idx))
            return None, None

        clip = clip_slot.clip
        device = track.devices[device_idx]
        param = device.parameters[param_idx]
        return clip, param

    def _get_or_create_envelope(self, clip, param):
        """Get existing envelope or create a new one."""
        envelope = clip.automation_envelope(param)
        if envelope is None:
            envelope = clip.create_automation_envelope(param)
        return envelope

    def _insert_step(self, params):
        """Insert a single automation step.

        Params: [track_idx, clip_idx, device_idx, param_idx,
                 start_time, duration, value]

        Value is in normalized 0.0-1.0 range, mapped to the parameter's
        min/max range.
        """
        track_idx = int(params[0])
        clip_idx = int(params[1])
        device_idx = int(params[2])
        param_idx = int(params[3])
        start_time = float(params[4])
        duration = float(params[5])
        value = float(params[6])

        clip, param = self._get_clip_and_param(track_idx, clip_idx, device_idx, param_idx)
        if clip is None:
            return ("error", "No clip found")

        # Map normalized value to parameter range
        native_value = param.min + value * (param.max - param.min)

        envelope = self._get_or_create_envelope(clip, param)
        if envelope is None:
            return ("error", "Could not create envelope")

        envelope.insert_step(start_time, duration, native_value)
        logger.info("Inserted automation step: track=%d clip=%d device=%d param=%d "
                     "time=%.2f dur=%.2f value=%.4f (native=%.4f)" %
                     (track_idx, clip_idx, device_idx, param_idx,
                      start_time, duration, value, native_value))

        return (track_idx, clip_idx, device_idx, param_idx, start_time, duration, value)

    def _insert_steps(self, params):
        """Insert multiple automation steps at once.

        Params: [track_idx, clip_idx, device_idx, param_idx,
                 start1, dur1, val1, start2, dur2, val2, ...]

        Values are normalized 0.0-1.0.
        """
        track_idx = int(params[0])
        clip_idx = int(params[1])
        device_idx = int(params[2])
        param_idx = int(params[3])

        clip, param = self._get_clip_and_param(track_idx, clip_idx, device_idx, param_idx)
        if clip is None:
            return ("error", "No clip found")

        envelope = self._get_or_create_envelope(clip, param)
        if envelope is None:
            return ("error", "Could not create envelope")

        step_data = params[4:]
        count = 0
        for i in range(0, len(step_data), 3):
            if i + 2 < len(step_data):
                start_time = float(step_data[i])
                duration = float(step_data[i + 1])
                value = float(step_data[i + 2])
                native_value = param.min + value * (param.max - param.min)
                envelope.insert_step(start_time, duration, native_value)
                count += 1

        logger.info("Inserted %d automation steps for track=%d clip=%d device=%d param=%d" %
                     (count, track_idx, clip_idx, device_idx, param_idx))

        return (track_idx, clip_idx, device_idx, param_idx, count)

    def _get_value(self, params):
        """Get the automation value at a specific time.

        Params: [track_idx, clip_idx, device_idx, param_idx, time]
        Returns: normalized value 0.0-1.0
        """
        track_idx = int(params[0])
        clip_idx = int(params[1])
        device_idx = int(params[2])
        param_idx = int(params[3])
        time = float(params[4])

        clip, param = self._get_clip_and_param(track_idx, clip_idx, device_idx, param_idx)
        if clip is None:
            return ("error", "No clip found")

        envelope = clip.automation_envelope(param)
        if envelope is None:
            return (track_idx, clip_idx, device_idx, param_idx, time, 0.0)

        native_value = envelope.value_at_time(time)
        # Normalize to 0-1
        if param.max != param.min:
            normalized = (native_value - param.min) / (param.max - param.min)
        else:
            normalized = 0.0

        return (track_idx, clip_idx, device_idx, param_idx, time, normalized)

    def _clear_envelope(self, params):
        """Clear automation for a specific parameter on a clip.

        Params: [track_idx, clip_idx, device_idx, param_idx]
        """
        track_idx = int(params[0])
        clip_idx = int(params[1])
        device_idx = int(params[2])
        param_idx = int(params[3])

        clip, param = self._get_clip_and_param(track_idx, clip_idx, device_idx, param_idx)
        if clip is None:
            return ("error", "No clip found")

        clip.clear_envelope(param)
        logger.info("Cleared automation for track=%d clip=%d device=%d param=%d" %
                     (track_idx, clip_idx, device_idx, param_idx))

        return (track_idx, clip_idx, device_idx, param_idx)

    def _clear_all(self, params):
        """Clear all automation on a clip.

        Params: [track_idx, clip_idx]
        """
        track_idx = int(params[0])
        clip_idx = int(params[1])

        track = self.song.tracks[track_idx]
        clip_slot = track.clip_slots[clip_idx]
        if not clip_slot.clip:
            return ("error", "No clip found")

        clip_slot.clip.clear_all_envelopes()
        logger.info("Cleared all automation for track=%d clip=%d" % (track_idx, clip_idx))

        return (track_idx, clip_idx)
