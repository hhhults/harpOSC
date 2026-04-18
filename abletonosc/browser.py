from typing import Tuple, Any, Optional
from .handler import AbletonOSCHandler
import Live
import os
import logging

logger = logging.getLogger("abletonosc")


class BrowserHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "browser"

    @property
    def browser(self):
        return Live.Application.get_application().browser

    def _resolve_track(self, track_spec):
        """Resolve a track specifier to a track object.

        Supports:
          - int or numeric string: song.tracks[index]
          - "return:N": song.return_tracks[N]
          - "master": song.master_track
        """
        song = self.song
        spec = str(track_spec)
        if spec == "master":
            return song.master_track
        if spec.startswith("return:"):
            idx = int(spec.split(":")[1])
            return song.return_tracks[idx]
        return song.tracks[int(spec)]

    def init_api(self):
        self.osc_server.add_handler("/live/browser/load_sample", self._load_sample)
        self.osc_server.add_handler("/live/browser/load_sample_pad", self._load_sample_pad)
        self.osc_server.add_handler("/live/browser/load_instrument", self._load_instrument)
        self.osc_server.add_handler("/live/browser/load_effect", self._load_effect)
        self.osc_server.add_handler("/live/browser/load_device_pad", self._load_device_pad)
        self.osc_server.add_handler("/live/browser/load_drum_rack", self._load_drum_rack)
        self.osc_server.add_handler("/live/browser/hotswap_device", self._hotswap_device)
        self.osc_server.add_handler("/live/browser/search", self._search)
        self.osc_server.add_handler("/live/browser/list_children", self._list_children)
        self.osc_server.add_handler("/live/track/insert_device", self._insert_device)

    def _has_children(self, item):
        """Check if a browser item can be recursed into.

        In Live 11, category items (e.g. 'Reverb & Resonance') report
        is_folder=False even though they have children. We treat any
        non-loadable item as potentially having children.
        """
        if item.is_folder:
            return True
        if not item.is_loadable:
            try:
                return len(list(item.children)) > 0
            except Exception:
                return False
        return False

    def _find_item_recursive(self, parent, name, max_depth=6):
        """Recursively search browser tree for an item by name (case-insensitive)."""
        name_lower = name.lower()
        try:
            for item in parent.children:
                if item.name.lower() == name_lower:
                    return item
                if self._has_children(item) and max_depth > 0:
                    result = self._find_item_recursive(item, name, max_depth - 1)
                    if result:
                        return result
        except Exception as e:
            logger.warning("Error browsing: %s" % str(e))
        return None

    def _find_item_partial(self, parent, search_term, max_depth=6, results=None):
        """Find items whose name contains the search term (case-insensitive)."""
        if results is None:
            results = []
        search_lower = search_term.lower()
        try:
            for item in parent.children:
                if search_lower in item.name.lower():
                    results.append(item)
                    if len(results) >= 20:
                        return results
                if self._has_children(item) and max_depth > 0:
                    self._find_item_partial(item, search_term, max_depth - 1, results)
                    if len(results) >= 20:
                        return results
        except Exception as e:
            logger.warning("Error browsing: %s" % str(e))
        return results

    def _get_loadable(self, item):
        """Get the first loadable item (the item itself or its first loadable child)."""
        if item.is_loadable:
            return item
        try:
            for child in item.children:
                if child.is_loadable:
                    return child
        except Exception:
            pass
        return None

    def _load_sample(self, params):
        """Load a sample onto a track. Creates a Simpler with the sample.

        Params: [track_index, sample_name]

        The sample_name is searched in: user_library, samples, user_folders, current_project.
        """
        track_index = int(params[0])
        sample_name = str(params[1])

        browser = self.browser
        song = self.song

        # Select the target track so browser.load_item loads onto it
        track = song.tracks[track_index]
        song.view.selected_track = track

        # Search multiple browser categories for the sample
        categories = [
            browser.user_library,
            browser.samples,
            browser.current_project,
        ]
        # Add user_folders if available
        try:
            for folder in browser.user_folders:
                categories.append(folder)
        except Exception:
            pass

        item = None
        for category in categories:
            item = self._find_item_recursive(category, sample_name)
            if item:
                break
            # Try partial match if exact match fails
            results = self._find_item_partial(category, sample_name, max_depth=6)
            if results:
                item = results[0]
                break

        if not item:
            logger.error("Sample not found: %s" % sample_name)
            return ("error", "Sample not found: %s" % sample_name)

        loadable = self._get_loadable(item)
        if not loadable:
            logger.error("Sample not loadable: %s" % sample_name)
            return ("error", "Sample not loadable: %s" % sample_name)

        logger.info("Loading sample: %s onto track %d" % (loadable.name, track_index))
        browser.load_item(loadable)
        return (track_index, loadable.name)

    def _schedule_pad_load(self, track, device, pad, loadable):
        """Defer a browser.load_item that fills the given DrumPad.

        Uses the Push-canonical pattern: set browser.hotswap_target to the pad
        and filter_type to drum_pad_hotswap before load_item. Selecting the pad
        via device.view.selected_drum_pad is UI feedback only — it does not
        route loads. Scheduling by one tick lets view state propagate first.
        """
        import Live
        app = Live.Application.get_application()
        browser = self.browser
        song = self.song

        def deferred_load():
            song.view.selected_track = track
            app.view.show_view("Detail/DeviceChain")
            device.view.selected_drum_pad = pad
            browser.hotswap_target = pad
            try:
                browser.filter_type = Live.Browser.FilterType.drum_pad_hotswap
            except Exception as e:
                logger.info("Could not set filter_type: %s" % e)
            browser.load_item(loadable)
            browser.hotswap_target = None
            try:
                browser.filter_type = Live.Browser.FilterType.disabled
            except Exception:
                pass

        self.manager.schedule_message(1, deferred_load)

    def _load_sample_pad(self, params):
        """Load a sample into a drum rack pad. Creates a Simpler in the pad.

        Params: [track_index, device_index, pad_note, sample_name]
        """
        track_index = int(params[0])
        device_index = int(params[1])
        pad_note = int(params[2])
        sample_name = str(params[3])

        browser = self.browser
        song = self.song

        track = song.tracks[track_index]
        device = track.devices[device_index]
        pad = device.drum_pads[pad_note]

        categories = [
            browser.user_library,
            browser.samples,
            browser.current_project,
        ]
        try:
            for folder in browser.user_folders:
                categories.append(folder)
        except Exception:
            pass

        item = None
        for category in categories:
            item = self._find_item_recursive(category, sample_name)
            if item:
                break
            results = self._find_item_partial(category, sample_name, max_depth=6)
            if results:
                item = results[0]
                break

        if not item:
            logger.error("Sample not found for pad: %s" % sample_name)
            return ("error", "Sample not found: %s" % sample_name)

        loadable = self._get_loadable(item)
        if not loadable:
            return ("error", "Sample not loadable: %s" % sample_name)

        logger.info("Loading sample %s into pad %d on track %d" %
                    (loadable.name, pad_note, track_index))
        self._schedule_pad_load(track, device, pad, loadable)
        return (track_index, device_index, pad_note, loadable.name)

    def _load_instrument(self, params):
        """Load an instrument by name onto a track.

        Params: [track_index, instrument_name]

        Searches instruments and sounds categories with exact-match priority.
        """
        track_index = int(params[0])
        instrument_name = str(params[1])

        song = self.song
        track = song.tracks[track_index]
        song.view.selected_track = track

        browser = self.browser
        categories = [browser.drums, browser.instruments, browser.sounds]
        try:
            categories.append(browser.plugins)
        except Exception:
            pass

        # First pass: exact name match deep in the tree
        item = None
        for category in categories:
            item = self._find_item_recursive(category, instrument_name)
            if item:
                break

        if item:
            loadable = self._get_loadable(item)
            if loadable:
                logger.info("Loading instrument: %s onto track %d" % (loadable.name, track_index))
                browser.load_item(loadable)
                return (track_index, loadable.name)

        # Second pass: partial match with sorting
        all_matches = []
        for category in categories:
            results = self._find_item_partial(category, instrument_name, max_depth=6)
            all_matches.extend(results)

        if not all_matches:
            return ("error", "Instrument not found: %s" % instrument_name)

        name_lower = instrument_name.lower()
        all_matches.sort(key=lambda m: (
            0 if m.name.lower() == name_lower else 1,
            0 if m.is_loadable else 1,
        ))

        loadable = None
        for match in all_matches:
            if match.is_loadable:
                loadable = match
                break
            child = self._get_loadable(match)
            if child:
                loadable = child
                break

        if not loadable:
            return ("error", "Instrument not loadable: %s" % instrument_name)

        logger.info("Loading instrument: %s onto track %d" % (loadable.name, track_index))
        browser.load_item(loadable)
        return (track_index, loadable.name)

    def _load_effect(self, params):
        """Load an audio effect by name onto a track.

        Params: [track_spec, effect_name]

        track_spec can be an index (int), "return:N", or "master".
        Only searches audio_effects and midi_effects categories to avoid
        matching sample files from user_library/packs.
        """
        track_spec = params[0]
        effect_name = str(params[1])

        song = self.song
        track = self._resolve_track(track_spec)
        song.view.selected_track = track

        browser = self.browser
        # Only search effect categories — not user_library, packs, etc.
        categories = [browser.audio_effects, browser.midi_effects]

        # First pass: exact name match deep in the tree
        item = None
        for category in categories:
            item = self._find_item_recursive(category, effect_name, max_depth=10)
            if item:
                logger.info("Exact match '%s': is_loadable=%s, is_folder=%s" %
                            (item.name, item.is_loadable, item.is_folder))
                break

        if item:
            loadable = self._get_loadable(item)
            if loadable:
                logger.info("Loading effect: %s onto track %s" % (loadable.name, track_spec))
                browser.load_item(loadable)
                return (str(track_spec), loadable.name)

        # Second pass: partial match, sorted by relevance
        all_matches = []
        for category in categories:
            results = self._find_item_partial(category, effect_name, max_depth=10)
            all_matches.extend(results)

        if not all_matches:
            return ("error", "Effect not found: %s" % effect_name)

        name_lower = effect_name.lower()
        all_matches.sort(key=lambda m: (
            0 if m.name.lower() == name_lower else 1,
            0 if m.is_loadable else 1,
        ))

        loadable = None
        for match in all_matches:
            logger.info("Partial match '%s': is_loadable=%s" % (match.name, match.is_loadable))
            if match.is_loadable:
                loadable = match
                break
            child = self._get_loadable(match)
            if child:
                loadable = child
                break

        if not loadable:
            return ("error", "Effect not loadable: %s" % effect_name)

        logger.info("Loading effect: %s onto track %s" % (loadable.name, track_spec))
        browser.load_item(loadable)
        return (str(track_spec), loadable.name)

    def _search(self, params):
        """Search the browser for items matching a query.

        Params: [search_term, category (optional: "samples", "instruments", "effects", "all")]
        Returns: list of (name, is_loadable, is_folder) tuples
        """
        search_term = str(params[0])
        category_name = str(params[1]) if len(params) > 1 else "all"

        browser = self.browser

        category_map = {
            "samples": [browser.samples, browser.user_library],
            "instruments": [browser.instruments, browser.sounds],
            "effects": [browser.audio_effects, browser.midi_effects],
        }

        if category_name == "all":
            categories = [
                browser.samples, browser.user_library,
                browser.instruments, browser.sounds,
                browser.audio_effects, browser.midi_effects,
                browser.current_project,
            ]
        else:
            categories = category_map.get(category_name, [browser.samples])

        all_results = []
        for category in categories:
            results = self._find_item_partial(category, search_term, max_depth=6)
            all_results.extend(results)
            if len(all_results) >= 20:
                break

        names = tuple(item.name for item in all_results[:20])
        return names if names else ("No results found",)

    def _list_children(self, params):
        """List children of a browser category.

        Params: [category_name] where category_name is one of:
        "samples", "instruments", "effects", "sounds", "drums",
        "user_library", "current_project", "packs"
        """
        category_name = str(params[0])

        browser = self.browser
        category_map = {
            "samples": browser.samples,
            "instruments": browser.instruments,
            "effects": browser.audio_effects,
            "midi_effects": browser.midi_effects,
            "sounds": browser.sounds,
            "drums": browser.drums,
            "user_library": browser.user_library,
            "current_project": browser.current_project,
            "packs": browser.packs,
        }

        category = category_map.get(category_name)
        if not category:
            return ("error", "Unknown category: %s" % category_name)

        try:
            names = tuple(item.name for item in category.children)
            return names if names else ("empty",)
        except Exception as e:
            return ("error", str(e))

    def _insert_device(self, params):
        """Insert a native Live device onto a track by internal class name.

        Params: [track_spec, device_uri, position (optional, default -1 = end)]

        track_spec can be an index (int), "return:N", or "master".

        Common device URIs:
            Audio effects: "Reverb", "Hybrid Reverb", "Delay", "Chorus-Ensemble",
                          "Erosion", "Redux", "Grain Delay", "Spectral Time",
                          "Echo", "Phaser-Flanger", "Saturator", "Compressor",
                          "EQ Eight", "Auto Filter", "Utility"
            Instruments:  "InstrumentSimpler", "InstrumentSampler", "Operator",
                          "Analog", "Collision", "Drift", "Meld", "Wavetable"
        """
        track_spec = params[0]
        device_uri = str(params[1])
        position = int(params[2]) if len(params) > 2 else -1

        song = self.song
        track = self._resolve_track(track_spec)
        song.view.selected_track = track

        if position < 0:
            position = len(track.devices)

        try:
            track.insert_device(device_uri, position)
            logger.info("Inserted device '%s' at position %d on track %s" %
                         (device_uri, position, track_spec))
            return (str(track_spec), device_uri, position)
        except Exception as e:
            logger.error("Failed to insert device '%s': %s" % (device_uri, str(e)))
            return ("error", "Failed to insert device: %s" % str(e))

    def _hotswap_device(self, params):
        """Hot-swap a device's preset in place without removing the device.

        Params: [track_spec, device_index, preset_name]

        Auto-detects filter_type from device.type (instrument/midi_effect/
        audio_effect). Uses the Push-canonical pattern: set browser.hotswap_target
        to the device, set a matching filter_type, load the preset, then clear.
        """
        track_spec = params[0]
        device_index = int(params[1])
        preset_name = str(params[2])

        song = self.song
        track = self._resolve_track(track_spec)
        device = track.devices[device_index]

        browser = self.browser
        filter_types = Live.Browser.FilterType

        filter_type = filter_types.disabled
        categories = [browser.instruments, browser.sounds, browser.drums,
                      browser.audio_effects, browser.midi_effects]
        try:
            dt = device.type
            if dt == Live.Device.DeviceType.instrument:
                filter_type = filter_types.instrument_hotswap
                categories = [browser.instruments, browser.sounds, browser.drums]
            elif dt == Live.Device.DeviceType.audio_effect:
                filter_type = filter_types.audio_effect_hotswap
                categories = [browser.audio_effects]
            elif dt == Live.Device.DeviceType.midi_effect:
                filter_type = filter_types.midi_effect_hotswap
                categories = [browser.midi_effects]
        except (AttributeError, Exception) as e:
            logger.info("Could not read device.type (%s), searching all categories" % e)

        item = None
        for category in categories:
            item = self._find_item_recursive(category, preset_name, max_depth=10)
            if item:
                break
        if not item:
            all_matches = []
            for category in categories:
                all_matches.extend(self._find_item_partial(category, preset_name, max_depth=10))
            if all_matches:
                name_lower = preset_name.lower()
                all_matches.sort(key=lambda m: (
                    0 if m.name.lower() == name_lower else 1,
                    0 if m.is_loadable else 1,
                ))
                item = all_matches[0]

        if not item:
            logger.error("Preset not found: %s" % preset_name)
            return ("error", "Preset not found: %s" % preset_name)
        loadable = self._get_loadable(item)
        if not loadable:
            return ("error", "Preset not loadable: %s" % preset_name)

        logger.info("Hotswap %s -> %s (filter=%s)" %
                    (device.name, loadable.name, filter_type))

        def deferred_load():
            song.view.selected_track = track
            song.view.select_device(device)
            browser.hotswap_target = device
            try:
                browser.filter_type = filter_type
            except Exception as e:
                logger.info("filter_type set failed: %s" % e)
            browser.load_item(loadable)
            browser.hotswap_target = None
            try:
                browser.filter_type = filter_types.disabled
            except Exception:
                pass

        self.manager.schedule_message(1, deferred_load)
        return (str(track_spec), device_index, loadable.name)

    def _load_drum_rack(self, params):
        """Load an empty Drum Rack onto a track via the browser.

        Params: [track_spec]

        Uses browser.load_item so it works regardless of whether the
        internal class name ('DrumGroupDevice') is accepted by
        track.insert_device on a given Live version.
        """
        track_spec = params[0]
        track = self._resolve_track(track_spec)

        browser = self.browser
        song = self.song
        song.view.selected_track = track

        item = self._find_item_recursive(browser.drums, "Drum Rack", max_depth=4)
        if not item:
            item = self._find_item_recursive(browser.instruments, "Drum Rack", max_depth=4)
        if not item:
            logger.error("Drum Rack not found in browser")
            return ("error", "Drum Rack not found in browser")

        loadable = self._get_loadable(item)
        if not loadable:
            return ("error", "Drum Rack not loadable")

        logger.info("Loading Drum Rack onto track %s" % track_spec)
        browser.load_item(loadable)
        return (str(track_spec), loadable.name)

    def _load_device_pad(self, params):
        """Load an instrument or effect into a drum rack pad's chain.

        Params: [track_index, device_index, pad_note, device_name]

        Selects the pad in the UI, defers one tick, then calls
        browser.load_item — this inserts the device into the pad's chain.
        Searches instruments, sounds, drums, audio_effects, midi_effects.
        """
        track_index = int(params[0])
        device_index = int(params[1])
        pad_note = int(params[2])
        device_name = str(params[3])

        browser = self.browser
        song = self.song

        track = song.tracks[track_index]
        device = track.devices[device_index]
        pad = device.drum_pads[pad_note]

        categories = [
            browser.instruments,
            browser.sounds,
            browser.drums,
            browser.audio_effects,
            browser.midi_effects,
        ]

        item = None
        for category in categories:
            item = self._find_item_recursive(category, device_name, max_depth=10)
            if item:
                break

        if not item:
            all_matches = []
            for category in categories:
                results = self._find_item_partial(category, device_name, max_depth=10)
                all_matches.extend(results)
            if all_matches:
                name_lower = device_name.lower()
                all_matches.sort(key=lambda m: (
                    0 if m.name.lower() == name_lower else 1,
                    0 if m.is_loadable else 1,
                ))
                item = all_matches[0]

        if not item:
            logger.error("Device not found for pad: %s" % device_name)
            return ("error", "Device not found: %s" % device_name)

        loadable = self._get_loadable(item)
        if not loadable:
            return ("error", "Device not loadable: %s" % device_name)

        logger.info("Loading device %s into pad %d on track %d" %
                    (loadable.name, pad_note, track_index))
        self._schedule_pad_load(track, device, pad, loadable)
        return (track_index, device_index, pad_note, loadable.name)
