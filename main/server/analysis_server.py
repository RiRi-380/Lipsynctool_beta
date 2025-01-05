# -*- coding: utf-8 -*-
"""
analysis_server.py

gRPCサーバを起動し、analysis.proto に定義された
AnalysisService のRPCメソッド (AnalyzeAudio) を提供します。

依存:
- grpc (pip install grpcio)
- analysis.proto のコンパイルによって生成された analysis_pb2 / analysis_pb2_grpc
- Python 3.7 以上推奨

使用例:
    python analysis_server.py
    # → "localhost:50051" で gRPC サーバが起動
"""

import time
import numpy as np
import grpc
from concurrent import futures

# analysis.proto をコンパイルして生成されたモジュールを絶対インポート
# 例: python -m grpc_tools.protoc --python_out=. --grpc_python_out=. -I. analysis.proto
from main.server import analysis_pb2
from main.server import analysis_pb2_grpc


class AnalysisServiceServicer(analysis_pb2_grpc.AnalysisServiceServicer):
    """
    AnalysisServiceServicer は、analysis.proto に定義された
    AnalysisService の RPC メソッドを実装するためのクラス。
    """

    def AnalyzeAudio(self, request, context):
        """
        AnalyzeAudio RPC:
         - request : AnalyzeRequest
         - returns : AnalyzeResponse

        音声データを受け取り、RMS 等の解析や音素解析などを行う。
        このサンプルではダミー実装（簡易的な RMS 計算 & テキスト→音素の一例）を行う。
        """

        # リクエストから取得
        audio_bytes = request.audio_data
        text_input = request.text
        character_name = request.character
        use_gpu = request.use_gpu

        # GPUフラグなどは用途に応じて処理を分岐
        if use_gpu:
            print("[AnalysisServer] GPUを使用した解析を実行します。")
        else:
            print("[AnalysisServer] CPUを使用した解析を実行します。")

        # ====== ダミーのRMS計算例 ======
        try:
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            if audio_array.size == 0:
                rms_value = 0.0
            else:
                rms_value = float(np.sqrt(np.mean(audio_array ** 2)))
        except Exception as e:
            print(f"[AnalysisServer] 音声処理中に例外が発生: {e}")
            rms_value = 0.0

        # ====== ダミーの音素解析例 ======
        phoneme_list = []
        if text_input:
            # サンプルとして、テキスト全体を surface にし、phoneme をダミー文字列で返却
            phoneme_list.append(
                analysis_pb2.Phoneme(
                    surface=text_input,
                    phoneme="dummy_phoneme"  # 実際には more detailed な音素列を生成
                )
            )

        # 結果をレスポンスメッセージに詰める
        response = analysis_pb2.AnalyzeResponse(
            rms_value=rms_value,
            phonemes=phoneme_list
        )
        return response


def serve(host="0.0.0.0", port=50051):
    """
    gRPCサーバを起動し、AnalysisService を提供する関数。
    Args:
        host (str): バインドするホストアドレス (デフォルト: 0.0.0.0)
        port (int): バインドするポート番号 (デフォルト: 50051)
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    analysis_pb2_grpc.add_AnalysisServiceServicer_to_server(
        AnalysisServiceServicer(),
        server
    )

    server.add_insecure_port(f"{host}:{port}")
    server.start()
    print(f"[AnalysisServer] gRPCサーバを起動しました: {host}:{port}")

    try:
        while True:
            time.sleep(60 * 60 * 24)  # サーバ継続稼働のため長時間スリープ
    except KeyboardInterrupt:
        print("[AnalysisServer] シャットダウンします...")
        server.stop(0)


if __name__ == "__main__":
    serve()
