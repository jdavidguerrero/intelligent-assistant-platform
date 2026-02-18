# Claude Chords — Max for Live Device

Insert chord progressions into Ableton Live directly from Claude Desktop
via the `ableton_insert_chords` MCP tool.

## Architecture

```
Claude Desktop
    │  prompt: "insert Am F C G melancholic"
    ▼
MCP Tool: ableton_insert_chords
    │  resolves chord names → MIDI notes (core/midi.py)
    │  sends OSC/UDP packets (musical_mcp/ableton.py)
    ▼
UDP localhost:11001
    ▼
ClaudeChords.amxd (Max for Live)
    │  udpreceive 11001 → js claudechords.js
    │  parses OSC messages
    │  writes notes via Live Object Model
    ▼
Ableton Piano Roll
```

## Files

| File | Description |
|------|-------------|
| `ClaudeChords.amxd` | Max for Live MIDI Effect device |
| `claudechords.js` | JS script — OSC parser + LOM clip writer |

## OSC Protocol

| Message | Args | Description |
|---------|------|-------------|
| `/chord/clear` | — | Reset note buffer |
| `/chord/note` | `pitch:i velocity:i start_beat:f duration_beats:f` | Buffer one note |
| `/chord/commit` | `note_count:i clip_length_beats:f` | Write all buffered notes to clip |

## Setup

1. Copy `claudechords.js` to `~/Documents/Max 8/Library/` (Max search path)
2. Drag `ClaudeChords.amxd` onto a **MIDI track** in Ableton Live
3. Click an empty clip slot on that track to select it
4. In Claude Desktop, use the `ableton_insert_chords` tool

## Example prompts

```
"Insert a melancholic progression in C minor in the selected clip"
"Add Am7 Fmaj7 Dm7 G7 at 120 BPM, 2 bars each"
"Create a dark 8-bar progression in F# minor for organic house"
```

## Supported chord qualities

`maj` `m` `maj7` `m7` `7` `dim` `dim7` `aug` `sus2` `sus4` `add9` `m7b5` `9`

## Requirements

- Ableton Live 11 or 12
- Max for Live (included in Live Suite)
- MCP server running (`musical_mcp.server`)
- Claude Desktop with `musical-intelligence` MCP configured
