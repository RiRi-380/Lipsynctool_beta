# -*- coding: utf-8 -*-
"""
generate.py

lip_sync_config.jsonなどの設定ファイルをもとに、
プロジェクト内で必要なデータやフォルダ構成を自動生成するためのユーティリティモジュール。
・使用目的例: 初期テンプレートファイルの生成、サンプルデータのコピーなど
・コマンドラインスクリプトとしても利用可能
"""

import os
import json
import shutil
from typing import Any, Dict, Optional

# テンプレート例: リップシンク用サンプルデータ
DEFAULT_SAMPLE_DATA = {
    "text": "Hello world",
    "audio_file": "sample.wav",
    "config": {
        "fps": 30,
        "resolution": "1280x720"
    }
}


def load_lip_sync_config(config_path: str) -> Dict[str, Any]:
    """
    lip_sync_config.jsonを読み込んで辞書を返すヘルパー。
    
    Args:
        config_path (str): configファイルのパス
    
    Returns:
        Dict[str, Any]: 設定内容を保持した辞書
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    return config_data


def generate_sample_data(output_dir: str, sample_data: Optional[Dict[str, Any]] = None) -> None:
    """
    サンプルデータ(例: text, audio_file名など)をjsonに書き出す。
    大規模プロジェクトでのテスト・デモに用いることを想定。

    Args:
        output_dir (str): 出力先ディレクトリ
        sample_data (Dict[str, Any] or None): デフォルト以外のサンプルデータを指定可能
    """
    if sample_data is None:
        sample_data = DEFAULT_SAMPLE_DATA

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "sample_data.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)

    print(f"サンプルデータを生成しました: {output_path}")


def copy_audio_template(src_audio_file: str, dst_dir: str) -> None:
    """
    例: テンプレート音声ファイルを指定ディレクトリにコピー。
    デモやテンプレートとして配布する場合に使用。

    Args:
        src_audio_file (str): コピー元の音声ファイルパス
        dst_dir (str): コピー先ディレクトリ
    """
    if not os.path.exists(src_audio_file):
        raise FileNotFoundError(f"Template audio file not found: {src_audio_file}")

    os.makedirs(dst_dir, exist_ok=True)
    dst_file = os.path.join(dst_dir, os.path.basename(src_audio_file))
    shutil.copy2(src_audio_file, dst_file)
    print(f"音声テンプレートをコピーしました: {dst_file}")


def initialize_project_structure(config_path: str, base_dir: str) -> None:
    """
    lip_sync_config.jsonを読み込み、そこに定義された
    プロジェクト用ディレクトリや初期ファイルなどを生成する例。

    Args:
        config_path (str): lip_sync_config.jsonのパス
        base_dir (str): プロジェクトのベースディレクトリ
    """
    config_data = load_lip_sync_config(config_path)

    # 例: config_data["project_folders"] にディレクトリ一覧があるとして
    project_folders = config_data.get("project_folders", [])
    for folder in project_folders:
        full_path = os.path.join(base_dir, folder)
        os.makedirs(full_path, exist_ok=True)
        print(f"フォルダ生成: {full_path}")

    # 例: config_data["sample_files"] にコピー元-コピー先情報があるとして
    sample_files = config_data.get("sample_files", [])
    for item in sample_files:
        src = item.get("src")
        dst_folder = item.get("dst_folder")
        if src and dst_folder:
            dst_path = os.path.join(base_dir, dst_folder)
            copy_audio_template(src, dst_path)


def main():
    """
    コマンドラインから呼び出す例:
    python generate.py --config lip_sync_config.json --output some_out_dir
    など。argparse等で実装可。
    """
    # 簡易サンプル実装:
    config_path = "lip_sync_config.json"
    base_dir = "example_output"

    # lip_sync_config.jsonに基づくフォルダ等生成
    initialize_project_structure(config_path, base_dir)

    # サンプルデータを生成
    sample_dir = os.path.join(base_dir, "samples")
    generate_sample_data(sample_dir)

    # (任意) テンプレート音声ファイルもコピー
    # copy_audio_template("template.wav", sample_dir)


if __name__ == "__main__":
    main()
