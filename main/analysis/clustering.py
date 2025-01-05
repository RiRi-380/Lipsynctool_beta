"""
clustering.py

音声解析や音素解析の結果をクラスタリングするモジュール。
KMeansなどのクラスタリングアルゴリズムを使って、
音素や音声区間を類似度に基づいてグルーピングします。

Usage:
    # 例: フォン特徴量を用いたクラスタリング
    from analysis.clustering import PhonemeClustering

    clustering = PhonemeClustering(num_clusters=5)
    cluster_labels = clustering.fit_predict(phoneme_features)
    # cluster_labelsに各音素のクラスタ番号が割り当てられる

Note:
    - scikit-learnがインストールされている必要があります。
    - GPU加速が必要であればcuMLなど別ライブラリの検討も可能です。

"""

import os
import json
import logging
from typing import List, Optional

import numpy as np
from sklearn.cluster import KMeans

# 将来的にGPU対応 (cuMLなど) をする場合のimport例 (コメントアウト)
# try:
#     import cuml
#     from cuml.cluster import KMeans as cuKMeans
#     GPU_AVAILABLE = True
# except ImportError:
#     GPU_AVAILABLE = False


class PhonemeClustering:
    """
    音素や音声区間の特徴量ベクトルをクラスタリングするクラス。

    Attributes:
        num_clusters (int): クラスタ数
        random_state (int): 乱数シード
        model (KMeans): sklearnのKMeansモデルインスタンス
    """

    def __init__(self, 
                 num_clusters: int = 5, 
                 random_state: int = 42) -> None:
        """
        コンストラクタ。

        Args:
            num_clusters (int, optional): クラスタ数。 Defaults to 5.
            random_state (int, optional): 乱数シード。 Defaults to 42.
        """
        self.num_clusters = num_clusters
        self.random_state = random_state
        self.model: Optional[KMeans] = None

        # ロガー設定（必要に応じて好みで設定）
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            self.logger.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "[%(levelname)s] %(asctime)s - %(name)s : %(message)s")
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        self.logger.debug("PhonemeClustering initialized with "
                          f"num_clusters={num_clusters}, random_state={random_state}")

    def fit_predict(self, feature_vectors: np.ndarray) -> np.ndarray:
        """
        特徴量ベクトルに対してクラスタリングを実行し、各ベクトルのクラスタ番号を返す。

        Args:
            feature_vectors (np.ndarray): (サンプル数, 特徴次元) の形状を想定した行列

        Returns:
            np.ndarray: shape=(サンプル数,) 各サンプルのクラスタ番号が入った配列
        """
        self.logger.debug(f"Fitting KMeans with shape={feature_vectors.shape}")
        if self.model is None:
            # KMeansインスタンスを作成
            self.model = KMeans(
                n_clusters=self.num_clusters,
                random_state=self.random_state,
                init="k-means++",
                n_init="auto",  # sklearn>=1.2.0 なら n_init="auto" が推奨
            )
        self.model.fit(feature_vectors)
        labels = self.model.labels_
        self.logger.debug(f"Clustering done. Unique labels={set(labels)}")
        return labels

    def predict(self, feature_vector: np.ndarray) -> int:
        """
        学習済みモデルに対して、新たな1サンプルベクトルをクラスタ判定する。

        Args:
            feature_vector (np.ndarray): shape=(特徴次元,)

        Returns:
            int: 予測されたクラスタ番号
        """
        if self.model is None:
            raise RuntimeError("Model is not fitted yet. Call fit_predict() first.")

        # 2次元に形状変換してpredict
        label = self.model.predict(feature_vector.reshape(1, -1))[0]
        return label


def load_cluster_config(config_path: str = "lip_sync_config.json") -> dict:
    """
    lip_sync_config.json等からクラスタリング設定を読み込み、
    必要に応じてパラメータを返すヘルパー関数。

    Args:
        config_path (str, optional): コンフィグファイルのパス。 Defaults to "lip_sync_config.json".

    Returns:
        dict: クラスタリング設定などの辞書
    """
    if not os.path.exists(config_path):
        logging.warning(f"Config file not found: {config_path}. Using defaults.")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    clustering_cfg = data.get("clustering", {})
    logging.debug(f"Loaded clustering config: {clustering_cfg}")
    return clustering_cfg


# 例: このファイルを直接実行した場合のテストコード的役割
if __name__ == "__main__":
    # ダミーの特徴量を生成 (e.g., 10サンプル, 次元5)
    dummy_features = np.random.rand(10, 5).astype(np.float32)

    cluster_cfg = load_cluster_config("lip_sync_config.json")
    # configから必要であればクラスタ数などを上書き
    num_clusters = cluster_cfg.get("num_clusters", 5)

    clustering = PhonemeClustering(num_clusters=num_clusters, random_state=0)
    labels = clustering.fit_predict(dummy_features)
    print("Cluster labels:", labels)

    # 1サンプル予測
    test_vec = np.random.rand(5).astype(np.float32)
    predicted_label = clustering.predict(test_vec)
    print("Predicted label for new sample:", predicted_label)
