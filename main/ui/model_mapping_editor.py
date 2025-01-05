# -*- coding: utf-8 -*-
"""
model_mapping_editor.py

キャラクターごとのモーフ/音素マッピングを編集するためのUI。

[主な機能]
 - lip_sync_config.json から "character_settings" セクションを読み込み
 - キャラクターを選択すると、その音素マッピングをテーブル表示
 - 例: "reimu" -> { "a": ["a","a2","a3"], "i": ["i","i2"], ... }
 - ユーザがテーブル上でマッピング内容を編集
 - "Save" ボタンで上書き or 別名保存
 - "Load Config" ボタンで再読み込み (破棄)
 - 追加/削除ボタンで音素やエイリアスを編集する簡易機能

[想定ユース]
 from main.ui.model_mapping_editor import ModelMappingEditor

 def on_mappings_changed(new_config_data: dict):
     # 受け取った新しい設定を処理
     print("[DEBUG] Updated config data:", new_config_data)

 editor = ModelMappingEditor(config_path="lip_sync_config.json")
 editor.mappingsUpdated.connect(on_mappings_changed)
 editor.show()
"""

import os
import json
from typing import Dict, Any, Optional, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QFileDialog, QMessageBox, QHeaderView
)
from PyQt5.QtCore import pyqtSignal, Qt


class ModelMappingEditor(QWidget):
    """
    キャラクターごとの音素マッピングを編集するためのウィジェット。
    lip_sync_config.json の "character_settings" セクションを対象とする。
    """

    mappingsUpdated = pyqtSignal(dict)  
    """
    Save ボタン押下時など、キャラクター設定が更新されたタイミングで発行。
    引数は config全体 or "character_settings" の新データを含む辞書。
    """

    def __init__(self, parent=None, config_path: str = "lip_sync_config.json"):
        super().__init__(parent)
        self.setWindowTitle("Model Mapping Editor")

        self._config_path = config_path
        self._config_data: Dict[str, Any] = {}
        self._char_settings: Dict[str, Dict[str, List[str]]] = {}
        """
        self._char_settings = {
          "default": {
             "a": ["a"], "i": ["i"], ...
          },
          "reimu": {
             "a": ["a","a2","a3"], "i": ["i","i2"], ...
          },
          ...
        }
        """
        self._current_char: Optional[str] = None  # コンボボックスで選択中のキャラ名

        self._create_ui()
        self._load_config_file()  # コンストラクタで自動読み込み

    def _create_ui(self):
        """
        ウィジェットの構造を作成する。
        """
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # === 上部: ファイル操作ボタン ===
        file_layout = QHBoxLayout()
        btn_load = QPushButton("Load Config")
        btn_load.clicked.connect(self._on_load_clicked)
        file_layout.addWidget(btn_load)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._on_save_clicked)
        file_layout.addWidget(btn_save)

        btn_save_as = QPushButton("Save As...")
        btn_save_as.clicked.connect(self._on_save_as_clicked)
        file_layout.addWidget(btn_save_as)

        main_layout.addLayout(file_layout)

        # === キャラクター選択コンボ ===
        char_select_layout = QHBoxLayout()
        lbl_char = QLabel("Character:")
        self.combo_char = QComboBox()
        self.combo_char.currentIndexChanged.connect(self._on_char_changed)
        char_select_layout.addWidget(lbl_char)
        char_select_layout.addWidget(self.combo_char)
        main_layout.addLayout(char_select_layout)

        # === テーブル (音素: [エイリアス一覧]) ===
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Phoneme", "Aliases (comma-separated)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table)

        # === 下部: 行の追加 / 削除 ボタン ===
        row_control_layout = QHBoxLayout()

        btn_add_row = QPushButton("Add Row")
        btn_add_row.clicked.connect(self._on_add_row_clicked)
        row_control_layout.addWidget(btn_add_row)

        btn_remove_row = QPushButton("Remove Selected Row")
        btn_remove_row.clicked.connect(self._on_remove_row_clicked)
        row_control_layout.addWidget(btn_remove_row)

        main_layout.addLayout(row_control_layout)

        # スタイル微調整など
        self.resize(640, 480)

    # -------------------------------------
    # Configファイルの読み書き
    # -------------------------------------
    def _load_config_file(self, path: Optional[str] = None):
        """
        指定されたパス or self._config_path から jsonを読み込み、character_settingsを反映。
        """
        if path:
            self._config_path = path

        if not os.path.exists(self._config_path):
            QMessageBox.warning(self, "Warning", f"Config file not found:\n{self._config_path}")
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")
            return

        # "character_settings"を抽出
        if "character_settings" in self._config_data:
            self._char_settings = self._config_data["character_settings"]
        else:
            self._char_settings = {}
            self._config_data["character_settings"] = {}

        # キャラクターの一覧をコンボボックスへ再セット
        self._update_character_combo()

    def _save_config_file(self, path: Optional[str] = None):
        """
        現在の self._config_data (特に self._char_settings) を指定ファイルへ保存。
        """
        if path:
            save_path = path
        else:
            save_path = self._config_path

        # まず _sync_table_to_data() でテーブルの内容を self._char_settings に反映
        self._sync_table_to_data()

        # 更新結果を config_data に書き戻す
        self._config_data["character_settings"] = self._char_settings

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self._config_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Info", f"Saved config to:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")
            return

        # 成功したら、外部にも変更を通知 (mappingsUpdatedシグナル)
        self.mappingsUpdated.emit(self._config_data)

    # -------------------------------------
    # UI更新 (コンボボックス / テーブル)
    # -------------------------------------
    def _update_character_combo(self):
        """
        character_settings のキーからキャラ一覧を取得し、コンボボックスを更新。
        """
        self.combo_char.blockSignals(True)
        self.combo_char.clear()
        char_list = sorted(self._char_settings.keys())
        self.combo_char.addItems(char_list)
        self.combo_char.blockSignals(False)

        if char_list:
            self.combo_char.setCurrentIndex(0)
            self._on_char_changed(0)  # 先頭をロード
        else:
            # キャラがいない場合、テーブルクリア
            self._current_char = None
            self.table.setRowCount(0)

    def _on_char_changed(self, index: int):
        """
        コンボでキャラを選択したとき、テーブルにマッピングを表示する。
        """
        char_list = sorted(self._char_settings.keys())
        if index < 0 or index >= len(char_list):
            self._current_char = None
            self.table.setRowCount(0)
            return

        self._current_char = char_list[index]
        # テーブル更新
        self._update_table_from_data()

    def _update_table_from_data(self):
        """
        現在の self._current_char について、音素マッピングをテーブルに表示。
        """
        if not self._current_char:
            self.table.setRowCount(0)
            return

        # 例: "reimu": { "a": ["a","a2","a3"], "i": ["i","i2"], ... }
        char_dict = self._char_settings.get(self._current_char, {})
        # phoneme一覧
        phonemes = list(char_dict.keys())

        self.table.setRowCount(len(phonemes))

        for row, phoneme in enumerate(phonemes):
            # Phoneme
            item_phoneme = QTableWidgetItem(phoneme)
            item_phoneme.setFlags(item_phoneme.flags() & ~Qt.ItemIsEditable)  # phoneme列は編集不可にする例
            self.table.setItem(row, 0, item_phoneme)

            # Aliases
            aliases = char_dict[phoneme]  # List[str]
            aliases_str = ", ".join(aliases)
            item_aliases = QTableWidgetItem(aliases_str)
            self.table.setItem(row, 1, item_aliases)

    def _sync_table_to_data(self):
        """
        テーブル内容を self._char_settings[self._current_char] に書き戻す。
        """
        if not self._current_char:
            return

        row_count = self.table.rowCount()
        updated_map = {}

        for row in range(row_count):
            phoneme_item = self.table.item(row, 0)
            alias_item = self.table.item(row, 1)

            if phoneme_item is None:
                continue

            phoneme = phoneme_item.text().strip()
            if not phoneme:
                continue

            if alias_item:
                alias_str = alias_item.text().strip()
            else:
                alias_str = ""

            # comma-separated -> list
            if alias_str:
                alias_list = [x.strip() for x in alias_str.split(",")]
            else:
                alias_list = []

            updated_map[phoneme] = alias_list

        self._char_settings[self._current_char] = updated_map

    # -------------------------------------
    # ボタン押下ハンドラ
    # -------------------------------------
    def _on_load_clicked(self):
        """
        Configファイルを再選択して読み込む例。
        """
        dlg = QFileDialog(self, "Select Config JSON", ".", "JSON Files (*.json);;All Files (*.*)")
        dlg.setFileMode(QFileDialog.ExistingFile)
        if dlg.exec_() == QFileDialog.Accepted:
            selected_path = dlg.selectedFiles()[0]
            self._load_config_file(selected_path)

    def _on_save_clicked(self):
        """
        現在のconfigパスへ上書き保存。
        """
        if not self._config_path:
            self._on_save_as_clicked()
        else:
            self._save_config_file()

    def _on_save_as_clicked(self):
        """
        別名保存ダイアログを表示。
        """
        dlg = QFileDialog(self, "Save As...", ".", "JSON Files (*.json)")
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.setDefaultSuffix("json")

        if dlg.exec_() == QFileDialog.Accepted:
            save_path = dlg.selectedFiles()[0]
            self._save_config_file(save_path)

    def _on_add_row_clicked(self):
        """
        新しい行を追加する -> phoneme名は仮のユニーク文字列を生成するか、空のままにするか。
        ここでは「new_phoneme_{n}」のような一時名前を入れる例に。
        """
        if not self._current_char:
            QMessageBox.warning(self, "Warning", "No character selected.")
            return

        row_count = self.table.rowCount()
        self.table.insertRow(row_count)

        # デフォルトのphoneme名
        new_phoneme_name = f"new_phoneme_{row_count}"

        # 1列目: phoneme (編集不可にしてるので setFlags 調整)
        item_phoneme = QTableWidgetItem(new_phoneme_name)
        item_phoneme.setFlags(item_phoneme.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row_count, 0, item_phoneme)

        # 2列目: Aliases (空)
        item_aliases = QTableWidgetItem("")
        self.table.setItem(row_count, 1, item_aliases)

    def _on_remove_row_clicked(self):
        """
        選択された行を削除する。
        """
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            return

        # 1つの選択範囲だけを考慮する簡易実装 (複数選択対応は拡張で)
        sel_range = selected_ranges[0]
        top_row = sel_range.topRow()
        bottom_row = sel_range.bottomRow()

        for row in range(bottom_row, top_row - 1, -1):
            self.table.removeRow(row)


# ------------------------------
# テスト & デモ用
# ------------------------------
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    def on_updated(config_data: dict):
        print("[DEMO] mappingsUpdated signal received!")
        print(config_data.get("character_settings", {}))

    app = QApplication(sys.argv)
    editor = ModelMappingEditor(config_path="lip_sync_config.json")
    editor.mappingsUpdated.connect(on_updated)
    editor.show()
    sys.exit(app.exec_())
