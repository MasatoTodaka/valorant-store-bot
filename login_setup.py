"""Riot Clientのローカルセッションが正しく読み取れるか確認するスクリプト。

事前に Riot Client(ランチャー。VALORANT本体の起動は不要)を起動し、
ログインしておくこと。

使い方:
    python login_setup.py
"""

from riot_auth import RiotAuth, RiotAuthError


def main():
    auth = RiotAuth()
    try:
        auth.ensure_valid()
    except RiotAuthError as e:
        print(f"接続に失敗しました: {e}")
        return

    print("Riot Clientのセッションを取得しました")
    print(f"  PUUID  : {auth.puuid}")
    print(f"  region : {auth.region}")
    print("これでBot(bot.py)を起動すればストアを取得できます。")
    print("Botを使い続ける間は、Riot Clientをバックグラウンドで起動したままにしてください。")


if __name__ == "__main__":
    main()
