# PROJECT_ROOT/main/utils/logger_setup.py
# -*- coding: utf-8 -*-

"""
logger_setup.py

プロジェクト全体で使用するログのセットアップを行うためのユーティリティモジュール。

- Python 標準の logging モジュールを用いて、コンソール出力とファイル出力を同時に行う。
- lip_sync_config.json の "logging" セクションを読み込み、
  - enable_file_logging: True/False でファイル出力の有無を切り替え
  - log_file_path: ファイル出力先のパス
  - log_level: ログレベル (DEBUG, INFO, WARNING, ERROR, CRITICAL)
 などの設定を行う想定。
- ログローテーション（logging.handlers.RotatingFileHandler等）が必要であれば実装を加える。

使い方:
    from main.utils.logger_setup import setup_logger
    logger = setup_logger(config_dict)

    logger.info("This is an info message")
    logger.error("Some error occurred")
"""

import os
import logging
from logging import handlers

def setup_logger(config_dict: dict = None) -> logging.Logger:
    """
    ロガーをセットアップして返す。
    config_dict["logging"] 内の以下のキーを参照:
        - enable_file_logging: bool  (ファイル出力するかどうか)
        - log_file_path: str       (ファイル出力先)
        - log_level: str           (DEBUG / INFO / WARNING / ERROR / CRITICAL)
        - max_bytes: int           (オプション: ファイルローテーションで使用)
        - backup_count: int        (オプション: ローテーション世代数)

    Args:
        config_dict (dict): lip_sync_config.json などから読み込んだ設定辞書。
                            未指定ならデフォルト設定を使う。

    Returns:
        logging.Logger: セットアップ済みのロガーインスタンス。
    """

    # デフォルトの設定
    default_logging_conf = {
        "enable_file_logging": True,
        "log_file_path": "./logs/lipsync_tool.log",
        "log_level": "INFO",
        "max_bytes": 1_000_000,      # 1MB (RotatingFileHandler用)
        "backup_count": 3,          # ローテーション世代数
    }

    # config_dict がなければ空辞書を使う
    if config_dict is None:
        config_dict = {}

    logging_conf = config_dict.get("logging", {})
    # デフォルトとマージ
    merged_conf = {**default_logging_conf, **logging_conf}

    enable_file_logging = merged_conf.get("enable_file_logging", True)
    log_file_path = merged_conf.get("log_file_path", "./logs/lipsync_tool.log")
    log_level_str = merged_conf.get("log_level", "INFO")
    max_bytes = merged_conf.get("max_bytes", 1_000_000)
    backup_count = merged_conf.get("backup_count", 3)

    # ログレベルを文字列から logging.LEVEL に変換
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # 既定のロガー名を "lipsync_logger" とする例
    logger = logging.getLogger("lipsync_logger")
    logger.setLevel(log_level)
    logger.propagate = False  # 他のロガーに伝播させない

    # もし既にハンドラが付与されている場合は一度クリア
    if logger.hasHandlers():
        logger.handlers.clear()

    # フォーマット設定
    log_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    )

    # 1) コンソール出力ハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 2) ファイル出力ハンドラ (オプション)
    if enable_file_logging:
        # ディレクトリ作成
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        # ローテーション可能なハンドラ
        file_handler = handlers.RotatingFileHandler(
            filename=log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)

    logger.debug("Logger setup completed.")
    return logger


def demo():
    """簡易デモ: 設定無しでセットアップ → デフォルトで ./logs/lipsync_tool.log に出力"""
    logger = setup_logger({})
    logger.info("This is an info log in the demo.")
    logger.warning("This is a warning in the demo.")
    logger.error("This is an error in the demo.")


if __name__ == "__main__":
    demo()
