from typing import Tuple, Any
from .handler import AbletonOSCHandler


class SimplerHandler(AbletonOSCHandler):
    """Handlers for Simpler sample/slice manipulation.

    Targeting forms:
      Track-level:  (track_idx, device_idx)
      Drum pad:     (track_idx, rack_device_idx, pad_note)    # uses pad.chains[0].devices[0]
    """

    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "simpler"

    def _drill_to_simpler(self, device, max_depth=4):
        """Follow nested rack chains until we find a device with a `.sample` attr.

        load_sample_pad often wraps a Simpler inside an InstrumentRack, so a
        pad's first device is often a rack, not the Simpler itself.
        """
        for _ in range(max_depth):
            if hasattr(device, "sample"):
                return device
            chains = getattr(device, "chains", None)
            if not chains:
                break
            try:
                first_chain = chains[0]
            except (IndexError, Exception):
                break
            devs = getattr(first_chain, "devices", None)
            if not devs or len(devs) == 0:
                break
            device = devs[0]
        if not hasattr(device, "sample"):
            raise ValueError("no Simpler found (deepest: %s)" % device.__class__.__name__)
        return device

    def _resolve_simpler(self, params):
        track_idx = int(params[0])
        device_idx = int(params[1])
        track = self.song.tracks[track_idx]
        device = track.devices[device_idx]

        if len(params) >= 3:
            pad_note = int(params[2])
            pad = device.drum_pads[pad_note]
            if len(pad.chains) == 0:
                raise ValueError("drum pad %d has no chain" % pad_note)
            chain_device_idx = int(params[3]) if len(params) >= 4 else 0
            device = pad.chains[0].devices[chain_device_idx]

        return self._drill_to_simpler(device)

    def init_api(self):
        def wrap(handler):
            """Resolve a Simpler from params and call handler(simpler, remaining)."""
            def cb(params):
                try:
                    # Params are: (track_idx, device_idx, [pad_note, [chain_device_idx]], ...extras)
                    # Extras count depends on the form. For simplicity we accept both shapes
                    # and try to detect by trying 4-arg resolve first (pad + chain_device),
                    # falling back to 3, then 2.
                    for span in (4, 3, 2):
                        if len(params) >= span:
                            try:
                                simpler = self._resolve_simpler(params[:span])
                                extras = params[span:]
                                rv = handler(simpler, extras)
                                if rv is not None:
                                    return tuple(params[:span]) + tuple(rv)
                                return None
                            except Exception:
                                if span == 2:
                                    raise
                                continue
                except Exception as e:
                    self.logger.error("Simpler handler error: %s" % e)
                return None
            return cb

        def slice_times(simpler, _extras):
            sample = simpler.sample
            return tuple(float(s) for s in sample.slices)

        def slice_insert(simpler, extras):
            time = float(extras[0])
            simpler.sample.insert_slice(time)
            return (int(len(simpler.sample.slices)),)

        def slice_clear(simpler, _extras):
            simpler.sample.clear_slices()
            return (0,)

        def slice_reset(simpler, _extras):
            simpler.sample.reset_slices()
            return (int(len(simpler.sample.slices)),)

        def selected_slice_get(simpler, _extras):
            return (int(simpler.view.selected_slice),)

        def selected_slice_set(simpler, extras):
            simpler.view.selected_slice = int(extras[0])
            return (int(simpler.view.selected_slice),)

        def sample_length(simpler, _extras):
            return (float(simpler.sample.length),)

        def sample_path(simpler, _extras):
            return (str(simpler.sample.file_path),)

        def sample_sr(simpler, _extras):
            # Sample rate may or may not be exposed depending on Live version
            try:
                return (int(simpler.sample.sample_rate),)
            except Exception:
                return (0,)

        def playback_mode_get(simpler, _extras):
            """Return Simpler.playback_mode. 0=Classic, 1=One-Shot, 2=Slicing."""
            try:
                return (int(simpler.playback_mode),)
            except Exception as e:
                self.logger.info("Could not read playback_mode: %s" % e)
                return (-1,)

        def playback_mode_set(simpler, extras):
            try:
                simpler.playback_mode = int(extras[0])
                return (int(simpler.playback_mode),)
            except Exception as e:
                self.logger.error("Could not set playback_mode: %s" % e)
                return None

        self.osc_server.add_handler("/live/simpler/slice/get/times", wrap(slice_times))
        self.osc_server.add_handler("/live/simpler/slice/insert", wrap(slice_insert))
        self.osc_server.add_handler("/live/simpler/slice/clear", wrap(slice_clear))
        self.osc_server.add_handler("/live/simpler/slice/reset", wrap(slice_reset))
        self.osc_server.add_handler("/live/simpler/slice/selected/get", wrap(selected_slice_get))
        self.osc_server.add_handler("/live/simpler/slice/selected/set", wrap(selected_slice_set))
        self.osc_server.add_handler("/live/simpler/sample/get/length", wrap(sample_length))
        self.osc_server.add_handler("/live/simpler/sample/get/path", wrap(sample_path))
        self.osc_server.add_handler("/live/simpler/sample/get/sample_rate", wrap(sample_sr))
        self.osc_server.add_handler("/live/simpler/get/playback_mode", wrap(playback_mode_get))
        self.osc_server.add_handler("/live/simpler/set/playback_mode", wrap(playback_mode_set))
