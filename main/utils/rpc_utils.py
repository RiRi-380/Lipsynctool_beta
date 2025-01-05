# -*- coding: utf-8 -*-
"""
rpc_utils.py

gRPC 通信を扱うためのユーティリティ関数群。
- gRPC チャンネルの作成
- AnalysisServiceStub の生成
- 音声解析 RPC 呼び出し (RMS 計算や音素解析)

本ファイルはライブラリ的に扱えるように設計されており、
他のモジュールから容易に gRPC を使った音声解析を呼び出すことができます。

依存:
- grpc (pip install grpcio)
- analysis.proto をコンパイルして生成された analysis_pb2 / analysis_pb2_grpc
- Python 3.7 以上推奨

使い方(例):
    from main.utils.rpc_utils import try_connect_and_analyze

    audio_data = some_float32_pcm_bytes
    rms_value, phonemes = try_connect_and_analyze(
        host="localhost",
        port=50051,
        audio_data=audio_data,
        text="こんにちは",
        character="Miku",
        use_gpu=False
    )
"""

import grpc
from typing import Tuple, Optional

# analysis.proto から自動生成された Python モジュール (同一プロジェクト内 server フォルダ想定)
# 例: python -m grpc_tools.protoc --python_out=. --grpc_python_out=. -I. analysis.proto
from main.server import analysis_pb2
from main.server import analysis_pb2_grpc


def create_channel(host: str = "localhost", port: int = 50051) -> grpc.Channel:
    """
    gRPC チャンネルを作成するヘルパー関数。

    Args:
        host (str): サーバホスト名またはIPアドレス
        port (int): サーバポート番号

    Returns:
        grpc.Channel: 作成された gRPC チャンネル
    """
    target = f"{host}:{port}"
    channel = grpc.insecure_channel(target)
    return channel


def get_analysis_stub(channel: grpc.Channel) -> analysis_pb2_grpc.AnalysisServiceStub:
    """
    AnalysisServiceStub を生成して返すヘルパー関数。

    Args:
        channel (grpc.Channel): 作成済みの gRPC チャンネル

    Returns:
        AnalysisServiceStub: AnalysisService 用のスタブ
    """
    return analysis_pb2_grpc.AnalysisServiceStub(channel)


def analyze_audio(
    stub: analysis_pb2_grpc.AnalysisServiceStub,
    audio_data: bytes,
    text: Optional[str] = None,
    character: Optional[str] = None,
    use_gpu: bool = False,
    timeout_sec: float = 30.0
) -> Tuple[float, list]:
    """
    音声解析 RPC を呼び出し、RMS 値と音素リストを取得する関数。

    Args:
        stub (AnalysisServiceStub): AnalysisServiceStub インスタンス
        audio_data (bytes): 音声データ（例: PCM float32 など）
        text (str, optional): テキスト（音素解析用）。指定しない場合は音素解析を行わない
        character (str, optional): キャラクター名
        use_gpu (bool): GPU 使用フラグ
        timeout_sec (float): RPC 呼び出しのタイムアウト (秒)

    Returns:
        Tuple[float, list]:
            - float: RMS 値
            - list: phoneme のリスト（例: [{"surface":..., "phoneme":...}, ...]）
    """
    # gRPC 送信用リクエストを生成
    request = analysis_pb2.AnalyzeRequest(
        audio_data=audio_data,
        text=text if text else "",
        character=character if character else "",
        use_gpu=use_gpu
    )

    try:
        response = stub.AnalyzeAudio(request, timeout=timeout_sec)
    except grpc.RpcError as e:
        print(f"[analyze_audio] RPCエラー: {e.code()} - {e.details()}")
        return 0.0, []

    # レスポンスより RMS 値と音素リストを抽出
    rms_value = response.rms_value
    phonemes = [{"surface": p.surface, "phoneme": p.phoneme} for p in response.phonemes]

    return rms_value, phonemes


def try_connect_and_analyze(
    host: str = "localhost",
    port: int = 50051,
    audio_data: bytes = b"",
    text: Optional[str] = None,
    character: Optional[str] = None,
    use_gpu: bool = False
) -> Tuple[float, list]:
    """
    チャンネル・スタブ作成から RPC 呼び出しまでを一括で行う
    サンプル便利関数。

    Args:
        host (str): gRPC サーバホスト
        port (int): gRPC サーバポート
        audio_data (bytes): 音声データ
        text (str, optional): 音素解析用テキスト
        character (str, optional): キャラクター名
        use_gpu (bool): GPU 使用フラグ

    Returns:
        Tuple[float, list]: 
            - float: RMS 値
            - list: phoneme のリスト
    """
    channel = create_channel(host, port)
    stub = get_analysis_stub(channel)

    return analyze_audio(
        stub=stub,
        audio_data=audio_data,
        text=text,
        character=character,
        use_gpu=use_gpu
    )


if __name__ == "__main__":
    # デモ用
    print("[rpc_utils] Demo: gRPC 呼び出しテストを行います。")
    dummy_audio_data = b"\x00\x00\x00\x00" * 1600  # 6400 バイト程度のダミーデータ

    test_rms, test_phonemes = try_connect_and_analyze(
        host="localhost",
        port=50051,
        audio_data=dummy_audio_data,
        text="テスト用の音声です。",
        character="TestCharacter",
        use_gpu=True
    )

    print(f"[rpc_utils] 取得RMS値: {test_rms}")
    print(f"[rpc_utils] 取得Phonemes: {test_phonemes}")
