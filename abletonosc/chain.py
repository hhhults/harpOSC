from typing import Tuple, Any
from .handler import AbletonOSCHandler


class ChainHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "chain"

    def init_api(self):
        # ============================================================================
        # Chain enumeration (on device level)
        # ============================================================================
        def device_get_num_chains(params):
            try:
                track_index = int(params[0])
                device_index = int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                if not device.can_have_chains:
                    self.logger.warning("Device %d on track %d cannot have chains" % (device_index, track_index))
                    return (track_index, device_index, 0)
                return (track_index, device_index, len(device.chains))
            except Exception as e:
                self.logger.error("Error in device_get_num_chains: %s" % str(e))

        def device_get_chains_name(params):
            try:
                track_index = int(params[0])
                device_index = int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                if not device.can_have_chains:
                    return (track_index, device_index)
                return (track_index, device_index, *tuple(chain.name for chain in device.chains))
            except Exception as e:
                self.logger.error("Error in device_get_chains_name: %s" % str(e))

        self.osc_server.add_handler("/live/device/get/num_chains", device_get_num_chains)
        self.osc_server.add_handler("/live/device/get/chains/name", device_get_chains_name)

        # ============================================================================
        # Chain callback factory
        # ============================================================================
        def create_chain_callback(func, *args):
            def chain_callback(params):
                try:
                    track_index = int(params[0])
                    device_index = int(params[1])
                    chain_index = int(params[2])
                    device = self.song.tracks[track_index].devices[device_index]
                    chain = device.chains[chain_index]
                    rv = func(chain, *args, params[3:])
                    if rv is not None:
                        return (track_index, device_index, chain_index, *rv)
                except Exception as e:
                    self.logger.error("Error in chain callback: %s" % str(e))
            return chain_callback

        # ============================================================================
        # Chain properties (get/set)
        # ============================================================================
        properties_rw = [
            "name",
            "mute",
            "solo",
            "color",
            "color_index",
        ]

        for prop in properties_rw:
            self.osc_server.add_handler("/live/chain/get/%s" % prop,
                                        create_chain_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/chain/set/%s" % prop,
                                        create_chain_callback(self._set_property, prop))

        # ============================================================================
        # Chain mixer: volume and panning
        # ============================================================================
        def chain_get_mixer_property(chain, prop, params=()):
            parameter_object = getattr(chain.mixer_device, prop)
            self.logger.info("Getting mixer property for chain: %s = %s" % (prop, parameter_object.value))
            return (parameter_object.value,)

        def chain_set_mixer_property(chain, prop, params=()):
            parameter_object = getattr(chain.mixer_device, prop)
            self.logger.info("Setting mixer property for chain: %s (new value %s)" % (prop, params[0]))
            parameter_object.value = params[0]

        for prop in ["volume", "panning"]:
            self.osc_server.add_handler("/live/chain/get/%s" % prop,
                                        create_chain_callback(chain_get_mixer_property, prop))
            self.osc_server.add_handler("/live/chain/set/%s" % prop,
                                        create_chain_callback(chain_set_mixer_property, prop))

        # ============================================================================
        # Chain device listing
        # ============================================================================
        def chain_get_num_devices(chain, params=()):
            return (len(chain.devices),)

        def chain_get_devices_name(chain, params=()):
            return tuple(device.name for device in chain.devices)

        def chain_get_devices_class_name(chain, params=()):
            return tuple(device.class_name for device in chain.devices)

        self.osc_server.add_handler("/live/chain/get/num_devices", create_chain_callback(chain_get_num_devices))
        self.osc_server.add_handler("/live/chain/get/devices/name", create_chain_callback(chain_get_devices_name))
        self.osc_server.add_handler("/live/chain/get/devices/class_name", create_chain_callback(chain_get_devices_class_name))

        # ============================================================================
        # Chain device parameters (4-element prefix: track, device, chain, chain_device)
        # ============================================================================
        def create_chain_device_callback(func):
            def callback(params):
                try:
                    track_index = int(params[0])
                    device_index = int(params[1])
                    chain_index = int(params[2])
                    chain_device_index = int(params[3])
                    device = self.song.tracks[track_index].devices[device_index]
                    chain = device.chains[chain_index]
                    chain_device = chain.devices[chain_device_index]
                    rv = func(chain_device, params[4:])
                    if rv is not None:
                        return (track_index, device_index, chain_index, chain_device_index, *rv)
                except Exception as e:
                    self.logger.error("Error in chain device callback: %s" % str(e))
            return callback

        def chain_device_get_num_parameters(device, params=()):
            return (len(device.parameters),)

        def chain_device_get_parameters_name(device, params=()):
            return tuple(p.name for p in device.parameters)

        def chain_device_get_parameters_value(device, params=()):
            return tuple(p.value for p in device.parameters)

        def chain_device_get_parameters_min(device, params=()):
            return tuple(p.min for p in device.parameters)

        def chain_device_get_parameters_max(device, params=()):
            return tuple(p.max for p in device.parameters)

        def chain_device_get_parameter_value(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].value)

        def chain_device_set_parameter_value(device, params=()):
            param_index, param_value = params[:2]
            param_index = int(param_index)
            device.parameters[param_index].value = param_value

        def chain_device_get_parameter_name(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].name)

        self.osc_server.add_handler("/live/chain/device/get/num_parameters", create_chain_device_callback(chain_device_get_num_parameters))
        self.osc_server.add_handler("/live/chain/device/get/parameters/name", create_chain_device_callback(chain_device_get_parameters_name))
        self.osc_server.add_handler("/live/chain/device/get/parameters/value", create_chain_device_callback(chain_device_get_parameters_value))
        self.osc_server.add_handler("/live/chain/device/get/parameters/min", create_chain_device_callback(chain_device_get_parameters_min))
        self.osc_server.add_handler("/live/chain/device/get/parameters/max", create_chain_device_callback(chain_device_get_parameters_max))
        self.osc_server.add_handler("/live/chain/device/get/parameter/value", create_chain_device_callback(chain_device_get_parameter_value))
        self.osc_server.add_handler("/live/chain/device/set/parameter/value", create_chain_device_callback(chain_device_set_parameter_value))
        self.osc_server.add_handler("/live/chain/device/get/parameter/name", create_chain_device_callback(chain_device_get_parameter_name))
