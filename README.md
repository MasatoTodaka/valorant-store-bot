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
- macOS / Windows で動作します(Riot ClientがLinuxに対応していないため、Linuxでは
  動きません)

## セットアップ

### 1. 依存関係のインストール

**macOS / Linux**

```bash
cd ~/valorant-store-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows(PowerShell)**

```powershell
cd valorant-store-bot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

以降のコマンド例はmacOS向け(`python ...`)で記載していますが、Windowsでも同じ
コマンドをそのまま(有効化した仮想環境内で)実行すれば問題ありません。

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
- `DISCORD_CHANNEL_ID`: (任意)設定すると、ストア更新タイミングに合わせて自動通知される
  (取得方法: Discordの「詳細設定→開発者モード」をON→通知したいチャンネルを右クリック→
  「チャンネルIDをコピー」)

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

## 自動通知

`DISCORD_CHANNEL_ID` を設定していると、Botはストアの残り時間を見ながら次の更新
タイミングを自分で計算し、更新される頃に自動的に指定チャンネルへ通知します
(更新直後はサーバー反映が少し遅れることがあるため、2分ほど余裕を持って取得します)。
通知後は、そのとき取得した新しい残り時間から次の通知タイミングを再計算する、
というのを繰り返します。

Riot Clientが起動していないタイミングと重なった場合は自動的にRiot Clientの起動を
試みたうえで取得をリトライし続けます(ログは `logs/bot.log` に出力され、5MB x 5世代で
自動的にローテーションされます)。

## 常時稼働させたい場合

`/store` をいつでも実行できるようにするには、`bot.py` に加えて **Riot Clientも
バックグラウンドで起動したまま** にしておく必要があります。

**macOS**: `launchd`(LaunchAgent)に登録するのがおすすめです。
`~/Library/LaunchAgents/` に以下のような内容のplistを作成し、
`launchctl bootstrap gui/$(id -u) <plistのパス>` で登録します。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.valorant-store-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/valorant-store-bot/.venv/bin/python</string>
        <string>-u</string>
        <string>/path/to/valorant-store-bot/bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/valorant-store-bot</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/valorant-store-bot/logs/bot.out.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/valorant-store-bot/logs/bot.err.log</string>
</dict>
</plist>
```

ノートPCの蓋を閉じても止めたくない場合は、Apple Siliconでは
`pmset disablesleep` が効かないことがあるため、蓋を開けたまま
ディスプレイだけスリープさせるか、Amphetamine等のアプリ、または
外部ディスプレイ接続によるクラムシェルモードを利用してください。

**Windows**: タスクスケジューラに登録するのが簡単です。`start_bot.bat`(クラッシュ時に
15秒後へ自動再起動するループ入り)を `run_hidden.vbs`(コマンドプロンプトの
ウィンドウを表示せずに起動する)経由で呼ぶ構成にしています。

1. 「タスクスケジューラ」を開き、「基本タスクの作成」
2. トリガーを「ログオン時」に設定(ネットワーク初期化を待つため30秒程度の
   遅延を入れておくと、起動直後のDNS失敗を避けられます)
3. 操作で「プログラムの開始」→ プログラムに `wscript.exe`、引数に
   `"<プロジェクトのパス>\run_hidden.vbs"`、開始(作業)フォルダーに
   プロジェクトのフォルダーを指定
4. 「ユーザーがログオンしているときのみ実行する」のままで問題ありません
   (このBotは管理者権限を必要としません)

PowerShellで一括登録する場合の例:

```powershell
$wd = "<プロジェクトのパス>"
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$wd\run_hidden.vbs`"" -WorkingDirectory $wd
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$env:USERNAME"
$trigger.Delay = "PT30S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 0)
Register-ScheduledTask -TaskName "ValorantStoreBot" -Action $action -Trigger $trigger -Settings $settings
```

ノートPCの蓋を閉じても止めたくない場合は、「コントロールパネル→電源オプション→
カバーを閉じたときの動作」を「何もしない」に設定してください(電源接続時のみの
設定にしておくと安全です)。また「電源とスリープ」設定でスリープを「なし」に
しておかないと、スリープ中はBotも止まります。

### 365日稼働させる場合の耐障害性について

- `start_bot.bat` はbot.pyが(未処理の例外などで)終了しても15秒後に自動的に
  再起動するループになっています。タスクスケジューラの「失敗時の再起動」設定は
  `wscript.exe` 経由の起動では効かない(実プロセスがタスクから見て「切り離される」
  ため)ので、このバッチファイル側のループが実質的な自動復旧の仕組みです。
- ログは `logs/bot.log` に出力され、5MB x 5世代でローテーションされます
  (Pythonの `RotatingFileHandler` によるもので、際限なく肥大化しません)。
- `logs/bot.crash.log` は、ロギング機構が破損するレベルの想定外のクラッシュ
  (通常は空)を拾うための最終防衛ラインで、5MBを超えたら自動的に削除されます。
- PC再起動後もログオン時に自動起動しますが、ネットワークの初期化が
  間に合わないことがあるため、ログオンから30秒の遅延を入れています。

## うまく取得できない場合

`/store` 実行時に「Riot Clientのローカルセッション取得に失敗しました」という
メッセージが出た場合は、Riot Clientが起動していないか、ログアウトされている
可能性があります。Riot Clientを起動してログインし直してから、もう一度お試しください。
