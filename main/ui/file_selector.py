# -*- coding: utf-8 -*-
"""
file_selector.py

ファイル一覧を表示し、並べ替えや検索、直接パス入力などを行うUI。
ダブルクリックでファイルを開いたり、OKボタンで確定したりできる。

[想定機能]
 1. ファイルを縦リスト表示 (ListWidget等)
 2. 上部にソート方法を選ぶComboBox (新しい順/古い順/名前順)
 3. 検索用LineEdit (部分一致検索)
 4. ファイルを直接指定するLineEdit + 参照(Browse)ボタン
 5. ダブルクリック or OKボタンでファイル決定
 6. (将来的に) 複数ファイルやフォルダ単位の扱い拡張

使い方の例:
    from main.ui.file_selector import FileSelectorWidget

    def on_file_selected(selected_path: str):
        print("ファイルが選択されました:", selected_path)

    widget = FileSelectorWidget()
    widget.fileSelected.connect(on_file_selected)
    widget.show()
"""

import os
import glob
import time
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QFileDialog, QComboBox
)
from PyQt5.QtCore import pyqtSignal, Qt

class FileSelectorWidget(QWidget):
    """
    ファイルを検索・並べ替え・選択するためのウィジェット。
    ダブルクリック or OKボタン押下時に `fileSelected` シグナルを発行する。
    """

    fileSelected = pyqtSignal(str)  # 選択ファイルのパスを通知

    def __init__(self, parent=None, initial_dir: str = ".", file_filter="*"):
        super(FileSelectorWidget, self).__init__(parent)
        self.setWindowTitle("File Selector")

        self.initial_dir = os.path.abspath(initial_dir)
        self.file_filter = file_filter  # 例: "*.wav" / "*.json" / "*"

        self._create_ui()
        self._scan_files()

    def _create_ui(self):
        """
        UI部品の作成とレイアウト配置。
        """
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- 上段: 並べ替え, 検索, 直接指定フォーム ---
        top_layout = QHBoxLayout()

        # 並べ替え: "Newest first", "Oldest first", "Name ascending", "Name descending"
        self.combo_sort = QComboBox()
        self.combo_sort.addItems([
            "Newest First",
            "Oldest First",
            "Name Ascending",
            "Name Descending"
        ])
        self.combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        top_layout.addWidget(self.combo_sort)

        # 検索テキスト
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Search by name...")
        self.edit_search.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.edit_search)

        main_layout.addLayout(top_layout)

        # --- ファイルを直接指定 + Browse ---
        direct_layout = QHBoxLayout()

        self.edit_direct_path = QLineEdit()
        self.edit_direct_path.setPlaceholderText("Enter file path directly...")
        direct_layout.addWidget(self.edit_direct_path)

        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._on_browse_file)
        direct_layout.addWidget(btn_browse)

        main_layout.addLayout(direct_layout)

        # --- 中段: ファイル一覧 ---
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        main_layout.addWidget(self.list_widget)

        # --- 下段: 操作ボタン (OK / Cancel 等) ---
        bottom_layout = QHBoxLayout()

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._on_ok_clicked)
        bottom_layout.addWidget(btn_ok)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self._on_cancel_clicked)
        bottom_layout.addWidget(btn_cancel)

        main_layout.addLayout(bottom_layout)

    def _scan_files(self):
        """
        initial_dir 内をファイル検索し、ListWidgetへ表示。
        file_filter を利用して限定する。
        """
        # ディレクトリが存在しなければ作る or エラーにする
        if not os.path.exists(self.initial_dir):
            os.makedirs(self.initial_dir, exist_ok=True)

        pattern = os.path.join(self.initial_dir, self.file_filter)
        files = glob.glob(pattern)

        # ファイルのみリスト化 (サブディレクトリは除く)
        files = [f for f in files if os.path.isfile(f)]

        # ListWidgetに表示用データを保持
        self.files_data = []
        for f in files:
            # 取得メタ情報(更新時刻など)
            mtime = os.path.getmtime(f)
            self.files_data.append((f, mtime))

        self._update_list_widget()

    def _update_list_widget(self):
        """
        self.files_data を現在のソート・検索ワードに応じてフィルタし、表示を更新。
        files_data = [ (path, mtime), ... ]
        """
        # 1. ソート適用
        sort_mode = self.combo_sort.currentText()
        if sort_mode == "Newest First":
            sorted_data = sorted(self.files_data, key=lambda x: x[1], reverse=True)
        elif sort_mode == "Oldest First":
            sorted_data = sorted(self.files_data, key=lambda x: x[1], reverse=False)
        elif sort_mode == "Name Ascending":
            sorted_data = sorted(self.files_data, key=lambda x: os.path.basename(x[0]).lower(), reverse=False)
        else:  # "Name Descending"
            sorted_data = sorted(self.files_data, key=lambda x: os.path.basename(x[0]).lower(), reverse=True)

        # 2. 検索フィルタ適用
        search_text = self.edit_search.text().strip().lower()
        if search_text:
            filtered_data = []
            for (path, mtime) in sorted_data:
                filename = os.path.basename(path).lower()
                if search_text in filename:
                    filtered_data.append((path, mtime))
        else:
            filtered_data = sorted_data

        # 3. ListWidgetへ反映
        self.list_widget.clear()
        for (path, mtime) in filtered_data:
            item_text = self._format_item_text(path, mtime)
            list_item = QListWidgetItem(item_text)
            # アイテムのユーザーデータとしてフルパスを持たせる
            list_item.setData(Qt.UserRole, path)
            self.list_widget.addItem(list_item)

    def _format_item_text(self, path: str, mtime: float) -> str:
        """
        ListWidgetに表示するテキストを作成。
        例: "filename.ext  (2023-01-01 12:34:56)"
        """
        base_name = os.path.basename(path)
        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        return f"{base_name}   ({t_str})"

    # ------------------------------
    # イベントハンドラ / コールバック
    # ------------------------------
    def _on_sort_changed(self, index: int):
        self._update_list_widget()

    def _on_search_text_changed(self, text: str):
        self._update_list_widget()

    def _on_browse_file(self):
        """
        ダイアログを開いて任意のファイルを選択し、list_widgetに追加 or 選択。
        """
        dlg = QFileDialog(self, "Select File", self.initial_dir, "All Files (*.*)")
        dlg.setFileMode(QFileDialog.ExistingFile)
        if dlg.exec_() == QFileDialog.Accepted:
            selected_file = dlg.selectedFiles()[0]
            self.edit_direct_path.setText(selected_file)
            # もし「選択したファイルをリストに追加しておきたい」なら下記のように追加する例:
            if os.path.isfile(selected_file):
                # 既にfiles_dataに無ければ追加
                if not any(selected_file == f[0] for f in self.files_data):
                    mtime = os.path.getmtime(selected_file)
                    self.files_data.append((selected_file, mtime))
                    self._update_list_widget()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        selected_path = item.data(Qt.UserRole)
        self._emit_file_selected(selected_path)

    def _on_ok_clicked(self):
        """
        現在の direct_path があればそれを優先し、無ければリスト選択アイテムを確定。
        """
        direct_path = self.edit_direct_path.text().strip()
        if direct_path and os.path.isfile(direct_path):
            self._emit_file_selected(direct_path)
            return

        # リストで選択中のファイルがあればそれ
        item = self.list_widget.currentItem()
        if item:
            selected_path = item.data(Qt.UserRole)
            self._emit_file_selected(selected_path)
        else:
            # 何も選択されていない場合は空文字などを返すか、何もしないかは仕様次第
            print("[FileSelector] No file selected.")

    def _on_cancel_clicked(self):
        """
        Cancel: ファイル選択を破棄してウィンドウを閉じる例。
        ここではシグナルは送らず単に閉じるのみ。
        """
        self.close()

    def _emit_file_selected(self, file_path: str):
        """
        fileSelected シグナルを発行し、ウィンドウを閉じる。
        """
        self.fileSelected.emit(file_path)
        self.close()


# ------------------------------
# 単体テスト or デモ用エントリーポイント
# ------------------------------
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    def on_file_selected_cb(path: str):
        print("ファイルが選択されました:", path)

    app = QApplication(sys.argv)
    w = FileSelectorWidget(initial_dir=".", file_filter="*.*")
    w.fileSelected.connect(on_file_selected_cb)
    w.resize(600, 400)
    w.show()
    sys.exit(app.exec_())
