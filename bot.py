"""VALORANTのデイリーストアをDiscordのスラッシュコマンドで確認するBot。

コマンド:
    /store   本日のデイリーショップのスキン4枚を表示する

DISCORD_CHANNEL_ID が設定されている場合、ストアの更新タイミングに合わせて
自動的にそのチャンネルへ通知する(store_notifier_loop)。
"""

import asyncio
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from riot_auth import RiotAuth, RiotAuthError, RiotClientNotRunningError
from valorant_store import get_daily_skins

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 指定するとそのサーバーだけ即時反映される
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")  # 設定すると自動通知が有効になる

VALORANT_RED = 0xFF4655
# ストア更新直後はサーバー側の反映が少し遅れることがあるため、余裕を持たせる
REFRESH_BUFFER_SECONDS = 120
# Riot Client未起動などで取得に失敗した場合のリトライ間隔
RETRY_SECONDS = 300
# Riot Clientを自動起動した直後のリトライ間隔(起動・ログインは数十秒で終わることが多いため短め)
RETRY_SECONDS_AFTER_LAUNCH = 30
# /store コマンドでRiot Clientの自動起動〜ログイン完了を待つ最大時間・ポーリング間隔
STORE_COMMAND_LAUNCH_TIMEOUT = 90
STORE_COMMAND_POLL_INTERVAL = 5

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

auth = RiotAuth()
_notifier_started = False


def build_store_embeds(skins: list[dict], remaining: int) -> list[discord.Embed]:
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
    return embeds


async def store_notifier_loop():
    """ストアの更新タイミングに合わせて、自動的にチャンネルへ通知し続けるループ。"""
    await client.wait_until_ready()
    try:
        channel = await client.fetch_channel(int(CHANNEL_ID))
    except discord.DiscordException as e:
        print(f"[notifier] チャンネル({CHANNEL_ID})の取得に失敗したため自動通知は無効です: {e}")
        return

    print(f"[notifier] 自動通知を開始します(通知先: #{getattr(channel, 'name', CHANNEL_ID)})")

    # 起動直後は「今のストア」をいきなり通知せず、次の更新タイミングまで待つだけにする
    try:
        await asyncio.to_thread(auth.ensure_valid)
        _, remaining = await asyncio.to_thread(get_daily_skins, auth)
        await asyncio.sleep(max(remaining, 0) + REFRESH_BUFFER_SECONDS)
    except Exception as e:  # noqa: BLE001 - 起動時の失敗は下のループに委ねる
        print(f"[notifier] 初回チェックに失敗しました(下のループでリトライします): {e}")

    while not client.is_closed():
        try:
            await asyncio.to_thread(auth.ensure_valid)
            skins, remaining = await asyncio.to_thread(get_daily_skins, auth)
        except RiotClientNotRunningError as e:
            print(f"[notifier] {e} {RETRY_SECONDS_AFTER_LAUNCH}秒後にリトライします")
            await asyncio.sleep(RETRY_SECONDS_AFTER_LAUNCH)
            continue
        except Exception as e:  # noqa: BLE001 - その他の失敗もログに残してリトライ
            print(f"[notifier] ストア取得に失敗しました。{RETRY_SECONDS}秒後にリトライします: {e}")
            await asyncio.sleep(RETRY_SECONDS)
            continue

        await channel.send(embeds=build_store_embeds(skins, remaining))
        await asyncio.sleep(max(remaining, 0) + REFRESH_BUFFER_SECONDS)


@client.event
async def on_ready():
    global _notifier_started
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    print(f"Logged in as {client.user} (guild sync: {GUILD_ID or 'global'})")

    if CHANNEL_ID and not _notifier_started:
        _notifier_started = True
        client.loop.create_task(store_notifier_loop())


async def _ensure_riot_ready(interaction: discord.Interaction) -> bool:
    """Riot Clientのセッションを確立する。未起動なら自動起動し、ログイン完了まで待つ。

    成功すれば True を返す。諦めた場合は followup でユーザーに通知したうえで False を返す。
    """
    try:
        await asyncio.to_thread(auth.ensure_valid)
        return True
    except RiotClientNotRunningError:
        pass
    except RiotAuthError as e:
        await interaction.followup.send(f"ログインに失敗しました: {e}")
        return False

    await interaction.followup.send(
        "Riot Clientが起動していなかったため自動的に起動しました。ログイン完了を待っています…"
    )
    loop = asyncio.get_event_loop()
    deadline = loop.time() + STORE_COMMAND_LAUNCH_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(STORE_COMMAND_POLL_INTERVAL)
        try:
            await asyncio.to_thread(auth.ensure_valid)
            return True
        except RiotAuthError:
            continue

    await interaction.followup.send(
        "Riot Clientの起動待ちがタイムアウトしました。手動でログインしてから、もう一度 /store を実行してください。"
    )
    return False


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
    client.run(DISCORD_TOKEN)
