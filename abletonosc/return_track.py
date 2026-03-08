from typing import Tuple, Any, Callable, Optional
from .handler import AbletonOSCHandler


class ReturnTrackHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "return_track"

    def init_api(self):
        def create_return_track_callback(func, *args, include_track_id=False):
            def callback(params):
                if params[0] == "*":
                    indices = list(range(len(self.song.return_tracks)))
                else:
                    indices = [int(params[0])]

                for track_index in indices:
                    track = self.song.return_tracks[track_index]
                    if include_track_id:
                        rv = func(track, *args, tuple([track_index] + params[1:]))
                    else:
                        rv = func(track, *args, tuple(params[1:]))
                    if rv is not None:
                        return (track_index, *rv)
            return callback

        # ── Track-level properties ──
        properties_r = [
            "is_visible",
            "output_meter_level",
            "output_meter_left",
            "output_meter_right",
        ]
        properties_rw = [
            "color",
            "color_index",
            "mute",
            "solo",
            "name",
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/return_track/get/%s" % prop,
                                        create_return_track_callback(self._get_property, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/return_track/set/%s" % prop,
                                        create_return_track_callback(self._set_property, prop))

        # ── Mixer: volume and panning ──
        for prop in ["volume", "panning"]:
            self.osc_server.add_handler("/live/return_track/get/%s" % prop,
                                        create_return_track_callback(self._get_mixer_property, prop))
            self.osc_server.add_handler("/live/return_track/set/%s" % prop,
                                        create_return_track_callback(self._set_mixer_property, prop))

        # ── Sends (return-to-return) ──
        def rt_get_send(track, params=()):
            send_id, = params
            return send_id, track.mixer_device.sends[send_id].value

        def rt_set_send(track, params=()):
            send_id, value = params
            track.mixer_device.sends[send_id].value = value

        self.osc_server.add_handler("/live/return_track/get/send", create_return_track_callback(rt_get_send))
        self.osc_server.add_handler("/live/return_track/set/send", create_return_track_callback(rt_set_send))

        # ── Song-level: names and count ──
        def get_return_track_names(params):
            return tuple(t.name for t in self.song.return_tracks)

        def get_num_return_tracks(params):
            return (len(self.song.return_tracks),)

        self.osc_server.add_handler("/live/return_track/get/names", get_return_track_names)
        self.osc_server.add_handler("/live/return_track/get/count", get_num_return_tracks)

        # ── Device listing ──
        def rt_get_num_devices(track, _):
            return (len(track.devices),)

        def rt_get_device_names(track, _):
            return tuple(device.name for device in track.devices)

        def rt_get_device_types(track, _):
            return tuple(device.type for device in track.devices)

        def rt_get_device_class_names(track, _):
            return tuple(device.class_name for device in track.devices)

        self.osc_server.add_handler("/live/return_track/get/num_devices", create_return_track_callback(rt_get_num_devices))
        self.osc_server.add_handler("/live/return_track/get/devices/name", create_return_track_callback(rt_get_device_names))
        self.osc_server.add_handler("/live/return_track/get/devices/type", create_return_track_callback(rt_get_device_types))
        self.osc_server.add_handler("/live/return_track/get/devices/class_name", create_return_track_callback(rt_get_device_class_names))

        # ── Device parameters ──
        def create_rt_device_callback(func):
            def callback(params):
                track_index = int(params[0])
                device_index = int(params[1])
                track = self.song.return_tracks[track_index]
                device = track.devices[device_index]
                rv = func(device, params[2:])
                if rv is not None:
                    return (track_index, device_index, *rv)
            return callback

        def rt_device_get_num_parameters(device, params=()):
            return (len(device.parameters),)

        def rt_device_get_parameters_name(device, params=()):
            return tuple(p.name for p in device.parameters)

        def rt_device_get_parameters_value(device, params=()):
            return tuple(p.value for p in device.parameters)

        def rt_device_get_parameters_min(device, params=()):
            return tuple(p.min for p in device.parameters)

        def rt_device_get_parameters_max(device, params=()):
            return tuple(p.max for p in device.parameters)

        def rt_device_set_parameters_value(device, params=()):
            for index, value in enumerate(params):
                device.parameters[index].value = value

        def rt_device_get_parameter_value(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].value)

        def rt_device_set_parameter_value(device, params=()):
            param_index, param_value = params[:2]
            param_index = int(param_index)
            device.parameters[param_index].value = param_value

        def rt_device_get_parameter_name(device, params=()):
            param_index = int(params[0])
            return (param_index, device.parameters[param_index].name)

        self.osc_server.add_handler("/live/return_track/device/get/num_parameters", create_rt_device_callback(rt_device_get_num_parameters))
        self.osc_server.add_handler("/live/return_track/device/get/parameters/name", create_rt_device_callback(rt_device_get_parameters_name))
        self.osc_server.add_handler("/live/return_track/device/get/parameters/value", create_rt_device_callback(rt_device_get_parameters_value))
        self.osc_server.add_handler("/live/return_track/device/get/parameters/min", create_rt_device_callback(rt_device_get_parameters_min))
        self.osc_server.add_handler("/live/return_track/device/get/parameters/max", create_rt_device_callback(rt_device_get_parameters_max))
        self.osc_server.add_handler("/live/return_track/device/set/parameters/value", create_rt_device_callback(rt_device_set_parameters_value))
        self.osc_server.add_handler("/live/return_track/device/get/parameter/value", create_rt_device_callback(rt_device_get_parameter_value))
        self.osc_server.add_handler("/live/return_track/device/set/parameter/value", create_rt_device_callback(rt_device_set_parameter_value))
        self.osc_server.add_handler("/live/return_track/device/get/parameter/name", create_rt_device_callback(rt_device_get_parameter_name))

    def _set_mixer_property(self, target, prop, params):
        parameter_object = getattr(target.mixer_device, prop)
        self.logger.info("Setting mixer property for %s: %s (new value %s)" % (self.class_identifier, prop, params[0]))
        parameter_object.value = params[0]

    def _get_mixer_property(self, target, prop, params=()):
        parameter_object = getattr(target.mixer_device, prop)
        self.logger.info("Getting mixer property for %s: %s = %s" % (self.class_identifier, prop, parameter_object.value))
        return (parameter_object.value,)
