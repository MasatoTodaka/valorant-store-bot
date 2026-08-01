"""VALORANTのストア(デイリーショップ)を取得し、スキン名・画像に解決するモジュール。

アイテムIDから表示名/画像への変換には、Riot公認のコミュニティAPIである
valorant-api.com を使用する(認証不要・無料)。
"""

import requests

from riot_auth import RiotAuth

_SKINS_CACHE: dict | None = None


def _skins_lookup() -> dict:
    """スキンレベルUUID -> スキン情報 の辞書を(初回のみ)取得してキャッシュする。"""
    global _SKINS_CACHE
    if _SKINS_CACHE is not None:
        return _SKINS_CACHE

    resp = requests.get("https://valorant-api.com/v1/weapons/skins?language=ja-JP", timeout=15)
    resp.raise_for_status()
    lookup: dict[str, dict] = {}
    for item in resp.json()["data"]:
        for level in item.get("levels", []):
            lookup[level["uuid"]] = item
    _SKINS_CACHE = lookup
    return lookup


def get_storefront(auth: RiotAuth) -> dict:
    # v2(GET)は廃止されており、現在はv3(POST、空ボディ)が正しいエンドポイント。
    url = f"https://pd.{auth.region}.a.pvp.net/store/v3/storefront/{auth.puuid}"
    resp = auth.session.post(url, json={}, headers=auth.pvp_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_daily_skins(auth: RiotAuth) -> tuple[list[dict], int]:
    """本日のデイリーショップのスキン一覧と、残り時間(秒)を返す。"""
    store = get_storefront(auth)
    panel = store["SkinsPanelLayout"]
    offer_ids = panel["SingleItemOffers"]
    remaining = panel["SingleItemOffersRemainingDurationInSeconds"]

    # 価格情報は Offers 配列側にある
    price_by_offer = {}
    for offer in store.get("SkinsPanelLayout", {}).get("SingleItemStoreOffers", []) or []:
        cost = offer.get("Cost", {})
        price_by_offer[offer["OfferID"]] = next(iter(cost.values()), None)

    lookup = _skins_lookup()
    skins = []
    for offer_id in offer_ids:
        item = lookup.get(offer_id)
        if item:
            icon = item.get("displayIcon")
            if not icon and item.get("levels"):
                icon = item["levels"][0].get("displayIcon")
            skins.append(
                {
                    "name": item["displayName"],
                    "icon": icon,
                    "price": price_by_offer.get(offer_id),
                }
            )
        else:
            skins.append({"name": f"不明なアイテム ({offer_id})", "icon": None, "price": None})
    return skins, remaining


def get_wallet(auth: RiotAuth) -> dict:
    """VP/Radianite等の所持ポイントを取得する。"""
    url = f"https://pd.{auth.region}.a.pvp.net/store/v1/wallet/{auth.puuid}"
    resp = auth.session.get(url, headers=auth.pvp_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()
