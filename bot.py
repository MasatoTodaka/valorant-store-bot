"""VALORANTのデイリーストアをDiscordのスラッシュコマンドで確認するBot。

コマンド:
    /store   本日のデイリーショップのスキン4枚を表示する
"""

import asyncio
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from riot_auth import RiotAuth, RiotAuthError
from valorant_store import get_daily_skins

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 指定するとそのサーバーだけ即時反映される

VALORANT_RED = 0xFF4655

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
    print(f"Logged in as {client.user} (guild sync: {GUILD_ID or 'global'})")


@tree.command(name="store", description="本日のVALORANTストア(デイリーショップ)を表示します")
async def store_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        await asyncio.to_thread(auth.ensure_valid)
    except RiotAuthError as e:
        await interaction.followup.send(f"ログインに失敗しました: {e}")
        return

    try:
        skins, remaining = await asyncio.to_thread(get_daily_skins, auth)
    except Exception as e:  # noqa: BLE001 - Discordに失敗理由をそのまま返したいため
        await interaction.followup.send(f"ストア情報の取得に失敗しました: {e}")
        return

    hours, rem = divmod(remaining, 3600)
    minutes = rem // 60

    embeds = [
        discord.Embed(
            title="本日のVALORANTストア",
            description=f"残り時間: {hours}時間{minutes}分",
            color=VALORANT_RED,
        )
    ]
    for skin in skins:
        e = discord.Embed(title=skin["name"], color=VALORANT_RED)
        if skin.get("price") is not None:
            e.add_field(name="価格", value=f"{skin['price']} VP")
        if skin.get("icon"):
            e.set_image(url=skin["icon"])
        embeds.append(e)

    await interaction.followup.send(embeds=embeds)


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
