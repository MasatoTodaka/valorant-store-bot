"""Riot Client(公式ランチャー)のローカルAPIから認証トークンを取得するモジュール。

VALORANTには公式のストア確認APIは存在しない。このツールはRiot Client(ログイン専用の
ランチャー。VALORANT本体の起動は不要)がバックグラウンドで起動してログイン済みの場合、
127.0.0.1宛のローカルAPI経由で正規の認証トークンをそのまま読み取る。

これは実際にRiot Client(公式アプリ)自身が発行したトークンを読むだけなので、
パスワード直接送信やブラウザ自動化で直面したボット検知(hCaptcha/TLSフィンガープリント)を
一切経由しない、最も確実な方式。

前提条件:
    Riot Client(ランチャーのみ。VALORANT本体は不要)がバックグラウンドで起動していて、
    ログイン済みであること。
"""

import base64
import json
import platform
import re
from pathlib import Path

import requests
import urllib3
from curl_cffi import requests as cffi_requests

# Riot Clientのローカルサーバーは自己署名証明書を使うため証明書検証を無効化する。
# (127.0.0.1宛のみ・Riot Client自身が発行した証明書であることを理解した上での無効化)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ENTITLEMENTS_LOCAL_PATH = "/entitlements/v1/token"

CLIENT_PLATFORM = base64.b64encode(
    json.dumps(
        {
            "platformType": "PC",
            "platformOS": "Windows",
            "platformOSVersion": "10.0.19042.1.256.64bit",
            "platformChipset": "Unknown",
        }
    ).encode()
).decode()


class RiotAuthError(Exception):
    pass


def _decode_jwt_payload(token: str) -> dict:
    """JWTのペイロード部分だけをデコードする(署名検証はしない。ローカルAPIが返した
    自分自身のトークンからクレームを読み取るだけなので検証は不要)。"""
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _lockfile_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Riot Games/Riot Client/Config/lockfile"
    if system == "Windows":
        import os

        return Path(os.environ["LOCALAPPDATA"]) / "Riot Games/Riot Client/Config/lockfile"
    raise RiotAuthError(f"未対応のOSです: {system}")


class RiotAuth:
    def __init__(self):
        # ストアAPI(pd.*.a.pvp.net)呼び出し用。curl_cffiでブラウザのTLS指紋を模倣する。
        self.session = cffi_requests.Session(impersonate="chrome124")
        self.access_token = None
        self.entitlements_token = None
        self.puuid = None
        self.region = None
        self.client_version = None

    def ensure_valid(self):
        """Riot Clientのlockfileからローカルセッション情報を読み、トークンを取得する。

        Riot Clientはプロセスが生きている限り内部でトークンを自動更新し続けるため、
        呼び出すたびにローカルAPIから最新のものを取得し直す(キャッシュはしない)。
        """
        path = _lockfile_path()
        if not path.exists():
            raise RiotAuthError(
                "Riot Clientのlockfileが見つかりません。"
                "Riot Client(ランチャー。VALORANT本体の起動は不要)を起動してログインしてください。"
            )

        try:
            _name, _pid, port, password, protocol = path.read_text().strip().split(":")
        except ValueError as e:
            raise RiotAuthError(f"lockfileの形式が想定と異なります: {e}") from e

        base_url = f"{protocol}://127.0.0.1:{port}"
        auth_header = "Basic " + base64.b64encode(f"riot:{password}".encode()).decode()
        local_headers = {"Authorization": auth_header}

        try:
            r = requests.get(
                f"{base_url}{ENTITLEMENTS_LOCAL_PATH}", headers=local_headers, verify=False, timeout=5
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise RiotAuthError(
                f"Riot Clientのローカルセッション取得に失敗しました: {e}\n"
                "Riot Clientが起動していてログイン済みか確認してください。"
            ) from e

        self.access_token = data["accessToken"]
        self.entitlements_token = data.get("token") or data.get("entitlements_token")
        self.puuid = data["subject"]

        # access_tokenのJWTペイロードに埋め込まれた "dat.c"(例: "ap1")が実際の
        # VALORANTシャード名。末尾の数字を除いた "ap" がストアAPIのホスト名
        # (pd.ap.a.pvp.net 等)に使う値。riotclient/region-localeが返す値は
        # 国/言語ロケール(例: "JP")であり、シャード名とは別物なので使えない。
        try:
            claims = _decode_jwt_payload(self.access_token)
            shard = claims["dat"]["c"]
            self.region = re.sub(r"\d+$", "", shard).lower()
        except (KeyError, IndexError, ValueError) as e:
            raise RiotAuthError(f"access_tokenからリージョンを取得できませんでした: {e}") from e

    def pvp_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Riot-Entitlements-JWT": self.entitlements_token,
            "X-Riot-ClientPlatform": CLIENT_PLATFORM,
            "X-Riot-ClientVersion": self.get_client_version(),
        }

    def get_client_version(self):
        if self.client_version:
            return self.client_version
        r = requests.get("https://valorant-api.com/v1/version", timeout=10)
        r.raise_for_status()
        self.client_version = r.json()["data"]["riotClientVersion"]
        return self.client_version
