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
 * ID-based navigation
 * ───────────────────
 *   LiveAPI objects are created using the "id N" string returned by
 *   api.get('tracks') etc. rather than by path string.  Path-string
 *   construction (e.g. new LiveAPI(null, 'live_set tracks 0')) fails
 *   silently in some Max/Ableton versions — the resulting object has id=0
 *   and all get/set calls are no-ops.  Using "id N" format always resolves.
 *
 *   lom_path fields stored on tracks/devices/parameters are therefore the
 *   "id N" string (e.g. "id 3"), not the human-readable LOM path.  The
 *   action handlers (set_parameter, set_property, call_method) receive these
 *   IDs from the frontend and use new LiveAPI(null, id) to resolve objects.
 *
 *   Exception: live_set root and live_set master_track use the string path
 *   because they are root objects that always resolve correctly by path.
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
 * Safe LiveAPI.get() that returns a default on error.
 * Guards against unresolved objects (id falsy) to prevent console spam.
 * @param {LiveAPI} api
 * @param {string}  prop
 * @param {*}       [fallback]
 */
function safeGet(api, prop, fallback) {
    try {
        // !api.id means the object didn't resolve — skip to avoid console spam
        if (!api || !api.id) return fallback !== undefined ? fallback : null;
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
 * LiveAPI.get('tracks') returns [id, path, id, path, …]
 * Returns array of {id, path} objects.
 */
function getChildList(api, prop) {
    var raw;
    try {
        // Guard against unresolved LOM objects to avoid "no valid object set" spam
        if (!api || !api.id) return [];
        raw = api.get(prop);
    } catch (e) {
        return [];
    }
    if (!raw || raw.length === 0) return [];
    var result = [];
    for (var i = 0; i + 1 < raw.length; i += 2) {
        result.push({ id: raw[i], path: raw[i + 1] });
    }
    return result;
}

/* ── Parameter scanner ─────────────────────────────────────────────────── */

function scanParameters(deviceApi, trackIdx, devIdx) {
    var children = getChildList(deviceApi, 'parameters');
    var params = [];
    for (var i = 0; i < children.length; i++) {
        var pApi = new LiveAPI(null, children[i].id);
        params.push({
            name:         safeGet(pApi, 'name', 'Parameter ' + i),
            value:        safeGet(pApi, 'value', 0),
            min:          safeGet(pApi, 'min', 0),
            max:          safeGet(pApi, 'max', 1),
            default:      safeGet(pApi, 'default_value', 0),
            display:      safeGet(pApi, 'str_for_value', ''),
            is_quantized: safeGet(pApi, 'is_quantized', 0) ? true : false,
            lom_path:     children[i].id,
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
        var dApi = new LiveAPI(null, children[i].id);
        devices.push({
            name:       safeGet(dApi, 'name', 'Device ' + i),
            class_name: safeGet(dApi, 'class_name', ''),
            is_active:  safeGet(dApi, 'is_active', 1) ? true : false,
            lom_path:   children[i].id,
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
        var slotApi = new LiveAPI(null, slots[i].id);
        var hasClip = safeGet(slotApi, 'has_clip', 0);
        if (!hasClip) continue;

        var clipChildren = getChildList(slotApi, 'clip');
        if (!clipChildren.length) continue;

        var cApi = new LiveAPI(null, clipChildren[0].id);
        clips.push({
            name:         safeGet(cApi, 'name', ''),
            length:       safeGet(cApi, 'length', 0),
            is_playing:   safeGet(cApi, 'is_playing', 0) ? true : false,
            is_triggered: safeGet(cApi, 'is_triggered', 0) ? true : false,
            is_midi:      safeGet(cApi, 'is_midi_clip', 0) ? true : false,
            color:        safeGet(cApi, 'color', 0),
            lom_path:     clipChildren[0].id,
            slot_index:   i,
            notes:        []   // populated on demand via 'scan_clip_notes' message
        });
    }
    return clips;
}

/* ── Track scanner ─────────────────────────────────────────────────────── */

function scanTrack(trackId, idx, isReturn) {
    var api = new LiveAPI(null, trackId);

    // Mixer device for volume/pan
    var volRaw = 0.85; // default = 0 dB
    var panRaw = 0.5;
    try {
        var mixerChildren = getChildList(api, 'mixer_device');
        if (mixerChildren.length > 0) {
            var mApi = new LiveAPI(null, mixerChildren[0].id);
            var volChildren = getChildList(mApi, 'volume');
            var panChildren = getChildList(mApi, 'panning');
            if (volChildren.length > 0) {
                var vApi = new LiveAPI(null, volChildren[0].id);
                volRaw = safeGet(vApi, 'value', 0.85);
            }
            if (panChildren.length > 0) {
                var pApi = new LiveAPI(null, panChildren[0].id);
                panRaw = safeGet(pApi, 'value', 0.5);
            }
        }
    } catch (e) { /* use defaults */ }

    var trackType = safeGet(api, 'type', 0);
    var typeNames = ['audio', 'midi', 'return', 'master', 'group'];
    var typeStr = typeNames[trackType] || 'audio';

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
        lom_path: trackId,
        devices:  isReturn ? [] : scanDevices(api, idx),
        clips:    isReturn ? [] : scanClips(api, idx)
    };
}

/* ── Master track ──────────────────────────────────────────────────────── */

function scanMasterTrack() {
    var api = new LiveAPI(null, 'live_set master_track');
    // Navigate LOM tree for volume/pan (dot-notation is not supported by LiveAPI)
    var volRaw = 0.85; // default = 0 dB
    var panRaw = 0.5;
    try {
        var mixerChildren = getChildList(api, 'mixer_device');
        if (mixerChildren.length > 0) {
            var mApi = new LiveAPI(null, mixerChildren[0].id);
            var volChildren = getChildList(mApi, 'volume');
            var panChildren = getChildList(mApi, 'panning');
            if (volChildren.length > 0) {
                var vApi = new LiveAPI(null, volChildren[0].id);
                volRaw = safeGet(vApi, 'value', 0.85);
            }
            if (panChildren.length > 0) {
                var pApi = new LiveAPI(null, panChildren[0].id);
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
        lom_path: 'live_set master_track',
        devices:  [],
        clips:    []
    };
}

/* ── Full session scan ─────────────────────────────────────────────────── */

function scan() {
    var rootApi = new LiveAPI(null, 'live_set');

    var trackList = getChildList(rootApi, 'tracks');
    var returnList = getChildList(rootApi, 'return_tracks');

    var tracks = [];
    for (var i = 0; i < trackList.length; i++) {
        tracks.push(scanTrack(trackList[i].id, i, false));
    }

    var returnTracks = [];
    for (var j = 0; j < returnList.length; j++) {
        returnTracks.push(scanTrack(returnList[j].id, j, true));
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

    // Send to node.script via outlet 0
    outlet(0, 'session_data', JSON.stringify(session));
}

/* ── LOM parameter write ───────────────────────────────────────────────── */

/**
 * Handle set_parameter commands from node.script.
 * msg format: '{"lom_path":"id 5","value":0.72}'
 */
function set_parameter(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api = new LiveAPI(null, cmd.lom_path);
        api.set('value', cmd.value);
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_path: cmd.lom_path, value: cmd.value }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Handle set_property commands (track arm/solo/mute, live_set transport props, etc.)
 * msg format: '{"lom_path":"id 3","property":"mute","value":1}'
 *             '{"lom_path":"live_set","property":"loop","value":1}'
 */
function set_property(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api = new LiveAPI(null, cmd.lom_path);
        api.set(cmd.property, cmd.value);
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_path: cmd.lom_path, property: cmd.property, value: cmd.value }));
    } catch (e) {
        outlet(0, 'error', JSON.stringify({ type: 'error', message: '' + e }));
    }
}

/**
 * Handle call_method commands — invokes an LOM method (e.g. start_playing).
 * msg format: '{"lom_path":"live_set","method":"start_playing"}'
 *             '{"lom_path":"live_set","method":"jump_to_next_cue"}'
 */
function call_method(jsonStr) {
    try {
        var cmd = JSON.parse(jsonStr);
        var api = new LiveAPI(null, cmd.lom_path);
        if (cmd.args && cmd.args.length > 0) {
            // Build the args array for api.call — concat method name with args
            var callArgs = [cmd.method].concat(cmd.args);
            api.call.apply(api, callArgs);
        } else {
            api.call(cmd.method);
        }
        outlet(0, 'ack', JSON.stringify({ type: 'ack', lom_path: cmd.lom_path, method: cmd.method }));
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
    // Remove old observers
    for (var i = 0; i < _observers.length; i++) {
        try { _observers[i].id = 'undefined'; } catch (e) {}
    }
    _observers = [];

    var rootApi = new LiveAPI(null, 'live_set');
    var trackList = getChildList(rootApi, 'tracks');

    for (var ti = 0; ti < trackList.length; ti++) {
        var tApi = new LiveAPI(null, trackList[ti].id);
        var devList = getChildList(tApi, 'devices');
        for (var di = 0; di < devList.length; di++) {
            var dApi = new LiveAPI(null, devList[di].id);
            var paramList = getChildList(dApi, 'parameters');
            for (var pi = 0; pi < paramList.length; pi++) {
                (function(tIdx, dIdx, pIdx, pId) {
                    var obs = new LiveAPI(function() {
                        var now = Date.now();
                        if (now - _lastBroadcast < _THROTTLE_MS) return;
                        _lastBroadcast = now;
                        var pApi2 = new LiveAPI(null, pId);
                        var delta = {
                            type:     'parameter_delta',
                            lom_path: pId,
                            value:    safeGet(pApi2, 'value', 0),
                            display:  safeGet(pApi2, 'str_for_value', '')
                        };
                        outlet(0, 'delta', JSON.stringify(delta));
                    }, pId);
                    obs.property = 'value';
                    _observers.push(obs);
                })(ti, di, pi, paramList[pi].id);
            }
        }
    }

    post('ALS Listener: installed ' + _observers.length + ' parameter observers\n');
}

/* ── Max message handlers ──────────────────────────────────────────────── */

// Called when Max sends 'scan' to inlet 0
function msg_int(v) { /* ignore */ }
function bang() { scan(); }
