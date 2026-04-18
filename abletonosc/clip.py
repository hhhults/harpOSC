import re
from typing import Tuple, Callable, Any, Optional
from .handler import AbletonOSCHandler
import Live

def note_name_to_midi(name):
    """ Maps a MIDI note name (D3, C#6) to a value.
    Assumes that middle C is C4. """
    note_names = [["C"],
                  ["C#", "Db"],
                  ["D"],
                  ["D#", "Eb"],
                  ["E"],
                  ["F"],
                  ["F#", "Gb"],
                  ["G"],
                  ["G#", "Ab"],
                  ["A"],
                  ["A#", "Bb"],
                  ["B"]]

    for index, names in enumerate(note_names):
        if name in names:
            return index
    return None

class ClipHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "clip"
        self._clip_notes_cache = []

    def init_api(self):
        def create_clip_callback(func, *args, pass_clip_index=False):
            """
            Creates a callback that expects the following set of arguments:
              (track_index, clip_index, *args)

            The callback then extracts the relevant `Clip` object from the current Song,
            and calls `func` with this `Clip` object plus any additional *args.

            pass_clip_index is a bit of an ugly hack, although seems like the lesser of
            evils for scenarios where the track/clip index is needed (as a clip is unable
            to query its own index). Other alternatives include _always_ passing track/clip
            index to the callback, but this adds arg clutter to every single callback.
            """

            def clip_callback(params: Tuple[Any]) -> Tuple:
                #--------------------------------------------------------------------------------
                # Cast to int to support clients such as TouchOSC that, by default, pass all
                # numeric arguments as float.
                #--------------------------------------------------------------------------------
                track_index, clip_index = int(params[0]), int(params[1])
                track = self.song.tracks[track_index]
                clip = track.clip_slots[clip_index].clip
                if pass_clip_index:
                    rv = func(clip, *args, tuple(params[0:]))
                else:
                    rv = func(clip, *args, tuple(params[2:]))

                if rv is not None:
                    return (track_index, clip_index, *rv)

            return clip_callback

        methods = [
            "fire",
            "stop",
            "duplicate_loop", 
            "remove_notes_by_id"
        ]
        properties_r = [
            "end_time",
            "file_path",
            "gain_display_string",
            "has_groove",
            "is_midi_clip",
            "is_audio_clip",
            "is_overdubbing",
            "is_playing",
            "is_recording",
            "is_triggered",
            "length",
            "playing_position",
            "sample_length",
            "start_time",
            "will_record_on_start"
            ## TODO list:
            ##"groove", ## if other than None, says "Error handling OSC message: Infered arg_value type is not supported"
            ## is_arrangement_clip            
            ##"warp_markers", ## "Infered arg_value type is not supported"
            ##"view", ##"Infered arg_value type is not supported"
        ]
        properties_rw = [
            "color",
            "color_index",
            "end_marker",
            "gain",
            "launch_mode",
            "launch_quantization",
            "legato",
            "loop_end",
            "loop_start",
            "looping",
            "muted",
            "name",
            "pitch_coarse",
            "pitch_fine",
            "position",
            "ram_mode",
            "start_marker",
            "velocity_amount",
            "warp_mode",
            "warping",
        ]

        for method in methods:
            self.osc_server.add_handler("/live/clip/%s" % method,
                                        create_clip_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/clip/get/%s" % prop,
                                        create_clip_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/clip/start_listen/%s" % prop,
                                        create_clip_callback(self._start_listen, prop, pass_clip_index=True))
            self.osc_server.add_handler("/live/clip/stop_listen/%s" % prop,
                                        create_clip_callback(self._stop_listen, prop, pass_clip_index=True))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/clip/set/%s" % prop,
                                        create_clip_callback(self._set_property, prop))

        def clip_get_notes(clip, params: Tuple[Any] = ()):
            if len(params) == 4:
                pitch_start, pitch_span, time_start, time_span = params
            elif len(params) == 0:
                pitch_start, pitch_span, time_start, time_span = 0, 127, -8192, 16384
            else:
                raise ValueError("Invalid number of arguments for /clip/get/notes. Either 0 or 4 arguments must be passed.")
            notes = clip.get_notes_extended(pitch_start, pitch_span, time_start, time_span)
            all_note_attributes = []
            for note in notes:
                all_note_attributes += [note.pitch, note.start_time, note.duration, note.velocity, note.mute]
            return tuple(all_note_attributes)

        def clip_add_notes(clip, params: Tuple[Any] = ()):
            notes = []
            for offset in range(0, len(params), 5):
                pitch, start_time, duration, velocity, mute = params[offset:offset + 5]
                note = Live.Clip.MidiNoteSpecification(start_time=start_time,
                                                       duration=duration,
                                                       pitch=pitch,
                                                       velocity=velocity,
                                                       mute=mute)
                notes.append(note)
            clip.add_new_notes(tuple(notes))

        def clip_remove_notes(clip, params: Tuple[Any] = ()):
            if len(params) == 4:
                pitch_start, pitch_span, time_start, time_span = params
            elif len(params) == 0:
                pitch_start, pitch_span, time_start, time_span = 0, 127, -8192, 16384
            else:
                raise ValueError("Invalid number of arguments for /clip/remove/notes. Either 0 or 4 arguments must be passed.")
            clip.remove_notes_extended(pitch_start, pitch_span, time_start, time_span)

        self.osc_server.add_handler("/live/clip/get/notes", create_clip_callback(clip_get_notes))
        self.osc_server.add_handler("/live/clip/add/notes", create_clip_callback(clip_add_notes))
        self.osc_server.add_handler("/live/clip/remove/notes", create_clip_callback(clip_remove_notes))

        # ---------- Extended note API (probability, velocity_deviation, release_velocity) ----------

        def clip_get_notes_ext(clip, params: Tuple[Any] = ()):
            """Return notes with all per-note expression fields.

            Payload per note: note_id, pitch, start_time, duration, velocity,
                              mute, probability, velocity_deviation, release_velocity
            """
            if len(params) == 4:
                pitch_start, pitch_span, time_start, time_span = params
            elif len(params) == 0:
                pitch_start, pitch_span, time_start, time_span = 0, 127, -8192, 16384
            else:
                raise ValueError("Invalid number of arguments for /clip/get/notes_ext")
            notes = clip.get_notes_extended(pitch_start, pitch_span, time_start, time_span)
            flat = []
            for n in notes:
                flat += [
                    int(n.note_id),
                    int(n.pitch),
                    float(n.start_time),
                    float(n.duration),
                    float(n.velocity),
                    bool(n.mute),
                    float(n.probability),
                    float(n.velocity_deviation),
                    float(n.release_velocity),
                ]
            return tuple(flat)

        def clip_add_notes_ext(clip, params: Tuple[Any] = ()):
            self.logger.info("add_notes_ext: %d values (%d notes)" % (len(params), len(params) // 8))
            """Add notes with expressive fields.

            8 values per note: pitch, start_time, duration, velocity, mute,
                               probability, velocity_deviation, release_velocity

            Tries MidiNoteSpecification with all kwargs first (Live 11+).
            Falls back to two-step: add basic, then re-fetch and mutate properties
            directly (no apply_note_modifications call — direct property writes
            on MidiNote objects take effect immediately in Live's Clip API).
            """
            if len(params) == 0:
                return
            if len(params) % 8 != 0:
                raise ValueError("add/notes_ext expects 8 values per note")

            parsed = []
            for offset in range(0, len(params), 8):
                pitch, start, dur, vel, mute, prob, vdev, rvel = params[offset:offset + 8]
                parsed.append((
                    int(pitch), float(start), float(dur), float(vel),
                    bool(mute), float(prob), float(vdev), float(rvel),
                ))

            # Try one-shot: pass everything to MidiNoteSpecification
            try:
                specs = [Live.Clip.MidiNoteSpecification(
                    pitch=p, start_time=s, duration=d, velocity=v, mute=m,
                    probability=prob, velocity_deviation=vd, release_velocity=rv,
                ) for (p, s, d, v, m, prob, vd, rv) in parsed]
                clip.add_new_notes(tuple(specs))
                return
            except (TypeError, Exception) as e:
                logger.info("MidiNoteSpecification one-shot failed, falling back: %s" % e)

            # Fallback: basic add, then direct property mutation on refetched notes
            specs = [Live.Clip.MidiNoteSpecification(
                pitch=p, start_time=s, duration=d, velocity=v, mute=m,
            ) for (p, s, d, v, m, _, _, _) in parsed]
            clip.add_new_notes(tuple(specs))

            needs_mod = any(
                (prob != 1.0) or (vd != 0.0) or (abs(rv - 64.0) > 0.001)
                for (_, _, _, _, _, prob, vd, rv) in parsed
            )
            if not needs_mod:
                return

            min_start = min(p[1] for p in parsed)
            max_end = max(p[1] + p[2] for p in parsed)
            min_pitch = min(p[0] for p in parsed)
            max_pitch = max(p[0] for p in parsed)

            existing = list(clip.get_notes_extended(
                max(0, min_pitch),
                min(128, max_pitch - min_pitch + 1),
                min_start,
                max(0.001, max_end - min_start + 0.01),
            ))
            matched = set()
            for (pitch, start, dur, vel, mute, prob, vdev, rvel) in parsed:
                for i, ex in enumerate(existing):
                    if i in matched:
                        continue
                    if (ex.pitch == pitch
                            and abs(ex.start_time - start) < 1e-4
                            and abs(ex.duration - dur) < 1e-4):
                        ex.probability = prob
                        ex.velocity_deviation = vdev
                        ex.release_velocity = rvel
                        matched.add(i)
                        break

        def clip_apply_note_mods(clip, params: Tuple[Any] = ()):
            """Modify notes in place by note_id.

            9 values per note: note_id, pitch, start_time, duration, velocity,
                               mute, probability, velocity_deviation, release_velocity
            Looks up each note by id from the current clip state and applies
            only the fields that differ, then calls apply_note_modifications.
            """
            if len(params) == 0:
                return
            if len(params) % 9 != 0:
                raise ValueError("apply_note_mods expects 9 values per note")

            # Build index of existing notes by id
            existing = list(clip.get_notes_extended(0, 127, -8192, 16384))
            by_id = {int(n.note_id): n for n in existing}

            for offset in range(0, len(params), 9):
                note_id, pitch, start, dur, vel, mute, prob, vdev, rvel = params[offset:offset + 9]
                n = by_id.get(int(note_id))
                if n is None:
                    continue
                n.pitch = int(pitch)
                n.start_time = float(start)
                n.duration = float(dur)
                n.velocity = float(vel)
                n.mute = bool(mute)
                n.probability = float(prob)
                n.velocity_deviation = float(vdev)
                n.release_velocity = float(rvel)

        self.osc_server.add_handler("/live/clip/get/notes_ext",
                                    create_clip_callback(clip_get_notes_ext))
        self.osc_server.add_handler("/live/clip/add/notes_ext",
                                    create_clip_callback(clip_add_notes_ext))
        self.osc_server.add_handler("/live/clip/apply_note_mods",
                                    create_clip_callback(clip_apply_note_mods))

        def clips_filter_handler(params: Tuple):
            # TODO: Pre-cache clip notes
            if len(self._clip_notes_cache) == 0:
                self.logger.warning("Building clip notes cache...")
                self._build_clip_name_cache()
            else:
                self.logger.warning("Found existing clip notes cache (len = %d)" % len(self._clip_notes_cache))
            note_indices = [note_name_to_midi(name) for name in params]

            self.logger.warning("Got note indices: %s" % note_indices)
            for track_index, track in enumerate(self.song.tracks):
                for clip_slot_index, clip_slot in enumerate(track.clip_slots):
                    clip_notes_list = self._clip_notes_cache[track_index][clip_slot_index]
                    if clip_notes_list:
                        clip = clip_slot.clip
                        if all(note in note_indices for note in clip_notes_list):
                            clip.muted = False
                        else:
                            clip.muted = True

        self.osc_server.add_handler("/live/clips/filter", clips_filter_handler)

        def clips_unfilter_handler(params: Tuple):
            track_start = params[0] if len(params) > 0 else 0
            track_end = params[1] if len(params) > 1 else len(self.song.tracks)

            self.logger.info("Unfiltering tracks: %d .. %d" % (track_start, track_end))
            for track in self.song.tracks[track_start:track_end]:
                for clip_slot in track.clip_slots:
                    if clip_slot.has_clip:
                        clip = clip_slot.clip
                        clip.muted = False

        self.osc_server.add_handler("/live/clips/unfilter", clips_unfilter_handler)

    def _build_clip_name_cache(self):
        regex = "([_-])([A-G][A-G#b1-9-]*)$"
        for track_index, track in enumerate(self.song.tracks):
            self._clip_notes_cache.append([])
            for clip_slot_index, clip_slot in enumerate(track.clip_slots):
                self._clip_notes_cache[-1].append([])
                if clip_slot.has_clip:
                    clip = clip_slot.clip
                    clip_name = clip.name
                    match = re.search(regex, clip_name)
                    if match:
                        clip_notes_str = match.group(2)
                        clip_notes_str = re.sub("[1-9]", "", clip_notes_str)
                        clip_notes_list = clip_notes_str.split("-")
                        clip_notes_list = [note_name_to_midi(name) for name in clip_notes_list]
                        self._clip_notes_cache[-1][-1] = clip_notes_list
