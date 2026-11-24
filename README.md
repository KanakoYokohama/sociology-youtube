# チャンネル分析ノート

YouTube チャンネルのデータ（YouTube Studio のデータを含む）を毎日自動で記録し、
グラフとアドバイスで変化を見るための専用ダッシュボードです。

- **初めての設定** → [SETUP.md](SETUP.md)
- **チャンネルを伸ばす方針とアドバイス** → [ADVICE.md](ADVICE.md)

| ファイル | 内容 |
|---|---|
| `.github/workflows/daily.yml` | 毎日 6:17（日本時間）に自動実行 |
| `scripts/collect.py` | YouTube Data API / Analytics API からデータ取得 |
| `scripts/advice.py` | データから「今日のアドバイス」を生成 |
| `scripts/crypto.py` | データの暗号化（パスワード保護） |
| `docs/index.html` | ダッシュボード（GitHub Pages） |
| `docs/data/history.enc` | 暗号化された記録（自動で更新） |
