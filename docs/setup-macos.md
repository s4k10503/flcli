# macOS セットアップガイド

README の手順に加えて、macOS で実機セットアップする際に詰まりがちなポイントを
具体的な手順込みで記録しておく。FL Studio 2024 / MIDI scripting v37 で実際に
疎通確認済み。

## 1. IAC ポートの作成

`flcli` と `flcli-rx` の 2 本の仮想 MIDI ポートが必要。

### 手順

1. **Audio MIDI 設定** を起動 (`open -a "Audio MIDI Setup"`)
2. メニュー **ウィンドウ → MIDI スタジオを表示** (⌘2)
3. **IAC ドライバ** アイコンをダブルクリック
4. 「**装置はオンライン**」にチェック
5. ポートリストで **+** ボタンを押して 2 本作成し、それぞれ次の名前にリネーム
   - `flcli`
   - `flcli-rx`
6. 「**適用**」を押して反映

### CLI 側で確認

ポート名は macOS の表示言語に依存して `IACドライバ flcli` のような前置がつく。
CLI は部分一致で解決するので問題ない。

```bash
uv run flcli ports
# {"ok": true, ..., "result": {"ports": ["IACドライバ flcli", "IACドライバ flcli-rx"]}}
```

## 2. デバイススクリプトの配置

```bash
SRC="src/flstudio_cli/shared/infrastructure/fl_device"

mkdir -p "$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/flcli"
cp "$SRC/device_flcli.py" "$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/flcli/"

mkdir -p "$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts"
cp "$SRC/flcli_import.pyscript" "$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/"
cp "$SRC/flcli_export.pyscript" "$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/"
```

スクリプトを後で更新したら、上書きコピーしたうえで FL Studio 側で
**Controller type を一度 `(none)` に戻してから `flcli` に戻す** ことで
`OnInit` を再実行できる。

## 3. FL Studio 起動順序

**IAC ポートを先に作成してから FL Studio を起動する。**

逆順 (FL Studio 起動 → IAC ポート作成) だと FL Studio が新ポートを認識せず、
後述の `event.sysex` が常に None になる症状が出る。一度 FL Studio を再起動すれば
直る。

## 4. FL Studio の MIDI 設定 (F10 → MIDI)

ここが一番ハマりやすい。**Input と Output の両方** を設定する必要があり、
さらに `flcli` (送信用) と `flcli-rx` (応答用) を **異なる Port 番号で分離** しないと
応答ループが発生する。

### 動作確認済みの正しい構成

| 種別 | デバイス | Enable | Port | Controller type |
|------|----------|--------|------|-----------------|
| Input | `IACドライバ flcli` | **ON** | **200** | **flcli** |
| Input | `IACドライバ flcli-rx` | OFF | (任意) | (none) |
| Output | `IACドライバ flcli` | (Port で制御) | **200 以外** (例: 186) | — |
| Output | `IACドライバ flcli-rx` | (Port で制御) | **200** | — |

ポイント:

- **Input `flcli`** と **Output `flcli-rx`** を **同じ Port 番号 (200)** に揃える。
  FL Studio のスクリプト側 `device.midiOutSysex()` は、Input の port 番号と一致する
  Output ポートに送信するので、ここを揃えないと応答が物理 MIDI バスに乗らない。
- **Output `flcli`** は **別の Port 番号** (200 以外) にしておく。
  Output `flcli` も 200 にすると、応答が Output `flcli` 経由で IAC `flcli` バスにも
  ばらまかれ、CLI から見ると応答が `flcli-rx` ではなく `flcli` バスに届く現象が起きる。
- **Input `flcli-rx`** は **無効**。有効にすると、スクリプトの応答が IAC `flcli-rx`
  バスを通って FL Studio 自身の Input にも戻り、`OnMidiIn` が無限ループ的に発火する。

### macOS の Output Enable

FL Studio macOS 版の Output セクションは「Enable」チェックボックスを直接編集できない。
**Port 番号を設定すること自体が有効化** に相当するので、無効化したい場合は
Port を `---` (空欄) にするか、衝突しない別番号 (例: 186) を入れて退避させる。

## 5. 確認手順

```bash
uv run flcli ports     # ポートが 2 本見えるか
uv run flcli ping      # ポート疎通 (FL Studio へは送信しない)
uv run flcli state     # FL Studio との往復確認
```

`state` でフルスナップショットが返ってくれば疎通成功。

## 6. ハマったときのチェックリスト

`flcli state` が `TIMEOUT` を返す場合、Script output (FL Studio: View → Script output)
の最新行で原因を切り分けられる。

| Script output | 原因 | 対処 |
|---------------|------|------|
| ログが何も出ない | スクリプトがロードされていない | F10 で Controller type を `(none)` → `flcli` にトグル |
| `Traceback ... AttributeError: module 'midi' has no attribute 'SONGLENGTH_BEATS'` | FL Studio の MIDI scripting バージョンに該当定数が無い | `device_flcli.py` 側で `getattr(midi, ..., None)` フォールバック済み (本リポジトリで対応済み) |
| `[flcli] OnSysEx: cannot read event.sysex` / `sysex: None` | 古い IAC バインディングのため `OnSysEx` で sysex が来ない | FL Studio を一度終了し、IAC ポートが存在する状態で再起動。`OnMidiIn` 経由でも受信するよう `device_flcli.py` で対応済み |
| `[flcli] OnMidiIn: cmd=... reply sent NN bytes via port=-1` | スクリプトに紐づく Input port が確定していない | F10 で Input `flcli` の Port を 200 に明示設定 |
| `[flcli] OnMidiIn: ...` が無限に流れ続ける | 応答が Input `flcli-rx` を経由して自身に戻っている | Input `flcli-rx` を **Disable** にする |
| `port=200` で送信できているのに CLI 側がタイムアウト | 応答が Output `flcli` 経由で `flcli` バスに流れている | Output `flcli` の Port を 200 以外に変更 |

## 7. Piano Roll への打込ワークフロー (macOS)

ノートを Piano Roll に書き込むには 3 経路あるが、macOS だと事情が違う。

### A. `flcli piano-roll` (リアルタイム録音 / 完全ハンズフリー)

ノートを CLI から MIDI で実時間ストリームし、FL Studio の録音機能で
録音させる。Tools → Scripts のクリック不要。

```bash
flcli select-channel <N>
flcli piano-roll notes.csv --bpm 128
```

初回 1 回だけ FL Studio の **"What would you like to record?"**
ダイアログで **`Notes and automation`** を選択し、可能なら
**"Don't ask anymore"** をチェックする。以降は完全ハンズフリー。
8 小節 BPM 128 で約 15 秒の wall-clock 待機。

### B. `flcli queue-piano-roll --auto-trigger` (即時インポート, 要事前プライミング)

`flcli_import.pyscript` をホットキーで自動再実行する。**FL Studio
macOS は 1 つのスクリプトに固有のホットキーを割り当てる UI を持って
いない** (Image-Line 公式・コミュニティで未提供) ため、代わりに
FL Studio に組込みの「最後に実行した Piano Roll スクリプトを再実行」
ショートカット **`Cmd + Option + Y`** を活用する。

ワークフロー:

1. FL Studio 起動後、Piano Roll を開いた状態で
   **Tools → Scripts → flcli_import** を**1 回だけ手動でクリック**
   (ここで flcli_import が "last script" として記憶される)
2. 以降は CLI から:
   ```bash
   flcli queue-piano-roll notes.csv --auto-trigger
   ```
   が `Cmd+Option+Y` を送信して flcli_import を再実行する
3. 別の Piano Roll スクリプトを手動実行すると "last script" が
   そちらに切り替わるので、再度 1. のプライミングが必要

このため CLI のデフォルトショートカットは macOS では `cmd+alt+y`、
他プラットフォームでは `ctrl+alt+i` (右クリックで個別バインド)
になる (`flcli piano-roll-trigger setup` 参照)。

### C. `flcli queue-piano-roll` (手動 Tools→Scripts)

`--auto-trigger` 抜きで使う場合は、毎回 Tools → Scripts → flcli_import
をクリックする必要がある。サンプル精度は最高だが手数が多い。

## 8. Piano Roll script のサンドボックス制限

FL Studio の Piano Roll スクリプト (`flcli_import.pyscript` /
`flcli_export.pyscript`) が動く埋め込み Python は、`open()` / `os.open()` /
`io.open()` の**絶対パス**指定が壊れている (`_io.FileIO returned NULL
without setting an exception`)。`os.stat` / `os.access` は通るので「ファイル
は見えるのに開けない」という挙動になる。

**回避策はスクリプトと同じディレクトリの相対パスで開くこと。** 本リポジトリの
CLI は `pending_notes.json` / `piano_roll_export.json` を
`~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/` (= pyscript
本体と同じフォルダ) に書き出し、pyscript 側はファイル名のみで
`open(...)` する構成にすることでこの制限を回避している。

`FLCLI_QUEUE_PATH` / `FLCLI_EXPORT_PATH` 環境変数で他のパスに上書きすることは
できるが、その場合は pyscript 側からはアクセスできない点に注意 (CLI 側だけで
JSON を扱うバッチ処理用途向け)。

## 9. アクセシビリティ / オートメーション権限

以下のコマンドは `osascript` 経由で FL Studio にキー入力を送るため、ターミナル
（Claude Code を起動しているシェル / VSCode / iTerm 等）に macOS の
**アクセシビリティ** と **オートメーション** の両方の許可が必要:

- `flcli queue-piano-roll --auto-trigger` (Piano Roll Import を Cmd+Alt+Y で再実行)
- `flcli duplicate-channel` (Channel Rack の Clone ホットキー Alt+C を発火)
- `osascript` で Audio MIDI 設定の GUI スクリプティングをする場合

**設定手順**:

1. **システム設定 → プライバシーとセキュリティ → アクセシビリティ**
   ターミナル / VSCode 等をリストに追加してトグル ON
2. **システム設定 → プライバシーとセキュリティ → オートメーション**
   ターミナル / VSCode 等の下に "System Events" が並ぶ。**System Events を ON**
   (ここを許可しないと `AUTOMATION_FAILED: -1743 (System EventsにApple Events
   を送信する権限がありません)` で失敗する)

権限が無いときの典型エラー:

- アクセシビリティ未許可: `1002: osascript にはキー操作の送信は許可されません`
- オートメーション未許可: `-1743: System EventsにApple Eventsを送信する権限が
  ありません` / `AUTOMATION_FAILED`

該当コマンドを使わない場合 (手動で Channel Rack を操作 / Audio MIDI 設定を
手動でいじる場合) は不要。

## 10. 補助ツール

GUI スクリプティングからマウスダブルクリックを発火するために
[`cliclick`](https://www.bluem.net/en/projects/cliclick/) を使用。

```bash
brew install cliclick
```

不要なら入れなくて良い。手動で Audio MIDI 設定を操作する分には必要ない。
