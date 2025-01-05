# -*- coding: utf-8 -*-
"""
lip_sync_main.py

プロジェクトのリップシンク処理全体を実行するエントリーポイントスクリプト。
コマンドライン引数を受け取り、lip_sync_generator等の機能を呼び出して
最終的に口パク用のデータや動画生成などを実行する例。

依存:
- Python 3.7 以上推奨
- 必要に応じて librosa, numpy, etc.
- 同一プロジェクト内の pipeline / analysis モジュールをimport

想定ユース:
  python lip_sync_main.py --audio path/to/audio.wav --text "こんにちは"
  python lip_sync_main.py --config path/to/lip_sync_config.json
  python lip_sync_main.py --output result.json

例: オプション追加
  python lip_sync_main.py --audio input.wav --text "こんにちは" --gpu --rms-threshold 0.01 --output output.json
"""

import os
import sys
import argparse
import json
import traceback

def parse_arguments():
    """
    コマンドライン引数をパースし、設定オブジェクトを返す。
    """
    parser = argparse.ArgumentParser(description="Lip Sync Main Script")

    parser.add_argument("--audio", type=str, default="",
                        help="入力音声ファイルのパス (WAVなど)")
    parser.add_argument("--text", type=str, default="",
                        help="リップシンク対象のテキスト")
    parser.add_argument("--config", type=str, default="",
                        help="lip_sync_config.json などの設定ファイルパス")
    parser.add_argument("--output", type=str, default="output.json",
                        help="解析結果を保存するJSONファイルパス (例)")

    # 追加オプション例:
    parser.add_argument("--gpu", action="store_true",
                        help="GPUを使用するフラグ (configのenable_gpuを上書きする)")
    parser.add_argument("--rms-threshold", type=float, default=None,
                        help="RMS閾値 (configを上書き)")

    args = parser.parse_args()
    return args


def main():
    """
    リップシンク処理全体を管理するエントリーポイント。
    """
    args = parse_arguments()

    audio_file = args.audio
    input_text = args.text
    config_path = args.config
    output_json_path = args.output
    use_gpu_flag = args.gpu
    override_rms = args.rms_threshold

    # 1) 引数チェック
    if not audio_file or not os.path.exists(audio_file):
        print(f"[Error] 音声ファイルが指定されていないか、存在しません: {audio_file}")
        sys.exit(1)

    if not input_text:
        print("[Error] テキストが指定されていません。")
        sys.exit(1)

    # 2) 設定ファイルの読み込み or デフォルト
    config_data = {}
    if config_path:
        if not os.path.exists(config_path):
            print(f"[Error] 指定された設定ファイルが見つかりません: {config_path}")
            sys.exit(1)
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"[Warning] 設定ファイルの読み込みに失敗: {e}\n  -> デフォルト設定で進行します。")
            config_data = {}
    else:
        # configが指定されなかった場合、空dict(デフォルト)で進行
        print("[Info] 設定ファイルが指定されていないため、デフォルト設定で進行します。")

    # 3) コマンドラインオプションで一部設定を上書き
    if use_gpu_flag:
        # "processing_options" の "enable_gpu" を True に
        config_data.setdefault("processing_options", {})
        config_data["processing_options"]["enable_gpu"] = True
        print("[Info] コマンドラインオプションにより GPU使用を有効化しました。")

    if override_rms is not None:
        config_data.setdefault("processing_options", {})
        config_data["processing_options"]["rms_threshold"] = override_rms
        print(f"[Info] コマンドラインオプションにより RMS閾値を {override_rms} に上書きしました。")

    # 4) 音声ファイルをロード (librosa で読み込み)
    try:
        import numpy as np
        import librosa

        print(f"[Info] 音声ファイルを読み込み中: {audio_file}")
        audio_data, sr = librosa.load(audio_file, sr=16000, mono=True)
        audio_data = audio_data.astype(np.float32)
        print(f"[Info] 音声ロード完了: shape={audio_data.shape}, sr={sr}")
    except Exception as e:
        print(f"[Error] 音声の読み込みに失敗: {traceback.format_exc()}")
        sys.exit(1)

    # 5) LipSyncGenerator を使ってリップシンク解析
    try:
        from main.pipeline.lip_sync_generator import LipSyncGenerator

        print("[Info] LipSyncGenerator を初期化します...")
        # generator に config_data を渡すか、config_path を渡すかは実装次第
        # ここでは config_path も存在するならそちらを優先
        if config_path and os.path.exists(config_path):
            generator = LipSyncGenerator(config_path=config_path)
        else:
            # 内部で config_data を活用するなら LipSyncGenerator を改修しておく
            generator = LipSyncGenerator()

            # あるいは generator 側が受け取れるように setterを用意して
            # generator.set_config_data(config_data)
            # のようにしてもOK

        print("[Info] リップシンク解析を実行します...")
        result = generator.generate_lip_sync(
            audio_data,
            input_text,
            sample_rate=sr
        )

    except ImportError as ie:
        print(f"[Error] LipSyncGeneratorのインポートに失敗しました: {ie}\nモジュール構成を確認してください。")
        sys.exit(1)
    except Exception as e:
        print(f"[Error] リップシンク解析に失敗: {traceback.format_exc()}")
        sys.exit(1)

    # 6) 結果をJSONファイルに出力
    try:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[Info] 解析結果を {output_json_path} に出力しました。")
    except Exception as e:
        print(f"[Error] 結果出力に失敗: {traceback.format_exc()}")
        sys.exit(1)

    print("[Info] リップシンク解析が完了しました。")


if __name__ == "__main__":
    main()
