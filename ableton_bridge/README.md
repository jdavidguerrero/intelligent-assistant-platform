# Ableton Bridge — M4L Devices

Bidirectional bridge between the Musical Intelligence Platform and Ableton Live.

```
intelligent-assistant-platform (Python)
    ingestion/ableton_bridge.py   ←→   ws://localhost:11005
                                              │
                               ALS Listener (Max for Live device)
                                    als_listener/
                                        als_listener.js   (Node for Max, WebSocket server)
                                        lom_scanner.js    (Max JS engine, LiveAPI)
                                              │  LOM
                                         Ableton Live
                                              │  OSC
                               claude_notes/claude_notes.js   (port 11002)
                               claude_drums/claude_drums.js   (port 11003)
```

---

## Devices

| Device | File | Port | Purpose |
|--------|------|------|---------|
| ALS Listener | `als_listener/` | 11005 (WebSocket) | Full session read/write |
| Claude Notes | `claude_notes/` | 11002 (OSC) | Insert melody/bass notes |
| Claude Drums | `claude_drums/` | 11003 (OSC) | Insert drum patterns |

---

## ALS Listener — Setup

### 1. Install Node for Max dependency

```bash
cd ableton_bridge/als_listener
npm install
```

This installs the `ws` WebSocket library (the only npm dependency).

### 2. Build the Max patch

Create a new Max for Live MIDI Effect device (`.amxd`) with the following objects:

```
[comment "ALS Listener — Ableton Bridge"]

[loadbang]
    |
[delay 500]            ← give M4L time to initialize
    |
[node.script als_listener.js @autostart 1]   ← Node for Max (WebSocket server)
    |                    ↑
    |              inlet receives: session_data <json>, delta <json>, ack <json>
    |
outlet 0  → [js lom_scanner.js]              ← Max's built-in JS (LiveAPI access)
              |
              outlet 0 → [node.script] inlet (routes back session_data, delta, ack)
```

**Patch wiring:**

```
[loadbang] → [delay 500] → [node.script als_listener.js]
                                     |
                    ┌────────────────┘  outlet 0 sends: scan, set_parameter, set_property
                    ↓
              [js lom_scanner.js]
                    |
                    └──────────────────→ [node.script als_listener.js] inlet 0
                        outlet 0 sends: session_data, delta, ack, error
```

### 3. Script file locations

Max for Live requires script files to be in the Max search path.  Options:
- Place in `~/Documents/Max 8/Max for Live Devices/` alongside the `.amxd`
- Add `ableton_bridge/als_listener/` to Max's file preferences

### 4. Load in Ableton

1. Open Ableton Live
2. Drag the `.amxd` device onto the **last MIDI track** (so it sees all other tracks)
3. Click the device to open it; you should see "ALS Listener: WebSocket server ready on ws://localhost:11005" in the Max console
4. Test: `python -c "from ingestion.ableton_bridge import AbletonBridge; b = AbletonBridge(); print(b.ping(), 'ms')"`

---

## Claude Notes — Setup

OSC receiver for note/melody insertion.

### Max patch objects:

```
[udpreceive 11002]
    |
[route /notes/clear /note/add /notes/commit /clip/create]
    |
[fromsymbol] → unpack args → [node.script claude_notes.js]

[node.script claude_notes.js]
    outlet 0 → [live.path selected_clip]
               [live.object]  ← for add_new_notes API
    outlet 1 (create_clip) → [live.object create_clip <beats>]
    outlet 2 (clear_clip)  → [live.object remove_notes 0 0 128 <length>]
    outlet 3 (note) → note pitch, start_beat, duration_beat, velocity, mute
               → [live.object add_new_notes ...]
    outlet 4 (commit) → nothing needed (Live auto-updates on add_new_notes)
```

**Note:** `live.path selected_clip` dynamically resolves to the currently selected clip slot.

---

## Claude Drums — Setup

Same architecture as Claude Notes, listening on port 11003.

```
[udpreceive 11003]
    |
[route /drums/clear /drum/hit /drums/commit /drums/pattern]
    |
[node.script claude_drums.js]
```

---

## Protocol Reference

### ALS Listener (WebSocket)

**Server → Client:**
```json
{"type": "session_state", "data": {
    "tracks": [...],
    "return_tracks": [...],
    "master_track": {...},
    "tempo": 128.0,
    "time_sig_numerator": 4,
    "time_sig_denominator": 4,
    "is_playing": false,
    "scene_count": 8
}}

{"type": "parameter_delta", "data": {
    "lom_path": "live_set tracks 2 devices 1 parameters 5",
    "value": 0.72,
    "display": "2.00 kHz"
}}

{"type": "ack", "lom_path": "...", "value": 0.72}
{"type": "pong", "ts": 1700000000000}
```

**Client → Server:**
```json
{"type": "set_parameter", "lom_path": "live_set tracks 2 devices 1 parameters 5", "value": 0.72}
{"type": "set_property", "lom_path": "live_set tracks 0", "property": "mute", "value": 1}
{"type": "get_session"}
{"type": "ping"}
```

---

## LOM Path Reference

| Target | LOM Path |
|--------|----------|
| Track N | `live_set tracks N` |
| Return track R | `live_set return_tracks R` |
| Master | `live_set master_track` |
| Device M on track N | `live_set tracks N devices M` |
| Parameter P on device M, track N | `live_set tracks N devices M parameters P` |
| Clip slot S on track N | `live_set tracks N clip_slots S clip` |

### EQ Eight parameter indices (per band, 1-based)

Band N starts at index `2 + (N-1) * 5`:

| Offset | Parameter |
|--------|-----------|
| +0 | Frequency (log, 20–20 000 Hz) |
| +1 | Gain (linear, –15 to +15 dB, 0.5 = 0 dB) |
| +2 | Q (log, 0.1–10) |
| +3 | Filter Type (0–7, quantized) |
| +4 | Active (0 or 1) |

Band A = band 1, Band H = band 8.

### Common device class_names

| Ableton Name | class_name |
|-------------|-----------|
| EQ Eight | `Eq8` |
| Compressor | `Compressor2` |
| Glue Compressor | `GlueCompressor` |
| Utility | `StereoGain` |
| Auto Filter | `AutoFilter` |
| Saturator | `Saturator` |
| Reverb | `Reverb` |
| Delay | `StereoDelay` |
| Simpler | `OriginalSimpler` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 11005 in use | Close other ALS Listener instances; check with `lsof -i :11005` |
| `ws` not found | Run `npm install` in `als_listener/` |
| LOM paths change | Use `class_name` not device index; re-scan on set reload |
| CPU spike | Observers throttle at 30 fps; reduce if needed in `lom_scanner.js` `_THROTTLE_MS` |
| Ableton loads new set | Bridge auto-reconnects on next call; session cache is invalidated |
| Push conflicts | ALS Listener is read-only for parameters it doesn't write; no conflicts |
