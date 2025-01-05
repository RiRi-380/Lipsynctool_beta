# main/ui/timeline_data_model.py
# -*- coding: utf-8 -*-

"""
timeline_data_model.py

タイムライン上で扱う音素イベント（phoneme, start_time, durationなど）を
一元的に保持・管理するデータモデルクラス。

[変更点]
1. End列を追加して、 start_time + duration の結果を表示できるようにした
   (ユーザ側からは読み取り専用で編集不可)
2. setData / data 内で End 列を制御し、編集不能にする例を実装
3. JSON保存・読み込み時には end_time は保存しない (動的に計算されるため)
4. 既存の columns: [Phoneme, Start, Duration] に "End" を加え、4列モデル化
5. Undo/Redoのため、PhonemeEvent にイベントID (event_id) を追加（BlockItemと対になる）

[特徴]
    - QAbstractTableModel を継承し、GUI要素（QTableView など）にバインド可能
    - 音素イベントをリスト構造で保持し、追加・削除・編集を行う
    - JSONファイルへの保存・読み込みを行える
    - End列は読み取り専用：StartとDurationから自動計算
    - イベントID (event_id) によって Scene上のブロックと DataModel 上の行を関連付けできる

[想定用途]
    - timeline_editor.py と組み合わせて、音素ブロックのリストを表示・編集
    - QGraphicsScene (TimelineGraphicsView) との相互更新時に役立つ

[依存ライブラリ]
    pip install PyQt5
"""

import json
import os
import uuid
from typing import List, Optional
from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QVariant
)


class PhonemeEvent:
    """
    タイムライン上で扱う単一の音素イベントを表すクラス。
    event_id: Sceneの PhonemeBlockItem(block_id) と紐付けるためのID
    """
    __slots__ = ("event_id", "phoneme", "start_time", "duration")

    def __init__(self, phoneme: str, start_time: float, duration: float, event_id: Optional[str] = None):
        self.phoneme = phoneme
        self.start_time = start_time
        self.duration = duration
        # 省略可だが、未指定なら新しくuuidを付与
        self.event_id = event_id if event_id else str(uuid.uuid4())

    @property
    def end_time(self) -> float:
        """start_time + duration を計算して返す。"""
        return self.start_time + self.duration

    def to_dict(self) -> dict:
        """
        JSON化などに使用するための辞書形式へ変換。
        end_time は動的計算なので保存しない。
        """
        return {
            "event_id": self.event_id,
            "phoneme": self.phoneme,
            "start_time": self.start_time,
            "duration": self.duration,
            # "end_time" は保存しない（ロード時にも自動計算できる）
        }

    @classmethod
    def from_dict(cls, data: dict):
        """
        辞書形式（JSONロード後など）から PhonemeEvent を復元。
        """
        return cls(
            phoneme=data.get("phoneme", "a"),
            start_time=float(data.get("start_time", 0.0)),
            duration=float(data.get("duration", 0.1)),
            event_id=data.get("event_id")  # Noneの場合は自動生成
        )


class TimelineDataModel(QAbstractTableModel):
    """
    音素イベントのリストを保持するテーブルモデル。
    1行 = 1つのPhonemeEvent
    列 = (Phoneme, Start_time, Duration, End_time) の4列例

    QTableViewなどにセットすることでGUI上で編集・表示も可能になる。
    """
    HEADERS = ["Phoneme", "Start", "Duration", "End"]

    COL_PHONEME = 0
    COL_START = 1
    COL_DURATION = 2
    COL_END = 3  # 自動計算列（編集不可）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events: List[PhonemeEvent] = []

        # UndoStackなどを仕込む場合は、外部から set_undo_stack() などで注入してもOK
        # 例: self.undo_stack = QUndoStack()

    # ----------------------------------------------------------------------
    # 必須実装: 行数・列数・データ取得
    # ----------------------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._events)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return QVariant()

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._events):
            return QVariant()

        event = self._events[row]

        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == self.COL_PHONEME:
                return event.phoneme
            elif col == self.COL_START:
                return f"{event.start_time:.3f}"
            elif col == self.COL_DURATION:
                return f"{event.duration:.3f}"
            elif col == self.COL_END:
                # end_timeは自動計算
                return f"{event.end_time:.3f}"

        return QVariant()

    # ----------------------------------------------------------------------
    # ヘッダの表示用
    # ----------------------------------------------------------------------
    def headerData(self, section: int, orientation: int, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    # ----------------------------------------------------------------------
    # データ編集を有効にするにはフラグの設定と setData の実装が必要
    # ----------------------------------------------------------------------
    def flags(self, index: QModelIndex):
        if not index.isValid():
            return super().flags(index)

        col = index.column()
        # End列は自動計算なので編集不可、それ以外は編集可
        if col == self.COL_END:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False

        row = index.row()
        col = index.column()
        event = self._events[row]

        try:
            if col == self.COL_PHONEME:
                event.phoneme = str(value)
            elif col == self.COL_START:
                event.start_time = float(value)
            elif col == self.COL_DURATION:
                event.duration = float(value)
            elif col == self.COL_END:
                # End列は編集不可
                return False
            else:
                return False
        except ValueError:
            return False

        # データ更新通知
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])

        # End列も連動して変化するので、そこも再描画必要
        # start_time or durationが変わったら End列も変わるため
        end_index = self.index(row, self.COL_END)
        self.dataChanged.emit(end_index, end_index, [Qt.DisplayRole, Qt.EditRole])

        return True

    # ----------------------------------------------------------------------
    # カスタムAPI: イベント操作メソッド
    # ----------------------------------------------------------------------
    def add_event(self, phoneme: str, start: float, duration: float, event_id: Optional[str] = None):
        """
        新しい音素イベントを末尾に追加。
        event_id を指定してブロックIDと合わせる場合もあり。
        """
        self.beginInsertRows(QModelIndex(), len(self._events), len(self._events))
        evt = PhonemeEvent(phoneme, start, duration, event_id=event_id)
        self._events.append(evt)
        self.endInsertRows()

    def insert_event(self, idx: int, phoneme: str, start: float, duration: float, event_id: Optional[str] = None):
        """
        指定した行に挿入する例。
        """
        if idx < 0:
            idx = 0
        elif idx > len(self._events):
            idx = len(self._events)

        self.beginInsertRows(QModelIndex(), idx, idx)
        evt = PhonemeEvent(phoneme, start, duration, event_id=event_id)
        self._events.insert(idx, evt)
        self.endInsertRows()

    def remove_event(self, row_index: int):
        """
        指定した行のイベントを削除。
        """
        if 0 <= row_index < len(self._events):
            self.beginRemoveRows(QModelIndex(), row_index, row_index)
            self._events.pop(row_index)
            self.endRemoveRows()

    def get_event(self, row_index: int) -> Optional[PhonemeEvent]:
        """
        指定行のイベントを取得。
        """
        if 0 <= row_index < len(self._events):
            return self._events[row_index]
        return None

    def clear_events(self):
        """
        全イベントをクリア。
        """
        self.beginResetModel()
        self._events.clear()
        self.endResetModel()

    # ----------------------------------------------------------------------
    # イベントIDを元に行を探すユーティリティ (Undo/Redo用)
    # ----------------------------------------------------------------------
    def find_row_by_event_id(self, event_id: str) -> Optional[int]:
        """
        event_id を持つPhonemeEventが何行目にあるかを返す。
        見つからなければ None。
        """
        for row, evt in enumerate(self._events):
            if evt.event_id == event_id:
                return row
        return None

    # ----------------------------------------------------------------------
    # JSON への保存 / JSON から読み込み
    # ----------------------------------------------------------------------
    def load_from_json(self, json_path: str) -> bool:
        """
        JSONファイルからイベントリストを読み込む。
        フォーマット例:
            [
                {
                  "event_id": "xxxx-xxxx-uuid",
                  "phoneme": "a",
                  "start_time": 0.0,
                  "duration": 0.3
                },
                ...
            ]
        """
        if not os.path.exists(json_path):
            print(f"[TimelineDataModel] File not found: {json_path}")
            return False

        with open(json_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
            if not isinstance(data_list, list):
                print("[TimelineDataModel] JSON structure error: not a list.")
                return False

        self.beginResetModel()
        self._events.clear()
        for d in data_list:
            evt = PhonemeEvent.from_dict(d)
            self._events.append(evt)
        self.endResetModel()
        return True

    def save_to_json(self, json_path: str) -> bool:
        """
        現在保持しているイベントリストを JSONファイルとして保存する。
        """
        data_list = [evt.to_dict() for evt in self._events]
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data_list, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[TimelineDataModel] Failed to save JSON: {e}")
            return False


def _demo():
    """
    このモジュールを単独で実行した場合のデモ。
    QTableView にデータを表示して編集を試す。
    """
    from PyQt5.QtWidgets import QApplication, QTableView
    import sys

    app = QApplication(sys.argv)

    model = TimelineDataModel()
    # 例: event_idを省略 → 自動生成
    model.add_event("a", 0.0, 0.3)
    # 例: event_idを指定
    model.add_event("i", 0.3, 0.2, event_id="my-block-id-1234")
    model.add_event("u", 0.5, 0.4)

    view = QTableView()
    view.setModel(model)
    view.setWindowTitle("TimelineDataModel Demo")
    view.resize(500, 250)
    view.show()

    # JSONファイルの読み込みテスト:
    # model.load_from_json("my_phoneme_timeline.json")

    sys.exit(app.exec_())


if __name__ == "__main__":
    _demo()
