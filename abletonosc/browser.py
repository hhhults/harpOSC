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

    def init_api(self):
        self.osc_server.add_handler("/live/browser/load_sample", self._load_sample)
        self.osc_server.add_handler("/live/browser/load_instrument", self._load_instrument)
        self.osc_server.add_handler("/live/browser/load_effect", self._load_effect)
        self.osc_server.add_handler("/live/browser/search", self._search)
        self.osc_server.add_handler("/live/browser/list_children", self._list_children)
        self.osc_server.add_handler("/live/track/insert_device", self._insert_device)

    def _find_item_recursive(self, parent, name, max_depth=6):
        """Recursively search browser tree for an item by name (case-insensitive)."""
        name_lower = name.lower()
        try:
            for item in parent.children:
                if item.name.lower() == name_lower:
                    return item
                if item.is_folder and max_depth > 0:
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
                if item.is_folder and max_depth > 0:
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

    def _load_instrument(self, params):
        """Load an instrument by name onto a track.

        Params: [track_index, instrument_name]
        """
        track_index = int(params[0])
        instrument_name = str(params[1])

        browser = self.browser
        song = self.song

        track = song.tracks[track_index]
        song.view.selected_track = track

        categories = [browser.instruments, browser.sounds]
        try:
            categories.append(browser.plugins)
        except Exception:
            pass

        item = None
        for category in categories:
            item = self._find_item_recursive(category, instrument_name)
            if item:
                break
            results = self._find_item_partial(category, instrument_name, max_depth=6)
            if results:
                item = results[0]
                break

        if not item:
            return ("error", "Instrument not found: %s" % instrument_name)

        loadable = self._get_loadable(item)
        if not loadable:
            return ("error", "Instrument not loadable: %s" % instrument_name)

        logger.info("Loading instrument: %s onto track %d" % (loadable.name, track_index))
        browser.load_item(loadable)
        return (track_index, loadable.name)

    def _load_effect(self, params):
        """Load an audio effect by name onto a track.

        Params: [track_index, effect_name]
        """
        track_index = int(params[0])
        effect_name = str(params[1])

        browser = self.browser
        song = self.song

        track = song.tracks[track_index]
        song.view.selected_track = track

        # Search audio_effects, midi_effects, and all top-level categories
        categories = [browser.audio_effects, browser.midi_effects]
        try:
            categories.append(browser.instruments)
            categories.append(browser.sounds)
            categories.append(browser.user_library)
            categories.append(browser.packs)
        except Exception:
            pass

        item = None
        for category in categories:
            item = self._find_item_recursive(category, effect_name, max_depth=10)
            if item:
                logger.info("Found '%s' in category, is_loadable=%s, is_folder=%s" %
                            (item.name, item.is_loadable, item.is_folder))
                break

        # Collect all matches, not just the first
        all_matches = []
        if not item:
            for category in categories:
                results = self._find_item_partial(category, effect_name, max_depth=10)
                all_matches.extend(results)
        else:
            all_matches.append(item)
            # Also search for more matches in case this one isn't loadable
            for category in categories:
                results = self._find_item_partial(category, effect_name, max_depth=10)
                for r in results:
                    if r.name != item.name or r.is_loadable != item.is_loadable:
                        all_matches.append(r)

        if not all_matches:
            return ("error", "Effect not found: %s" % effect_name)

        # Find the first loadable item among all matches
        loadable = None
        for match in all_matches:
            logger.info("Checking match '%s': is_loadable=%s, is_folder=%s" %
                         (match.name, match.is_loadable, match.is_folder))
            if match.is_loadable:
                loadable = match
                break
            child = self._get_loadable(match)
            if child:
                loadable = child
                logger.info("Using loadable child: '%s'" % child.name)
                break

        if not loadable:
            return ("error", "Effect not loadable: %s" % effect_name)

        logger.info("Loading effect: %s onto track %d" % (loadable.name, track_index))
        browser.load_item(loadable)
        return (track_index, loadable.name)

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

        Params: [track_index, device_uri, position (optional, default -1 = end)]

        Common device URIs:
            Audio effects: "Reverb", "Hybrid Reverb", "Delay", "Chorus-Ensemble",
                          "Erosion", "Redux", "Grain Delay", "Spectral Time",
                          "Echo", "Phaser-Flanger", "Saturator", "Compressor",
                          "EQ Eight", "Auto Filter", "Utility"
            Instruments:  "InstrumentSimpler", "InstrumentSampler", "Operator",
                          "Analog", "Collision", "Drift", "Meld", "Wavetable"
        """
        track_index = int(params[0])
        device_uri = str(params[1])
        position = int(params[2]) if len(params) > 2 else -1

        song = self.song
        track = song.tracks[track_index]
        song.view.selected_track = track

        if position < 0:
            position = len(track.devices)

        try:
            track.insert_device(device_uri, position)
            logger.info("Inserted device '%s' at position %d on track %d" %
                         (device_uri, position, track_index))
            # Return the name of the device that was actually created
            import time
            # Give Live a moment to create the device
            return (track_index, device_uri, position)
        except Exception as e:
            logger.error("Failed to insert device '%s': %s" % (device_uri, str(e)))
            return ("error", "Failed to insert device: %s" % str(e))
