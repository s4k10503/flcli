---
name: flstudio-compose
description: Generates and writes musical content (chord progressions, melodies, basslines, drum patterns, loops, sections, arrangements) into a running FL Studio project through the local `flcli` CLI. Make sure to use this skill whenever the user mentions FL Studio, flcli, piano roll, step sequencer, pattern, chord progression, melody, bassline, drum pattern, arrangement, MIDI composition, mixer, plugin, transport, undo, or asks to "play / write / put / record / generate / drop" notes into FL Studio. Encodes the CLI's note-write paths, mixer controls, plugin parameters, transport position/loop, undo/redo, CSV format, channel rules, and hard limits so commands work first try.
---

# flstudio-compose

`flcli` drives FL Studio over a bidirectional SysEx protocol via two virtual
MIDI ports (`flcli` for commands, `flcli-rx` for responses). Every command
returns a synchronous JSON envelope — no file polling.

Read this whole file before emitting any command — the wrong path silently
drops pitch or loses timing.

## Decide the write path first

| Need | Command | Trade-off |
|---|---|---|
| Pitched notes (chords, melody, bass) — accuracy matters | `flcli queue-piano-roll <file>` | Sample-accurate, but needs **one manual click** in FL: Tools → Scripts → flcli_import |
| Pitched notes, fully hands-free | `flcli piano-roll <file> --bpm N` | Realtime recording: ms-level jitter; FL must be focused; takes wall-clock time |
| Drum / step-sequencer cells (one channel = one sample) | `flcli step-melody <file>` or `flcli step CH STEP ON` | **Pitch is silently dropped**; never use for melody |

Default to `queue-piano-roll`. Only fall back to `piano-roll` when the
user explicitly says "no clicks" / "fully automatic". Only use
`step-melody` for drums or step-grid patterns.

## CSV note format (shared by all three)

One note per line, `#` for comments, blank lines ignored:

```
pitch,velocity,length,position
```

- `pitch`: MIDI 0–127 (C4=60). Stay in **1–127** and transpose up an octave if needed.
- `velocity`: 0–127. 0 is legal but acts as note-off (silent).
- `length`: beats, float, > 0. Quarter=1.0, eighth=0.5, whole-in-4/4=4.0.
- `position`: beats from pattern start, float, ≥ 0. Bar `b` beat `n` (1-indexed) in 4/4 = `(b-1)*4 + (n-1)`.

Chords are simultaneous notes — emit one row per chord tone sharing the
same `position` and `length`. Comment every bar/chord:

```
# Bar 1 — Cmaj
60,80,4.0,0.0
64,80,4.0,0.0
67,80,4.0,0.0
```

## Channel selection (do not skip)

`queue-piano-roll` writes into **whichever Piano Roll the user has open**
when they click `flcli_import`. The CLI cannot pick the channel for
them — always tell the user which channel to open.

`piano-roll` and `step-melody` write to FL Studio's currently *selected*
channel, which the CLI can change:

```bash
flcli select-channel 2   # 0-indexed; sticky across calls
```

For multi-instrument arrangements, write **one queue file per channel**
and ask the user to click once per channel. Do not try to multiplex
channels through a single queue.

## Transport position, loop, and undo

```bash
# Playhead position (default: beats)
flcli transport-position get
flcli transport-position get --mode ticks
flcli transport-position set 8.0           # jump to beat 8
flcli transport-position set 1920 --mode ticks

# Loop mode
flcli transport-loop get
flcli transport-loop toggle

# Undo / Redo
flcli undo
flcli redo
flcli undo-history                         # count + last entry
```

Batch step names: `transport_position_get`, `transport_position_set`,
`transport_loop_get`, `transport_loop_toggle`, `undo`, `redo`,
`undo_history`.

## Plugin inspection and control

```bash
flcli plugin list --channel 0              # all slots for channel
flcli plugin params --channel 0            # parameter list (slot 0)
flcli plugin params --channel 0 --slot 1

# Get / set by index or name (0.0–1.0 normalized)
flcli plugin param get --channel 0 --param 5
flcli plugin param get --channel 0 --param-name "Cutoff"
flcli plugin param set 0.75 --channel 0 --param 5
flcli plugin param set 0.5 --channel 0 --param-name "Resonance"
```

Batch step names: `plugin_list`, `plugin_params`, `plugin_param_get`,
`plugin_param_set`.

## Piano roll editing

Read back exported notes, transform, and re-queue:

```bash
flcli piano-roll-show                      # show current export
flcli piano-roll-edit --transpose 12       # +1 octave
flcli piano-roll-edit --shift 4.0          # move 1 bar later
flcli piano-roll-edit --scale-length 0.5   # halve note lengths
flcli piano-roll-edit --delete 0,3         # remove specific notes
flcli piano-roll-edit --only 0,1,2 --transpose -12 --clear
```

After editing, the user must run `flcli_import` in FL Studio (same as
`queue-piano-roll`).

## Mixer operations

The CLI exposes full mixer control. Use these for session setup:

```bash
# List all tracks
flcli mixer list

# Volume (0.0 - 1.0) / Pan (-1.0 to 1.0)
flcli mixer volume set 0.75 --track 1
flcli mixer pan set -0.3 --track 2

# Naming (arbitrary UTF-8 strings)
flcli mixer name set "Drums" --track 3

# Mute / Solo / Arm (toggle)
flcli mixer mute --track 4
flcli mixer solo --track 5
flcli mixer arm --track 6 --on

# Routing
flcli mixer route --from 1 --to 0 --on
flcli mixer link-to-channel --track 1
```

All mixer commands are also available as batch steps:
`mixer_list`, `mixer_volume_get`, `mixer_volume_set`, `mixer_pan_get`,
`mixer_pan_set`, `mixer_name_get`, `mixer_name_set`, `mixer_mute`,
`mixer_solo`, `mixer_arm`, `mixer_route_set`, `mixer_link_to_channel`.

## Hard limits — do not fabricate around them

- **No live pattern-length command exists.** FL's MIDI Scripting API doesn't
  expose pattern length at runtime. For offline `.flp` files, use
  `flcli flp pattern set-length <file> -p <pattern> <steps>` as an escape
  hatch. For a running session, tell the user to set it in the GUI.
- **No live playlist-insertion command exists.** Same reason. For offline
  `.flp` files, use `flcli flp clip create <file> -t <track> -p <pattern>
  --position <beats>` to place clips. For a running session, the user must
  drag clips manually.
- **`flcli step` step indices are 0–63.** The step-sequencer grid is
  16 steps × 4 beats. A 1/32 grid does not fit.
- **`flcli tempo` accepts BPM 1–999.** Outside that range the CLI
  rejects with `{"ok": false, ...}`.
- **`flcli select-channel` indices are 0–127** (0-indexed, sticky).
- **All `*melody` commands default `SOURCE` to `-` (stdin).** If you
  forget the path argument, the command **hangs waiting on stdin**.
  Always pass an explicit file path or pipe via heredoc.
- **`queue-piano-roll` writes a single-shot queue.** The Piano Roll
  Script deletes the queue file on success. A second click of
  `flcli_import` reports "no pending notes" — re-run
  `queue-piano-roll` to re-arm.

## Workflow templates

### A. Pitched composition (the default)

```bash
cat > /tmp/song.csv <<'EOF'
# Bar 1 — Cmaj
60,80,4.0,0.0
64,80,4.0,0.0
67,80,4.0,0.0
72,100,1.0,0.0
74,100,1.0,1.0
76,100,1.0,2.0
77,100,1.0,3.0
EOF

flcli tempo 100
flcli queue-piano-roll /tmp/song.csv --clear
```

Then say to the user, verbatim:

> Open the destination channel in FL Studio's Piano Roll, then run **Tools → Scripts → flcli_import**.

`--clear` makes the import script wipe existing notes first; omit it to
append.

### B. Drum pattern via step grid

```bash
flcli select-channel 0           # kick channel
flcli step 0 0  1 -v 110         # beat 1
flcli step 0 4  1 -v 100         # beat 2
flcli step 0 8  1 -v 110         # beat 3
flcli step 0 12 1 -v 100         # beat 4
```

### C. Hands-free realtime recording

```bash
flcli select-channel 1
flcli piano-roll /tmp/song.csv --bpm 120
```

FL must be the foreground app. Streams in real time, so an 8-bar piece
takes ≈ 16 s at 120 BPM.

### D. Session setup with mixer

```bash
flcli tempo 128
flcli name-channel 0 --name "Kick"
flcli name-channel 1 --name "Snare"
flcli name-channel 2 --name "Hi-Hat"
flcli mixer name set "Drums" --track 1
flcli mixer volume set 0.8 --track 1
flcli mixer pan set 0.0 --track 1
```

### E. Batch session setup (single MIDI session)

```bash
cat <<'JSON' | flcli batch run
{
  "steps": [
    {"name": "tempo", "args": {"bpm": 128}},
    {"name": "name_channel", "args": {"channel": 0, "name": "Kick"}},
    {"name": "name_channel", "args": {"channel": 1, "name": "Snare"}},
    {"name": "mixer_volume_set", "args": {"track": 1, "value": 0.8}},
    {"name": "mixer_name_set", "args": {"track": 1, "name": "Drums"}},
    {"name": "set_step", "args": {"channel": 0, "step": 0, "on": true, "velocity": 110}},
    {"name": "set_step", "args": {"channel": 0, "step": 4, "on": true, "velocity": 100}},
    {"name": "play"}
  ]
}
JSON
```

## Reading FL state back

```bash
flcli state                              # full expanded snapshot
flcli state --field tempo                # top-level scalar
flcli state --field channels.0.name      # dotted path → "Kick"
flcli state --field mixer.tracks.1.volume # → 0.75
flcli state --field song_position.beats  # → 4.0
flcli state --field patterns.0.name      # → "Verse"
```

The expanded snapshot contains these sections:

| Section | Shape | Content |
|---|---|---|
| scalars | flat | `tempo`, `current_pattern`, `pattern_count`, `selected_channel`, `channel_count`, `is_playing`, `is_recording` |
| `song_position` | `{beats, ms}` | playhead position in two units |
| `channels` | `[{index, name, color, volume, pan, target_fx_track, plugin_name}]` | every channel rack channel |
| `patterns` | `[{index, name, color}]` | every pattern |
| `mixer` | `{tracks: [{index, name, volume, pan, mute, solo}], routing: [[from, to]]}` | mixer state + active routes |

Any section or field can be `null` if the FL Studio API version doesn't
support it — always handle `null` defensively.

### Throttle

Large snapshots are cached device-side (default 500 ms):

```bash
flcli --state-throttle-ms 100 state      # allow 100ms refresh interval
export FLCLI_STATE_THROTTLE_MS=250       # env var override
```

State queries are **synchronous via SysEx** (< 5 ms round trip, no file
polling).

## Snapshot and diff

Capture state before/after a batch to verify changes landed:

```bash
flcli snapshot --out before.json
# ... run batch commands ...
flcli snapshot --out after.json
flcli diff before.json after.json
```

Use `--assert` to verify specific expectations:

```bash
flcli diff before.json after.json --assert checks.json
```

Where `checks.json` contains: `{"assertions": [{"path": "tempo", "op": "eq", "value": 140.0}]}`.
Operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`.

## Output contract

Every `flcli` invocation prints exactly one JSON line:

```json
{"ok": true, "command": "tempo", "args": {"bpm": 140.0}, "result": {"bpm": 140.0}, "error": null}
```

```json
{"ok": false, "command": "tempo", "args": {}, "result": null, "error": {"code": "INVALID_ARGUMENT", "message": "missing required argument: 'bpm'"}}
```

Parse the JSON; do not scrape text. Check `ok` first, then read
`result` or `error.code`.

## Worked example: 4-5-3-6 progression in C, 8 bars

```bash
cat > /tmp/4536.csv <<'EOF'
# 2 bars per chord, whole-note voicings (root + 3rd + 5th)
# Bar 1-2 — F (IV)
65,80,8.0,0.0
69,80,8.0,0.0
72,80,8.0,0.0
# Bar 3-4 — G (V)
67,80,8.0,8.0
71,80,8.0,8.0
74,80,8.0,8.0
# Bar 5-6 — Em (iii)
64,80,8.0,16.0
67,80,8.0,16.0
71,80,8.0,16.0
# Bar 7-8 — Am (vi)
69,80,8.0,24.0
72,80,8.0,24.0
76,80,8.0,24.0
# Quarter-note melody, C major scale (bars 1-2 shown; extend to bar 8)
72,100,1.0,0.0
74,100,1.0,1.0
76,100,1.0,2.0
77,100,1.0,3.0
79,100,1.0,4.0
77,100,1.0,5.0
76,100,1.0,6.0
74,100,1.0,7.0
EOF

flcli tempo 100
flcli queue-piano-roll /tmp/4536.csv --clear
```

Then prompt the user to open the target channel's Piano Roll and run
**Tools → Scripts → flcli_import**.

## Closing reminders

- Always confirm the `{"ok": true, ...}` JSON before claiming success.
- After `queue-piano-roll`, **always** end your message with the manual
  click instruction. Otherwise the user assumes it silently failed.
- Keep `pitch` in 1–127, `velocity` in 1–127 (use 0 only for silence),
  `position ≥ 0`, `length > 0`.
- Always pass an explicit file path to `*melody` / `queue-piano-roll` /
  `piano-roll`, or pipe via heredoc — never invoke with no argument.
- If the user wants pattern length or playlist clips in a **live session** —
  say up front it must be done in the GUI. If they have a `.flp` file, offer
  `flcli flp pattern set-length` or `flcli flp clip create` as offline alternatives.
