import os
import time
import json
from typing import Any, Optional

class CacheManager:
    """
    キャッシュ管理を行うクラス。
    ここではファイルベースのシンプルなキャッシュを例示。
    例えばRMS計算結果や音素解析結果などをキャッシュする場合などに利用可能。
    """

    def __init__(self, cache_dir: str = "./cache_data", default_ttl: float = 3600.0):
        """
        Args:
            cache_dir (str): キャッシュファイルを保存するディレクトリパス
            default_ttl (float): キャッシュのデフォルト有効時間(秒)
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_file_path(self, key: str) -> str:
        """
        キャッシュ用ファイルのパスを返す。
        """
        # key からファイル名を生成 (安全のため一部置換 or ハッシュ化しても良い)
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        キャッシュを保存する。
        Args:
            key (str): キャッシュキー
            value (Any): キャッシュしたいデータ
            ttl (float, optional): 有効期限(秒)。未指定の場合 default_ttl を使用。
        """
        if ttl is None:
            ttl = self.default_ttl

        # 有効期限のタイムスタンプ(エポック秒)
        expire_time = time.time() + ttl

        data_to_store = {
            "value": value,
            "expire": expire_time
        }

        cache_file = self._get_cache_file_path(key)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data_to_store, f, ensure_ascii=False)
        except Exception as e:
            print(f"[CacheManager] キャッシュの保存に失敗: key={key}, error={e}")

    def get(self, key: str) -> Optional[Any]:
        """
        キャッシュを取得する。期限切れの場合は None を返す。
        Args:
            key (str): キャッシュキー
        Returns:
            Any or None: キャッシュ値。期限切れ、ファイル未存在等なら None。
        """
        cache_file = self._get_cache_file_path(key)
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[CacheManager] キャッシュファイルの読込に失敗: key={key}, error={e}")
            return None

        expire_time = data.get("expire", 0)
        if time.time() > expire_time:
            # 期限切れ => キャッシュファイル削除
            self.delete(key)
            return None

        return data.get("value")

    def delete(self, key: str) -> None:
        """
        キャッシュを削除する。
        Args:
            key (str): キャッシュキー
        """
        cache_file = self._get_cache_file_path(key)
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except OSError as e:
                print(f"[CacheManager] キャッシュファイル削除失敗: key={key}, error={e}")

    def clear_all(self) -> None:
        """
        キャッシュディレクトリ内の全キャッシュファイルを削除する。
        """
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.cache_dir, filename)
                    os.remove(file_path)
        except Exception as e:
            print(f"[CacheManager] キャッシュの全削除に失敗: error={e}")


# 使用例:
# if __name__ == "__main__":
#     cm = CacheManager(cache_dir="./cache_data", default_ttl=600.0)
#     cm.set("test_key", {"foo": 123}, ttl=120.0)
#     val = cm.get("test_key")
#     print("Cached value:", val)
#     time.sleep(2)
#     val2 = cm.get("test_key")
#     print("Cached value after 2 seconds:", val2)
#     cm.delete("test_key")
#     cm.clear_all()
