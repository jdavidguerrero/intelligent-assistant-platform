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
 * LiveAPI.get('tracks') returns [idStr, path, idStr, path, …] alternating.
 * Returns array of {intId, path} objects.  intId is the integer form of "id N".
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

    // Detect format: "id N" strings interleaved with path strings
    // Each pair is [idStr, pathStr].  If raw.length is odd or first element
    // doesn't look like "id N", fall back to treating every element as an id.
    var result = [];
    var isInterleaved = (raw.length % 2 === 0) && (typeof raw[0] === 'string') && (raw[0].indexOf('id ') === 0);
    if (isInterleaved) {
        for (var i = 0; i + 1 < raw.length; i += 2) {
            var intId = idStrToInt(raw[i]);
            if (intId > 0) result.push({ intId: intId, path: raw[i + 1] });
        }
    } else {
        // Possibly only IDs (no path column)
        for (var j = 0; j < raw.length; j++) {
            var intId2 = idStrToInt(raw[j]);
            if (intId2 > 0) result.push({ intId: intId2, path: '' });
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

function scanDevices(trackApi, trackIdx) {
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
            parameters: scanParameters(dApi, trackIdx, i)
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

function scanTrack(trackIntId, idx, isReturn) {
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

    var trackType = safeGet(api, 'type', 0);
    var typeNames = ['audio', 'midi', 'return', 'master', 'group'];
    var typeStr = typeNames[trackType] || 'audio';
    var prefix = isReturn ? 'live_set return_tracks ' : 'live_set tracks ';

    return {
        name:     safeGet(api, 'name', 'Track ' + idx),
        index:    idx,
        type:     typeStr,
        arm:      safeGet(api, 'arm', 0) ? true : false,
        solo:     safeGet(api, 'solo', 0) ? true : false,
        mute:     safeGet(api, 'mute', 0) ? true : false,
        volume:   volRaw,
        pan:      panRaw,
        color:    safeGet(api, 'color', 0),
        lom_id:   trackIntId,
        lom_path: prefix + idx,
        devices:  isReturn ? [] : scanDevices(api, idx),
        clips:    isReturn ? [] : scanClips(api, idx)
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

    // ── Diagnostic: log first few raw values to confirm format ──────────
    try {
        var rawTracks = rootApi.get('tracks');
        if (rawTracks && rawTracks.length >= 2) {
            post('ALS diag: tracks[0]=' + rawTracks[0] + ' tracks[1]=' + rawTracks[1] + '\n');
        }
        // Test id setter: does apiById work for first track?
        if (rawTracks && rawTracks.length >= 1) {
            var testId = idStrToInt(rawTracks[0]);
            if (testId > 0) {
                var testApi = apiById(testId);
                var testName = (testApi.id > 0) ? 'id_ok:' + testApi.id : 'id_zero';
                post('ALS diag: apiById(' + testId + ') → ' + testName + ' name=' + JSON.stringify(testApi.get('name')) + '\n');
            }
        }
    } catch (e) {
        post('ALS diag error: ' + e + '\n');
    }
    // ── End diagnostic ───────────────────────────────────────────────────

    var trackList = getChildList(rootApi, 'tracks');
    var returnList = getChildList(rootApi, 'return_tracks');

    var tracks = [];
    for (var i = 0; i < trackList.length; i++) {
        tracks.push(scanTrack(trackList[i].intId, i, false));
    }

    var returnTracks = [];
    for (var j = 0; j < returnList.length; j++) {
        returnTracks.push(scanTrack(returnList[j].intId, j, true));
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

/* ── Max message handlers ──────────────────────────────────────────────── */

function msg_int(v) { /* ignore */ }
function bang() { scan(); }
