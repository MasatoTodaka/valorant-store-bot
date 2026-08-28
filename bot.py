"""VALORANTのデイリーストアをDiscordのスラッシュコマンドで確認するBot。

コマンド:
    /store   本日のデイリーショップのスキン4枚を表示する

毎日の自動通知は notify_once.py が担当する(スリープ+ウェイクタスクで実行)。
このBotはログオン中(=PCが起きている間)だけ動く、対話コマンド専用。
"""

import asyncio
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from bot_logging import setup_logging
from embeds import build_store_embeds
from riot_auth import RiotAuth, RiotAuthError
from valorant_store import get_daily_skins

load_dotenv()

logger, _log_handler = setup_logging("valorant_store_bot", "logs/bot.log")

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 指定するとそのサーバーだけ即時反映される

# /store コマンドでRiot Clientの自動起動〜ログイン完了を待つ最大時間・ポーリング間隔
STORE_COMMAND_LAUNCH_TIMEOUT = 90
STORE_COMMAND_POLL_INTERVAL = 5

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

auth = RiotAuth()


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    logger.info(f"Logged in as {client.user} (guild sync: {GUILD_ID or 'global'})")


async def _ensure_riot_ready(interaction: discord.Interaction) -> bool:
    """Riot Clientのセッションを確立する。未起動なら自動起動し、ログイン完了まで待つ。

    成功すれば True を返す。諦めた場合は followup でユーザーに通知したうえで False を返す。
    """

    async def on_waiting():
        await interaction.followup.send(
            "Riot Clientが起動していなかったため自動的に起動しました。ログイン完了を待っています…"
        )

    try:
        ok = await auth.ensure_valid_with_retry(
            timeout=STORE_COMMAND_LAUNCH_TIMEOUT,
            poll_interval=STORE_COMMAND_POLL_INTERVAL,
            on_waiting=on_waiting,
        )
    except RiotAuthError as e:
        await interaction.followup.send(f"ログインに失敗しました: {e}")
        return False

    if not ok:
        await interaction.followup.send(
            "Riot Clientの起動待ちがタイムアウトしました。手動でログインしてから、もう一度 /store を実行してください。"
        )
    return ok


@tree.command(name="store", description="本日のVALORANTストア(デイリーショップ)を表示します")
async def store_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not await _ensure_riot_ready(interaction):
        return

    try:
        skins, remaining = await asyncio.to_thread(get_daily_skins, auth)
    except Exception as e:  # noqa: BLE001 - Discordに失敗理由をそのまま返したいため
        await interaction.followup.send(f"ストア情報の取得に失敗しました: {e}")
        return

    await interaction.followup.send(embeds=build_store_embeds(skins, remaining))


if __name__ == "__main__":
    client.run(DISCORD_TOKEN, log_handler=_log_handler)
