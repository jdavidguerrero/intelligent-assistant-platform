/**
 * claudechords.js — Max for Live JS script
 *
 * udpreceive parses OSC automatically and calls the JS function
 * matching the OSC address. Slashes are converted to underscores
 * by Max's js object routing, BUT the actual selector sent is the
 * full OSC address string as a symbol.
 *
 * Max's js object receives OSC from udpreceive as:
 *   message name = OSC address (e.g. "/chord/clear")
 *   arguments    = OSC args
 *
 * We use the `anything` handler to catch all messages and dispatch
 * based on messagename.
 */

outlets = 1;  // outlet 0: status text

var pendingNotes = [];

// ---------------------------------------------------------------------------
// anything() catches every message the js object receives
// ---------------------------------------------------------------------------

function anything() {
    var addr = messagename;          // e.g. "/chord/clear"
    var args = arrayfromargs(arguments);

    if (addr === "/chord/clear") {
        do_clear();
    } else if (addr === "/chord/note") {
        do_note(args);
    } else if (addr === "/chord/commit") {
        do_commit(args);
    }
    // ignore everything else silently
}

// ---------------------------------------------------------------------------
// Message handlers
// ---------------------------------------------------------------------------

function do_clear() {
    pendingNotes = [];
    outlet(0, "set", "Buffer cleared");
}

function do_note(args) {
    // args = [pitch, velocity, start_beat, duration_beats]
    if (args.length >= 4) {
        pendingNotes.push({
            pitch:    Math.round(args[0]),
            velocity: Math.round(args[1]),
            start:    parseFloat(args[2]),
            duration: parseFloat(args[3])
        });
    }
}

function do_commit(args) {
    var clipBeats = (args.length >= 2) ? parseFloat(args[1]) : 16.0;
    insert_notes(clipBeats);
}

// ---------------------------------------------------------------------------
// LOM clip writer
// ---------------------------------------------------------------------------

function insert_notes(clipLengthBeats) {
    if (pendingNotes.length === 0) {
        outlet(0, "set", "No notes to insert");
        return;
    }

    // Strategy: use highlighted_clip_slot to create/find clip.
    // detail_clip requires clip view to be open; highlighted_clip_slot is more reliable.
    var slot = new LiveAPI("live_set view highlighted_clip_slot");
    post("slot id: " + slot.id + "\n");

    var clip;

    if (slot && slot.id != 0) {
        // Check if slot already has a clip
        var hasClip = slot.get("has_clip");
        post("slot has_clip: " + hasClip + "\n");

        if (!hasClip || hasClip == 0) {
            // Create clip in the empty slot
            slot.call("create_clip", clipLengthBeats);
        }
        // Get clip from slot
        clip = new LiveAPI(slot.get("clip"));
        if (!clip || clip.id == 0) {
            // Fallback: try detail_clip after creation
            clip = new LiveAPI("live_set view detail_clip");
        }
    } else {
        // No highlighted slot — try detail_clip directly
        clip = new LiveAPI("live_set view detail_clip");
    }

    post("clip id: " + (clip ? clip.id : "null") + "\n");

    if (!clip || clip.id == 0) {
        outlet(0, "set", "ERROR: select a clip slot first");
        post("ERROR: no clip selected\n");
        return;
    }

    // Resize clip
    clip.set("loop_end", clipLengthBeats);
    clip.set("loop_start", 0);
    clip.set("looping", 1);

    // Clear existing notes
    clip.call("remove_notes_extended", 0, 0, 128, clipLengthBeats);

    // Live 12 MIDI API: build the dict JSON string directly and parse it.
    // This bypasses Max Dict object issues entirely.
    // Format confirmed by Ableton LOM docs:
    //   {"notes":[{"pitch":60,"start_time":0.0,"duration":3.6,"velocity":90,"mute":false},...]}
    var noteJsonParts = [];
    for (var i = 0; i < pendingNotes.length; i++) {
        var n = pendingNotes[i];
        noteJsonParts.push(
            '{"pitch":' + n.pitch +
            ',"start_time":' + n.start +
            ',"duration":' + n.duration +
            ',"velocity":' + n.velocity +
            ',"mute":false}'
        );
    }
    var jsonStr = '{"notes":[' + noteJsonParts.join(",") + ']}';
    post("Sending JSON: " + jsonStr.substring(0, 120) + "\n");

    var d = new Dict();
    d.parse(jsonStr);
    clip.call("add_new_notes", d);

    var bars = Math.round(clipLengthBeats / 4);
    var msg = "OK: " + pendingNotes.length + " notes, " + bars + " bars";
    outlet(0, "set", msg);
    post(msg + "\n");

    pendingNotes = [];
}

post("claudechords.js loaded OK — OSC listener ready\n");
