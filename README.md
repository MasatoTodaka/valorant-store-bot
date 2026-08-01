# valorant-store-bot

ゲーム本体を起動せずに、Discordのスラッシュコマンド `/store` でVALORANTの本日の
デイリーショップ(スキン4枚)を確認できるBotです。スマートフォンのDiscordアプリからも
そのまま利用できます。

## 仕組み

VALORANTには公式のストア確認APIは存在しません。このツールは **Riot Client
(ログイン専用のランチャー。VALORANT本体ではない)** がバックグラウンドで起動して
ログイン済みの場合、`127.0.0.1`宛のローカルAPI経由で、Riot Client自身が発行した
正規の認証トークンをそのまま読み取ります。取得したトークンでストアAPI
(`pd.*.a.pvp.net`)を呼び出し、アイテムID→スキン名/画像の変換にはRiot公認の
コミュニティAPIである [valorant-api.com](https://valorant-api.com)(認証不要)を
使っています。

これは実際のRiot Client(公式アプリ)自身が発行したトークンを読むだけなので、
パスワードの直接送信やブラウザ自動化(Playwright等)で直面するボット検知
(hCaptcha・TLSフィンガープリント)を一切経由しません。**Riotのパスワードを
どこにも保存する必要がない**のもこの方式の利点です。

読み取り専用(ストア閲覧のみ)の用途であればリスクは低いとされていますが、
Riotの公式APIではないため利用規約上グレーゾーンである点は理解した上で
自己責任で利用してください。

**トークンやCookieの値は絶対にチャットや外部サービスに貼り付けないでください。**
実際のセッションを乗っ取れてしまう秘密情報です。

## 前提条件

- **Riot Client(ランチャー)** がインストールされていて、`/store` を使いたい間は
  常にバックグラウンドで起動 & ログイン済みであること(VALORANT本体は起動不要)

## セットアップ

### 1. 依存関係のインストール

```bash
cd ~/valorant-store-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Discord Botの作成

1. [Discord Developer Portal](https://discord.com/developers/applications) で「New Application」
2. 左メニュー「Bot」→「Reset Token」でトークンを取得
3. 「OAuth2」→「URL Generator」で scope に `bot` と `applications.commands` を選択、
   Permissions に `Send Messages` / `Embed Links` を選択して生成されたURLからサーバーに招待

### 3. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を開いて以下を埋める:

- `DISCORD_BOT_TOKEN`: 手順2で取得したトークン
- `DISCORD_GUILD_ID`: (任意)開発中に使うテストサーバーのID。設定するとコマンドが即反映される

Riotの認証情報は不要です(Riot Clientのログイン状態をそのまま使うため)。

### 4. Riot Clientの起動 & 接続確認

Riot Client(ランチャーのみでOK、VALORANT本体は起動しなくてよい)を起動し、
普段通りログインしてください。ログインできたら、以下でローカルAPIから
正しくトークンを読み取れるか確認します。

```bash
python login_setup.py
```

成功すると `PUUID` と `region` が表示されます。失敗する場合はRiot Clientが
起動していない、またはログインしていない可能性が高いです。

### 5. Botの起動

```bash
python bot.py
```

Discord側でBotがオンラインになったら、任意のチャンネル(スマートフォンの
Discordアプリからでも可)で `/store` と入力すれば本日のストアが表示されます。

## 常時稼働させたい場合

`/store` をいつでも実行できるようにするには、`bot.py` に加えて **Riot Clientも
バックグラウンドで起動したまま** にしておく必要があります。PCを閉じても動かし
続けたい場合は、`pm2` や `systemd`などで `python bot.py` をバックグラウンド実行
しつつ、Riot Clientも同じマシン上で起動し続けてください。

## うまく取得できない場合

`/store` 実行時に「Riot Clientのローカルセッション取得に失敗しました」という
メッセージが出た場合は、Riot Clientが起動していないか、ログアウトされている
可能性があります。Riot Clientを起動してログインし直してから、もう一度お試しください。
