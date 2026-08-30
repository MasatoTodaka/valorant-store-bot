"""365日稼働させ続けても際限なく肥大化しないよう、5MB x 5世代でローテーションする
ログ設定。bot.py(対話コマンド)とnotify_once.py(定期通知)で共有する。"""

import logging
import logging.handlers
import os


def setup_logging(name: str, filename: str) -> tuple[logging.Logger, logging.Handler]:
    os.makedirs("logs", exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=filename, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", style="{"))

    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # riot_auth.py のログも同じファイルに残す。discord.py 自身のロガーは
    # client.run(log_handler=...) 側で個別に処理されるため、ここでは触れない
    # (rootに付けると、discordのログがそちらとの二重付けで重複出力されてしまう)。
    riot_auth_logger = logging.getLogger("riot_auth")
    riot_auth_logger.addHandler(handler)
    riot_auth_logger.setLevel(logging.INFO)

    return logger, handler
