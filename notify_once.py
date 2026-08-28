"""1回だけストアを取得してDiscordチャンネルに通知し、終了するスクリプト。

タスクスケジューラの「スリープを解除してタスクを実行する」機能で、毎日ストア更新の
少し後の時刻に実行される想定。常駐する bot.py とは別プロセス・別ログとして動く。

Riot Clientが未起動(スリープ復帰直後などで間に合っていない場合を含む)なら自動起動して
ログイン完了を待ち、それでもダメならログに残して何もせず終了する(次の起動時に再試行)。
"""

import asyncio
import os
import sys

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
        logger.info(f"通知を送信しました(残り時間: {remaining}秒)")
    except Exception:
        logger.exception("通知処理中にエラーが発生しました")
    finally:
        await client.close()


if __name__ == "__main__":
    if not CHANNEL_ID:
        logger.error("DISCORD_CHANNEL_ID が未設定のため終了します")
        sys.exit(1)
    # スリープ復帰直後はネットワークの初期化が間に合わずclient.run()自体が例外を投げる
    # ことがある(pythonwにはコンソールがなく、素の例外は何も出さずに消えてしまうため、
    # 必ずログに残す)。
    try:
        client.run(DISCORD_TOKEN, log_handler=_log_handler)
    except Exception:
        logger.exception("client.run()が異常終了しました")
        sys.exit(1)
