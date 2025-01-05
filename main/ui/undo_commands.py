# main/ui/undo_commands.py
# -*- coding: utf-8 -*-

"""
undo_commands.py

タイムライン上の各種操作 (ブロック追加・移動・削除 等) を Undo/Redo するためのコマンドクラスを定義。

前提:
 - PyQt5 の QUndoCommand を用いる。
 - TimelineDataModel (main/ui/timeline_data_model.py) が提供する
   add_event(), remove_event(), setData() などを使って編集を行う。
 - コマンドパターンにより、redo() 時に操作を実行し、undo() 時に操作を元に戻す。
 
想定するシナリオ:
 - ユーザが音素ブロックをドラッグ: 1回のドラッグ完了時に MoveBlockCommand を生成
 - ユーザが新規ブロックを追加: AddBlockCommand
 - ユーザがブロックを削除: RemoveBlockCommand
 - リサイズや音素変更は EditBlockCommand や ResizeBlockCommand など
 - 複数ブロック同時操作に対応するなら MultiRemoveCommand, MultiMoveCommand 等が考えられる
"""

from PyQt5.QtWidgets import QUndoCommand

class AddBlockCommand(QUndoCommand):
    """
    新しい音素ブロック（PhonemeEvent）を追加するコマンド。
    """
    def __init__(self, model, phoneme, start, duration, event_id=None, desc="Add Block", parent=None):
        """
        Args:
            model: TimelineDataModel のインスタンス
            phoneme (str): 追加する音素名
            start (float): 開始時間
            duration (float): ブロックの長さ
            event_id (str or None): 既存のevent_idを指定する場合 (なければ新規生成)
            desc (str): コマンドの説明 (Undoスタックに表示される文字列)
        """
        super().__init__(desc, parent)
        self.model = model
        self.phoneme = phoneme
        self.start = start
        self.duration = duration
        self.event_id = event_id  # NoneならDataModel.add_event()で自動生成される
        self.inserted_index = -1  # 実際に追加された行番号を格納

    def redo(self):
        """
        コマンド実行 (やり直し)。
        """
        row_count = self.model.rowCount()
        self.model.beginInsertRows(self.model.index(row_count - 1, 0), row_count, row_count)

        # event_idを渡すことで DataModel 側で PhonemeEvent(event_id=...) が作られる
        self.model.add_event(self.phoneme, self.start, self.duration, event_id=self.event_id)
        self.inserted_index = row_count

        self.model.endInsertRows()

    def undo(self):
        """
        コマンドを取り消し。
        """
        if 0 <= self.inserted_index < self.model.rowCount():
            self.model.beginRemoveRows(
                self.model.index(self.inserted_index, 0),
                self.inserted_index,
                self.inserted_index
            )
            self.model._events.pop(self.inserted_index)
            self.model.endRemoveRows()


class RemoveBlockCommand(QUndoCommand):
    """
    既存の音素ブロックを削除するコマンド。
    - row_index で削除するのではなく event_id ベースで行を検索する形に変更。
    """
    def __init__(self, model, event_id, desc="Remove Block", parent=None):
        """
        Args:
            model: TimelineDataModel
            event_id (str): 削除対象のイベントID
        """
        super().__init__(desc, parent)
        self.model = model
        self.event_id = event_id
        self.removed_event = None
        self.removed_row = None

    def redo(self):
        """
        コマンド実行 (やり直し)。
        """
        row_index = self.model.find_row_by_event_id(self.event_id)
        if row_index is not None and 0 <= row_index < self.model.rowCount():
            self.model.beginRemoveRows(self.model.index(row_index, 0),
                                       row_index, row_index)
            self.removed_event = self.model._events.pop(row_index)
            self.removed_row = row_index
            self.model.endRemoveRows()

    def undo(self):
        """
        コマンドを取り消し。
        """
        # 以前削除した row の位置に戻す
        if self.removed_event is not None and self.removed_row is not None:
            row_count = self.model.rowCount()
            insert_index = min(self.removed_row, row_count)

            self.model.beginInsertRows(self.model.index(insert_index - 1, 0),
                                       insert_index, insert_index)
            self.model._events.insert(insert_index, self.removed_event)
            self.model.endInsertRows()


class MoveBlockCommand(QUndoCommand):
    """
    ブロックの移動操作を Undo/Redo するコマンド。
    イベントIDで対象を特定し、start_time を書き換える。
    """
    def __init__(self, model, event_id, old_start, new_start, desc="Move Block", parent=None):
        """
        Args:
            model: TimelineDataModel
            event_id (str): 移動したイベントのevent_id
            old_start (float): 移動前の開始時間
            new_start (float): 移動後の開始時間
        """
        super().__init__(desc, parent)
        self.model = model
        self.event_id = event_id
        self.old_start = old_start
        self.new_start = new_start

    def redo(self):
        """コマンドを実行。"""
        self._apply_start_time(self.new_start)

    def undo(self):
        """コマンドを取り消し。"""
        self._apply_start_time(self.old_start)

    def _apply_start_time(self, start_time):
        row_index = self.model.find_row_by_event_id(self.event_id)
        if row_index is not None and 0 <= row_index < self.model.rowCount():
            evt = self.model._events[row_index]
            evt.start_time = start_time
            # Start列(col=1), End列(col=3)
            idx_start = self.model.index(row_index, 1)
            self.model.dataChanged.emit(idx_start, idx_start, [])
            idx_end = self.model.index(row_index, 3)
            self.model.dataChanged.emit(idx_end, idx_end, [])


class ResizeBlockCommand(QUndoCommand):
    """
    ブロックのリサイズ操作を Undo/Redo するコマンド。
    イベントIDで対象を特定し、duration を書き換える。
    """
    def __init__(self, model, event_id, old_duration, new_duration,
                 desc="Resize Block", parent=None):
        """
        Args:
            model: TimelineDataModel
            event_id (str): リサイズ対象のイベントID
            old_duration (float): リサイズ前のduration
            new_duration (float): リサイズ後のduration
        """
        super().__init__(desc, parent)
        self.model = model
        self.event_id = event_id
        self.old_duration = old_duration
        self.new_duration = new_duration

    def redo(self):
        self._apply_duration(self.new_duration)

    def undo(self):
        self._apply_duration(self.old_duration)

    def _apply_duration(self, duration):
        row_index = self.model.find_row_by_event_id(self.event_id)
        if row_index is not None and 0 <= row_index < self.model.rowCount():
            evt = self.model._events[row_index]
            evt.duration = duration
            # duration列(col=2) と end列(col=3) が影響
            idx_dur = self.model.index(row_index, 2)
            self.model.dataChanged.emit(idx_dur, idx_dur, [])
            idx_end = self.model.index(row_index, 3)
            self.model.dataChanged.emit(idx_end, idx_end, [])


class EditBlockCommand(QUndoCommand):
    """
    ブロックの複合的な変更(音素/開始時間/durationなど)を1つの操作として記録。
    イベントIDで対象を検索し、まとめて更新。
    """
    def __init__(self, model, event_id,
                 old_phoneme, new_phoneme,
                 old_start, new_start,
                 old_duration, new_duration,
                 desc="Edit Block", parent=None):
        super().__init__(desc, parent)
        self.model = model
        self.event_id = event_id

        # phoneme
        self.old_phoneme = old_phoneme
        self.new_phoneme = new_phoneme

        # start_time
        self.old_start = old_start
        self.new_start = new_start

        # duration
        self.old_duration = old_duration
        self.new_duration = new_duration

    def redo(self):
        self._apply_edit(self.new_phoneme, self.new_start, self.new_duration)

    def undo(self):
        self._apply_edit(self.old_phoneme, self.old_start, self.old_duration)

    def _apply_edit(self, phoneme, start, duration):
        row_index = self.model.find_row_by_event_id(self.event_id)
        if row_index is not None and 0 <= row_index < self.model.rowCount():
            evt = self.model._events[row_index]
            evt.phoneme = phoneme
            evt.start_time = start
            evt.duration = duration

            # phoneme=col0, start=col1, duration=col2, end=col3
            top_idx = self.model.index(row_index, 0)
            bottom_idx = self.model.index(row_index, 3)
            self.model.dataChanged.emit(top_idx, bottom_idx, [])
