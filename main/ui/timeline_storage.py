# main/ui/undo_commands.py
# -*- coding: utf-8 -*-

"""
undo_commands.py

PyQt5 の QUndoCommand を活用し、タイムライン編集操作の Undo/Redo を管理するためのコマンドクラス群。
主に timeline_data_model.py や timeline_editor.py 等と連携し、ユーザが行った編集操作を取り消す/やり直す仕組みを提供する。

[前提]
  - PyQt5 QUndoStack と QUndoCommand を利用
  - TimelineDataModel や PhonemeEvent の編集をコマンドオブジェクト化

[使い方の例]
  1) 何らかの編集操作が起きたら、以下のようにコマンドを生成し QUndoStack に push する:
       command = AddPhonemeCommand(model, phoneme="a", start=0.0, duration=0.3)
       undo_stack.push(command)

  2) Undo ボタンが押されたとき:
       undo_stack.undo()

  3) Redo ボタンが押されたとき:
       undo_stack.redo()

  このように、コマンドオブジェクトが do/undo メソッドを実行することで
  変更を反映/取り消しできる。
"""

from PyQt5.QtWidgets import QUndoCommand

# 例: TimelineDataModel や PhonemeEvent を利用する想定
#   from main.ui.timeline_data_model import TimelineDataModel, PhonemeEvent


class AddPhonemeCommand(QUndoCommand):
    """
    新規音素イベントをタイムラインデータモデルに追加するコマンド。
    """
    def __init__(self, model, phoneme, start, duration, index=None, description="Add Phoneme"):
        super().__init__(description)
        self.model = model
        self.phoneme = phoneme
        self.start_time = start
        self.duration = duration
        self.insert_index = index  # どこに挿入するか、Noneなら末尾
        self._row_added = None     # 実際に追加した行のインデックス

    def redo(self):
        """
        コマンドを実行（再度やり直し）するとき、または最初に呼び出されたとき。
        """
        if self.insert_index is None:
            # 末尾に追加
            row_before = self.model.rowCount()
            self.model.add_event(self.phoneme, self.start_time, self.duration)
            self._row_added = row_before
        else:
            # 指定行に挿入
            self.model.insert_event(self.insert_index, self.phoneme, self.start_time, self.duration)
            self._row_added = self.insert_index

    def undo(self):
        """
        取り消し処理。
        """
        if self._row_added is not None:
            self.model.remove_event(self._row_added)
            self._row_added = None


class RemovePhonemeCommand(QUndoCommand):
    """
    タイムラインデータモデルから音素イベントを削除するコマンド。
    """
    def __init__(self, model, row_index, description="Remove Phoneme"):
        super().__init__(description)
        self.model = model
        self.row_index = row_index
        self._saved_event = None

    def redo(self):
        """
        削除を実行。
        """
        # 削除対象を保存
        event = self.model.get_event(self.row_index)
        if event is None:
            return
        self._saved_event = (event.phoneme, event.start_time, event.duration)
        self.model.remove_event(self.row_index)

    def undo(self):
        """
        削除を取り消して元に戻す。
        """
        if self._saved_event is not None:
            phoneme, start, duration = self._saved_event
            self.model.insert_event(self.row_index, phoneme, start, duration)


class EditPhonemeCommand(QUndoCommand):
    """
    既存の音素イベントの内容を変更するコマンド（phoneme名やstart_time, durationなど）。
    """
    def __init__(self, model, row_index, old_value, new_value, field="phoneme", description="Edit Phoneme Field"):
        """
        Args:
            model: TimelineDataModel
            row_index: 編集対象行
            old_value: 変更前の値
            new_value: 変更後の値
            field (str): "phoneme"/"start_time"/"duration" など、編集フィールド名
        """
        super().__init__(description)
        self.model = model
        self.row_index = row_index
        self.old_value = old_value
        self.new_value = new_value
        self.field = field

    def redo(self):
        """
        値を new_value に変更。
        """
        event = self.model.get_event(self.row_index)
        if not event:
            return

        if self.field == "phoneme":
            event.phoneme = self.new_value
        elif self.field == "start_time":
            event.start_time = float(self.new_value)
        elif self.field == "duration":
            event.duration = float(self.new_value)

        # dataChanged を発行
        idx = self.model.index(self.row_index, 0)
        self.model.dataChanged.emit(idx, idx)

    def undo(self):
        """
        値を old_value に戻す。
        """
        event = self.model.get_event(self.row_index)
        if not event:
            return

        if self.field == "phoneme":
            event.phoneme = self.old_value
        elif self.field == "start_time":
            event.start_time = float(self.old_value)
        elif self.field == "duration":
            event.duration = float(self.old_value)

        idx = self.model.index(self.row_index, 0)
        self.model.dataChanged.emit(idx, idx)


class MovePhonemeCommand(QUndoCommand):
    """
    音素イベント(ブロック)をドラッグ移動などで start_time を変更するコマンド。
    例: 2.0s -> 2.3s に移動したら Undo で戻せる。
    """
    def __init__(self, model, row_index, old_start_time, new_start_time, description="Move Phoneme"):
        super().__init__(description)
        self.model = model
        self.row_index = row_index
        self.old_start = old_start_time
        self.new_start = new_start_time

    def redo(self):
        event = self.model.get_event(self.row_index)
        if event:
            event.start_time = self.new_start
            idx = self.model.index(self.row_index, 1)  # 1列目は start_time
            self.model.dataChanged.emit(idx, idx)

    def undo(self):
        event = self.model.get_event(self.row_index)
        if event:
            event.start_time = self.old_start
            idx = self.model.index(self.row_index, 1)
            self.model.dataChanged.emit(idx, idx)
