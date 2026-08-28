"""Discord Embed組み立て。bot.py(対話コマンド)とnotify_once.py(定期通知)で共有する。"""

import discord

VALORANT_RED = 0xFF4655


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
