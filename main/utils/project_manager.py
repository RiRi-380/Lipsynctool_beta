# main/utils/project_manager.py
# -*- coding: utf-8 -*-

"""
project_manager.py

タイムラインプロジェクト全体を保存・読み込み・管理するためのモジュール。
- TimelineDataModel (音素ブロック一覧)
- lip_sync_config.json のロード／セーブ
- その他、プロジェクト固有のメタ情報（例: キャラクター設定、エクスポート先フォルダ 等）

[アップデート要点]
1. TimelineDataModel の PhonemeEvent に event_id プロパティを追加する想定。
   プロジェクトファイルには "events" 内で以下のように保存する:
       {
         "event_id": "<uuid or unique_str>",
         "phoneme": "a",
         "start_time": 0.0,
         "duration": 0.3
       }
   ロード時に既存IDとマージする・新規追加するなどの拡張にも対応しやすい。

2. project_meta の内容を JSONに保存し、GUI等で取り扱う。 
   例： "character": "reimu", "last_export_path": "./output"

3. JSON構造例:
       {
         "events": [
           {
             "event_id": "evt-xxx",
             "phoneme": "a",
             "start_time": 0.0,
             "duration": 0.3
           },
           ...
         ],
         "meta": {
           "character": "reimu",
           "last_export_path": "./output"
         }
       }

4. ロード・セーブ失敗時の例外ハンドリングやメッセージ出力を強化。
"""

import json
import os
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from main.ui.timeline_data_model import TimelineDataModel


class ProjectManager:
    """
    タイムラインプロジェクト全体を統括するマネージャークラス。

    - timeline_model: TimelineDataModelと紐づけ、プロジェクトファイルを
      介してイベント(PhonemeEvent)の一覧をロード/セーブする。
    - project_meta: 各種メタ情報 (character, last_export_path, etc) を管理。
    """

    def __init__(self, timeline_model: Optional["TimelineDataModel"] = None):
        """
        Args:
            timeline_model (TimelineDataModel, optional):
                管理対象のデータモデルインスタンス。
                後から set_model() で注入してもよい。
        """
        self.timeline_model = timeline_model
        self.project_meta = {}  # プロジェクト全体のメタ情報を入れる辞書

    def set_model(self, model: "TimelineDataModel"):
        """
        TimelineDataModel を後から注入する場合に使用。
        """
        self.timeline_model = model

    def load_project(self, project_file: str) -> bool:
        """
        プロジェクトファイル(JSON)を読み込み、TimelineDataModel と
        プロジェクトメタ情報を設定する。

        例: JSON構造
            {
              "events": [
                {
                  "event_id": "evt-001",
                  "phoneme": "a",
                  "start_time": 0.0,
                  "duration": 0.3
                },
                ...
              ],
              "meta": {
                "character": "reimu",
                "last_export_path": "./output"
              }
            }

        Args:
            project_file (str): 読み込むプロジェクトファイル(.json)

        Returns:
            bool: ロード成功ならTrue、失敗ならFalse
        """
        if not os.path.exists(project_file):
            print(f"[ProjectManager] Load failed: file not found: {project_file}")
            return False

        try:
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # events 部分を TimelineDataModel に反映
            if self.timeline_model:
                events_data = data.get("events", [])

                self.timeline_model.beginResetModel()
                self.timeline_model._events.clear()

                for evt_dict in events_data:
                    # PhonemeEvent に event_id を含めて復元する想定:
                    #   evt_dict = {
                    #     "event_id": <str>,
                    #     "phoneme": <str>,
                    #     "start_time": <float>,
                    #     "duration": <float>
                    #   }
                    evt = self.timeline_model.PhonemeEvent.from_dict(evt_dict)
                    self.timeline_model._events.append(evt)

                self.timeline_model.endResetModel()

            # meta 部分 (プロジェクトメタ情報)
            self.project_meta = data.get("meta", {})

            print(f"[ProjectManager] Project loaded from {project_file}")
            return True

        except Exception as e:
            print(f"[ProjectManager] Load failed with exception: {e}")
            return False

    def save_project(self, project_file: str) -> bool:
        """
        TimelineDataModel のイベント一覧 + プロジェクトメタ情報 を
        JSONファイルとして保存。

        例:
          {
            "events": [...],
            "meta": {...}
          }

        Args:
            project_file (str): 保存先ファイル(.json)

        Returns:
            bool: 成功時 True, 失敗時 False
        """
        if not self.timeline_model:
            print("[ProjectManager] Save failed: no timeline_model set.")
            return False

        # events リストを構築
        events_list = []
        for evt in self.timeline_model._events:
            dict_evt = evt.to_dict()  # { "phoneme", "start_time", "duration" ...}
            # もし event_id があるならここで dict_evt["event_id"] = evt.event_id
            # (TimelineDataModel.PhonemeEvent で持っている想定)
            events_list.append(dict_evt)

        data_to_save = {
            "events": events_list,
            "meta": self.project_meta
        }

        # ディレクトリがない場合は作成
        os.makedirs(os.path.dirname(project_file), exist_ok=True)

        try:
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            print(f"[ProjectManager] Project saved to {project_file}")
            return True

        except Exception as e:
            print(f"[ProjectManager] Save failed with exception: {e}")
            return False

    def set_meta(self, key: str, value):
        """
        プロジェクトメタ情報を設定。
        例: set_meta("character", "reimu")
        """
        self.project_meta[key] = value

    def get_meta(self, key: str, default=None):
        """
        プロジェクトメタ情報を取得。
        例: get_meta("character", "unselected")
        """
        return self.project_meta.get(key, default)


# ---------------------------------------
# 簡易デモ
# ---------------------------------------
def _demo():
    """
    簡易デモコード: TimelineDataModelを使ってプロジェクトの保存/読み込みをテスト
    """
    # TimelineDataModel 取り込み (文字列アノテーションとの依存回避を防ぐ例)
    try:
        from main.ui.timeline_data_model import TimelineDataModel
    except ImportError:
        print("[ProjectManager Demo] TimelineDataModel not available.")
        return

    # モデル生成 & イベント追加
    model = TimelineDataModel()
    model.add_event("a", 0.0, 0.3)
    model.add_event("i", 0.3, 0.2)
    # ここで本当は evt.event_id を付与しておく

    mgr = ProjectManager(model)
    mgr.set_meta("character", "reimu")
    mgr.set_meta("last_export_path", "./output")

    # 保存
    save_ok = mgr.save_project("./test_project.json")
    if save_ok:
        print("[_demo] Save project success.")

    # 別のマネージャで読み込み
    model2 = TimelineDataModel()
    mgr2 = ProjectManager(model2)
    load_ok = mgr2.load_project("./test_project.json")
    if load_ok:
        print("[_demo] Load project success.")
        print("Loaded meta:", mgr2.project_meta)
    else:
        print("[_demo] Load project failed.")

    # 確認: model2._events の内容を出力
    for idx, evt in enumerate(model2._events):
        print(f"Event {idx}: phoneme={evt.phoneme}, start={evt.start_time}, dur={evt.duration}")


if __name__ == "__main__":
    _demo()
