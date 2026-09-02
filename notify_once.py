"""1回だけストアを取得してDiscordチャンネルに通知し、終了するスクリプト。

タスクスケジューラの「スリープを解除してタスクを実行する」機能で、毎日ストア更新の
少し後の時刻に実行される想定。常駐する bot.py とは別プロセス・別ログとして動く。

Riot Clientが未起動(スリープ復帰直後などで間に合っていない場合を含む)なら自動起動して
ログイン完了を待ち、それでもダメならログに残して何もせず終了する(次の起動時に再試行)。

S3スリープからの復帰自体がハードウェア/ドライバ都合で失敗する(クラッシュ・強制再起動)
ことがあり、その場合はスケジュールされたウェイク自体が実行されない。これはPython側の
リトライでは救えないため、「ログオン時」にも同じスクリプトを実行するようタスクを
登録し、本日まだ送信していなければここで送る、というフォールバックにしている
(送信済みなら logs/last_notify_date.txt を見て即座に何もせず終了する)。
"""

import asyncio
import datetime
import os
import socket
import sys
import time
from pathlib import Path

import discord
from dotenv import load_dotenv

from bot_logging import setup_logging
from embeds import build_store_embeds
from riot_auth import RiotAuth, RiotAuthError
from valorant_store import get_daily_skins

load_dotenv()

logger, _log_handler = setup_logging("valorant_store_notify", "logs/notify.log")

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")

# スリープ復帰直後はネットワークの初期化が遅れることがあるため、/store コマンドより長めに待つ
LAUNCH_TIMEOUT = 180
POLL_INTERVAL = 10

# discord.com へのTCP接続そのものが確立できるようになるまで待つ時間・間隔。
# スリープ復帰直後は、DNSは引けてもTCP接続がハングして[WinError 121]
# (セマフォがタイムアウトしました)で失敗することがあり、これはclient.run()より
# 前で起きるため上のRiot Client向けリトライの対象外になる。
NETWORK_WAIT_TIMEOUT = 120
NETWORK_WAIT_INTERVAL = 5

LAST_NOTIFY_MARKER = Path("logs/last_notify_date.txt")


def already_sent_today() -> bool:
    try:
        saved = LAST_NOTIFY_MARKER.read_text().strip()
    except FileNotFoundError:
        return False
    return saved == datetime.date.today().isoformat()


def mark_sent_today() -> None:
    LAST_NOTIFY_MARKER.write_text(datetime.date.today().isoformat())


def wait_for_network(host: str = "discord.com", port: int = 443) -> bool:
    deadline = time.monotonic() + NETWORK_WAIT_TIMEOUT
    while True:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError as e:
            logger.info(f"ネットワーク未準備、待機します: {e}")
        if time.monotonic() >= deadline:
            return False
        time.sleep(NETWORK_WAIT_INTERVAL)

intents = discord.Intents.default()
client = discord.Client(intents=intents)

auth = RiotAuth()


@client.event
async def on_ready():
    try:
        if not CHANNEL_ID:
            logger.error("DISCORD_CHANNEL_ID が未設定のため通知できません")
            return

        ok = await auth.ensure_valid_with_retry(timeout=LAUNCH_TIMEOUT, poll_interval=POLL_INTERVAL)
        if not ok:
            logger.error("Riot Clientの起動待ちがタイムアウトしたため、今回の通知は諦めます")
            return

        skins, remaining = await asyncio.to_thread(get_daily_skins, auth)
        channel = await client.fetch_channel(int(CHANNEL_ID))
        await channel.send(embeds=build_store_embeds(skins, remaining))
        mark_sent_today()
        logger.info(f"通知を送信しました(残り時間: {remaining}秒)")
    except Exception:
        logger.exception("通知処理中にエラーが発生しました")
    finally:
        await client.close()


if __name__ == "__main__":
    if already_sent_today():
        logger.info("本日は送信済みのため何もせず終了します")
        sys.exit(0)

    if not CHANNEL_ID:
        logger.error("DISCORD_CHANNEL_ID が未設定のため終了します")
        sys.exit(1)
    if not wait_for_network():
        logger.error(f"{NETWORK_WAIT_TIMEOUT}秒待ってもネットワークに接続できなかったため終了します")
        sys.exit(1)

    # スリープ復帰直後はネットワークの初期化が間に合わずclient.run()自体が例外を投げる
    # ことがある(pythonwにはコンソールがなく、素の例外は何も出さずに消えてしまうため、
    # 必ずログに残す)。
    try:
        client.run(DISCORD_TOKEN, log_handler=_log_handler)
    except Exception:
        logger.exception("client.run()が異常終了しました")
        sys.exit(1)
