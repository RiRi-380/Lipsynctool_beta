import os
import subprocess
import sys
from typing import Optional

"""
gpu_accel_utils.py

Nvidia GPUなどのハードウェアアクセラレーションを活用するための
ユーティリティ関数をまとめたモジュール。

例えば、PyTorch/TensorFlow など機械学習系ライブラリでGPUを使用するかどうかのチェック、
あるいは ffmpeg の nvenc / cuvid などを利用する際の環境判定を行うことを想定。
"""

def is_nvidia_gpu_available() -> bool:
    """
    システムがNvidia GPUを使用可能かどうかを簡易チェックする関数。
    - nvidia-smiが実行可能かどうかを調べる
    - 追加でCUDA_PATH等の環境変数もチェックする例

    Returns:
        bool: Trueの場合、Nvidia GPU対応環境の可能性がある
    """
    # nvidia-smiコマンドを呼び出してみる
    try:
        subprocess.run(["nvidia-smi"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 環境変数にCUDA_PATHがある場合も一応True判定の一例
    # if "CUDA_PATH" in os.environ:
    #     return True

    return False


def get_ffmpeg_hardware_decode_flags() -> list:
    """
    ffmpegコマンドでハードウェアデコード(NVDECなど)を使う際の引数例を返す。
    システムに応じてカスタマイズ可能。

    Returns:
        list: ffmpegコマンド実行時に追加する引数リスト
    """
    # 例: Nvidia GPUがある場合、CUVID系オプションを付与
    # 下記は一例で、実際には環境やffmpegのビルドオプションなどに依存。
    if is_nvidia_gpu_available():
        # 例: '-hwaccel cuvid'を使用する
        return ["-hwaccel", "cuda"]
    else:
        return []


def get_ffmpeg_hardware_encode_flags(codec: Optional[str] = "h264") -> list:
    """
    ffmpegでハードウェアエンコード(NVENCなど)を使う際の引数リストを返す。
    Args:
        codec (str or None): 使用したいコーデック。'h264'や'hevc'など。

    Returns:
        list: ffmpegコマンド実行時に追加する引数リスト
    """
    if not is_nvidia_gpu_available():
        return []

    # 例: nvenc で h264/h265 エンコードを使用
    if codec == "h264":
        return ["-c:v", "h264_nvenc"]
    elif codec == "hevc":
        return ["-c:v", "hevc_nvenc"]
    else:
        # デフォルトはh264_nvenc
        return ["-c:v", "h264_nvenc"]


def print_gpu_info_if_available() -> None:
    """
    コンソールにGPU情報を表示する例。
    """
    if is_nvidia_gpu_available():
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8"
            )
            print("Nvidia GPU が利用可能です。以下はnvidia-smi出力です:")
            print(result.stdout)
        except Exception as e:
            print(f"nvidia-smi 実行中にエラー: {e}")
    else:
        print("Nvidia GPU は利用できません。CPUのみで動作します。")


def configure_ml_framework_for_gpu(framework: str = "pytorch") -> bool:
    """
    例: PyTorchやTensorFlowなどでGPUを使うための初期化処理をまとめた関数の一例。
    Args:
        framework (str): "pytorch" または "tensorflow" を想定

    Returns:
        bool: TrueならGPU初期化成功、Falseなら失敗または非対応
    """
    if not is_nvidia_gpu_available():
        return False

    try:
        if framework.lower() == "pytorch":
            import torch  # type: ignore
            if torch.cuda.is_available():
                print(f"PyTorchでGPU使用可能: {torch.cuda.get_device_name(0)}")
                return True
            else:
                print("PyTorchでGPUは使用不可")
        elif framework.lower() == "tensorflow":
            import tensorflow as tf  # type: ignore
            gpus = tf.config.list_physical_devices('GPU')
            if len(gpus) > 0:
                print(f"TensorFlowでGPU使用可能: {gpus}")
                return True
            else:
                print("TensorFlowでGPUは使用不可")
        else:
            print("対応していないframework指定です。")
    except ImportError:
        print(f"{framework} がインストールされていません。")
    except Exception as e:
        print(f"{framework} のGPU使用初期化中にエラー: {e}")

    return False


if __name__ == "__main__":
    # 簡易動作確認
    print("GPUアクセラレーション環境チェック")
    print_gpu_info_if_available()

    # ffmpeg 用ハードウェアオプションを表示
    decode_flags = get_ffmpeg_hardware_decode_flags()
    encode_flags = get_ffmpeg_hardware_encode_flags("h264")
    print(f"ffmpegハードウェアデコードフラグ: {decode_flags}")
    print(f"ffmpegハードウェアエンコードフラグ: {encode_flags}")

    # PyTorch/TensorFlow初期化例
    configure_ml_framework_for_gpu("pytorch")
    configure_ml_framework_for_gpu("tensorflow")
