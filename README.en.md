# flcli

> **Status: unmaintained.** Provided AS-IS under the MIT License. Active
> development has stopped — forks are explicitly encouraged. Issues and
> PRs filed on this repository may not be reviewed.

[日本語](README.md) | [English](README.en.md)

An LLM-friendly CLI for controlling FL Studio. Sends commands to FL Studio
over a bidirectional SysEx protocol and returns results as JSON. Every output
is unified as a single-line JSON envelope so LLMs like Anthropic Claude can
invoke it directly through tools like `Bash`.

## Architecture

```
LLM / shell
  ↓ argv
flcli (this CLI)
  ↓ SysEx (F0 7D 02 … F7) via virtual MIDI port "flcli"
FL Studio + device_flcli.py
  ↓ SysEx response via "flcli-rx"
flcli (response receive)
```

Protocol v2 uses **bidirectional SysEx**. The CLI sends commands as SysEx
frames carrying a JSON payload, and the device script returns a response
keyed by the same `request_id`. There is no file polling — every command
returns success/failure synchronously.

### Package layout

```
src/flstudio_cli/
├── shared/                          cross-feature scaffolding
│   ├── utility/                     layer-free generics (Outcome / Result-like)
│   ├── domain/                      Value Objects and Domain Services (pure types)
│   ├── application/                 Use Cases / Ports / DTOs
│   ├── infrastructure/              Adapters (every outer concern)
│   │   ├── protocol/                wire format (v2 + _device_portable)
│   │   ├── transport/               MIDI I/O (sink / return port / record / replay)
│   │   ├── flp/                     .flp file format adapter (pyflp)
│   │   ├── fl_device/               FL Studio sandbox-side scripts (device_flcli.py, ...)
│   │   ├── io_utils.py              tmp+rename atomic write / read_text
│   │   └── os_automation.py         OS automation (auto-trigger)
│   ├── composition/                 Composition Root (DI — effects / facades / transport)
│   └── presentation/                Interface Adapters (CA): cli_helpers / cli_dispatch / exit_codes
├── batch/  config/  completion/  flp_cli/  mixer/  piano_roll/  plugin/
├── project/  state/  transport/    each feature: application/handlers.py +
│                                   presentation/cmd_<feature>.py + feature.py
└── __main__.py                     Click root group + entry-point discovery
```

Each feature defines a `FEATURE = Feature(...)` constant in
`feature.py` and registers it in `pyproject.toml` under
`[project.entry-points."flstudio_cli.features"]`.  `__main__.py` walks
that registry to assemble the CLI subcommands and batch handlers.

Layer dependencies are unidirectional (`presentation` → `composition` →
`application` → `domain`). `domain` is pure and references nothing outer,
including `infrastructure`. Only `composition` may import `infrastructure`,
and `presentation` reaches external adapters only via `composition`.
`__main__.py` is responsible only for top-level wiring; side effects are
pushed down into `application`.  `shared/utility/` is the layer-free
analogue of Rust's `std::result` — every layer may import it freely
(currently hosts the `Outcome` / `Ok` / `Err` types only).

### File-level role-tag convention

Every non-test `.py` module opens its docstring with one of **nine
canonical DDD / Clean-Architecture role tags**.  Running `grep -E
'^"""[A-Z][a-zA-Z ]+:'` over the source tree yields exactly one match
per file.

| Role tag | Origin | Examples |
|---|---|---|
| `Composition root:` | Mark Seemann (DI) | `__main__.py`, `composition/*.py`, per-feature `feature.py` |
| `Use case:` | CA ≡ DDD Application Service | application orchestration, `handlers.py`, use-case scaffolding, facade re-exports (`batch.py`) |
| `Application port:` | Hexagonal Port | `*_port.py`, `ports.py` |
| `Application DTO:` | Fowler | `*_dto.py`, `*_errors.py`, constants modules, DTO factories / parsers, DTO facades (`envelope.py`) |
| `Domain value object:` | DDD | frozen dataclass / NewType vocabulary |
| `Domain service:` | DDD | pure operations on domain types (`edit_ops`, `snapshot_diff`) |
| `Infrastructure adapter:` | Hexagonal | concrete impls of Application Ports (transport sinks, file-format adapters, wire codec, FL sandbox) |
| `Interface adapter:` | CA Layer 3 | Click commands (`cmd_*.py`) and CLI helpers |
| `Utility:` | layer-free | `shared/utility/*` (Outcome) |

See the docstring in `src/flstudio_cli/__init__.py` for the full
taxonomy.  Per-layer file-naming refinements live in each layer's
`__init__.py` (e.g. `shared/application/__init__.py`).

### Mechanical enforcement of dependency rules

`tach.toml` declares the layer constraints above plus feature
independence (cross-feature imports must go through `shared/`), and CI
plus pre-commit run `tach check` on every change. New violating imports
fail CI. `tach check-external` additionally verifies that imports match
the declarations in `pyproject.toml`.

```bash
uv run tach check          # architectural enforcement
uv run tach check-external # external dependency consistency
uv run tach show --web     # visualize the dependency graph (optional)
```

Known carve-outs are tagged inline with `TODO(#NNN)` in `tach.toml`;
once the linked issue is resolved, the entry can be removed and `tach
check --exact` will flag any regression.

## Setup

### 1. Create virtual MIDI ports

You need **two** ports:

| Port name | Direction | Purpose |
|-----------|-----------|---------|
| `flcli` | CLI → FL Studio | Send commands |
| `flcli-rx` | FL Studio → CLI | Return responses |

- **Windows:** Create `flcli` and `flcli-rx` with [LoopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
- **macOS:** Audio MIDI Setup → enable the IAC Driver and add two buses
  named `flcli` and `flcli-rx`.
  See [`docs/setup-macos.md`](docs/setup-macos.md) for macOS-specific gotchas
  (port number assignment, avoiding response loops, etc.).

### 2. Install the device script

Place `src/flstudio_cli/shared/infrastructure/fl_device/device_flcli.py` into FL Studio's hardware settings folder:

```
Documents/Image-Line/FL Studio/Settings/Hardware/flcli/device_flcli.py
```

If you use direct piano-roll writes (`queue-piano-roll`), also place
`src/flstudio_cli/shared/infrastructure/fl_device/flcli_import.pyscript` at:

```
Documents/Image-Line/FL Studio/Settings/Piano roll scripts/flcli_import.pyscript
```

### 3. Configure FL Studio

In Options → MIDI Settings, enable both the `flcli` and `flcli-rx` ports
and set the controller type to `flcli`.

### 4. Install the CLI

```bash
pip install -e .
```

## Basic commands

```bash
flcli ports                                # List MIDI output ports
flcli ping                                 # Check port reachability
flcli state                                # Synchronously fetch FL Studio state (extended snapshot)
flcli state --field tempo                  # Get a top-level field
flcli state --field channels.0.name        # Get a deep value via dot path
flcli state --field mixer.tracks.1.volume  # Individual mixer track value

# Transport
flcli play                                 # Play
flcli stop                                 # Stop
flcli record                               # Toggle record
flcli tempo 128                            # Set BPM

# Project / pattern / channel
flcli new-project                          # New project
flcli new-pattern                          # New pattern
flcli select-pattern 2                     # Select pattern
flcli duplicate-channel                    # Duplicate the selected channel (FL Ctrl+C/V)
flcli select-channel 0                     # Select channel
flcli name-channel 3 --name "my synth"     # Set channel name (any UTF-8)

# Transport position / loop
flcli transport-position get               # Playback position (default: beats)
flcli transport-position get --mode ticks  # Get in ticks
flcli transport-position set 8.0           # Move playhead to beat 8
flcli transport-position set 1920 --mode ticks
flcli transport-loop get                   # Get current loop mode
flcli transport-loop toggle                # Toggle loop mode

# Undo / Redo
flcli undo                                 # Undo last action
flcli redo                                 # Redo
flcli undo-history                         # Undo count and recent history entries

# Step sequencer
flcli step 0 4 1 -v 110                    # Turn on step 4 of ch 0 (velocity 110)
```

## Plugins

The `flcli plugin` group inspects and controls plugins on the channel rack:

```bash
# List plugins (all slots on channel 0)
flcli plugin list --channel 0

# List parameters
flcli plugin params --channel 0             # Default slot (0)
flcli plugin params --channel 0 --slot 1    # Specific slot

# Get parameter (by index or name)
flcli plugin param get --channel 0 --param 5
flcli plugin param get --channel 0 --param-name "Cutoff"

# Set parameter (0.0 - 1.0)
flcli plugin param set 0.75 --channel 0 --param 5
flcli plugin param set 0.5 --channel 0 --param-name "Resonance"
```

## Mixer

The `flcli mixer` group operates on mixer tracks:

```bash
flcli mixer list                           # List state of all tracks

# Volume (0.0 - 1.0)
flcli mixer volume get --track 1
flcli mixer volume set 0.75 --track 1

# Pan (-1.0 to 1.0)
flcli mixer pan get --track 2
flcli mixer pan set -0.3 --track 2

# Track name (any UTF-8)
flcli mixer name get --track 3
flcli mixer name set "Drums" --track 3

# Mute / solo / arm (toggle)
flcli mixer mute --track 4
flcli mixer solo --track 5
flcli mixer arm --track 6 --on
flcli mixer arm --track 6 --off

# Routing
flcli mixer route --from 1 --to 0 --on    # Enable send from track 1 → 0

# Channel link
flcli mixer link-to-channel --track 1      # Link to currently selected channel
```

## Melody / piano roll

### Step melody (step-grid input)

`pitch` is ignored — notes expand into 1/16 steps on the selected channel:

```bash
cat <<EOF | flcli step-melody -
60,100,1.0,0.0
62,100,1.0,1.0
64,100,1.0,2.0
67,100,2.0,3.0
EOF
```

### Piano Roll Script path (sample-accurate)

```bash
cat <<EOF | flcli queue-piano-roll -
60,100,1.0,0.0
64,100,1.0,1.0
67,100,1.0,2.0
72,100,1.0,3.0
EOF
# → In FL Studio, open the Piano Roll and run Tools → Scripts → flcli_import
```

### Real-time recording path (hands-free)

Bring FL Studio to the foreground and select the destination channel:

```bash
cat <<EOF | flcli piano-roll - --bpm 120
60,100,1.0,0.0
64,100,1.0,1.0
67,100,1.0,2.0
72,100,1.0,3.0
EOF
```

### Piano roll editing (read → transform → re-queue)

Edit exported notes and re-queue them:

```bash
# Inspect the current notes
flcli piano-roll-show

# Transpose (+12 = up one octave)
flcli piano-roll-edit --transpose 12

# Time shift (+4 beats = one bar later)
flcli piano-roll-edit --shift 4.0

# Halve note length
flcli piano-roll-edit --scale-length 0.5

# Delete specific notes (0-indexed)
flcli piano-roll-edit --delete 0,3,5

# Combined: transpose only notes 0–3 and re-queue
flcli piano-roll-edit --only 0,1,2,3 --transpose -12 --clear
```

After editing, just like with `queue-piano-roll`, run `flcli_import` from FL Studio.

### MIDI file reading

```bash
flcli read-midi song.mid                   # Output as JSON
flcli read-midi song.mid --format csv      # Output as CSV
```

## Output envelope

Every command — success or failure — emits JSON with the **same shape**:

```json
{"ok": true, "command": "tempo", "args": {"bpm": 140.0}, "result": {"bpm": 140.0}, "error": null}
```

```json
{"ok": false, "command": "tempo", "args": {}, "result": null, "error": {"code": "INVALID_ARGUMENT", "message": "missing required argument: 'bpm'"}}
```

## Snapshots and diffs

### `snapshot` (state capture)

Forces a fresh state read from the device and saves it to a file:

```bash
flcli snapshot                             # Print JSON envelope to stdout
flcli snapshot --out before.json           # Save to a file (atomic write)
flcli snapshot --out state.json --pretty   # Pretty-print
flcli snapshot --sections mixer,channels   # Filter sections
```

### `diff` (snapshot comparison)

Compares two snapshot files and returns structured changes:

```bash
flcli diff before.json after.json
```

Example output:

```json
{"ok": true, "command": "diff", "result": {
  "added": [{"path": "channels.2", "value": {"index": 2, "name": "Lead"}}],
  "removed": [],
  "changed": [
    {"path": "tempo", "before": 120.0, "after": 140.0},
    {"path": "mixer.tracks.0.volume", "before": 0.8, "after": 1.0}
  ]
}}
```

### `diff --assert` (assertion verification)

Test whether a snapshot meets expectations:

```bash
cat > /tmp/checks.json <<'EOF'
{
  "assertions": [
    {"path": "tempo", "op": "eq", "value": 140.0},
    {"path": "mixer.tracks.0.volume", "op": "gte", "value": 0.5},
    {"path": "channels.0.name", "op": "contains", "value": "Kick"}
  ]
}
EOF
flcli diff before.json after.json --assert /tmp/checks.json
```

Supported operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`.
Failures exit with code 2 (`INVALID_ARGUMENT`).

## Batch execution

### `batch run`

Run multiple commands in a single MIDI session:

```bash
cat <<'JSON' | flcli batch run
{
  "steps": [
    {"name": "tempo", "args": {"bpm": 128}},
    {"name": "new_pattern"},
    {"name": "select_channel", "args": {"index": 0}},
    {"name": "set_step", "args": {"channel": 0, "step": 0, "on": true, "velocity": 110}},
    {"name": "mixer_volume_set", "args": {"track": 1, "value": 0.8}},
    {"name": "play"}
  ]
}
JSON
```

By default it stops on the first failure. Use `--continue-on-error` to run
every step.

### `batch stream` (JSONL stream)

A JSONL mode for low-latency invocation from an LLM tool loop. The MIDI
port stays open for the duration of the session:

```bash
cat <<'JSONL' | flcli batch stream
{"id":"a1","name":"tempo","args":{"bpm":128}}
{"id":"a2","name":"mixer_volume_set","args":{"track":1,"value":0.75}}
{"id":"a3","name":"play"}
JSONL
```

Empty lines and `#` comments are skipped.

### Step names usable in batch

| Category | Commands |
|----------|----------|
| Transport | `play`, `stop`, `record` |
| Transport position | `transport_position_get`, `transport_position_set` (`args.mode?`: `beats`/`ticks`/`ms`/`abs-ticks`) |
| Loop | `transport_loop_get`, `transport_loop_toggle` |
| Undo/Redo | `undo`, `redo`, `undo_history` |
| Tempo | `tempo` (`args.bpm`) |
| Project | `new_project`, `new_pattern`, `select_pattern`, `duplicate_channel`, `name_channel`, `select_channel` |
| Step | `set_step`, `step_melody` |
| Mixer | `mixer_list`, `mixer_volume_get`, `mixer_volume_set`, `mixer_pan_get`, `mixer_pan_set`, `mixer_name_get`, `mixer_name_set`, `mixer_mute`, `mixer_solo`, `mixer_arm`, `mixer_route_set`, `mixer_link_to_channel` |
| Plugin | `plugin_list`, `plugin_params`, `plugin_param_get`, `plugin_param_set` |
| State | `state` (`args.field?`) |
| File | `piano_roll_show` (`args.export_file?`) |

## Extended state snapshot

`flcli state` returns a comprehensive snapshot of FL Studio:

```json
{
  "tempo": 128.0,
  "current_pattern": 1,
  "pattern_count": 4,
  "selected_channel": 0,
  "channel_count": 2,
  "is_playing": false,
  "is_recording": false,
  "song_position": {"beats": 0.0, "ms": 0.0},
  "channels": [
    {"index": 0, "name": "Kick", "color": 16711680, "volume": 0.78, "pan": 0.0, "target_fx_track": 1, "plugin_name": "FPC"}
  ],
  "patterns": [
    {"index": 1, "name": "Verse", "color": 255}
  ],
  "mixer": {
    "tracks": [
      {"index": 0, "name": "Master", "volume": 0.8, "pan": 0.0, "mute": false, "solo": false}
    ],
    "routing": [[1, 0]]
  },
  "updated_at": 1234567890.123
}
```

Use a dot path to fetch a specific value:

```bash
flcli state --field channels.0.name        # → "Kick"
flcli state --field mixer.tracks.1.volume  # → 0.75
flcli state --field song_position.beats    # → 4.0
```

### Throttling

To curb the polling cost of large snapshots, the device caches state
(default 500 ms):

```bash
flcli --state-throttle-ms 100 state        # allow 100ms refresh interval
export FLCLI_STATE_THROTTLE_MS=250         # also configurable via env var
```

## Dry-run

`--dry-run` previews the request without opening a MIDI port:

```bash
flcli --dry-run tempo 140
flcli --dry-run batch run --steps-file song.json
```

## Diagnostics

```bash
flcli ping                  # Check port reachability (failure: exit 10)
flcli doctor                # Comprehensive health check
```

`doctor` checks:

| Check | Description |
|-------|-------------|
| `midi_port` | MIDI output port detection |
| `piano_roll_queue` | Queue file state |
| `piano_roll_export` | Export file state |
| `song_position` | `song_position` from a live snapshot |
| `state_channels` | Presence of the `channels` section |
| `state_patterns` | Presence of the `patterns` section |
| `state_mixer` | Presence of the `mixer` section |
| `auto_trigger` | OS automation prerequisites (informational) |
| `pyflp` | pyflp installation status (informational) |

## Error taxonomy

| error.code | exit | Meaning |
|---|---|---|
| `INVALID_ARGUMENT` | 2 | User input failed validation |
| `NOT_FOUND` | 3 | Expected file/field is missing |
| `IO_ERROR` | 4 | OS exception during file I/O |
| `PORT_NOT_FOUND` | 10 | Virtual MIDI port not found |
| `TIMEOUT` | 12 | Response from device script timed out |
| `UNKNOWN_COMMAND` | 20 | Unregistered batch step name |
| `PROTOCOL_ERROR` | 30 | Internal encoder mismatch (bug) |
| `AUTOMATION_FAILED` | 31 | OS automation (auto-trigger, window focus) failed |
| `INTERNAL` | 99 | Unexpected exception (bug) |

```bash
flcli state --field tempo | jq '.result.value'
flcli --dry-run batch run < song.json | jq '.result.responses[] | select(.ok==false)'
```

## Wire protocol

All communication uses SysEx frames:

```
F0 7D 02 <rid0> <rid1> <rid2> <rid3> <packed_json> F7
```

| Field | Description |
|---|---|
| `7D` | Non-commercial manufacturer ID |
| `02` | Protocol version |
| `rid0-3` | 28-bit `request_id` (MSB-first, 7-bit clean) |
| `packed_json` | UTF-8 JSON, 8→7 bit packed (Roland scheme) |

Request: `{"cmd": "tempo", "args": {"bpm": 140.5}}`
Response: `{"request_id": 42, "ok": true, "command": "tempo", "result": {"bpm": 140.5}, "error": null}`

## Configuration file (TOML)

Putting settings in `~/.flcli/config.toml` lets you omit CLI flags and
environment variables.

### Precedence

1. CLI flags (`--port`, `--dry-run`, etc.)
2. Environment variables (`FLCLI_PORT`, `FLCLI_DRY_RUN`, etc.)
3. Config file (`~/.flcli/config.toml` or `$FLCLI_CONFIG`)
4. Hard-coded defaults

### TOML schema

```toml
[default]
port = "flcli"
channel = 0
dry_run = false

[paths]
state = "/path/to/state.json"
queue = "/path/to/pending_notes.json"
export = "/path/to/exported_notes.json"

[batch]
stop_on_error = true
state_throttle_ms = 250
```

### Environment variables

| Variable | Setting |
|----------|---------|
| `FLCLI_PORT` | port |
| `FLCLI_RETURN_PORT` | return_port |
| `FLCLI_CHANNEL` | channel |
| `FLCLI_DRY_RUN` | dry_run |
| `FLCLI_STATE_THROTTLE_MS` | state_throttle_ms |
| `FLCLI_STATE_PATH` | state_path |
| `FLCLI_QUEUE_PATH` | queue_path |
| `FLCLI_EXPORT_PATH` | export_path |
| `FLCLI_STOP_ON_ERROR` | stop_on_error |
| `FLCLI_CONFIG` | Override the config file path |

### `config` command

```bash
flcli config show       # Show resolved settings and the source of each value
flcli config path       # Show the active config file path
```

## Shell completion

```bash
flcli completion show                  # Print the completion script to stdout
flcli completion show --shell zsh      # Specify the shell
flcli completion install               # Auto-detect and install completion
flcli completion install --shell fish  # Install for fish
```

Install paths:
- **bash:** `~/.bash_completion.d/flcli`
- **zsh:** `~/.zfunc/_flcli`
- **fish:** `~/.config/fish/completions/flcli.fish`

## Stable references (refs)

Channels, mixer tracks, and patterns can be specified by index, name, or
substring — three modes total. This keeps batch scripts robust when an
index shifts.

```python
from flstudio_cli.refs import (
    ChannelRef, MixerTrackRef, PatternRef,
    resolve_channel, resolve_mixer_track, resolve_pattern,
    require_exactly_one_selector,
)

# By index
ref = ChannelRef(mode="index", index=0)

# By name (exact match)
ref = ChannelRef(mode="name", name="Kick")

# By substring (case-insensitive)
ref = ChannelRef(mode="query", query="kick")

# Resolve against a snapshot
index = resolve_channel(ref.__dict__, snapshot)
```

## JSONL traces (record / replay)

Record MIDI traffic to a JSONL file and replay it as-is during tests.
Useful for hardware-free regression tests and debugging.

### Recording

```python
from flstudio_cli.shared.infrastructure.transport.recording_sink import RecordingCommandTransport

with open("trace.jsonl", "w") as f:
    recording = RecordingCommandTransport(inner=real_transport, trace_file=f)
    recording.send_frame(frame)
```

Each line has the form:
```json
{"t": 0.001234, "dir": "out", "type": "sysex", "frame_hex": "f07d02...f7"}
```

### Replay

```python
from flstudio_cli.shared.infrastructure.transport.replay_sink import (
    ReplayCommandTransport,
    ReplayReturnPort,
    load_trace,
)

with open("trace.jsonl") as f:
    out_events, in_events = load_trace(f)

replay = ReplayCommandTransport(out_events)
replay.send_frame(frame)  # raises ReplayMismatchError on mismatch
```

## Auto-trigger (OS automation)

Adding `--auto-trigger` to `queue-piano-roll` runs `flcli_import`
automatically via an OS-level keyboard shortcut after the queue file is
written.

```bash
cat notes.csv | flcli queue-piano-roll - --auto-trigger
cat notes.csv | flcli queue-piano-roll - --auto-trigger --shortcut "ctrl+shift+i"
```

| Platform | Implementation | Requirement |
|----------|---------------|-------------|
| Windows | pynput | `pip install pynput` |
| macOS | osascript | Built-in |
| Linux | xdotool | `sudo apt install xdotool` |

`flcli doctor` reports installation status.

## FLP file operations (offline)

Use `pyflp` to read and write `.flp` files directly. Covers operations
that aren't possible via FL Studio's runtime API (e.g. inserting notes
into an arbitrary pattern).

```bash
pip install pyflp  # or pip install flstudio-cli[flp]
```

```bash
# FLP file info
flcli flp info song.flp

# Add notes to the piano roll
flcli flp notes add song.flp -c 0 --from-csv notes.csv
flcli flp notes add song.flp -c 0 --from-json notes.json
flcli flp notes add song.flp -c 0 -p 2 --from-csv -   # stdin, with pattern

# Clear piano-roll notes
flcli flp notes clear song.flp -c 0
flcli flp notes clear song.flp -c 0 -p 2               # with pattern

# Rename channel
flcli flp channel rename song.flp -c 0 "Kick"

# Set pattern length (in steps)
flcli flp pattern set-length song.flp -p 1 64

# Mixer routing
flcli flp mixer route song.flp --from 1 --to 0 --on

# Place a clip on the playlist
flcli flp clip create song.flp -t 0 -p 1 --position 0.0 --length 16.0
```

## Adding a command (for contributors)

To add a new command (4 edit sites):

1. **`FlCommandPort` Protocol + adapter:** add a method to
   `src/flstudio_cli/shared/application/fl_command_port.py` and have
   `DefaultFlCommands` return the matching `DeviceCommand("wire_name",
   {...})`.  This is the single source of truth for the wire format.
2. **Device handler:** in
   `src/flstudio_cli/shared/infrastructure/fl_device/device_flcli.py`'s
   `_build_v2_dispatcher`, add a `dispatcher.register("wire_name",
   _handler)` call alongside the implementation.
   `test_device_v2.py::TestDispatcherParityWithFlCommandPort` catches
   either side forgetting to update.
3. **Batch handler:** add `_handle_<name>(args) -> DeviceCommand` to the
   feature's `<feature>/application/handlers.py`, calling
   `fl.<method>(...)`.  Register it in the feature's `BATCH_HANDLERS`
   dict; entry-point discovery picks it up automatically.
4. **CLI command:** add the Click subcommand to
   `<feature>/presentation/cmd_<feature>.py` and append it to
   `CLI_COMMANDS`.  Delegate to `_dispatch_command()` (single call) or
   `_dispatch_with_track_selector()` (resolves name → index via
   `mixer_list` first); both go through the application-layer error
   handling in `shared/application/cli_dispatcher.py`.
5. **Test:** verify port-free behavior with `--dry-run`:
   ```bash
   flcli --dry-run <new-command> [args...]
   ```

## Optional dependencies

```bash
pip install flstudio-cli[flp]           # pyflp (FLP file operations)
pip install flstudio-cli[auto-trigger]  # pynput (Windows auto-trigger)
pip install flstudio-cli[all]           # All optional dependencies
```

## Limitations

- The FL Studio GUI must be running (no headless mode).
- Piano-roll writes have three paths (`step-melody`, `queue-piano-roll`,
  `piano-roll`), each with different trade-offs.
- Runtime (SysEx) `pattern-length` / `playlist-add` are not implemented
  because the API is not exposed. As an offline alternative, use
  `flcli flp pattern set-length` / `flcli flp clip create`.
