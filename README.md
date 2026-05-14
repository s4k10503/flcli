# flcli

> **Status: unmaintained.** Provided AS-IS under the MIT License. Active
> development has stopped — forks are explicitly encouraged. Issues and
> PRs filed on this repository may not be reviewed.

[日本語](README.md) | [English](README.en.md)

LLM フレンドリーな FL Studio 制御用 CLI。SysEx 双方向プロトコル経由で
FL Studio にコマンドを送り、結果を JSON で返します。Anthropic Claude
などの LLM から `Bash` ツール等で直接叩けるように、すべての出力を
1 行 JSON エンベロープに統一しています。

## アーキテクチャ

```
LLM / シェル
  ↓ argv
flcli (この CLI)
  ↓ SysEx (F0 7D 02 … F7) via 仮想 MIDI ポート "flcli"
FL Studio + device_flcli.py
  ↓ SysEx レスポンス via "flcli-rx"
flcli (応答受信)
```

プロトコル v2 は **双方向 SysEx** です。CLI はコマンドを JSON ペイロード
付き SysEx フレームで送信し、デバイススクリプトが同じ `request_id` で
レスポンスを返します。ファイルポーリングは不要で、全コマンドが同期的に
成功 / 失敗を返します。

### パッケージ構成

```
src/flstudio_cli/
├── shared/                          全 feature 横断の足場
│   ├── utility/                     レイヤフリーな汎用型 (Outcome / Result-like)
│   ├── domain/                      Value Object と Domain Service (純粋型)
│   ├── application/                 Use Case / Port / DTO
│   ├── infrastructure/              Adapter (外側の関心事すべて)
│   │   ├── protocol/                ワイヤフォーマット (v2 + _device_portable)
│   │   ├── transport/               MIDI I/O (sink / return port / record / replay)
│   │   ├── flp/                     .flp file format adapter (pyflp)
│   │   ├── fl_device/               FL Studio sandbox-side scripts (device_flcli.py 他)
│   │   ├── io_utils.py              tmp+rename atomic write / read_text
│   │   └── os_automation.py         OS automation (auto-trigger)
│   ├── composition/                 Composition Root (DI 合成 — effects / facades / transport)
│   └── presentation/                Interface Adapter (CA): cli_helpers / cli_dispatch / exit_codes
├── batch/  config/  completion/  flp_cli/  mixer/  piano_roll/  plugin/
├── project/  state/  transport/    各 feature: application/handlers.py +
│                                   presentation/cmd_<feature>.py + feature.py
└── __main__.py                     Click ルート group + entry-point discovery
```

各 feature は `feature.py` に `FEATURE = Feature(...)` を定義し、
`pyproject.toml` の `[project.entry-points."flstudio_cli.features"]` で登録される。
`__main__.py` は registry を walk して CLI / batch handlers を組み立てる。

レイヤ依存方向は単方向 (`presentation` → `composition` → `application` → `domain`)。
`domain` は純粋で、`infrastructure` を含むどの外側も参照しません。
`composition` だけが `infrastructure` を import でき、`presentation` は
`composition` 経由でのみ外部アダプタに触れます。
`__main__.py` は最上位の編成だけを担当し、副作用は `application` に押し下げます。
`shared/utility/` は Rust の `std::result` 相当のレイヤフリー領域で、
全レイヤから自由に依存可能(現状は Outcome 型のみ)。

### ファイルレベルのロールタグ規約

すべての非テスト `.py` ファイルは docstring 1 行目を **DDD / Clean Architecture
の 9 種ロールタグ**のいずれかで開始します。`grep -E '^"""[A-Z][a-zA-Z ]+:'`
を src ツリーに走らせると 1 ファイル 1 件マッチします。

| ロールタグ | 由来 | 適用例 |
|---|---|---|
| `Composition root:` | Mark Seemann (DI) | `__main__.py`, `composition/*.py`, 各 feature の `feature.py` |
| `Use case:` | CA = DDD の Application Service | application/ 内の orchestration、`handlers.py`、use-case helper、facade re-export (`batch.py`) |
| `Application port:` | Hexagonal Port | `*_port.py`, `ports.py` |
| `Application DTO:` | Fowler | `*_dto.py`, `*_errors.py`, 定数モジュール、DTO factory/parser、DTO facade (`envelope.py`) |
| `Domain value object:` | DDD | frozen dataclass / NewType vocabulary |
| `Domain service:` | DDD | 純粋なドメイン操作 (`edit_ops`, `snapshot_diff`) |
| `Infrastructure adapter:` | Hexagonal | Port を実装する concrete (transport sinks, file-format adapters, wire codec, FL sandbox) |
| `Interface adapter:` | CA Layer 3 | Click commands (`cmd_*.py`) と CLI helpers |
| `Utility:` | レイヤフリー | `shared/utility/*` (Outcome 型) |

詳細は `src/flstudio_cli/__init__.py` の docstring を参照。
レイヤ別の細則(ファイル命名規則)は各 layer の `__init__.py`(例:
`shared/application/__init__.py`)に記載。

### 依存ルールの機械的検証

`tach.toml` に上記の方向制約と feature 独立性 (cross-feature import は
`shared/` を介す) を宣言し、CI と pre-commit で `tach check` を回しています。
新しい違反 import が入ると CI が落ちます。`tach check-external` は
`pyproject.toml` の宣言と実 import が一致しているかも検証します。

```bash
uv run tach check          # アーキテクチャ違反の検出
uv run tach check-external # 外部依存の宣言整合性
uv run tach show --web     # 依存グラフを可視化 (任意)
```

許容済みの carve-out は `tach.toml` 内に `TODO(#NNN)` コメント付きで
記載され、関連 Issue の解消で機械的に検出可能になります。

## セットアップ

### 1. 仮想 MIDI ポートの作成

**2 本**のポートが必要です:

| ポート名 | 方向 | 用途 |
|----------|------|------|
| `flcli` | CLI → FL Studio | コマンド送信 |
| `flcli-rx` | FL Studio → CLI | レスポンス返信 |

- **Windows:** [LoopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) で `flcli` と `flcli-rx` を作成
- **macOS:** Audio MIDI 設定 → IAC ドライバを有効にし、`flcli` と `flcli-rx` の 2 バスを追加。
  Port 番号の割り当てや応答ループの回避など macOS 固有のハマりどころは
  [`docs/setup-macos.md`](docs/setup-macos.md) を参照。

### 2. デバイススクリプトの配置

`src/flstudio_cli/shared/infrastructure/fl_device/device_flcli.py` を FL Studio のハードウェア設定フォルダに配置:

```
Documents/Image-Line/FL Studio/Settings/Hardware/flcli/device_flcli.py
```

ピアノロール直接書込 (`queue-piano-roll`) を使う場合は併せて
`src/flstudio_cli/shared/infrastructure/fl_device/flcli_import.pyscript` を以下に配置:

```
Documents/Image-Line/FL Studio/Settings/Piano roll scripts/flcli_import.pyscript
```

### 3. FL Studio の設定

Options → MIDI Settings で `flcli` ポートと `flcli-rx` ポートの両方を有効化し、
コントローラタイプを `flcli` に設定。

### 4. CLI のインストール

```bash
pip install -e .
```

## 基本コマンド

```bash
flcli ports                                # MIDI 出力ポート一覧
flcli ping                                 # ポート疎通確認
flcli state                                # FL Studio の状態を同期取得 (拡張スナップショット)
flcli state --field tempo                  # トップレベルフィールドの取得
flcli state --field channels.0.name        # ドットパスで深い階層を取得
flcli state --field mixer.tracks.1.volume  # ミキサートラックの個別値

# トランスポート
flcli play                                 # 再生
flcli stop                                 # 停止
flcli record                               # 録音トグル
flcli tempo 128                            # BPM 設定

# プロジェクト / パターン / チャンネル
flcli new-project                          # 新規プロジェクト
flcli new-pattern                          # 新規パターン
flcli select-pattern 2                     # パターン選択
flcli duplicate-channel                    # 選択中チャンネルを複製 (FL の Ctrl+C/V 相当)
flcli select-channel 0                     # チャンネル選択
flcli name-channel 3 --name "my synth"     # チャンネル名設定 (任意 UTF-8)

# トランスポート位置 / ループ
flcli transport-position get               # 再生位置 (デフォルト beats)
flcli transport-position get --mode ticks  # ticks で取得
flcli transport-position set 8.0           # 再生位置を 8 拍目に移動
flcli transport-position set 1920 --mode ticks
flcli transport-loop get                   # 現在のループモードを取得
flcli transport-loop toggle                # ループモードを切り替え

# Undo / Redo
flcli undo                                 # 直前の操作を取り消し
flcli redo                                 # 取り消した操作をやり直し
flcli undo-history                         # Undo 回数と直近の履歴エントリ

# ステップシーケンサ
flcli step 0 4 1 -v 110                    # ch0 の step4 を ON (velocity 110)
```

## プラグイン

`flcli plugin` グループでチャンネルラック上のプラグインを検査・制御できます:

```bash
# プラグイン一覧 (チャンネル 0 の全スロット)
flcli plugin list --channel 0

# パラメータ一覧
flcli plugin params --channel 0             # デフォルトスロット (0)
flcli plugin params --channel 0 --slot 1    # 特定スロット

# パラメータ取得 (インデックスまたは名前で指定)
flcli plugin param get --channel 0 --param 5
flcli plugin param get --channel 0 --param-name "Cutoff"

# パラメータ設定 (0.0 - 1.0)
flcli plugin param set 0.75 --channel 0 --param 5
flcli plugin param set 0.5 --channel 0 --param-name "Resonance"
```

## ミキサー

`flcli mixer` グループでミキサートラックの操作ができます:

```bash
flcli mixer list                           # 全トラックの状態一覧

# ボリューム (0.0 - 1.0)
flcli mixer volume get --track 1
flcli mixer volume set 0.75 --track 1

# パン (-1.0 to 1.0)
flcli mixer pan get --track 2
flcli mixer pan set -0.3 --track 2

# トラック名 (任意 UTF-8)
flcli mixer name get --track 3
flcli mixer name set "Drums" --track 3

# ミュート / ソロ / アーム (トグル)
flcli mixer mute --track 4
flcli mixer solo --track 5
flcli mixer arm --track 6 --on
flcli mixer arm --track 6 --off

# ルーティング
flcli mixer route --from 1 --to 0 --on    # トラック1→0へセンド有効化

# チャンネルリンク
flcli mixer link-to-channel --track 1      # 選択中チャンネルにリンク
```

## メロディ / ピアノロール

### ステップメロディ (ステップグリッド入力)

pitch は無視され、選択中チャンネルの 1/16 ステップに展開されます:

```bash
cat <<EOF | flcli step-melody -
60,100,1.0,0.0
62,100,1.0,1.0
64,100,1.0,2.0
67,100,2.0,3.0
EOF
```

### Piano Roll Script 経路 (サンプル精度)

```bash
cat <<EOF | flcli queue-piano-roll -
60,100,1.0,0.0
64,100,1.0,1.0
67,100,1.0,2.0
72,100,1.0,3.0
EOF
# → FL Studio で Piano Roll を開き Tools → Scripts → flcli_import を実行
```

### 実時間レコーディング経路 (ハンズフリー)

FL Studio をフォアグラウンドにして書込先チャンネルを選択:

```bash
cat <<EOF | flcli piano-roll - --bpm 120
60,100,1.0,0.0
64,100,1.0,1.0
67,100,1.0,2.0
72,100,1.0,3.0
EOF
```

### ピアノロール編集 (読み取り → 変換 → 再キュー)

エクスポート済みノートを編集して再キューできます:

```bash
# 現在のノートを確認
flcli piano-roll-show

# トランスポーズ (+12 = 1オクターブ上)
flcli piano-roll-edit --transpose 12

# 時間シフト (+4 beats = 1小節後ろへ)
flcli piano-roll-edit --shift 4.0

# ノート長を半分に
flcli piano-roll-edit --scale-length 0.5

# 特定ノートだけ削除 (0-indexed)
flcli piano-roll-edit --delete 0,3,5

# 複合: ノート 0-3 だけトランスポーズして再キュー
flcli piano-roll-edit --only 0,1,2,3 --transpose -12 --clear
```

編集後は `queue-piano-roll` と同様、FL Studio で `flcli_import` の実行が必要です。

### MIDI ファイル読み込み

```bash
flcli read-midi song.mid                   # JSON で出力
flcli read-midi song.mid --format csv      # CSV で出力
```

## 出力エンベロープ

全コマンドは成功 / 失敗どちらも **同じ構造** の JSON を出力します:

```json
{"ok": true, "command": "tempo", "args": {"bpm": 140.0}, "result": {"bpm": 140.0}, "error": null}
```

```json
{"ok": false, "command": "tempo", "args": {}, "result": null, "error": {"code": "INVALID_ARGUMENT", "message": "missing required argument: 'bpm'"}}
```

## スナップショットと差分

### `snapshot` (状態キャプチャ)

デバイスから最新の状態を強制取得し、ファイルに保存:

```bash
flcli snapshot                             # stdout に JSON エンベロープ出力
flcli snapshot --out before.json           # ファイルに保存 (アトミック書込)
flcli snapshot --out state.json --pretty   # 整形出力
flcli snapshot --sections mixer,channels   # セクション絞り込み
```

### `diff` (スナップショット比較)

2つのスナップショットファイルを比較し、変更を構造化して返す:

```bash
flcli diff before.json after.json
```

出力例:

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

### `diff --assert` (アサーション検証)

スナップショットが期待値を満たすかテスト:

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

サポートする演算子: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`。
失敗時は exit code 2 (`INVALID_ARGUMENT`)。

## バッチ実行

### `batch run`

複数コマンドを 1 つの MIDI セッションで実行:

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

既定では最初の失敗で中断。全ステップを流すには `--continue-on-error`。

### `batch stream` (JSONL ストリーム)

LLM のツールループから低レイテンシで叩くための JSONL モード。
MIDI ポートはセッション中ずっと開いたまま:

```bash
cat <<'JSONL' | flcli batch stream
{"id":"a1","name":"tempo","args":{"bpm":128}}
{"id":"a2","name":"mixer_volume_set","args":{"track":1,"value":0.75}}
{"id":"a3","name":"play"}
JSONL
```

空行と `#` コメントはスキップされます。

### バッチで使えるステップ名

| カテゴリ | コマンド |
|----------|----------|
| トランスポート | `play`, `stop`, `record` |
| トランスポート位置 | `transport_position_get`, `transport_position_set` (`args.mode?`: `beats`/`ticks`/`ms`/`abs-ticks`) |
| ループ | `transport_loop_get`, `transport_loop_toggle` |
| Undo/Redo | `undo`, `redo`, `undo_history` |
| テンポ | `tempo` (`args.bpm`) |
| プロジェクト | `new_project`, `new_pattern`, `select_pattern`, `duplicate_channel`, `name_channel`, `select_channel` |
| ステップ | `set_step`, `step_melody` |
| ミキサー | `mixer_list`, `mixer_volume_get`, `mixer_volume_set`, `mixer_pan_get`, `mixer_pan_set`, `mixer_name_get`, `mixer_name_set`, `mixer_mute`, `mixer_solo`, `mixer_arm`, `mixer_route_set`, `mixer_link_to_channel` |
| プラグイン | `plugin_list`, `plugin_params`, `plugin_param_get`, `plugin_param_set` |
| 状態取得 | `state` (`args.field?`) |
| ファイル | `piano_roll_show` (`args.export_file?`) |

## 状態スナップショット (拡張)

`flcli state` は FL Studio の包括的なスナップショットを返します:

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

ドットパスで特定の値だけを取得:

```bash
flcli state --field channels.0.name        # → "Kick"
flcli state --field mixer.tracks.1.volume  # → 0.75
flcli state --field song_position.beats    # → 4.0
```

### スロットル

大きなスナップショットのポーリングコストを抑えるため、デバイスサイド
でキャッシュが効きます (デフォルト 500 ms):

```bash
flcli --state-throttle-ms 100 state        # 100ms 間隔で更新可能
export FLCLI_STATE_THROTTLE_MS=250         # 環境変数でも設定可能
```

## Dry-run

`--dry-run` を付けると MIDI ポートを開かず、送信されるリクエストをプレビュー:

```bash
flcli --dry-run tempo 140
flcli --dry-run batch run --steps-file song.json
```

## 診断

```bash
flcli ping                  # ポート疎通確認 (失敗: exit 10)
flcli doctor                # 包括的ヘルスチェック
```

`doctor` は以下を検査します:

| チェック名 | 内容 |
|-----------|------|
| `midi_port` | MIDI 出力ポートの検出 |
| `piano_roll_queue` | キューファイルの状態 |
| `piano_roll_export` | エクスポートファイルの状態 |
| `song_position` | ライブスナップショットの song_position |
| `state_channels` | channels セクションの有無 |
| `state_patterns` | patterns セクションの有無 |
| `state_mixer` | mixer セクションの有無 |
| `auto_trigger` | OS オートメーション前提条件 (情報のみ) |
| `pyflp` | pyflp のインストール状態 (情報のみ) |

## エラータクソノミー

| error.code | exit | 意味 |
|---|---|---|
| `INVALID_ARGUMENT` | 2 | ユーザー入力がバリデーションに失敗 |
| `NOT_FOUND` | 3 | 期待したファイル / フィールドが無い |
| `IO_ERROR` | 4 | ファイル読み書きで OS 例外 |
| `PORT_NOT_FOUND` | 10 | 仮想 MIDI ポートが見つからない |
| `TIMEOUT` | 12 | デバイススクリプトからの応答がタイムアウト |
| `UNKNOWN_COMMAND` | 20 | 未登録のバッチステップ名 |
| `PROTOCOL_ERROR` | 30 | 内部エンコーダ不整合 (バグ) |
| `AUTOMATION_FAILED` | 31 | OS自動化 (auto-trigger, window focus) が失敗 |
| `INTERNAL` | 99 | 予期しない例外 (バグ) |

```bash
flcli state --field tempo | jq '.result.value'
flcli --dry-run batch run < song.json | jq '.result.responses[] | select(.ok==false)'
```

## ワイヤープロトコル

すべての通信は SysEx フレームで行われます:

```
F0 7D 02 <rid0> <rid1> <rid2> <rid3> <packed_json> F7
```

| フィールド | 説明 |
|---|---|
| `7D` | 非商用 manufacturer ID |
| `02` | プロトコルバージョン |
| `rid0-3` | 28-bit `request_id` (MSB-first, 7-bit clean) |
| `packed_json` | UTF-8 JSON を 8→7 bit パッキング (Roland 方式) |

リクエスト: `{"cmd": "tempo", "args": {"bpm": 140.5}}`
レスポンス: `{"request_id": 42, "ok": true, "command": "tempo", "result": {"bpm": 140.5}, "error": null}`

## 設定ファイル (TOML)

`~/.flcli/config.toml` に設定を書くと、CLI フラグや環境変数を省略できます。

### 優先順位

1. CLI フラグ (`--port`, `--dry-run` 等)
2. 環境変数 (`FLCLI_PORT`, `FLCLI_DRY_RUN` 等)
3. 設定ファイル (`~/.flcli/config.toml` または `$FLCLI_CONFIG`)
4. ハードコードデフォルト

### TOML 構造

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

### 環境変数

| 変数名 | 対応設定 |
|--------|---------|
| `FLCLI_PORT` | port |
| `FLCLI_RETURN_PORT` | return_port |
| `FLCLI_CHANNEL` | channel |
| `FLCLI_DRY_RUN` | dry_run |
| `FLCLI_STATE_THROTTLE_MS` | state_throttle_ms |
| `FLCLI_STATE_PATH` | state_path |
| `FLCLI_QUEUE_PATH` | queue_path |
| `FLCLI_EXPORT_PATH` | export_path |
| `FLCLI_STOP_ON_ERROR` | stop_on_error |
| `FLCLI_CONFIG` | 設定ファイルパスのオーバーライド |

### config コマンド

```bash
flcli config show       # 解決済み設定と各値のソースを表示
flcli config path       # 使用中の設定ファイルパスを表示
```

## シェル補完

```bash
flcli completion show                  # 補完スクリプトを stdout に出力
flcli completion show --shell zsh      # シェル指定
flcli completion install               # 自動検出して補完をインストール
flcli completion install --shell fish  # fish 用にインストール
```

インストール先:
- **bash:** `~/.bash_completion.d/flcli`
- **zsh:** `~/.zfunc/_flcli`
- **fish:** `~/.config/fish/completions/flcli.fish`

## 安定リファレンス (refs)

チャンネル・ミキサートラック・パターンをインデックス・名前・部分文字列の
3 通りで指定できます。バッチスクリプトでインデックスがズレてもロバストに
ターゲットを解決するための仕組みです。

```python
from flstudio_cli.refs import (
    ChannelRef, MixerTrackRef, PatternRef,
    resolve_channel, resolve_mixer_track, resolve_pattern,
    require_exactly_one_selector,
)

# インデックス指定
ref = ChannelRef(mode="index", index=0)

# 名前指定 (完全一致)
ref = ChannelRef(mode="name", name="Kick")

# 部分文字列検索 (大文字小文字無視)
ref = ChannelRef(mode="query", query="kick")

# スナップショットに対して解決
index = resolve_channel(ref.__dict__, snapshot)
```

## JSONL トレース (録画 / 再生)

MIDI 通信を JSONL ファイルに録画し、テスト時にそのまま再生できます。
実機なしでの回帰テストやデバッグに有効です。

### 録画

```python
from flstudio_cli.shared.infrastructure.transport.recording_sink import RecordingCommandTransport

with open("trace.jsonl", "w") as f:
    recording = RecordingCommandTransport(inner=real_transport, trace_file=f)
    recording.send_frame(frame)
```

各行は以下の形式:
```json
{"t": 0.001234, "dir": "out", "type": "sysex", "frame_hex": "f07d02...f7"}
```

### 再生

```python
from flstudio_cli.shared.infrastructure.transport.replay_sink import (
    ReplayCommandTransport,
    ReplayReturnPort,
    load_trace,
)

with open("trace.jsonl") as f:
    out_events, in_events = load_trace(f)

replay = ReplayCommandTransport(out_events)
replay.send_frame(frame)  # 記録と一致しなければ ReplayMismatchError
```

## 自動トリガー (OS オートメーション)

`queue-piano-roll` に `--auto-trigger` を付けると、キューファイル書込後に
OS レベルのキーボードショートカットで `flcli_import` を自動実行します。

```bash
cat notes.csv | flcli queue-piano-roll - --auto-trigger
cat notes.csv | flcli queue-piano-roll - --auto-trigger --shortcut "ctrl+shift+i"
```

| プラットフォーム | 実装 | 要件 |
|-----------------|------|------|
| Windows | pynput | `pip install pynput` |
| macOS | osascript | 標準搭載 |
| Linux | xdotool | `sudo apt install xdotool` |

`flcli doctor` でインストール状況を確認できます。

## FLP ファイル操作 (オフライン)

`pyflp` を使って `.flp` ファイルを直接読み書きできます。FL Studio の
ランタイム API では不可能な操作 (任意パターンへのノート挿入等) に対応。

```bash
pip install pyflp  # または pip install flstudio-cli[flp]
```

```bash
# FLP ファイル情報
flcli flp info song.flp

# ピアノロールにノート追加
flcli flp notes add song.flp -c 0 --from-csv notes.csv
flcli flp notes add song.flp -c 0 --from-json notes.json
flcli flp notes add song.flp -c 0 -p 2 --from-csv -   # stdin, パターン指定

# ピアノロールのノートをクリア
flcli flp notes clear song.flp -c 0
flcli flp notes clear song.flp -c 0 -p 2               # パターン指定

# チャンネル名変更
flcli flp channel rename song.flp -c 0 "Kick"

# パターン長設定 (ステップ数)
flcli flp pattern set-length song.flp -p 1 64

# ミキサールーティング
flcli flp mixer route song.flp --from 1 --to 0 --on

# プレイリストにクリップ配置
flcli flp clip create song.flp -t 0 -p 1 --position 0.0 --length 16.0
```

## コマンドの追加方法 (コントリビューター向け)

新しいコマンドを追加する手順 (4 か所の編集):

1. **`FlCommandPort` Protocol + adapter**:
   `src/flstudio_cli/shared/application/fl_command_port.py` に method を 1 つ追加し、
   `DefaultFlCommands` で対応する `DeviceCommand("wire_name", {...})` を返す。
   wire 形式の単一情報源はここ。
2. **デバイスハンドラ**: `src/flstudio_cli/shared/infrastructure/fl_device/device_flcli.py`
   の `_build_v2_dispatcher` に `dispatcher.register("wire_name", _handler)` と
   実装関数を追加。`test_device_v2.py::TestDispatcherParityWithFlCommandPort` が
   片忘れを検出するので、Step 1 と必ずペアで揃える。
3. **バッチハンドラ**: 該当 feature の `<feature>/application/handlers.py` に
   `_handle_<name>(args) -> DeviceCommand` を追加し、`fl.<method>(...)` を呼ぶ形で
   実装。`BATCH_HANDLERS` dict に登録すれば entry_points 経由で自動 discovery される。
4. **CLI コマンド**: `<feature>/presentation/cmd_<feature>.py` に Click サブコマンド
   を追加し、`CLI_COMMANDS` リストに append。`_dispatch_command()` (1 コール) か
   `_dispatch_with_track_selector()` (mixer_list で名前→index 解決) に委譲する。
   どちらも内部で application 層 (`shared/application/cli_dispatcher.py`) の共通
   エラー処理を経由する。
5. **テスト**: `--dry-run` でポートなしの動作確認が可能:
   ```bash
   flcli --dry-run <new-command> [args...]
   ```

## オプション依存関係

```bash
pip install flstudio-cli[flp]           # pyflp (FLP ファイル操作)
pip install flstudio-cli[auto-trigger]  # pynput (Windows 自動トリガー)
pip install flstudio-cli[all]           # 全オプション依存
```

## 制限

- FL Studio の GUI が起動している必要があります (ヘッドレス不可)
- ピアノロール書込は 3 経路 (`step-melody`, `queue-piano-roll`, `piano-roll`) があり、それぞれトレードオフが異なります
- ランタイム (SysEx) での `pattern-length` / `playlist-add` は API 未公開のため未実装。オフライン代替として `flcli flp pattern set-length` / `flcli flp clip create` が利用可能
