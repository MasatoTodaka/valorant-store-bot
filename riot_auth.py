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

import asyncio
import base64
import json
import platform
import re
import subprocess
import time
from pathlib import Path

import requests
import urllib3
from curl_cffi import requests as cffi_requests

# Riot Clientのローカルサーバーは自己署名証明書を使うため証明書検証を無効化する。
# (127.0.0.1宛のみ・Riot Client自身が発行した証明書であることを理解した上での無効化)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ENTITLEMENTS_LOCAL_PATH = "/entitlements/v1/token"

# ストアAPI(pd.<shard>.a.pvp.net)として実際に存在が確認できているshard。
# Riot側でdat.c(推定シャード名)の命名規則が変わり、DNSすら引けない値になることが
# あるため、既知のshardをフォールバック候補として順に試す。
KNOWN_SHARDS = ("ap", "na", "eu", "kr", "latam", "br")

# Riot Client自動起動を試みてから、再度自動起動を試みるまでの最短間隔(秒)。
# ログイン完了まで数十秒かかることがあるため、その間に何度も起動し直さないようにする。
RIOT_CLIENT_LAUNCH_COOLDOWN = 60

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


class RiotClientNotRunningError(RiotAuthError):
    """Riot Clientが起動しておらず、自動起動を試みたことを示す。呼び出し側は
    しばらく待って ensure_valid() をリトライすることを期待されている。"""


def _riot_client_executable() -> Path | None:
    """インストール済みのRiot Client実行ファイルのパスを取得する(Windowsのみ)。"""
    import os

    installs_path = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Riot Games/RiotClientInstalls.json"
    if not installs_path.exists():
        return None
    try:
        data = json.loads(installs_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    exe = data.get("rc_live") or data.get("rc_default")
    return Path(exe) if exe else None


def launch_riot_client() -> bool:
    """Riot Clientの起動を試みる。起動コマンドを実行できたら True を返す
    (ログイン完了や起動完了までは待たない)。"""
    system = platform.system()
    if system == "Windows":
        exe = _riot_client_executable()
        if exe is None or not exe.exists():
            return False
        subprocess.Popen([str(exe)])
        return True
    if system == "Darwin":
        subprocess.Popen(["open", "-a", "Riot Client"])
        return True
    return False


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
        self._last_launch_attempt = 0.0
        self._verified_region = None

    def _try_auto_launch(self) -> bool:
        """クールダウンを考慮してRiot Clientの自動起動を試みる。

        直近で起動を試みたばかりの場合は再度起動コマンドは実行せず、
        「起動処理は進行中」として True を返す(呼び出し側はリトライ待ちをする)。
        """
        now = time.monotonic()
        if now - self._last_launch_attempt < RIOT_CLIENT_LAUNCH_COOLDOWN:
            return True
        launched = launch_riot_client()
        if launched:
            self._last_launch_attempt = now
        return launched

    def ensure_valid(self, auto_launch: bool = True):
        """Riot Clientのlockfileからローカルセッション情報を読み、トークンを取得する。

        Riot Clientはプロセスが生きている限り内部でトークンを自動更新し続けるため、
        呼び出すたびにローカルAPIから最新のものを取得し直す(キャッシュはしない)。

        Riot Clientが起動していない場合、auto_launch=True(デフォルト)であれば自動起動を
        試みたうえで RiotClientNotRunningError を送出する。呼び出し側はしばらく待って
        再度 ensure_valid() を呼び直すことを想定している。
        """
        path = _lockfile_path()
        if not path.exists():
            if auto_launch and self._try_auto_launch():
                raise RiotClientNotRunningError(
                    "Riot Clientが起動していなかったため自動的に起動しました。"
                    "ログインが完了するまでしばらくお待ちください。"
                )
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
            if auto_launch and self._try_auto_launch():
                raise RiotClientNotRunningError(
                    f"Riot Clientのローカルセッション取得に失敗したため自動的に起動しました: {e}\n"
                    "ログインが完了するまでしばらくお待ちください。"
                ) from e
            raise RiotAuthError(
                f"Riot Clientのローカルセッション取得に失敗しました: {e}\n"
                "Riot Clientが起動していてログイン済みか確認してください。"
            ) from e

        self.access_token = data["accessToken"]
        self.entitlements_token = data.get("token") or data.get("entitlements_token")
        self.puuid = data["subject"]

        # 一度確認できたshardはアカウントに紐づく値としてプロセス内でキャッシュする
        # (毎回APIを試し打ちしてshardを再検証するのは無駄なため)。
        if self._verified_region is None:
            self._verified_region = self._resolve_working_shard(self._guess_shard_hint())
        self.region = self._verified_region

    async def ensure_valid_with_retry(self, timeout: float = 90, poll_interval: float = 5, on_waiting=None) -> bool:
        """ensure_valid()をラップし、Riot Client未起動時は自動起動を待って
        timeout秒までポーリングする。/store コマンドとスリープ復帰後の
        一括通知スクリプトの両方から共通で使う。

        成功すれば True、timeout以内に確立できなければ False を返す
        (RiotAuthErrorをそのまま送出したい呼び出し元は使わないこと)。
        on_waiting: 自動起動を検知した最初の1回だけ呼ばれるコールバック(async可)。
        """
        try:
            await asyncio.to_thread(self.ensure_valid)
            return True
        except RiotClientNotRunningError:
            pass
        except RiotAuthError:
            return False

        if on_waiting is not None:
            result = on_waiting()
            if asyncio.iscoroutine(result):
                await result

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                await asyncio.to_thread(self.ensure_valid)
                return True
            except RiotAuthError:
                continue
        return False

    def _guess_shard_hint(self) -> str | None:
        """access_tokenのJWTペイロードに埋め込まれた "dat.c"(例: "ap1")からシャード名を
        推測する。末尾の数字を除いた "ap" がストアAPIのホスト名(pd.ap.a.pvp.net 等)に
        使われてきた値だが、Riot側でこの命名規則が変わりDNSも引けない値になることがあるため、
        あくまで最初に試す「ヒント」として扱い、_resolve_working_shard 側で実際に検証する。"""
        try:
            claims = _decode_jwt_payload(self.access_token)
            shard = claims["dat"]["c"]
            return re.sub(r"\d+$", "", shard).lower()
        except (KeyError, IndexError, ValueError):
            return None

    def _resolve_working_shard(self, hinted_shard: str | None) -> str:
        """ヒントのshardをまず試し、ダメなら既知のshardを順に試して、実際に
        ストアAPIが200を返すものを採用する。"""
        candidates = list(dict.fromkeys(s for s in (hinted_shard, *KNOWN_SHARDS) if s))
        last_error = "候補なし"
        for shard in candidates:
            try:
                url = f"https://pd.{shard}.a.pvp.net/store/v1/wallet/{self.puuid}"
                r = self.session.get(url, headers=self.pvp_headers(), timeout=8)
                if r.status_code == 200:
                    return shard
                last_error = f"{shard}: HTTP {r.status_code}"
            except Exception as e:  # noqa: BLE001 - 候補を順に試すため失敗は握りつぶして次へ
                last_error = f"{shard}: {e}"
        raise RiotAuthError(f"利用可能なリージョン(shard)を特定できませんでした(最後の試行: {last_error})")

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
