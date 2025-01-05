# -*- coding: utf-8 -*-

import sys
import os
import json
import traceback

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSlot
from PyQt5.QtGui import QFont, QClipboard
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QLineEdit, QCheckBox, QSpinBox,
    QDoubleSpinBox, QComboBox, QTextEdit, QMessageBox, QFormLayout, QGroupBox,
    QScrollArea, QGraphicsOpacityEffect, QMenu
)

# パイプライン・解析・ユーティリティ等
from main.pipeline.lip_sync_generator import LipSyncGenerator
from main.analysis.hatsuon import HatsuonEngine
from main.utils import generate
from main.video.video_processing import VideoProcessor

# AudioPlayer (存在しない場合はNone)
try:
    from main.utils.audio_player import AudioPlayer
except ImportError:
    AudioPlayer = None

# TimelineEditor等
try:
    from main.ui.timeline_editor import TimelineEditorWindow
except ImportError:
    TimelineEditorWindow = None

try:
    from main.ui.preview_3d import ThreeDPreviewWidget
except ImportError:
    ThreeDPreviewWidget = None

try:
    from main.ui.waveform_widget import WaveformWidget
except ImportError:
    WaveformWidget = None

# 【新規】進捗ダイアログ (progress_dialog.py)
try:
    from main.ui.progress_dialog import ProgressDialog
except ImportError:
    class ProgressDialog(QWidget):
        """ダミーの進捗ダイアログ。実際には progress_dialog.py などで本実装。"""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Progress")
            self.resize(300, 80)
            # ここではダミー。実際は QVBoxLayout, QProgressBar, QLabelなどを配置。
        def setLabelText(self, text):
            pass
        def setValue(self, val):
            pass
        def show(self):
            super().show()
        def close(self):
            super().close()

# VMD出力の本格実装
try:
    from main.pipeline.exporter_vmd import VMDExporter
except ImportError:
    VMDExporter = None

# phoneme_to_morph_map.json (音素→モーフ名マッピング) へのパス
PHONEME_MAP_JSON = os.path.join(os.path.dirname(__file__), "..", "phoneme_to_morph_map.json")

# 設定ファイルパス (例: PROJECT_ROOT/main/lip_sync_config.json)
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "lip_sync_config.json")


class MainWindow(QMainWindow):
    """
    リップシンクツールのメインウィンドウクラス。
    Tabs:
      1) Main : Analysis + Export を統合
      2) Timeline
      3) Settings
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lip Sync Tool - Unified Analysis/Export UI")
        self.resize(1200, 800)

        # メインタブウィジェットを配置
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # 設定ファイル読み込み
        self.config_data = self._load_config()

        # アニメーション(フェード)を保持
        self._animations = []

        # AudioPlayerあれば初期化
        self.audio_player = AudioPlayer() if AudioPlayer else None
        if self.audio_player:
            self.audio_player.positionChanged.connect(self._on_player_position_changed)
            self.audio_player.on_finished.connect(self._on_player_finished)

        # キャラ選択ロック用（今回はあまり使わない）
        self.character_selected = True  # デフォルトTrue

        # **解析結果を保持するための変数 (エクスポート時に使用)**
        self._last_lip_sync_data = None

        # タブ初期化
        self._init_tab_main()       # Analysis + Export 統合タブ
        self._init_tab_timeline()   # Timeline
        self._init_tab_settings()   # Settings

        # タブ切り替え時のフェードアニメ
        self.tab_widget.currentChanged.connect(self._animate_tab_transition)

        # UI設定適用
        self._apply_ui_settings()

        # ダークテーマ補足CSS
        self.setStyleSheet("""
            QPushButton:hover {
                border: 1px solid #88AADD;
                background-color: #4d4d4d;
            }
            QTabWidget::pane {
                background: #2b2b2b;
            }
            QTabBar::tab {
                padding: 8px;
                margin: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #444;
            }
        """)

    # ----------------------------------------------------------------
    # 設定ファイル読み込み & UI反映
    # ----------------------------------------------------------------
    def _load_config(self) -> dict:
        if not os.path.exists(CONFIG_FILE):
            print(f"[MainApp] lip_sync_config.json not found: {CONFIG_FILE}")
            return {}
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[MainApp] Failed to load config: {e}")
            return {}

    def _apply_ui_settings(self):
        """Settingsタブで保存された theme / font_size をUIに反映"""
        ui_settings = self.config_data.get("ui_settings", {})
        font_size = ui_settings.get("font_size", 12)
        theme = ui_settings.get("theme", "dark")

        base_font = self.font()
        base_font.setPointSize(font_size)
        self.setFont(base_font)

        if theme == "light":
            self.setStyleSheet("""
                QMainWindow { background-color: #f0f0f0; }
                QTabWidget::pane { background: #f8f8f8; }
                QPushButton:hover {
                    border: 1px solid #88AADD;
                    background-color: #eee;
                }
            """)

    # ----------------------------------------------------------------
    # Tab1: Main (Analysis + Export 統合)
    # ----------------------------------------------------------------
    def _init_tab_main(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --------- (A) Audio & Text or ASR mode ---------
        form_box = QFormLayout()

        # 1) モード選択: Text or ASR
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Text Mode", "ASR Mode"])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form_box.addRow("Input Mode:", self.combo_mode)

        # 2) 音声ファイルパス
        h_audio = QHBoxLayout()
        self.edit_audio_file = QLineEdit()
        self.btn_browse_audio = QPushButton("参照...")
        self.btn_browse_audio.clicked.connect(self._on_browse_audio)
        h_audio.addWidget(self.edit_audio_file)
        h_audio.addWidget(self.btn_browse_audio)
        form_box.addRow("Audio File:", h_audio)

        # 3) テキスト入力
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("ここにセリフを入力してください。")
        form_box.addRow("Text Input:", self.text_input)

        # 4) 解析ボタン
        self.btn_analyze = QPushButton("解析実行")
        self.btn_analyze.clicked.connect(self._on_click_analyze)
        form_box.addRow(self.btn_analyze)

        layout.addLayout(form_box)

        # --------- (B) Export Settings ---------
        export_box = QFormLayout()
        # Overlap
        self.spin_overlap = QDoubleSpinBox()
        self.spin_overlap.setRange(0.0, 1.0)
        self.spin_overlap.setValue(0.1)
        export_box.addRow("Overlap:", self.spin_overlap)

        # FPS
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 120)
        self.spin_fps.setValue(30)
        export_box.addRow("FPS:", self.spin_fps)

        # 出力形式
        self.combo_export_fmt = QComboBox()
        self.combo_export_fmt.addItems(["MMD (VMD)", "GMOD (JSON)"])
        export_box.addRow("Export Format:", self.combo_export_fmt)

        # 出力先 + ファイル名
        h_outputpath = QHBoxLayout()
        self.edit_outdir = QLineEdit("./output")
        self.btn_browse_outdir = QPushButton("参照...")
        self.btn_browse_outdir.clicked.connect(self._on_browse_outdir)
        h_outputpath.addWidget(self.edit_outdir)
        h_outputpath.addWidget(self.btn_browse_outdir)
        export_box.addRow("Output Dir:", h_outputpath)

        self.edit_filename = QLineEdit("lipsync_result")
        export_box.addRow("Output File:", self.edit_filename)

        # エクスポートボタン
        self.btn_export = QPushButton("エクスポート")
        self.btn_export.clicked.connect(self._on_click_export)
        export_box.addRow(self.btn_export)

        layout.addLayout(export_box)

        # --------- (C) Log表示 / 解析結果表示 ---------
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log)

        # サンプルデータ生成ボタン（任意）
        h_gen_sample = QHBoxLayout()
        self.btn_gen_sample = QPushButton("サンプルデータ生成(デバッグ)")
        self.btn_gen_sample.clicked.connect(self._on_click_gen_sample)
        h_gen_sample.addWidget(self.btn_gen_sample)
        layout.addLayout(h_gen_sample)

        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "Main")

    def _on_mode_changed(self, index):
        """Text Mode / ASR Mode の切り替え時にUIを制御"""
        mode_text = self.combo_mode.currentText()
        if "Text Mode" in mode_text:
            self.text_input.setEnabled(True)
        else:
            self.text_input.setEnabled(False)

    def _on_browse_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "音声ファイルを選択", "",
            "Audio Files (*.wav *.mp3 *.flac);;All Files (*)"
        )
        if file_path:
            self.edit_audio_file.setText(file_path)
            # AudioPlayerあればロード
            if self.audio_player:
                loaded = self.audio_player.load_audio_file(file_path)
                if not loaded:
                    QMessageBox.warning(self, "エラー", "Audioファイルのロードに失敗しました。")

    def _on_browse_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "出力ディレクトリを選択")
        if d:
            self.edit_outdir.setText(d)

    def _on_click_gen_sample(self):
        """サンプルデータ生成(デバッグ用)"""
        output_dir = QFileDialog.getExistingDirectory(self, "サンプルデータ出力先")
        if output_dir:
            try:
                generate.generate_sample_data(output_dir)
                QMessageBox.information(self, "成功", f"サンプルデータを生成しました:\n{output_dir}")
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"サンプルデータ生成失敗:\n{traceback.format_exc()}")

    def _on_click_analyze(self):
        """リップシンク解析 実行"""
        audio_path = self.edit_audio_file.text().strip()
        mode = self.combo_mode.currentText()
        text_data = self.text_input.toPlainText().strip()

        asr_mode = ("ASR Mode" in mode)

        # 1) 音声ファイルチェック
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "エラー", "有効な音声ファイルを指定してください。")
            return

        # 2) テキストが空なのに Text Mode の場合 → 確認ダイアログ
        if not asr_mode and not text_data:
            res = QMessageBox.question(
                self,
                "テキストが入力されていません",
                "テキストが入力されていません。\n解析方法をASR Modeに変更しますか？",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                self.combo_mode.setCurrentText("ASR Mode")
                return
            else:
                return

        # プログレスダイアログ表示
        progress_dialog = ProgressDialog(self)
        progress_dialog.setLabelText("解析を実行中...")
        progress_dialog.setValue(0)
        progress_dialog.show()

        try:
            # 3) 実際の解析開始
            import librosa
            import numpy as np

            progress_dialog.setValue(10)
            audio_data, sr = librosa.load(audio_path, sr=16000, mono=True)
            audio_data = audio_data.astype(np.float32, copy=False)

            progress_dialog.setValue(50)
            config_path = CONFIG_FILE if os.path.exists(CONFIG_FILE) else ""
            generator = LipSyncGenerator(config_path=config_path)
            generator.allow_asr = asr_mode

            progress_dialog.setValue(70)
            result = generator.generate_lip_sync(audio_data, text_data, sample_rate=sr)

            # 解析結果を表示
            progress_dialog.setValue(90)
            self.text_log.clear()
            self.text_log.append("[LipSync Analysis Result]\n")
            self.text_log.append(json.dumps(result, indent=2, ensure_ascii=False))

            # 解析結果を保持して、エクスポート時に使う
            self._last_lip_sync_data = result

            # 完了
            progress_dialog.setLabelText("解析完了！")
            progress_dialog.setValue(100)
            QMessageBox.information(self, "完了", "リップシンク解析が完了しました！")

        except Exception as e:
            # 進捗ダイアログを閉じる前にエラー表示
            progress_dialog.close()

            err_text = traceback.format_exc()
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("エラー")
            msg_box.setText("解析中にエラーが発生しました。詳細をコピーできます。")
            msg_box.setDetailedText(err_text)

            copy_button = msg_box.addButton("エラー内容をコピー", QMessageBox.ActionRole)
            close_button = msg_box.addButton("閉じる", QMessageBox.AcceptRole)
            msg_box.exec_()

            if msg_box.clickedButton() == copy_button:
                clipboard = QApplication.clipboard()
                clipboard.setText(err_text)

            return
        finally:
            progress_dialog.close()

    def _on_click_export(self):
        """
        「エクスポート」ボタン。ここで実際に VMDExporter を呼び出して
        本物の .vmd (バイナリ) を出力できるようにする。
        """
        overlap_val = self.spin_overlap.value()
        fps_val = self.spin_fps.value()
        export_fmt = self.combo_export_fmt.currentText()
        out_dir = self.edit_outdir.text().strip()
        out_name = self.edit_filename.text().strip()

        if not out_dir:
            QMessageBox.warning(self, "エラー", "出力先フォルダが指定されていません。")
            return
        if not out_name:
            out_name = "lipsync_result"

        # 事前に解析が行われ、_last_lip_sync_data があるか確認
        if not self._last_lip_sync_data:
            QMessageBox.warning(self, "エラー", "解析結果がありません。先に解析してください。")
            return

        # 出力ファイル名
        if "MMD" in export_fmt:
            ext = ".vmd"
            real_fmt = "vmd"
        else:
            ext = ".json"
            real_fmt = "json"

        out_path = os.path.join(out_dir, out_name + ext)

        # 実際のエクスポート処理
        try:
            if not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            if "MMD" in export_fmt:
                # → VMDExporter を用いて、lip_sync_data からモーフキーを生成し、バイナリ出力
                if not VMDExporter:
                    QMessageBox.warning(self, "エラー", "VMDExporter が読み込まれていません。")
                    return

                # phoneme_to_morph_map.json 読み込み
                mapping = {}
                if os.path.exists(PHONEME_MAP_JSON):
                    try:
                        with open(PHONEME_MAP_JSON, "r", encoding="utf-8") as fm:
                            mapping = json.load(fm)
                    except:
                        print("[Export] phoneme_to_morph_map.json の読み込み失敗。")

                exporter = VMDExporter(
                    model_name="MyMMDModel",  # 必要に応じて他の方法でモデル名を指定
                    phoneme_mapping=mapping
                )
                # lip_sync_data → モーフフレーム生成
                exporter.from_lip_sync_data(self._last_lip_sync_data, fps=fps_val, fade_out=True)
                # バイナリ出力
                exporter.export_vmd_binary(out_path)

                QMessageBox.information(
                    self, "Export完了", f"MMD(VMD) 形式で出力しました:\n{out_path}"
                )
                self.text_log.append(f"[Export] VMD出力 -> {out_path}")

            else:
                # → GMOD(JSON)形式 (ダミー)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(self._last_lip_sync_data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(
                    self, "Export完了", f"GMOD(JSON) 形式で出力しました:\n{out_path}"
                )
                self.text_log.append(f"[Export] JSON出力 -> {out_path}")

            # ログに追加
            self.text_log.append(f"[Export] Format: {export_fmt}")
            self.text_log.append(f"  Overlap: {overlap_val}")
            self.text_log.append(f"  FPS: {fps_val}")
            self.text_log.append(f"  OutFile: {out_path}")

        except Exception as e:
            err_msg = f"エクスポート中にエラー:\n{traceback.format_exc()}"
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("エラー")
            msg_box.setText("エクスポート中にエラーが発生しました。詳細をコピーできます。")
            msg_box.setDetailedText(err_msg)

            copy_button = msg_box.addButton("エラー内容をコピー", QMessageBox.ActionRole)
            close_button = msg_box.addButton("閉じる", QMessageBox.AcceptRole)
            msg_box.exec_()

            if msg_box.clickedButton() == copy_button:
                clipboard = QApplication.clipboard()
                clipboard.setText(err_msg)

    # ----------------------------------------------------------------
    # Tab2: Timeline
    # ----------------------------------------------------------------
    def _init_tab_timeline(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.timeline_overlay = QWidget(tab)
        self.timeline_overlay.setStyleSheet("background-color: rgba(100,100,100, 150);")
        self.timeline_overlay.setVisible(not self.character_selected)
        self.timeline_overlay.setDisabled(True)

        # 再生コントロール
        control_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")
        self.slow_check = QCheckBox("0.5x Speed")
        self.mute_check = QCheckBox("Audio Off")

        self.btn_play.clicked.connect(self._on_timeline_play)
        self.btn_pause.clicked.connect(self._on_timeline_pause)
        self.btn_stop.clicked.connect(self._on_timeline_stop)

        control_layout.addWidget(self.btn_play)
        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.slow_check)
        control_layout.addWidget(self.mute_check)
        layout.addLayout(control_layout)

        # 中央: 3Dプレビュー + 波形 + TimelineEditor
        center_layout = QHBoxLayout()

        if ThreeDPreviewWidget:
            self.preview_3d = ThreeDPreviewWidget(tab)
            self.preview_3d.setMinimumWidth(300)
            center_layout.addWidget(self.preview_3d, stretch=1)
        else:
            self.preview_3d = None

        if WaveformWidget:
            self.waveform_w = WaveformWidget(tab)
            self.waveform_w.setMinimumSize(300, 150)
            center_layout.addWidget(self.waveform_w, stretch=1)
            self.waveform_w.waveClicked.connect(self._on_wave_clicked)
        else:
            self.waveform_w = None

        if TimelineEditorWindow:
            self.timeline_editor = TimelineEditorWindow(parent=tab, config_data=self.config_data)
            center_layout.addWidget(self.timeline_editor, stretch=1)
        else:
            self.timeline_editor = None

        layout.addLayout(center_layout)
        tab.setLayout(layout)
        self.tab_widget.addTab(tab, "Timeline")

        # overlay位置を合わせる
        self.timeline_overlay.setGeometry(tab.rect())
        self.timeline_overlay.raise_()

        def _on_resize(event):
            self.timeline_overlay.setGeometry(tab.rect())
        tab.resizeEvent = _on_resize

    def _on_timeline_play(self):
        if not self.audio_player:
            QMessageBox.warning(self, "Info", "AudioPlayerがありません。")
            return
        rate = 0.5 if self.slow_check.isChecked() else 1.0
        self.audio_player.set_rate(rate)
        self.audio_player.set_mute(self.mute_check.isChecked())
        self.audio_player.play()

    def _on_timeline_pause(self):
        if self.audio_player:
            self.audio_player.pause()

    def _on_timeline_stop(self):
        if self.audio_player:
            self.audio_player.stop()

    @pyqtSlot(float)
    def _on_wave_clicked(self, time_sec: float):
        if self.audio_player:
            ms = int(time_sec * 1000)
            self.audio_player.set_position(ms)

    def _on_player_position_changed(self, pos_ms: int):
        current_time_sec = pos_ms / 1000.0
        if self.waveform_w:
            self.waveform_w.set_cursor_time(current_time_sec)
        if self.preview_3d:
            self.preview_3d.set_time(current_time_sec)
        if self.timeline_editor and hasattr(self.timeline_editor, "set_playhead_time"):
            self.timeline_editor.set_playhead_time(current_time_sec)

    def _on_player_finished(self):
        print("[MainApp] Audio playback finished.")

    # ----------------------------------------------------------------
    # Tab3: Settings
    # ----------------------------------------------------------------
    def _init_tab_settings(self):
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)

        scr = QScrollArea()
        scr.setWidgetResizable(True)
        container = QWidget()
        form_layout = QFormLayout(container)

        # Timeline
        box_tl = QGroupBox("Timeline")
        lay_tl = QFormLayout()
        self.spin_tl_zoom = QDoubleSpinBox()
        self.spin_tl_zoom.setRange(0.1, 10.0)
        self.spin_tl_zoom.setValue(self.config_data.get("timeline", {}).get("zoom_level", 1.0))
        lay_tl.addRow("Zoom Level:", self.spin_tl_zoom)

        self.spin_tl_scroll = QDoubleSpinBox()
        self.spin_tl_scroll.setRange(0.0, 9999.0)
        self.spin_tl_scroll.setValue(
            self.config_data.get("timeline", {}).get("scroll_position", 0.0)
        )
        lay_tl.addRow("Scroll Position:", self.spin_tl_scroll)
        box_tl.setLayout(lay_tl)
        form_layout.addRow(box_tl)

        # Logging
        box_log = QGroupBox("Logging")
        lay_log = QFormLayout()
        self.check_filelog = QCheckBox("ログをファイル出力する")
        self.check_filelog.setChecked(
            self.config_data.get("logging", {}).get("enable_file_logging", True)
        )
        self.edit_logpath = QLineEdit(
            self.config_data.get("logging", {}).get("log_file_path", "./logs/lipsync_tool.log")
        )
        btn_logbrowse = QPushButton("参照...")
        btn_logbrowse.clicked.connect(self._on_browse_log_file)
        h_log = QHBoxLayout()
        h_log.addWidget(self.edit_logpath)
        h_log.addWidget(btn_logbrowse)

        lay_log.addRow("ファイル出力:", self.check_filelog)
        lay_log.addRow("ログファイルパス:", h_log)
        box_log.setLayout(lay_log)
        form_layout.addRow(box_log)

        # Processing Options
        box_proc = QGroupBox("Processing Options")
        lay_proc = QFormLayout()

        self.check_gpu = QCheckBox("GPUを使用する")
        use_gpu = self.config_data.get("processing_options", {}).get("enable_gpu", False)
        self.check_gpu.setChecked(use_gpu)
        lay_proc.addRow("GPUアクセラレーション:", self.check_gpu)

        self.spin_rms = QDoubleSpinBox()
        self.spin_rms.setRange(0.0, 1.0)
        self.spin_rms.setSingleStep(0.01)
        self.spin_rms.setValue(
            self.config_data.get("processing_options", {}).get("rms_threshold", 0.02)
        )
        lay_proc.addRow("RMSしきい値:", self.spin_rms)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["naive", "advanced", "standard"])
        c_mode = self.config_data.get("processing_options", {}).get("mode", "standard")
        if self.combo_mode.findText(c_mode) < 0:
            self.combo_mode.addItem(c_mode)
        self.combo_mode.setCurrentText(c_mode)
        lay_proc.addRow("処理モード:", self.combo_mode)

        self.check_cache = QCheckBox("キャッシュを使用する")
        self.check_cache.setChecked(
            self.config_data.get("processing_options", {}).get("enable_cache", True)
        )
        lay_proc.addRow("キャッシュ利用:", self.check_cache)

        self.edit_cache_dir = QLineEdit(
            self.config_data.get("processing_options", {}).get("cache_directory", "./cache")
        )
        btn_cache_dir = QPushButton("参照...")
        btn_cache_dir.clicked.connect(self._on_browse_cache_dir)
        h_cache = QHBoxLayout()
        h_cache.addWidget(self.edit_cache_dir)
        h_cache.addWidget(btn_cache_dir)
        lay_proc.addRow("キャッシュディレクトリ:", h_cache)

        box_proc.setLayout(lay_proc)
        form_layout.addRow(box_proc)

        # Character Settings
        box_char = QGroupBox("Character Settings (マッピング)")
        lay_char = QVBoxLayout()
        self.edit_char_json = QTextEdit()
        char_json = json.dumps(
            self.config_data.get("character_settings", {}), indent=2, ensure_ascii=False
        )
        self.edit_char_json.setPlainText(char_json)
        lay_char.addWidget(QLabel("設定中のキャラクター音素マッピング:"))
        lay_char.addWidget(self.edit_char_json)
        box_char.setLayout(lay_char)
        form_layout.addRow(box_char)

        # UI settings
        box_ui = QGroupBox("UI Settings")
        lay_ui = QFormLayout()

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["light", "dark"])
        c_theme = self.config_data.get("ui_settings", {}).get("theme", "dark")
        if self.combo_theme.findText(c_theme) >= 0:
            self.combo_theme.setCurrentText(c_theme)

        self.spin_font = QSpinBox()
        self.spin_font.setRange(8, 72)
        self.spin_font.setValue(
            self.config_data.get("ui_settings", {}).get("font_size", 12)
        )
        lay_ui.addRow("テーマ:", self.combo_theme)
        lay_ui.addRow("フォントサイズ:", self.spin_font)
        box_ui.setLayout(lay_ui)
        form_layout.addRow(box_ui)

        # Output
        box_out = QGroupBox("Output Settings")
        lay_out = QFormLayout()
        self.combo_def_fmt = QComboBox()
        self.combo_def_fmt.addItems(["json", "vmd", "xml", "txt"])
        def_fmt = self.config_data.get("output", {}).get("default_format", "json")
        if self.combo_def_fmt.findText(def_fmt) < 0:
            self.combo_def_fmt.addItem(def_fmt)
        self.combo_def_fmt.setCurrentText(def_fmt)

        self.edit_outdir2 = QLineEdit(
            self.config_data.get("output", {}).get("output_directory", "./output")
        )
        btn_odir2 = QPushButton("参照...")
        btn_odir2.clicked.connect(self._on_browse_output_dir2)
        h_odir2 = QHBoxLayout()
        h_odir2.addWidget(self.edit_outdir2)
        h_odir2.addWidget(btn_odir2)

        lay_out.addRow("default_format:", self.combo_def_fmt)
        lay_out.addRow("output_directory:", h_odir2)
        box_out.setLayout(lay_out)
        form_layout.addRow(box_out)

        # 設定保存ボタン
        btn_save = QPushButton("設定を保存")
        btn_save.clicked.connect(self._on_save_settings)
        form_layout.addRow(btn_save)

        # ログ表示欄
        self.settings_log = QTextEdit()
        self.settings_log.setReadOnly(True)
        form_layout.addRow(QLabel("ログ:"))
        form_layout.addRow(self.settings_log)

        container.setLayout(form_layout)
        scr.setWidget(container)
        outer_layout.addWidget(scr)
        tab.setLayout(outer_layout)

        self.tab_widget.addTab(tab, "Settings")

    def _on_browse_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "ログファイルの保存先")
        if path:
            self.edit_logpath.setText(path)

    def _on_browse_cache_dir(self):
        c = QFileDialog.getExistingDirectory(self, "キャッシュディレクトリを選択")
        if c:
            self.edit_cache_dir.setText(c)

    def _on_browse_output_dir2(self):
        d = QFileDialog.getExistingDirectory(self, "出力ディレクトリを選択")
        if d:
            self.edit_outdir2.setText(d)

    def _on_save_settings(self):
        # Timeline
        self.config_data.setdefault("timeline", {})
        self.config_data["timeline"]["zoom_level"] = self.spin_tl_zoom.value()
        self.config_data["timeline"]["scroll_position"] = self.spin_tl_scroll.value()

        # Logging
        self.config_data.setdefault("logging", {})
        self.config_data["logging"]["enable_file_logging"] = self.check_filelog.isChecked()
        self.config_data["logging"]["log_file_path"] = self.edit_logpath.text()

        # Processing Options
        proc_opts = self.config_data.setdefault("processing_options", {})
        proc_opts["enable_gpu"] = self.check_gpu.isChecked()
        proc_opts["rms_threshold"] = self.spin_rms.value()
        proc_opts["mode"] = self.combo_mode.currentText()
        proc_opts["enable_cache"] = self.check_cache.isChecked()
        proc_opts["cache_directory"] = self.edit_cache_dir.text()

        # Character Settings
        try:
            new_chars = json.loads(self.edit_char_json.toPlainText())
            self.config_data["character_settings"] = new_chars
        except json.JSONDecodeError:
            pass

        # UI
        ui_settings = self.config_data.setdefault("ui_settings", {})
        ui_settings["theme"] = self.combo_theme.currentText()
        ui_settings["font_size"] = self.spin_font.value()

        # Output
        out_conf = self.config_data.setdefault("output", {})
        out_conf["default_format"] = self.combo_def_fmt.currentText()
        out_conf["output_directory"] = self.edit_outdir2.text()

        # JSON保存
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            self.settings_log.append("[Settings] 設定を保存しました。")
            QMessageBox.information(self, "完了", "設定を保存しました。")

            # 変更をUIに再反映
            self._apply_ui_settings()

        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定保存中にエラー:\n{traceback.format_exc()}")

    # ----------------------------------------------------------------
    # タブ切り替えのフェード演出
    # ----------------------------------------------------------------
    def _animate_tab_transition(self, index: int):
        current_tab = self.tab_widget.widget(index)
        if not current_tab:
            return

        effect = QGraphicsOpacityEffect(current_tab)
        current_tab.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(600)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()

        self._animations.append(anim)

    # ----------------------------------------------------------------
    # AudioPlayer関連シグナル
    # ----------------------------------------------------------------
    def _on_player_position_changed(self, pos_ms: int):
        current_time_sec = pos_ms / 1000.0
        if hasattr(self, "waveform_w") and self.waveform_w:
            self.waveform_w.set_cursor_time(current_time_sec)
        if hasattr(self, "preview_3d") and self.preview_3d:
            self.preview_3d.set_time(current_time_sec)
        if hasattr(self, "timeline_editor") and self.timeline_editor and \
           hasattr(self.timeline_editor, "set_playhead_time"):
            self.timeline_editor.set_playhead_time(current_time_sec)

    def _on_player_finished(self):
        print("[MainApp] Audio playback finished.")


def main():
    app = QApplication(sys.argv)

    window = MainWindow()

    # ダークテーマ適用（config読み取り）
    ctheme = window.config_data.get("ui_settings", {}).get("theme", "dark")
    if ctheme == "dark":
        app.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QLabel, QCheckBox, QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit,
            QComboBox, QTextEdit, QRadioButton {
                color: #ffffff;
                background-color: #3c3f41;
            }
            QTabWidget::pane {
                background: #2b2b2b;
            }
            QGroupBox {
                border: 1px solid #777;
                margin-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
            }
        """)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
