/**
 * lom_scanner.js — Live Object Model scanner for ALS Listener
 *
 * Runs inside Max for Live's built-in JavaScript engine (the `js` object,
 * NOT node.script).  This gives us access to the `LiveAPI` constructor which
 * is only available in Max's Spidermonkey JS engine.
 *
 * Architecture
 * ────────────
 *   Max patch
 *     [js lom_scanner.js] ←── triggered by 'scan' message
 *          │
 *          │  outlet(0, 'session_data', jsonString)
 *          ▼
 *     [node.script als_listener.js] ──► WebSocket clients
 *
 * Communication
 * ─────────────
 *   Inlet 0:  'scan'   — perform full session scan, send via outlet 0
 *             'delta <json>' — broadcast a parameter delta event
 *   Outlet 0: 'session_data <jsonString>'  (→ node.script inlet)
 *             'delta <jsonString>'          (→ node.script inlet)
 *
 * LOM Tree traversal
 * ──────────────────
 *   live_set
 *     ├── tracks[N]
 *     │     ├── name, type, arm, solo, mute, mixer_device.volume.value, mixer_device.panning.value
 *     │     ├── devices[M]
 *     │     │     ├── name, class_name, is_active
 *     │     │     └── parameters[P]
 *     │     │           ├── name, value, min, max, default_value, str_for_value, is_quantized
 *     │     └── clip_slots[K].clip (if hasclip)
 *     ├── return_tracks[R]
 *     └── master_track
 *
 * Integer-ID navigation
 * ──────────────────────
 *   LiveAPI objects are navigated using api.id = N (integer setter).
 *   This is the most reliable form in all Max/Ableton versions:
 *     1. Create a throwaway LiveAPI pointing to live_set (always resolves)
 *     2. Set api.id = N (integer extracted from "id N" string)
 *     3. api now points to the requested object — name/color/etc work
 *
 *   Why NOT new LiveAPI(null, "live_set tracks 0"):
 *     Path-string construction silently returns id=0 in some Max versions.
 *
 *   Why NOT new LiveAPI(null, "id 3"):
 *     "id N" string fails with "set path: invalid path" in this environment.
 *
 *   lom_path fields stored on tracks/devices/parameters are the integer IDs
 *   as plain numbers (e.g. 3, not "id 3"), so action handlers can do:
 *     var api = new LiveAPI(null, 'live_set'); api.id = cmd.lom_id;
 *
 * Performance notes
 * ─────────────────
 *   - A session with 20 tracks × 5 devices × 40 params = 4 000 API calls.
 *   - Each LiveAPI.get() is synchronous in the js engine but still takes ~0.1–0.5 ms.
 *   - Target: < 2 s for 20 tracks.  Achieved by avoiding redundant API objects.
 *   - Clip notes are NOT scanned on initial scan (too slow).  Use 'scan_clip_notes' message.
 */

autowatch = 1;

/* ── Helpers ───────────────────────────────────────────────────────────── */

/**
 * Extract an integer LiveAPI id from the "id N" strings returned by api.get().
 * "id 3" → 3.  Returns 0 if parsing fails.
 */
function idStrToInt(idStr) {
    if (typeof idStr !== 'string') return 0;
    var parts = idStr.split(' ');
    if (parts.length < 2) return 0;
    var n = parseInt(parts[1], 10);
    return isNaN(n) ? 0 : n;
}

/**
 * Create a LiveAPI that points to the object with the given integer id.
 * Uses the id setter (api.id = N) which is reliable across all Max versions.
 */
function apiById(intId) {
    var api = new LiveAPI(null, 'live_set'); // always-valid root to bootstrap
    api.id = intId;
    return api;
}

/**
 * Safe LiveAPI.get() that returns a default on error.
 * Guards against unresolved objects (id == 0) to prevent console spam.
 * @param {LiveAPI} api
 * @param {string}  prop
 * @param {*}       [fallback]
 */
function safeGet(api, prop, fallback) {
    try {
        if (!api || api.id == 0) return fallback !== undefined ? fallback : null;
        var result = api.get(prop);
        if (result === null || result === undefined || result.length === 0) {
            return fallback !== undefined ? fallback : null;
        }
        return result[0];
    } catch (e) {
        return fallback !== undefined ? fallback : null;
    }
}

/**
 * Get a child-object list from the LOM.
 *
 * Max 9 returns:   ["id", 238, "id", 245, …]   — keyword + integer pairs
 * Max 8 returns:   ["id 238", "live_set tracks 0", …] — combined idStr + path pairs
 *
 * Returns array of {intId} objects ready for apiById().
 */
function getChildList(api, prop) {
    var raw;
    try {
        if (!api || api.id == 0) return [];
        raw = api.get(prop);
    } catch (e) {
        return [];
    }
    if (!raw || raw.length === 0) return [];

    var result = [];

    // ── Max 9: ["id", 238, "id", 245, …] ───────────────────────────────
    // raw[0] === "id" (keyword string) and raw[1] is a number
    if (raw[0] === 'id' && typeof raw[1] === 'number') {
        for (var i = 0; i + 1 < raw.length; i += 2) {
            if (raw[i] === 'id' && raw[i + 1] > 0) {
                result.push({ intId: raw[i + 1] });
            }
        }
        return result;
    }

    // ── Max 8: ["id 238", "live_set tracks 0", …] ───────────────────────
    // raw[0] starts with "id " (combined string)
    if (typeof raw[0] === 'string' && raw[0].indexOf('id ') === 0) {
        for (var j = 0; j + 1 < raw.length; j += 2) {
            var intId = idStrToInt(raw[j]);
            if (intId > 0) result.push({ intId: intId });
        }
        return result;
    }

    // ── Fallback: plain integer array [238, 245, …] ─────────────────────
    for (var k = 0; k < raw.length; k++) {
        if (typeof raw[k] === 'number' && raw[k] > 0) {
            result.push({ intId: raw[k] });
        }
    }
    return result;
}

/* ── Parameter scanner ─────────────────────────────────────────────────── */

function scanParameters(deviceApi, trackIdx, devIdx) {
    var children = getChildList(deviceApi, 'parameters');
    var params = [];
    for (var i = 0; i < children.length; i++) {
        var pApi = apiById(children[i].intId);
        params.push({
            name:         safeGet(pApi, 'name', 'Parameter ' + i),
            value:        safeGet(pApi, 'value', 0),
            min:          safeGet(pApi, 'min', 0),
            max:          safeGet(pApi, 'max', 1),
            default:      safeGet(pApi, 'default_value', 0),
            display:      safeGet(pApi, 'str_for_value', ''),
            is_quantized: safeGet(pApi, 'is_quantized', 0) ? true : false,
            lom_id:       children[i].intId,
            lom_path:     'live_set tracks ' + trackIdx + ' devices ' + devIdx + ' parameters ' + i,
            index:        i
        });
    }
    return params;
}

/* ── Device scanner ────────────────────────────────────────────────────── */

/**
 * Scan devices for a track.
 * @param {LiveAPI} trackApi
 * @param {number}  trackIdx
 * @param {boolean} [deep=false]  When false, parameters are NOT scanned (fast path).
 *                                Pass true only for on-demand deep scans to avoid
 *                                blocking the Max/Ableton main thread.
 */
function scanDevices(trackApi, trackIdx, deep) {
    var children = getChildList(trackApi, 'devices');
    var devices = [];
    for (var i = 0; i < children.length; i++) {
        var dApi = apiById(children[i].intId);
        devices.push({
            name:       safeGet(dApi, 'name', 'Device ' + i),
            class_name: safeGet(dApi, 'class_name', ''),
            is_active:  safeGet(dApi, 'is_active', 1) ? true : false,
            lom_id:     children[i].intId,
            lom_path:   'live_set tracks ' + trackIdx + ' devices ' + i,
            index:      i,
            parameters: deep ? scanParameters(dApi, trackIdx, i) : []
        });
    }
    return devices;
}

/* ── Clip scanner ──────────────────────────────────────────────────────── */

function scanClips(trackApi, trackIdx) {
    var slots = getChildList(trackApi, 'clip_slots');
    var clips = [];
    for (var i = 0; i < slots.length; i++) {
        var slotApi = apiById(slots[i].intId);
        var hasClip = safeGet(slotApi, 'has_clip', 0);
        if (!hasClip) continue;

        var clipChildren = getChildList(slotApi, 'clip');
        if (!clipChildren.length) continue;

        var cApi = apiById(clipChildren[0].intId);
        clips.push({
            name:         safeGet(cApi, 'name', ''),
            length:       safeGet(cApi, 'length', 0),
            is_playing:   safeGet(cApi, 'is_playing', 0) ? true : false,
            is_triggered: safeGet(cApi, 'is_triggered', 0) ? true : false,
            is_midi:      safeGet(cApi, 'is_midi_clip', 0) ? true : false,
            color:        safeGet(cApi, 'color', 0),
            lom_id:       clipChildren[0].intId,
            lom_path:     'live_set tracks ' + trackIdx + ' clip_slots ' + i + ' clip',
            slot_index:   i,
            notes:        []
        });
    }
    return clips;
}

/* ── Track scanner ─────────────────────────────────────────────────────── */

/**
 * Scan a single track.
 * @param {number}  trackIntId  Integer LiveAPI id of the track.
 * @param {number}  idx         Track index in its list (tracks or return_tracks).
 * @param {boolean} isReturn    True for return tracks.
 * @param {boolean} [deep=false] When false, devices have no parameters and clips
 *                               are not scanned — keeps the initial scan fast.
 */
function scanTrack(trackIntId, idx, isReturn, deep) {
    var api = apiById(trackIntId);

    // Mixer device for volume/pan
    var volRaw = 0.85; // default = 0 dB
    var panRaw = 0.5;
    try {
        var mixerChildren = getChildList(api, 'mixer_device');
        if (mixerChildren.length > 0) {
            var mApi = apiById(mixerChildren[0].intId);
            var volChildren = getChildList(mApi, 'volume');
            var panChildren = getChildList(mApi, 'panning');
            if (volChildren.length > 0) {
                var vApi = apiById(volChildren[0].intId);
                volRaw = safeGet(vApi, 'value', 0.85);
            }
            if (panChildren.length > 0) {
                var pApi = apiById(panChildren[0].intId);
                panRaw = safeGet(pApi, 'value', 0.5);
            }
        }
    } catch (e) { /* use defaults */ }

    // Live 11/12 removed the 'type' property from the Track LOM object.
    // Infer track type from properties that DO exist:
    //   is_foldable=1 → group track
    //   has_midi_input=1 → midi track
    //   isReturn flag (passed in from scan loop) → return track
    var typeStr;
    if (isReturn) {
        typeStr = 'return';
    } else {
        var isFoldable  = safeGet(api, 'is_foldable',   0) ? true : false;
        var hasMidiIn   = safeGet(api, 'has_midi_input', 0) ? true : false;
        typeStr = isFoldable ? 'group' : (hasMidiIn ? 'midi' : 'audio');
    }

    // arm: only valid on regular (non-return) tracks.
    // Calling api.get('arm') on a return track logs "Main and Return Tracks
    // have no 'Arm' state!" to the Max console on every scan.
    var armVal = isReturn ? false : (safeGet(api, 'arm', 0) ? true : false);

    var prefix = isReturn ? 'live_set return_tracks ' : 'live_set tracks ';

    return {
        name:     safeGet(api, 'name', 'Track ' + idx),
        index:    idx,
        type:     typeStr,
        arm:      armVal,
        solo:     safeGet(api, 'solo', 0) ? true : false,
        mute:     safeGet(api, 'mute', 0) ? true : false,
        volume:   volRaw,
        pan:      panRaw,
        color:    safeGet(api, 'color', 0),
        lom_id:   trackIntId,
        lom_path: prefix + idx,
        devices:  isReturn ? [] : scanDevices(api, idx, deep),
        clips:    (isReturn || !deep) ? [] : scanClips(api, idx)
    };
}

/* ── Master track ──────────────────────────────────────────────────────── */

function scanMasterTrack() {
    var api = new LiveAPI(null, 'live_set master_track');
    var volRaw = 0.85;
    var panRaw = 0.5;
    try {
        var mixerChildren = getChildList(api, 'mixer_device');
        if (mixerChildren.length > 0) {
            var mApi = apiById(mixerChildren[0].intId);
            var volChildren = getChildList(mApi, 'volume');
            var panChildren = getChildList(mApi, 'panning');
            if (volChildren.length > 0) {
                var vApi = apiById(volChildren[0].intId);
                volRaw = safeGet(vApi, 'value', 0.85);
            }
            if (panChildren.length > 0) {
                var pApi = apiById(panChildren[0].intId);
                panRaw = safeGet(pApi, 'value', 0.5);
            }
        }
    } catch (e) { /* use defaults */ }
    return {
        name:     'Master',
        index:    0,
        type:     'master',
        arm:      false,
        solo:     false,
        mute:     false,
        volume:   volRaw,
        pan:      panRaw,
        color:    safeGet(api, 'color', 0),
        lom_id:   api.id,
        lom_path: 'live_set master_track',
        devices:  [],
        clips:    []
    };
}

/* ── Full session scan ─────────────────────────────────────────────────── */

function scan() {
    var rootApi = new LiveAPI(null, 'live_set');

    // ── Diagnostic: log raw format and test apiById on first track ───────
    try {
        var rawTracks = rootApi.get('tracks');
        var fmt = rawTracks ? (rawTracks.length + ' elements: [' + rawTracks[0] + ', ' + rawTracks[1] + ', ...]') : 'null';
        post('ALS diag: tracks raw fmt=' + fmt + '\n');
        // Extract first track integer id depending on format
        var firstIntId = 0;
        if (rawTracks && rawTracks.length >= 2) {
            if (rawTracks[0] === 'id' && typeof rawTracks[1] === 'number') {
                firstIntId = rawTracks[1]; // Max 9: ["id", 238, ...]
            } else if (typeof rawTracks[0] === 'string' && rawTracks[0].indexOf('id ') === 0) {
                firstIntId = idStrToInt(rawTracks[0]); // Max 8: ["id 238", ...]
            } else if (typeof rawTracks[0] === 'number') {
                firstIntId = rawTracks[0]; // plain int array
            }
        }
        if (firstIntId > 0) {
            var testApi = apiById(firstIntId);
            var nameArr = testApi.get('name');
            post('ALS diag: apiById(' + firstIntId + ').id=' + testApi.id + ' name=' + JSON.stringify(nameArr) + '\n');
        } else {
            post('ALS diag: could not extract first track id from raw data\n');
        }
    } catch (e) {
        post('ALS diag error: ' + e + '\n');
    }
    // ── End diagnostic ───────────────────────────────────────────────────

    var trackList = getChildList(rootApi, 'tracks');
    var returnList = getChildList(rootApi, 'return_tracks');

    // ── Fast path: deep=false skips parameters and clips.
    // A session with 20 tracks × 5 devices × 40 params = 4 000 synchronous
    // LiveAPI.get() calls, which blocks Ableton's main thread for several seconds.
    // We scan only track metadata + device names here (~5-10 calls per track).
    // Parameters are loaded on-demand via 'scan_params_for_device'.
    var tracks = [];
    for (var i = 0; i < trackList.length; i++) {
        tracks.push(scanTrack(trackList[i].intId, i, false, false));
    }

    var returnTracks = [];
    for (var j = 0; j < returnList.length; j++) {
        returnTracks.push(scanTrack(returnList[j].intId, j, true, false));
    }

    var session = {
        tracks:               tracks,
        return_tracks:        returnTracks,
        master_track:         scanMasterTrack(),
        tempo:                safeGet(rootApi, 'tempo', 120),
        time_sig_numerator:   safeGet(rootApi, 'signature_numerator', 4),
        time_sig_denominator: safeGet(rootApi, 'signature_denominator', 4),
        is_playing:           safeGet(rootApi, 'is_playing', 0) ? true : false,
        current_song_time:    safeGet(rootApi, 'current_song_time', 0),
        scene_count:          getChildList(rootApi, 'scenes').length,
        metronome:            safeGet(rootApi, 'metronome', 0) ? true : false,
        loop:                 safeGet(rootApi, 'loop', 0) ? true : false,
        session_record:       safeGet(rootApi, 'session_record', 0) ? true : false,
        overdub:              safeGet(rootApi, 'overdub', 0) ? true : false
    };

    outlet(0, 'session_data', JSON.stringify(session));
}

/* ── LOM parameter write ───────────────────────────────────────────────── */

/**
 * Handle set_parameter commands from node.script.
 * msg format: '{"lom_id":5,"value":0.72}'  — preferred (uses integer id)
 *             '{"lom_path":"live_set tracks 0 devices 1 parameters 5","value":0.72}' — fallback
 */
function set_parameter(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api;
        if (cmd.lom_id) {
            api = apiById(cmd.lom_id);
        } else {
            api = new LiveAPI(null, cmd.lom_path);
        }
        api.set('value', cmd.value);
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_id: cmd.lom_id || 0, value: cmd.value }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Handle set_property commands (track arm/solo/mute, live_set transport props, etc.)
 * msg format: '{"lom_id":3,"property":"mute","value":1}'           — preferred
 *             '{"lom_path":"live_set","property":"loop","value":1}' — for root objects
 */
function set_property(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api;
        if (cmd.lom_id) {
            api = apiById(cmd.lom_id);
        } else {
            api = new LiveAPI(null, cmd.lom_path);
        }
        api.set(cmd.property, cmd.value);
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_id: cmd.lom_id || 0, property: cmd.property, value: cmd.value }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Handle call_method commands — invokes an LOM method (e.g. start_playing).
 * msg format: '{"lom_path":"live_set","method":"start_playing"}'
 *             '{"lom_id":3,"method":"fire"}'
 */
function call_method(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api;
        if (cmd.lom_id) {
            api = apiById(cmd.lom_id);
        } else {
            api = new LiveAPI(null, cmd.lom_path);
        }
        if (cmd.args && cmd.args.length > 0) {
            var callArgs = [cmd.method].concat(cmd.args);
            api.call.apply(api, callArgs);
        } else {
            api.call(cmd.method);
        }
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_id: cmd.lom_id || 0, method: cmd.method }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/* ── Real-time observers ───────────────────────────────────────────────── */

var _observers = [];
var _lastBroadcast = 0;
var _THROTTLE_MS = 33; // ~30 fps

/**
 * Called by the Max patch to install observers on all track parameters.
 * Observers fire when any tracked parameter changes and send 'delta' messages.
 */
function install_observers() {
    for (var i = 0; i < _observers.length; i++) {
        try { _observers[i].id = 'undefined'; } catch (e) {}
    }
    _observers = [];

    var rootApi = new LiveAPI(null, 'live_set');
    var trackList = getChildList(rootApi, 'tracks');

    for (var ti = 0; ti < trackList.length; ti++) {
        var tApi = apiById(trackList[ti].intId);
        var devList = getChildList(tApi, 'devices');
        for (var di = 0; di < devList.length; di++) {
            var dApi = apiById(devList[di].intId);
            var paramList = getChildList(dApi, 'parameters');
            for (var pi = 0; pi < paramList.length; pi++) {
                (function(tIdx, dIdx, pIdx, pIntId) {
                    var obs = new LiveAPI(function() {
                        var now = Date.now();
                        if (now - _lastBroadcast < _THROTTLE_MS) return;
                        _lastBroadcast = now;
                        var pApi2 = apiById(pIntId);
                        var delta = {
                            type:     'parameter_delta',
                            lom_id:   pIntId,
                            lom_path: 'live_set tracks ' + tIdx + ' devices ' + dIdx + ' parameters ' + pIdx,
                            value:    safeGet(pApi2, 'value', 0),
                            display:  safeGet(pApi2, 'str_for_value', '')
                        };
                        outlet(0, 'delta', JSON.stringify(delta));
                    }, pIntId);
                    obs.property = 'value';
                    _observers.push(obs);
                })(ti, di, pi, paramList[pi].intId);
            }
        }
    }

    post('ALS Listener: installed ' + _observers.length + ' parameter observers\n');
}

/* ── On-demand deep scans ──────────────────────────────────────────────── */

/**
 * Scan parameters for a single device — called after the fast initial scan.
 * Send this message from node.script when the UI requests a device's parameters.
 *
 * msg format: '{"device_lom_id":42,"track_idx":0,"dev_idx":1}'
 *
 * Response outlet: 'device_params <json>'
 * JSON: { type, device_lom_id, track_idx, dev_idx, parameters: [...] }
 */
function scan_params_for_device(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var dApi = apiById(cmd.device_lom_id);
        var params = scanParameters(dApi, cmd.track_idx, cmd.dev_idx);
        outlet(0, 'device_params', JSON.stringify({
            type:          'device_params',
            device_lom_id: cmd.device_lom_id,
            track_idx:     cmd.track_idx,
            dev_idx:       cmd.dev_idx,
            parameters:    params
        }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Scan clips for a single track — called on-demand after the fast initial scan.
 *
 * msg format: '{"track_lom_id":238,"track_idx":0}'
 *
 * Response outlet: 'track_clips <json>'
 * JSON: { type, track_lom_id, track_idx, clips: [...] }
 */
function scan_clips_for_track(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var tApi = apiById(cmd.track_lom_id);
        var clips = scanClips(tApi, cmd.track_idx);
        outlet(0, 'track_clips', JSON.stringify({
            type:         'track_clips',
            track_lom_id: cmd.track_lom_id,
            track_idx:    cmd.track_idx,
            clips:        clips
        }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Full deep scan — includes parameters and clips for all tracks.
 * USE WITH CAUTION: blocks for several seconds on large sessions.
 * Prefer 'scan' (fast) + on-demand 'scan_params_for_device' in production.
 */
function scan_deep() {
    var rootApi = new LiveAPI(null, 'live_set');
    var trackList  = getChildList(rootApi, 'tracks');
    var returnList = getChildList(rootApi, 'return_tracks');

    var tracks = [];
    for (var i = 0; i < trackList.length; i++) {
        tracks.push(scanTrack(trackList[i].intId, i, false, true));
    }
    var returnTracks = [];
    for (var j = 0; j < returnList.length; j++) {
        returnTracks.push(scanTrack(returnList[j].intId, j, true, true));
    }

    var session = {
        tracks:               tracks,
        return_tracks:        returnTracks,
        master_track:         scanMasterTrack(),
        tempo:                safeGet(rootApi, 'tempo', 120),
        time_sig_numerator:   safeGet(rootApi, 'signature_numerator', 4),
        time_sig_denominator: safeGet(rootApi, 'signature_denominator', 4),
        is_playing:           safeGet(rootApi, 'is_playing', 0) ? true : false,
        current_song_time:    safeGet(rootApi, 'current_song_time', 0),
        scene_count:          getChildList(rootApi, 'scenes').length,
        metronome:            safeGet(rootApi, 'metronome', 0) ? true : false,
        loop:                 safeGet(rootApi, 'loop', 0) ? true : false,
        session_record:       safeGet(rootApi, 'session_record', 0) ? true : false,
        overdub:              safeGet(rootApi, 'overdub', 0) ? true : false
    };

    outlet(0, 'session_data', JSON.stringify(session));
    post('ALS Listener: deep scan complete (' + tracks.length + ' tracks)\n');
}

/* ── Max message handlers ──────────────────────────────────────────────── */

function msg_int(v) { /* ignore */ }
function bang() { scan(); }
