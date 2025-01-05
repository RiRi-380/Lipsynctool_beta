# PROJECT_ROOT/main/ui/timeline_editor.py
# -*- coding: utf-8 -*-

import sys
import os
import json
import uuid

from PyQt5.QtCore import (
    Qt, QPointF, QPropertyAnimation, QEasingCurve, pyqtSignal, QRectF
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QLineEdit, QDoubleSpinBox, QCheckBox, QGraphicsView,
    QGraphicsScene, QGraphicsObject, QMessageBox,
    QGraphicsOpacityEffect, QMenu
)

try:
    from main.ui.preview_3d import ThreeDPreviewWidget
except ImportError:
    ThreeDPreviewWidget = None

try:
    from main.ui.waveform_widget import WaveformWidget
except ImportError:
    WaveformWidget = None

try:
    from main.ui.timeline_data_model import TimelineDataModel
    from main.ui.undo_commands import (
        AddBlockCommand, MoveBlockCommand, ResizeBlockCommand, DeleteBlockCommand
    )
except ImportError:
    TimelineDataModel = None
    AddBlockCommand = None
    MoveBlockCommand = None
    ResizeBlockCommand = None
    DeleteBlockCommand = None

try:
    from main.utils.audio_player import AudioPlayer
except ImportError:
    AudioPlayer = None

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "lip_sync_config.json")


class PhonemeBlockItem(QGraphicsObject):
    """
    タイムライン上に配置される音素ブロック。
    - QGraphicsObject を継承し、シグナルが使えるようにする。
    - ドラッグ移動時にフレームスナップ対応
    - 端をドラッグするとリサイズ
    - 右クリックで音素バリエーション切り替えメニュー
    - ドラッグ前後の start_time / duration を記録 (Undo/Redo用にシグナル通知)
    - block_id で DataModel と対応させる（省略可）
    """
    blockMoved = pyqtSignal(object, float, float)   # (self, old_start, new_start)
    blockResized = pyqtSignal(object, float, float) # (self, old_duration, new_duration)
    blockRightClicked = pyqtSignal(object, QPointF) # (self, scenePos)

    HANDLE_SIZE = 8
    SNAP_FPS = 30

    def __init__(
        self,
        block_id=None,
        phoneme="a",
        start_time=0.0,
        duration=0.2,
        parent=None
    ):
        super().__init__(parent)
        self.block_id = block_id if block_id else str(uuid.uuid4())

        self.phoneme = phoneme
        self.start_time = start_time
        self.duration = duration

        # 右クリックメニューなどで参照するための表示色
        self.fill_color = QColor("#FFCC66")
        self.pen_color = QColor(Qt.black)

        # マウス操作でのリサイズ判定フラグ
        self._isResizingLeft = False
        self._isResizingRight = False

        # ドラッグ開始前に値を保存 (Undo/Redo用)
        self._dragOldStart = start_time
        self._resizeOldDuration = duration

        # 高さは固定で 30px としておく
        self.block_height = 30

        # 再描画用に setAcceptedMouseButtons 等を設定 (QGraphicsObject ではデフォルトON)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        # 選択を有効にする
        self.setFlag(QGraphicsObject.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.ItemSendsGeometryChanges, True)

    # ==============================================================
    # QGraphicsObject に必須: boundingRect() と paint() の実装
    # ==============================================================
    def boundingRect(self):
        # 横幅は duration に応じて変化 (1sec = 200px)
        width_px = self.duration * 200
        return QRectF(0, 0, width_px, self.block_height)

    def paint(self, painter, option, widget=None):
        # 背景の矩形
        painter.setBrush(QBrush(self.fill_color))
        painter.setPen(QPen(self.pen_color, 1))
        painter.drawRect(self.boundingRect())

        # テキスト表示
        painter.setPen(QPen(Qt.black, 1))
        painter.drawText(5, 20, self.phoneme)

    # ==============================================================
    # イベントハンドラ: マウス押下
    # ==============================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            local_x = event.pos().x()
            rect_width = self.boundingRect().width()

            # 開始時にドラッグ前の値を記録
            self._dragOldStart = self.start_time
            self._resizeOldDuration = self.duration

            # 左端 or 右端に近いかでリサイズモード判定
            if abs(local_x - 0.0) < self.HANDLE_SIZE:
                self._isResizingLeft = True
                event.accept()
                return
            elif abs(local_x - rect_width) < self.HANDLE_SIZE:
                self._isResizingRight = True
                event.accept()
                return
            else:
                self._isResizingLeft = False
                self._isResizingRight = False
                super().mousePressEvent(event)

        elif event.button() == Qt.RightButton:
            self.blockRightClicked.emit(self, event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    # ==============================================================
    # イベントハンドラ: マウス移動 (ドラッグ)
    # ==============================================================
    def mouseMoveEvent(self, event):
        if self._isResizingLeft or self._isResizingRight:
            local_x = event.pos().x()
            original_w = self.boundingRect().width()
            new_x = self.x()
            new_w = original_w

            def snap_px(px):
                time_val = px / 200.0
                f_exact = time_val * self.SNAP_FPS
                f_round = round(f_exact)
                return (f_round / float(self.SNAP_FPS)) * 200.0

            if self._isResizingLeft:
                # 左端リサイズ
                left_scene_x = self.mapToScene(local_x, 0).x()
                snapped_left = snap_px(left_scene_x)
                right_x = self.x() + original_w
                new_w = right_x - snapped_left
                if new_w < 5:
                    new_w = 5
                new_x = snapped_left

            elif self._isResizingRight:
                # 右端リサイズ
                right_scene_x = self.mapToScene(local_x, 0).x()
                snapped_right = snap_px(right_scene_x)
                left_x = self.x()
                new_w = snapped_right - left_x
                if new_w < 5:
                    new_w = 5

            # 位置や大きさを更新
            self.setPos(new_x, self.y())
            self.duration = new_w / 200.0  # boundingRect の幅に対応

            # 再描画を要求
            self.update()

        else:
            # 通常ドラッグ (移動)
            super().mouseMoveEvent(event)

    # ==============================================================
    # イベントハンドラ: マウスリリース
    # ==============================================================
    def mouseReleaseEvent(self, event):
        if self._isResizingLeft or self._isResizingRight:
            # リサイズ終了
            self._isResizingLeft = False
            self._isResizingRight = False

            old_duration = self._resizeOldDuration
            new_duration = self.duration
            self.blockResized.emit(self, old_duration, new_duration)

        else:
            # 通常移動 → スナップ
            px_per_sec = 200.0
            new_x = self.x()
            time_val = new_x / px_per_sec
            frame_exact = time_val * self.SNAP_FPS
            frame_rounded = round(frame_exact)
            snapped_time = frame_rounded / float(self.SNAP_FPS)
            snapped_x = snapped_time * px_per_sec
            self.setPos(snapped_x, self.y())

            old_start = self._dragOldStart
            new_start = snapped_time
            self.start_time = new_start
            self.blockMoved.emit(self, old_start, new_start)

        super().mouseReleaseEvent(event)

    # ==============================================================
    # ホバー時のカーソル形状変更など
    # ==============================================================
    def hoverMoveEvent(self, event):
        w = self.boundingRect().width()
        local_x = event.pos().x()
        if abs(local_x - 0.0) < self.HANDLE_SIZE or abs(local_x - w) < self.HANDLE_SIZE:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)


class TimelineGraphicsView(QGraphicsView):
    """
    タイムライン表示用のグラフィックスビュー。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setSceneRect(0, 0, 2000, 300)
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#EEEEEE")))

        # 複数選択を有効化
        self.setDragMode(QGraphicsView.RubberBandDrag)

        # 再生ヘッドライン
        pen_head = QPen(QColor("#FF0000"))
        pen_head.setWidth(2)
        self.playhead_line = self.scene().addLine(0, 0, 0, 300, pen_head)

    def update_playhead_position(self, current_time: float):
        x_pos = current_time * 200.0
        self.playhead_line.setLine(x_pos, 0, x_pos, 300)

    def add_phoneme_block(self, block_item: PhonemeBlockItem):
        self.scene().addItem(block_item)

    def get_selected_blocks(self):
        items = self.scene().selectedItems()
        return [it for it in items if isinstance(it, PhonemeBlockItem)]


class TimelineEditorWindow(QMainWindow):
    """
    タイムラインエディタのメインウィンドウ。
    """
    def __init__(self, parent=None, config_data=None):
        super().__init__(parent)
        self.setWindowTitle("LipSync Timeline Editor")
        self.resize(1400, 900)

        self.config_data = config_data or {}

        # データモデル (Undo/Redo)
        if TimelineDataModel:
            self.data_model = TimelineDataModel()
        else:
            self.data_model = None

        # AudioPlayer
        self.audio_player = AudioPlayer() if AudioPlayer else None
        if self.audio_player and hasattr(self.audio_player, "positionChanged"):
            self.audio_player.positionChanged.connect(self._on_player_position_changed)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # 上部バー
        self._init_top_bar()

        # 中央 (ファイルリスト + 波形/Timeline/3D)
        center_hlayout = QHBoxLayout()
        self.file_list_widget = self._init_file_list()
        center_hlayout.addWidget(self.file_list_widget, stretch=1)

        right_side_layout = QVBoxLayout()

        # Waveform
        self.waveform_widget = None
        if WaveformWidget:
            self.waveform_widget = WaveformWidget()
            self.waveform_widget.setMinimumHeight(150)
            right_side_layout.addWidget(self.waveform_widget, stretch=2)

        # Timeline
        self.timeline_view = TimelineGraphicsView()
        self.timeline_view.setMinimumHeight(250)
        right_side_layout.addWidget(self.timeline_view, stretch=3)

        # 3D Preview
        self.preview_widget = None
        if ThreeDPreviewWidget:
            self.preview_widget = ThreeDPreviewWidget()
            self.preview_widget.setMinimumHeight(300)
            right_side_layout.addWidget(self.preview_widget, stretch=3)

        # Control bar
        control_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.slow_checkbox = QCheckBox("0.5x Speed")
        self.mute_checkbox = QCheckBox("Audio Off")

        self.play_button.clicked.connect(self._on_click_play)
        self.pause_button.clicked.connect(self._on_click_pause)

        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.pause_button)
        control_layout.addWidget(self.slow_checkbox)
        control_layout.addWidget(self.mute_checkbox)

        right_side_layout.addLayout(control_layout)

        # キャラ未選択時のぼかし
        self.timeline_overlay_effect = QGraphicsOpacityEffect()
        self.timeline_overlay_effect.setOpacity(1.0 if not self._is_character_selected() else 0.0)
        self.timeline_view.setGraphicsEffect(self.timeline_overlay_effect)
        self.timeline_view.setEnabled(self._is_character_selected())

        center_hlayout.addLayout(right_side_layout, stretch=3)
        self.main_layout.addLayout(center_hlayout)

        # 下部バー (Advanced / UndoRedo / Export + DeleteSelectedなど)
        self._init_bottom_bar()

        # ダミーのブロック
        self._add_dummy_phoneme_blocks()

        # フェードイン
        self._apply_window_fade_in()

    # -----------------------------------
    # 上部バー
    # -----------------------------------
    def _init_top_bar(self):
        top_layout = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("ファイル名を検索...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)

        self.char_combo = QComboBox()
        self.char_combo.addItem("unselected")
        cset = self.config_data.get("character_settings", {})
        for ch_name in cset.keys():
            self.char_combo.addItem(ch_name)
        self.char_combo.currentIndexChanged.connect(self._on_character_changed)

        self.overlap_spin = QDoubleSpinBox()
        self.overlap_spin.setRange(0.0, 1.0)
        self.overlap_spin.setSingleStep(0.05)
        default_overlap = self.config_data.get("export_options", {}).get("mmd", {}).get("overlap_rate", 0.1)
        self.overlap_spin.setValue(default_overlap)

        top_layout.addWidget(QLabel("Search Files:"))
        top_layout.addWidget(self.search_edit)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Character:"))
        top_layout.addWidget(self.char_combo)
        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Overlap:"))
        top_layout.addWidget(self.overlap_spin)

        self.main_layout.addLayout(top_layout)

    def _init_file_list(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name Asc", "Name Desc", "Date New->Old", "Date Old->New"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_option_changed)
        layout.addWidget(self.sort_combo)

        h_path = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("またはファイルパスを直接入力...")
        btn_open_path = QPushButton("Open")
        btn_open_path.clicked.connect(self._on_open_direct_path)
        h_path.addWidget(self.path_edit)
        h_path.addWidget(btn_open_path)
        layout.addLayout(h_path)

        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self._on_file_item_double_clicked)
        layout.addWidget(self.file_list)

        dummy_files = ["project1.json", "sample_lipsync.vmd", "another_test.json", "my_video.mp4"]
        for f in dummy_files:
            self.file_list.addItem(f)

        return container

    # -----------------------------------
    # 下部バー
    # -----------------------------------
    def _init_bottom_bar(self):
        bottom_layout = QHBoxLayout()

        self.advanced_check = QCheckBox("Advanced Mode")
        self.advanced_check.toggled.connect(self._on_advanced_mode_toggled)
        bottom_layout.addWidget(self.advanced_check)

        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self._on_undo)
        self.redo_button = QPushButton("Redo")
        self.redo_button.clicked.connect(self._on_redo)
        bottom_layout.addWidget(self.undo_button)
        bottom_layout.addWidget(self.redo_button)

        # 選択ブロック削除ボタン
        btn_delete_sel = QPushButton("Delete Selected Blocks")
        btn_delete_sel.clicked.connect(self._delete_selected_blocks)
        bottom_layout.addWidget(btn_delete_sel)

        bottom_layout.addStretch()

        self.export_button = QPushButton("Export Animation")
        self.export_button.clicked.connect(self._on_export_clicked)
        bottom_layout.addWidget(self.export_button)

        self.main_layout.addLayout(bottom_layout)

    # -----------------------------------
    # ファイルリスト関係
    # -----------------------------------
    def _is_character_selected(self) -> bool:
        return self.char_combo.currentText() not in ("unselected", "", None)

    def _on_character_changed(self, index):
        if self._is_character_selected():
            self.timeline_overlay_effect.setOpacity(0.0)
            self.timeline_view.setEnabled(True)
        else:
            self.timeline_overlay_effect.setOpacity(1.0)
            self.timeline_view.setEnabled(False)

    def _on_search_text_changed(self, text: str):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _on_sort_option_changed(self, index):
        sorting_mode = self.sort_combo.currentText()
        items_text = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if sorting_mode == "Name Asc":
            items_text.sort()
        elif sorting_mode == "Name Desc":
            items_text.sort(reverse=True)
        # 日付ソートはダミー
        self.file_list.clear()
        for f in items_text:
            self.file_list.addItem(f)

    def _on_open_direct_path(self):
        path = self.path_edit.text().strip()
        if not path:
            return
        self.file_list.addItem(path)
        self.path_edit.clear()

    def _on_file_item_double_clicked(self, item: QListWidgetItem):
        QMessageBox.information(self, "Open Timeline", f"{item.text()} をタイムラインで開きます。")
        # TODO: 実際に読み込むなど

    def _delete_selected_blocks(self):
        selected_blocks = self.timeline_view.get_selected_blocks()
        if not selected_blocks:
            QMessageBox.information(self, "Delete", "No blocks selected.")
            return

        confirm = QMessageBox.question(self, "Delete Blocks",
                                       f"{len(selected_blocks)} blocks を削除しますか？",
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            for block in selected_blocks:
                self.timeline_view.scene().removeItem(block)
                # DataModelからの削除処理 (省略)
            print(f"Deleted {len(selected_blocks)} blocks.")

    # -----------------------------------
    # ダミーブロック追加
    # -----------------------------------
    def _add_dummy_phoneme_blocks(self):
        demo_data = [
            ("a",    0.0,  0.3),
            ("i",    0.4,  0.2),
            ("u",    0.65, 0.25),
            ("a2",   1.0,  0.3),
            ("i_alt",1.5,  0.2),
        ]
        for (ph, st, dur) in demo_data:
            block = PhonemeBlockItem(phoneme=ph, start_time=st, duration=dur)
            block.blockMoved.connect(self._on_phoneme_block_moved)
            block.blockResized.connect(self._on_phoneme_block_resized)
            block.blockRightClicked.connect(self._on_block_right_clicked)
            self.timeline_view.add_phoneme_block(block)

    # -----------------------------------
    # 再生コントロール
    # -----------------------------------
    def _on_click_play(self):
        speed = 0.5 if self.slow_checkbox.isChecked() else 1.0
        is_muted = self.mute_checkbox.isChecked()
        print(f"Play: speed={speed}, mute={is_muted}")
        if self.audio_player:
            self.audio_player.set_mute(is_muted)
            self.audio_player.set_rate(speed)
            self.audio_player.play()

    def _on_click_pause(self):
        print("Pause playback.")
        if self.audio_player:
            self.audio_player.pause()

    def _on_player_position_changed(self, ms: int):
        sec = ms / 1000.0
        self.timeline_view.update_playhead_position(sec)
        if self.preview_widget:
            self.preview_widget.set_time(sec)
        if self.waveform_widget:
            pass  # waveClicked の逆操作等

    # -----------------------------------
    # ブロック操作シグナルハンドラ
    # -----------------------------------
    def _on_phoneme_block_moved(self, block_item, old_start, new_start):
        print(f"Block moved: {block_item.phoneme}, old={old_start}, new={new_start}")
        if self.data_model and MoveBlockCommand:
            row_idx = self._find_row_index_by_blockid(block_item.block_id)
            if row_idx is not None:
                cmd = MoveBlockCommand(self.data_model, row_idx, old_start, new_start)
                # self.data_model.undo_stack.push(cmd)

    def _on_phoneme_block_resized(self, block_item, old_duration, new_duration):
        print(f"Block resized: {block_item.phoneme}, oldDur={old_duration}, newDur={new_duration}")
        if self.data_model and ResizeBlockCommand:
            row_idx = self._find_row_index_by_blockid(block_item.block_id)
            if row_idx is not None:
                cmd = ResizeBlockCommand(self.data_model, row_idx, old_duration, new_duration)
                # self.data_model.undo_stack.push(cmd)

    def _on_block_right_clicked(self, block_item, scene_pos):
        menu = QMenu(self)
        char_name = self.char_combo.currentText()
        if char_name == "unselected":
            return
        char_map = self.config_data.get("character_settings", {}).get(char_name, {})

        base_ph = block_item.phoneme
        variations = []
        for k, varlist in char_map.items():
            if base_ph.startswith(k):
                variations = varlist
                break
        if not variations:
            # すべて表示
            for k, varlist in char_map.items():
                for var in varlist:
                    menu.addAction(var, lambda _, v=var: self._apply_phoneme_variation(block_item, v))
        else:
            for var in variations:
                menu.addAction(var, lambda _, v=var: self._apply_phoneme_variation(block_item, v))

        view_pos = self.timeline_view.mapFromScene(scene_pos)
        global_pos = self.timeline_view.mapToGlobal(view_pos.toPoint())
        menu.exec_(global_pos)

    def _apply_phoneme_variation(self, block_item, new_phoneme):
        print(f"Change phoneme: {block_item.phoneme} -> {new_phoneme}")
        block_item.phoneme = new_phoneme
        block_item.update()

    # -----------------------------------
    # Undo/Redo & Export
    # -----------------------------------
    def _on_advanced_mode_toggled(self, checked):
        if checked:
            print("Advanced mode: ON")
        else:
            print("Advanced mode: OFF")

    def _on_undo(self):
        if self.data_model and hasattr(self.data_model, 'undo_stack'):
            if self.data_model.undo_stack.canUndo():
                self.data_model.undo_stack.undo()
            else:
                QMessageBox.information(self, "Undo", "Undoできる操作はありません。")
        else:
            QMessageBox.information(self, "Undo", "Undo機能はダミーです。")

    def _on_redo(self):
        if self.data_model and hasattr(self.data_model, 'undo_stack'):
            if self.data_model.undo_stack.canRedo():
                self.data_model.undo_stack.redo()
            else:
                QMessageBox.information(self, "Redo", "Redoできる操作はありません。")
        else:
            QMessageBox.information(self, "Redo", "Redo機能はダミーです。")

    def _on_export_clicked(self):
        overlap_val = self.overlap_spin.value()
        char_name = self.char_combo.currentText()
        QMessageBox.information(
            self,
            "Export",
            f"キャラ: {char_name}, Overlap: {overlap_val}\n(ダミー)アニメファイルをエクスポートしました。"
        )

    # -----------------------------------
    #  データモデルと BlockID の紐付け例
    # -----------------------------------
    def _find_row_index_by_blockid(self, block_id: str):
        """block_idとDataModel上のevent_idが一致する行を探して返す (無ければNone)。"""
        if not self.data_model:
            return None
        for i, evt in enumerate(self.data_model._events):
            # evtに .event_id がある想定
            if hasattr(evt, 'event_id') and evt.event_id == block_id:
                return i
        return None

    # -----------------------------------
    # ウィンドウフェードイン
    # -----------------------------------
    def _apply_window_fade_in(self):
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity")
        anim.setDuration(800)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)


def demo_main():
    app = QApplication(sys.argv)
    editor = TimelineEditorWindow()
    editor.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    demo_main()
