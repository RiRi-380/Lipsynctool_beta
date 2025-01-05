"""
distributed_tasks.py

音声解析やリップシンクの重い処理を分散して実行するためのタスクを定義。
主にCeleryなどの分散タスクキューを利用して、大規模データを効率的に処理できるようにする。

Usage:
    # 1) Celeryワーカー起動
    #    $ celery -A analysis.distributed_tasks worker --loglevel=info
    #
    # 2) タスク呼び出し例 (他のモジュールから)
    #    from analysis.distributed_tasks import analyze_audio_chunk_async
    #
    #    result_async = analyze_audio_chunk_async.delay(chunk_data, "chunk_id_x", use_gpu=True)
    #    # 後で result_async.get() 等で結果を取得

Note:
    - Celeryを使用する例。Brokerとして Redis や RabbitMQ などが必要。
    - GPU活用の場合はGPU対応コンテナやワーカー環境が必要。
    - Dask/Rayでも同様の分散実装が可能。
"""

import os
import json
import logging
from typing import List, Optional

from celery import Celery, shared_task

# もし別途GPU利用などで独自の処理が必要ならimport
# from .some_gpu_analysis import GPUAnalyzer

# 例: lip_sync_config.json からCelery設定を読み込むためのヘルパー
def load_distributed_config(config_path: str = "lip_sync_config.json") -> dict:
    """
    Celeryや分散タスク関連の設定を JSON ファイルから読み込む。

    Args:
        config_path (str): 設定ファイルパス

    Returns:
        dict: JSONで定義されるBroker設定等の辞書
    """
    if not os.path.exists(config_path):
        logging.warning(f"[distributed_tasks] Config file not found: {config_path}. Using defaults.")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    dist_cfg = data.get("distributed", {})
    logging.debug(f"[distributed_tasks] Loaded distributed config: {dist_cfg}")
    return dist_cfg


# Celeryアプリケーションの初期化: Broker/Backend設定
# 例: Redisをブローカー、RPCベースのresult backendを使うとする
dist_config = load_distributed_config("lip_sync_config.json")
BROKER_URL = dist_config.get("broker_url", "redis://localhost:6379/0")
RESULT_BACKEND = dist_config.get("result_backend", "rpc://")

celery_app = Celery(
    "lip_sync_analysis",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

# 必要に応じて追加コンフィグ
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # タスク再試行やタイムアウト設定例
    task_annotations={
        "*": {
            "max_retries": 3,           # 再試行回数
            "time_limit": 300,         # タスク実行タイムアウト (秒)
            "soft_time_limit": 250,    # ソフトタイムアウト
        }
    },
)


@shared_task(bind=True)
def analyze_audio_chunk_async(self, audio_chunk_data: bytes, chunk_id: str, use_gpu: bool = False) -> dict:
    """
    音声チャンクの解析処理を分散タスクとして実行。
    大量のチャンクを並列処理することでスループットを向上させる。

    Args:
        audio_chunk_data (bytes): 音声チャンクのバイナリデータ
        chunk_id (str): チャンクIDやファイル名など
        use_gpu (bool, optional): GPU使用フラグ

    Returns:
        dict: 解析結果をまとめた辞書 
              例: {"chunk_id":..., "rms":..., "phoneme_list":...} 
    """
    logger = analyze_audio_chunk_async.get_logger()
    logger.info(f"Start analyzing chunk_id={chunk_id}, use_gpu={use_gpu}")

    # ここで実際の音声解析処理を行う (ダミー処理例)
    # GPU利用時は別のライブラリを呼ぶ等の実装が考えられる
    try:
        # ダミー: RMSをランダムに計算する (本来はrms_fast等呼び出し)
        import numpy as np
        audio_array = np.frombuffer(audio_chunk_data, dtype=np.float32)
        # 単純に二乗和→平均→sqrt
        rms_val = float(np.sqrt(np.mean(audio_array ** 2)))
        # ダミーの音素配列
        phonemes = ["a", "i", "u", "e", "o"]  # 実際は外部APIやモデルで推論

        # TODO: use_gpu=Trueの場合、GPUアクセラレート処理を呼ぶ
        # if use_gpu:
        #     GPUAnalyzer().analyze(audio_array)

        result = {
            "chunk_id": chunk_id,
            "rms": rms_val,
            "phoneme_list": phonemes,
        }
        logger.info(f"Analysis done: chunk_id={chunk_id}, rms={rms_val}")
        return result

    except Exception as e:
        logger.error(f"Error in analyze_audio_chunk_async: {e}", exc_info=True)
        # Celeryのretry例
        raise self.retry(exc=e, countdown=10)


@shared_task
def example_combine_results(task_results: List[dict]) -> dict:
    """
    解析タスクの結果を集約するタスクの例。
    分散完了後に各ワーカーから返った結果をまとめ、追加処理を行う想定。

    Args:
        task_results (list of dict): 各チャンク解析結果のリスト

    Returns:
        dict: 全体レポートなど
    """
    logger = example_combine_results.get_logger()
    logger.info(f"Combining {len(task_results)} results...")

    try:
        # 例えば、全チャンクの平均RMSを計算したり、phoneme頻度を集計したり
        import numpy as np

        all_rms = []
        phoneme_counts = {}

        for res in task_results:
            rms = res.get("rms", 0.0)
            if rms:
                all_rms.append(rms)
            phonemes = res.get("phoneme_list", [])
            for p in phonemes:
                phoneme_counts[p] = phoneme_counts.get(p, 0) + 1

        overall_rms = float(np.mean(all_rms)) if all_rms else 0.0
        sorted_phonemes = sorted(phoneme_counts.items(), key=lambda x: -x[1])

        report = {
            "overall_rms": overall_rms,
            "phoneme_distribution": sorted_phonemes,
            "total_chunks": len(task_results),
        }
        logger.info(f"Combine done. overall_rms={overall_rms}, top_phonemes={sorted_phonemes[:3]}")
        return report

    except Exception as e:
        logger.error(f"Error in example_combine_results: {e}", exc_info=True)
        raise


# (Optional) このモジュールを直接実行した場合の動作例
if __name__ == "__main__":
    print("Celery distributed tasks module. Run a Celery worker to process tasks.")
    # python -m analysis.distributed_tasks で実行したときにメッセージを表示するだけ
