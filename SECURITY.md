# Security Policy

## Maintenance Status

このプロジェクトは **アクティブメンテナンスされていません** ([README](./README.md) 参照)。重大な脆弱性報告には可能な範囲で対応しますが、修正やリリースの保証はしません。安定して使い続けたい場合は **フォークを推奨** します。

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `main`  | best-effort        |
| 過去 commit / fork | フォーク所有者が対応 |

## Reporting a Vulnerability

**公開 issue に脆弱性を報告しないでください。** 代わりに以下のいずれかで非公開に連絡してください:

1. **GitHub Security Advisories (推奨):** [Report a vulnerability](https://github.com/s4k10503/flcli/security/advisories/new) からプライベートな advisory を作成。
2. GitHub プロフィール (`@s4k10503`) 経由のプライベートな連絡手段。

報告時には可能な範囲で以下を含めてください:

- 再現手順 / PoC
- 影響を受けるコミット SHA
- 想定される影響範囲 (RCE / DoS / 情報漏洩 など)
- 提案する修正 (あれば)

## Response Timeline (best-effort)

- メンテナンスされていないため、応答に **数週間以上かかる可能性** があります。
- 軽微な問題は対応されない可能性があります。フォークによる修正を歓迎します。

## Scope

本 CLI は **ローカルの仮想 MIDI ポート経由で FL Studio を操作** することを前提に設計されています。以下は本プロジェクトのセキュリティスコープ **外** です:

- FL Studio 本体の脆弱性 — [Image-Line](https://www.image-line.com/) に直接報告してください。
- `mido` / `python-rtmidi` 等の依存ライブラリの脆弱性 — 各プロジェクトの security policy に従って報告してください。本プロジェクトは依存先の既知脆弱性を Dependabot で追跡しています。
- FL Studio スクリプトフォルダに配置されるユーザー側スクリプト (`src/flstudio_cli/shared/infrastructure/fl_device/*.py` / `*.pyscript`) の改変 — 信頼できる出所から入手したスクリプトのみを配置してください。

## Threat Model Notes

- CLI は **ローカル** で動作し、ネットワーク I/O を行いません。
- MIDI ポートはローカル OS の仮想ポートのみで、認証機構はありません。同一マシン上の他プロセスが `flcli` 仮想ポートに書き込めるのは OS 側の設計です。
- `--dry-run` はネットワークや MIDI ポートを開かずに入力を検証するので、信頼できない JSON バッチを評価する際に利用できます。
