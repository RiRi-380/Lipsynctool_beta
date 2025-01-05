# main/ui/group_selection_manager.py
# -*- coding: utf-8 -*-

"""
group_selection_manager.py

タイムライン上で複数の QGraphicsItem (例: PhonemeBlockItem) を同時に選択・操作するための
管理クラスおよびユーティリティ関数をまとめたモジュール。

主な機能例:
  - 現在選択中のアイテム群を追跡 (QGraphicsViewの RubberBandDrag 等で複数選択できる)
  - Shift/Control キーによる選択追加/解除 (必要に応じて)
  - 選択されたアイテム全体をまとめて移動・削除・リサイズ など
  - Undo/Redo 実装と絡める場合は、本マネージャを介してコマンドを発行

使用想定:
  1) TimelineGraphicsView の mouseReleaseEvent 後などで「どのアイテムが選択状態になったか」を取得
  2) それを GroupSelectionManager に渡して内部リストを更新
  3) GroupSelectionManager は "selectionChanged" シグナル等を発行して、UIが一括操作可能にする
  4) 一括削除/移動時は GroupSelectionManager 内のメソッドを呼び出し、まとめて Undo/Redo コマンドを発行

依存:
  - PyQt5
  - PhonemeBlockItemなど、QGraphicsItemを継承したブロッククラス
  - Undo/Redoを行いたい場合は undo_commands などを参照
"""

from typing import List, Optional
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QGraphicsItem, QUndoStack

class GroupSelectionManager(QObject):
    """
    複数の QGraphicsItem (主に PhonemeBlockItem) をまとめて選択・編集するための管理クラス。
    TimelineGraphicsView 等から呼び出され、選択状態を追跡する。

    シグナル:
      - selectionChanged: 選択アイテム集合が変化した際に発行
    """

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None, undo_stack: Optional[QUndoStack] = None):
        super().__init__(parent)
        self._selected_items: List[QGraphicsItem] = []
        self._undo_stack = undo_stack  # Undo/Redoを使うなら外部のスタックを受け取る

    def update_selection(self, new_selection: List[QGraphicsItem]):
        """
        外部 (例: TimelineGraphicsView) から「現在選択されているアイテム」のリストを渡してもらい、
        内部状態を更新する。
        """
        # もし変更があるなら更新し、selectionChanged を発行
        old_set = set(self._selected_items)
        new_set = set(new_selection)

        if old_set != new_set:
            self._selected_items = new_selection
            self.selectionChanged.emit()

    def clear_selection(self):
        """選択解除。"""
        if self._selected_items:
            self._selected_items = []
            self.selectionChanged.emit()

    def selected_items(self) -> List[QGraphicsItem]:
        """
        現在選択されている QGraphicsItem のリストを返す。
        """
        return self._selected_items

    def delete_selected_items(self):
        """
        選択アイテムをまとめて削除する例。
        実際には Undo/Redo 用にコマンドを発行するなどが望ましい。
        """
        if not self._selected_items:
            return

        # 例: undo_commands の RemoveBlockCommand 等を個別に発行
        # あるいはまとめて 'DeleteMultipleCommand' を作る
        if self._undo_stack is not None:
            # UndoStack がある場合 -> コマンドを生成して push
            pass
        else:
            # Undo不要なら直接 scene から removeItem など
            for item in self._selected_items:
                scene = item.scene()
                if scene:
                    scene.removeItem(item)

        self._selected_items = []
        self.selectionChanged.emit()

    def move_selected_items(self, dx: float, dy: float):
        """
        選択中のアイテムをまとめて移動する簡易例。
        Undo/Redo対応するなら MoveMultipleCommand 等を作り、ここで push する。
        """
        if not self._selected_items:
            return

        for item in self._selected_items:
            old_pos = item.pos()
            new_x = old_pos.x() + dx
            new_y = old_pos.y() + dy
            item.setPos(new_x, new_y)
            # ここで start_time や duration を更新するかはアイテムクラス次第

        # もし UndoStack があればコマンド化すべき
        # self._undo_stack.push(MoveMultipleCommand(...))

    def group_selected_items(self):
        """
        選択中のアイテムを QGraphicsItemGroup にまとめる例。
        ただし実際には timeline の場合、個別座標管理が多いので
        group化メリットがあるか要検討。
        """
        if not self._selected_items:
            return

        scene = None
        for it in self._selected_items:
            scene = it.scene()  # 同じシーンに属している想定
            break

        if scene is None:
            return

        group = scene.createItemGroup(self._selected_items)
        # これで一括の QGraphicsItemGroup が生成される
        # まとめて移動/拡縮できるようになるが、個別のドラッグ制御と衝突する場合がある

    def ungroup_items(self, group_item: QGraphicsItem):
        """
        group化された QGraphicsItemGroup を解体する例。
        """
        scene = group_item.scene()
        if scene:
            scene.destroyItemGroup(group_item)


#
# もし TimelineEditorWindow 側からの使い方（例）:
#
#   1) RubberBandDrag 後に scene.selectedItems() を取得
#   2) group_sel_mgr.update_selection(scene.selectedItems())
#   3) group_sel_mgr.selected_items() を使って操作
#


def demo():
    """
    簡易デモ: このクラス単独では動かないが、テスト程度にコンソール出力だけ。
    実際には TimelineGraphicsView や timeline_editor.py から呼び出される想定。
    """
    mgr = GroupSelectionManager()
    print("GroupSelectionManager created.")
    # mgr.update_selection([...])
    # mgr.move_selected_items(10, 0)
    # mgr.delete_selected_items()
    pass


if __name__ == "__main__":
    demo()
