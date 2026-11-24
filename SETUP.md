# セットアップ手順（最初の1回だけ・約30分）

毎日 日本時間 6:17 に GitHub が自動でチャンネルのデータ（YouTube Studio のデータを含む）を取得し、
暗号化して保存します。ダッシュボードはパスワードを入れたときだけ中身が見られます。

必要なものは **Google Cloud の設定（ステップ1〜3）** と **GitHub の設定（ステップ4〜6）** です。
パソコンのブラウザで作業してください。

---

## ステップ1：Google Cloud でプロジェクトを作り、API を有効にする

1. https://console.cloud.google.com/ を開き、**チャンネルを持っている Google アカウント**でログイン
2. 画面上部のプロジェクト選択 →「新しいプロジェクト」→ 名前は `youtube-analytics` など → 作成
3. 左メニュー「API とサービス」→「ライブラリ」で次の2つを検索し、それぞれ **有効にする** を押す
   - **YouTube Data API v3**
   - **YouTube Analytics API**

## ステップ2：OAuth 同意画面を設定する

1. 「API とサービス」→「OAuth 同意画面」（「Google Auth Platform」と表示される場合もあります）
2. ユーザーの種類は **外部** を選び、アプリ名（例：`チャンネル分析`）、メールアドレスを入力して保存
3. 「対象」（または「公開ステータス」）で **「アプリを公開」→「本番環境」にする**
   > ⚠️ ここが一番大事です。「テスト」のままだと、7日でトークンが切れて自動記録が止まります。
   > 本番にしても Google の審査は不要です（自分専用のため）。

## ステップ3：OAuth クライアントを作り、リフレッシュトークンを取得する

### 3-1. クライアントを作る
1. 「API とサービス」→「認証情報」→「認証情報を作成」→「OAuth クライアント ID」
2. アプリケーションの種類：**ウェブ アプリケーション**
3. 「承認済みのリダイレクト URI」に次を追加
   `https://developers.google.com/oauthplayground`
4. 作成すると **クライアント ID** と **クライアント シークレット** が表示されます（メモ帳に一時的に控える）

### 3-2. OAuth Playground でトークンを取得
1. https://developers.google.com/oauthplayground を開く
2. 右上の ⚙（歯車）→ **Use your own OAuth credentials** にチェック → 3-1 のクライアント ID とシークレットを入力
3. 左の「Step 1」の入力欄に、次の2行をそれぞれ入力して追加し、**Authorize APIs** を押す
   ```
   https://www.googleapis.com/auth/yt-analytics.readonly
   https://www.googleapis.com/auth/youtube.readonly
   ```
4. Google のログイン画面で
   - チャンネルのアカウントを選ぶ（**ブランドアカウントの場合は「神奈川かなこ」のチャンネルを選ぶ**）
   - 「このアプリは確認されていません」と出たら「詳細」→「（安全でないページ）に移動」（自分で作ったアプリなので大丈夫です）
   - 権限を許可
5. 「Step 2」で **Exchange authorization code for tokens** を押す
6. 表示された **Refresh token**（`1//` で始まる長い文字列）を控える

> 🔒 クライアントシークレットとリフレッシュトークンは、チャットや他人に送らないでください。
> 次のステップで GitHub に登録したら、メモ帳の控えは削除してください。

## ステップ4：GitHub に秘密情報を登録する

リポジトリ `sociology-youtube` の **Settings → Secrets and variables → Actions → New repository secret** で、次の4つを登録します。

| Name | Value |
|---|---|
| `YT_CLIENT_ID` | 3-1 のクライアント ID |
| `YT_CLIENT_SECRET` | 3-1 のクライアント シークレット |
| `YT_REFRESH_TOKEN` | 3-2 のリフレッシュトークン |
| `DASHBOARD_PASSWORD` | ダッシュボードを開くためのパスワード（自分で決める。12文字以上推奨） |

> `DASHBOARD_PASSWORD` を後から変えると過去の記録が読めなくなります。決めたら変えないでください。

## ステップ5：ダッシュボードを公開する（GitHub Pages）

1. この作業ブランチを `main` にマージする（Claude に「PR を作って」と頼めば用意します）
   ※ 毎日の自動実行は `main` ブランチでのみ動きます
2. **Settings → Pages** → Source を「Deploy from a branch」、Branch を `main`、フォルダを `/docs` にして Save
3. 数分後に `https://<GitHubユーザー名>.github.io/sociology-youtube/` で開けます

> 無料プランで Pages を使うにはリポジトリを **Public（公開）** にする必要があります。
> データはパスワードで暗号化して保存しているので、公開しても Studio の数字は見られません
> （見えるのはプログラムのコードだけです）。

## ステップ6：初回を手動で実行する

1. **Actions** タブ →「毎日のチャンネル記録」→ **Run workflow**
2. 緑のチェックになれば成功。ダッシュボードを開き、パスワードを入力
3. 初回はチャンネル開設時からの Studio データをまとめて取得します。翌日以降は毎朝自動で更新されます

---

## うまくいかないとき

| 症状 | 対処 |
|---|---|
| Actions が `invalid_grant` で失敗 | リフレッシュトークンが失効しています。ステップ2の「本番環境」を確認し、3-2 をやり直して `YT_REFRESH_TOKEN` を更新 |
| `403` / `insufficient permissions` | 3-2 の権限（スコープ）2つが両方入っているか、正しいチャンネルを選んだか確認 |
| ダッシュボードで「まだデータがありません」 | ステップ6の初回実行がまだです |
| パスワードが通らない | `DASHBOARD_PASSWORD` と同じ文字列か確認（大文字小文字も区別） |

## しくみ（参考）

```
GitHub Actions（毎朝6:17）
  └ scripts/collect.py
      ├ YouTube Data API      … 登録者数・総再生・動画ごとの再生/高評価/コメント
      ├ YouTube Analytics API … 再生時間・視聴率・登録増減・流入元・検索語句・年齢性別・国・端末
      ├ scripts/advice.py     … データから「今日のアドバイス」を生成
      └ scripts/crypto.py     … AES-256 で暗号化 → docs/data/history.enc に保存
GitHub Pages（docs/index.html）… ブラウザでパスワードを使って復号し、グラフを表示
```

※ インプレッション数とクリック率（CTR）は YouTube の API では提供されていないため、Studio で確認してください。
