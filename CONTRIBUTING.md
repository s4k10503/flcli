# Contributing to flcli

> **このプロジェクトはアクティブにメンテナンスされていません。** バグ報告や PR は歓迎しますが、レビュー・マージは保証されません。継続したい変更がある場合は **フォークを推奨** します。

## Development Setup

```bash
git clone https://github.com/s4k10503/flcli
cd flcli
uv sync --group dev          # dev 依存もまとめてインストール
uv run pytest -q             # テスト実行
```

CI と同じ条件でテストするには Python 3.12 を使ってください。

## Pull Requests (フォーク向け推奨フロー)

1. フォークして作業ブランチを切る
2. 変更を加える (既存テストを壊さないこと)
3. 新規機能・バグ修正には原則テストを追加
4. `uv run pytest -q` をローカルでパスさせる
5. `uv run ruff check src/ conftest.py` / `uv run ruff format --check src/ conftest.py` / `uv run pyright src/` / `uv run tach check` を通す
6. PR を開く — CI / Scorecard が自動実行されます

## Commit Style

既存履歴は **命令形 & 簡潔** (例: `Add v2 dispatchers`, `Fix pitch validation`)。同じスタイルに合わせてください。1 論理変更 = 1 commit が理想です。

## Security Issues

**公開 issue として投稿しないでください。** [`SECURITY.md`](./SECURITY.md) の手順に従って GitHub Security Advisory 経由で報告してください。
