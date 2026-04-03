from typing import Tuple, Any
from .handler import AbletonOSCHandler


class DrumPadHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "drum_pad"

    def init_api(self):
        # ============================================================================
        # Drum pad enumeration (on device level)
        # ============================================================================
        def device_get_drum_pads_name(params):
            try:
                track_index = int(params[0])
                device_index = int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                names = []
                for pad in device.drum_pads:
                    if len(pad.chains) > 0:
                        names.append(pad.name)
                return (track_index, device_index, *names)
            except Exception as e:
                self.logger.error("Error in device_get_drum_pads_name: %s" % str(e))

        def device_get_drum_pads_note(params):
            try:
                track_index = int(params[0])
                device_index = int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                notes = []
                for pad in device.drum_pads:
                    if len(pad.chains) > 0:
                        notes.append(pad.note)
                return (track_index, device_index, *notes)
            except Exception as e:
                self.logger.error("Error in device_get_drum_pads_note: %s" % str(e))

        self.osc_server.add_handler("/live/device/get/drum_pads/name", device_get_drum_pads_name)
        self.osc_server.add_handler("/live/device/get/drum_pads/note", device_get_drum_pads_note)

        # ============================================================================
        # Individual drum pad properties
        # ============================================================================
        def create_drum_pad_callback(func, *args):
            def drum_pad_callback(params):
                try:
                    track_index = int(params[0])
                    device_index = int(params[1])
                    pad_note = int(params[2])
                    device = self.song.tracks[track_index].devices[device_index]
                    pad = device.drum_pads[pad_note]
                    rv = func(pad, *args, params[3:])
                    if rv is not None:
                        return (track_index, device_index, pad_note, *rv)
                except Exception as e:
                    self.logger.error("Error in drum pad callback: %s" % str(e))
            return drum_pad_callback

        properties_rw = [
            "name",
            "mute",
            "solo",
        ]

        for prop in properties_rw:
            self.osc_server.add_handler("/live/drum_pad/get/%s" % prop,
                                        create_drum_pad_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/drum_pad/set/%s" % prop,
                                        create_drum_pad_callback(self._set_property, prop))

        # ============================================================================
        # Drum pad chain access
        # ============================================================================
        def drum_pad_get_num_chains(pad, params=()):
            return (len(pad.chains),)

        self.osc_server.add_handler("/live/drum_pad/get/num_chains", create_drum_pad_callback(drum_pad_get_num_chains))

        def drum_pad_chain_get_devices_name(params):
            try:
                track_index = int(params[0])
                device_index = int(params[1])
                pad_note = int(params[2])
                device = self.song.tracks[track_index].devices[device_index]
                pad = device.drum_pads[pad_note]
                if len(pad.chains) == 0:
                    return (track_index, device_index, pad_note)
                chain = pad.chains[0]
                return (track_index, device_index, pad_note, *tuple(d.name for d in chain.devices))
            except Exception as e:
                self.logger.error("Error in drum_pad_chain_get_devices_name: %s" % str(e))

        self.osc_server.add_handler("/live/drum_pad/chain/get/devices/name", drum_pad_chain_get_devices_name)

        # ============================================================================
        # Drum pad chain device parameters
        # ============================================================================
        def create_drum_pad_chain_device_callback(func):
            def callback(params):
                try:
                    track_index = int(params[0])
                    device_index = int(params[1])
                    pad_note = int(params[2])
                    chain_device_index = int(params[3])
                    device = self.song.tracks[track_index].devices[device_index]
                    pad = device.drum_pads[pad_note]
                    if len(pad.chains) == 0:
                        self.logger.warning("Drum pad %d has no chains" % pad_note)
                        return None
                    chain = pad.chains[0]
                    chain_device = chain.devices[chain_device_index]
                    rv = func(chain_device, params[4:])
                    if rv is not None:
                        return (track_index, device_index, pad_note, chain_device_index, *rv)
                except Exception as e:
                    self.logger.error("Error in drum pad chain device callback: %s" % str(e))
            return callback

        def dp_device_get_num_parameters(device, params=()):
            return (len(device.parameters),)

        def dp_device_get_parameters_name(device, params=()):
            return tuple(p.name for p in device.parameters)

        def dp_device_get_parameters_value(device, params=()):
            return tuple(p.value for p in device.parameters)

        def dp_device_get_parameters_min(device, params=()):
            return tuple(p.min for p in device.parameters)

        def dp_device_get_parameters_max(device, params=()):
            return tuple(p.max for p in device.parameters)

        def dp_device_get_parameter_value(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].value)

        def dp_device_set_parameter_value(device, params=()):
            param_index, param_value = params[:2]
            param_index = int(param_index)
            device.parameters[param_index].value = param_value

        def dp_device_get_parameter_name(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].name)

        self.osc_server.add_handler("/live/drum_pad/chain/device/get/num_parameters", create_drum_pad_chain_device_callback(dp_device_get_num_parameters))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameters/name", create_drum_pad_chain_device_callback(dp_device_get_parameters_name))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameters/value", create_drum_pad_chain_device_callback(dp_device_get_parameters_value))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameters/min", create_drum_pad_chain_device_callback(dp_device_get_parameters_min))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameters/max", create_drum_pad_chain_device_callback(dp_device_get_parameters_max))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameter/value", create_drum_pad_chain_device_callback(dp_device_get_parameter_value))
        self.osc_server.add_handler("/live/drum_pad/chain/device/set/parameter/value", create_drum_pad_chain_device_callback(dp_device_set_parameter_value))
        self.osc_server.add_handler("/live/drum_pad/chain/device/get/parameter/name", create_drum_pad_chain_device_callback(dp_device_get_parameter_name))
