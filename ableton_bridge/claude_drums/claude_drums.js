/**
 * claude_drums.js — Claude Drums M4L device
 *
 * Receives OSC messages on localhost:11003 and inserts drum hits into
 * a MIDI clip on a Drum Rack track.
 *
 * Runs inside Max for Live via the `node.script` object.
 *
 * OSC Protocol
 * ────────────
 *   /drums/clear                  — erase existing notes
 *   /drum/hit <gm_note> <step> <velocity> <bar>
 *                                 — add a single drum hit
 *   /drums/commit <bpm> <bars> <steps_per_bar>
 *                                 — write pattern to clip
 *   /drums/pattern <json>         — bulk pattern insert (JSON string)
 *
 * Hit format
 * ──────────
 *   gm_note:       GM MIDI note (36=kick, 38=snare, 42=hi-hat closed, etc.)
 *   step:          0-based step number within the bar (0 = beat 1, 4 = beat 2 at 16-step)
 *   velocity:      MIDI velocity 1–127
 *   bar:           0-based bar number (0 = bar 1)
 *
 * GM Drum Map (most common)
 * ──────────────────────────
 *   36  Kick / Bass Drum 1
 *   38  Snare 1
 *   40  Snare 2 (electric)
 *   42  Hi-hat closed
 *   44  Hi-hat pedal
 *   46  Hi-hat open
 *   49  Crash 1
 *   51  Ride 1
 *   56  Cowbell
 *   76  Wood block hi
 */

'use strict';

const Max = require('max-api');

// ── Hit buffer ────────────────────────────────────────────────────────────

/**
 * @type {{gm_note:number, step:number, velocity:number, bar:number}[]}
 */
let hitBuffer = [];

// GM note → Ableton Drum Rack MIDI note
// Ableton Drum Rack maps: bottom pad = C1 (36), ascending by semitone
const GM_TO_DRUM_RACK = {
    36: 36,  // Kick
    38: 38,  // Snare 1
    40: 40,  // Snare 2
    42: 42,  // HH closed
    44: 44,  // HH pedal
    46: 46,  // HH open
    47: 47,  // Low tom
    48: 48,  // Mid tom
    49: 49,  // Crash 1
    50: 50,  // High tom
    51: 51,  // Ride 1
    52: 52,  // China
    53: 53,  // Ride bell
    54: 54,  // Tambourine
    55: 55,  // Splash
    56: 56,  // Cowbell
    57: 57,  // Crash 2
    59: 59,  // Ride 2
    60: 60,  // Hi bongo
    61: 61,  // Lo bongo
    62: 62,  // Mute hi conga
    63: 63,  // Open hi conga
    64: 64,  // Lo conga
    65: 65,  // High timbale
    66: 66,  // Lo timbale
    67: 67,  // Hi agogo
    68: 68,  // Lo agogo
    76: 76,  // Hi woodblock
    77: 77,  // Lo woodblock
};

// ── OSC message handlers ──────────────────────────────────────────────────

Max.addHandler('drums_clear', () => {
    hitBuffer = [];
    Max.outlet('clear_clip');
    Max.post('Claude Drums: buffer cleared');
});

/**
 * /drum/hit <gm_note> <step> <velocity> <bar>
 */
Max.addHandler('drum_hit', (gmNote, step, velocity, bar) => {
    gmNote   = Math.round(gmNote);
    step     = Math.max(0, Math.round(step));
    velocity = Math.max(1, Math.min(127, Math.round(velocity || 100)));
    bar      = Math.max(0, Math.round(bar || 0));

    const drNote = GM_TO_DRUM_RACK[gmNote] !== undefined ? GM_TO_DRUM_RACK[gmNote] : gmNote;
    hitBuffer.push({ gm_note: drNote, step, velocity, bar });
});

/**
 * /drums/commit <bpm> <bars> <steps_per_bar>
 * Converts step-based pattern to beat positions and writes to clip.
 */
Max.addHandler('drums_commit', (bpm, bars, stepsPerBar) => {
    bars        = Math.max(1, Math.round(bars || 2));
    stepsPerBar = Math.max(4, Math.round(stepsPerBar || 16));
    const beatsPerStep = 4.0 / stepsPerBar;  // assumes 4/4
    const clipBeats    = bars * 4;
    const noteDuration = beatsPerStep * 0.9; // slight gate reduction

    if (hitBuffer.length === 0) {
        Max.post('Claude Drums: commit called with empty buffer');
        return;
    }

    // Create clip
    Max.outlet('create_clip', clipBeats);

    // Send note events
    for (const hit of hitBuffer) {
        const beatPos = hit.bar * 4 + hit.step * beatsPerStep;
        Max.outlet('note', hit.gm_note, beatPos, noteDuration, hit.velocity, 0);
    }

    Max.outlet('commit');
    Max.post(`Claude Drums: committed ${hitBuffer.length} hits over ${bars} bars`);
    hitBuffer = [];
});

/**
 * /drums/pattern <json>
 * Bulk insert: JSON string of {hits:[{gm_note,step,velocity,bar},...], bars, steps_per_bar}
 */
Max.addHandler('drums_pattern', (jsonStr) => {
    let pattern;
    try {
        pattern = JSON.parse(jsonStr);
    } catch (e) {
        Max.post(`Claude Drums: invalid JSON pattern — ${e}`);
        return;
    }

    hitBuffer = [];
    for (const hit of (pattern.hits || [])) {
        hitBuffer.push({
            gm_note:  GM_TO_DRUM_RACK[hit.gm_note] || hit.gm_note,
            step:     hit.step || 0,
            velocity: hit.velocity || 100,
            bar:      hit.bar || 0
        });
    }

    const bars        = pattern.bars || 2;
    const stepsPerBar = pattern.steps_per_bar || 16;
    Max.outlet('drums_commit', 120, bars, stepsPerBar);
});

Max.addHandler('status', () => {
    Max.post(`Claude Drums: ${hitBuffer.length} hits in buffer`);
    Max.outlet('status', hitBuffer.length);
});

Max.post('Claude Drums: loaded. Listening on OSC port 11003.');
