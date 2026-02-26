/**
 * claude_notes.js — Claude Notes M4L device
 *
 * Receives OSC messages on localhost:11002 and inserts notes into
 * the currently selected MIDI clip slot.
 *
 * Runs inside Max for Live via the `node.script` object.
 * The Max patch has an `udpreceive 11002` object connected to this script's inlet.
 *
 * OSC Protocol
 * ────────────
 *   /notes/clear                  — erase existing notes from the selected clip
 *   /note/add <pitch> <start> <duration> <velocity>
 *                                 — add a single note (beat units)
 *   /notes/commit                 — write all queued notes to the clip
 *   /clip/create <length_bars>    — create a new empty clip in the selected slot
 *
 * Note format
 * ───────────
 *   pitch:    MIDI pitch 0–127 (middle C = 60)
 *   start:    beat position from clip start (0.0 = beat 1)
 *   duration: note length in beats (0.25 = 16th note at 4/4)
 *   velocity: MIDI velocity 0–127 (default 100)
 *
 * Max patch wiring
 * ────────────────
 *   [udpreceive 11002] → [route /notes/clear /note/add /notes/commit /clip/create]
 *      routed messages → [node.script claude_notes.js]
 *   [node.script] outlet 0 → [live.path] → write to selected clip
 *
 * Note: This script uses the LiveAPI available in the `js` object pattern.
 * The Max patch should route OSC args as typed Max messages to this script.
 */

'use strict';

const Max = require('max-api');

// ── Note buffer ───────────────────────────────────────────────────────────

/** @type {{pitch:number,start:number,duration:number,velocity:number}[]} */
let noteBuffer = [];

// ── OSC message handlers ──────────────────────────────────────────────────

/**
 * /notes/clear — Empty the note buffer and clear the selected clip.
 */
Max.addHandler('notes_clear', () => {
    noteBuffer = [];
    Max.outlet('clear_clip');
    Max.post('Claude Notes: buffer cleared');
});

/**
 * /note/add <pitch> <start> <duration> <velocity>
 */
Max.addHandler('note_add', (pitch, start, duration, velocity) => {
    const note = {
        pitch:    Math.max(0, Math.min(127, Math.round(pitch))),
        start:    Math.max(0, parseFloat(start)),
        duration: Math.max(0.0625, parseFloat(duration)),  // min 1/64 note
        velocity: Math.max(1, Math.min(127, Math.round(velocity || 100)))
    };
    noteBuffer.push(note);
});

/**
 * /notes/commit — Write all buffered notes to the selected MIDI clip.
 * Sends note data to the Max patch via outlet for LiveAPI to insert.
 */
Max.addHandler('notes_commit', () => {
    if (noteBuffer.length === 0) {
        Max.post('Claude Notes: commit called with empty buffer');
        return;
    }

    // Send each note as a 'note' message to the Max patch
    // The patch uses live.path → selected clip → add_new_notes
    for (const n of noteBuffer) {
        Max.outlet('note', n.pitch, n.start, n.duration, n.velocity, 0 /* mute=false */);
    }
    Max.outlet('commit');
    Max.post(`Claude Notes: committed ${noteBuffer.length} notes`);
    noteBuffer = [];
});

/**
 * /clip/create <length_bars> — Create a new clip in the selected slot.
 */
Max.addHandler('clip_create', (lengthBars) => {
    const beats = parseFloat(lengthBars) * 4; // assumes 4/4
    Max.outlet('create_clip', beats);
    Max.post(`Claude Notes: created ${lengthBars} bar clip`);
});

// ── Status ────────────────────────────────────────────────────────────────

Max.addHandler('status', () => {
    Max.post(`Claude Notes: ${noteBuffer.length} notes in buffer`);
    Max.outlet('status', noteBuffer.length);
});

Max.post('Claude Notes: loaded. Listening on OSC port 11002.');
