# main/ui/waveform_widget.py
# -*- coding: utf-8 -*-

"""
waveform_widget.py

音声波形を描画し、クリック・ドラッグ操作によるシークなどを扱うウィジェット。

【改良点】
1) set_cursor_time(...) の引数に対して、最大値を音声長(秒)にクランプ。
2) スクロール位置の範囲チェックをより安全にし、リサイズ時にもスクロール位置の有効範囲を再計算。
3) 波形データが非常に長い場合に対応しやすいよう、whileループの描画計算を微調整。
4) シグナル発行まわり (waveClicked, waveScrubbed) を複数回ドラッグしても問題ないよう、ドラッグ終了後にフラグをリセット。
5) 内部変数名やコメントの追加で可読性を向上。

"""

import sys
import numpy as np

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor
from PyQt5.QtWidgets import (
    QWidget, QScrollBar, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QApplication
)


class WaveformWidget(QWidget):
    """
    音声波形を描画するためのウィジェット。

    主な機能:
      - set_audio_data(audio_array, sample_rate):
          音声データ(np.float32) と サンプルレート を受け取り、描画準備。
      - set_zoom(samples_per_pixel):
          水平方向ズーム (1ピクセルあたりサンプル数) を設定。小さいほど拡大。
      - set_vertical_zoom(zoom: float):
          垂直方向の振幅拡大率を設定。1.0が標準、2.0なら2倍など。
      - set_scroll_position(scroll_samples):
          水平方向のスクロール位置をサンプル単位で設定。
      - set_cursor_time(time_sec):
          再生カーソルを指定秒数へ移動して描画する。音声長を超えないようクランプ。
      - set_enable_scrub_drag(enable: bool):
          Trueにすると、左ドラッグ中に waveScrubbed シグナルを連続で発行する。
          これを利用してスクラブ再生できる。

    シグナル:
      - waveClicked(float time_sec): 左クリックした地点の時間(秒)を通知。
      - waveScrubbed(float time_sec): ドラッグ中(スクラブ)のマウス位置(秒)を連続通知。
    """

    waveClicked = pyqtSignal(float)
    waveScrubbed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.audio_data: np.ndarray = None
        self.sample_rate: int = 16000

        # 1ピクセルあたり何サンプルか (水平ズーム)
        self.samples_per_pixel: int = 128
        # 垂直方向の拡大率
        self.vertical_zoom: float = 1.0

        # スクロール位置 (サンプル単位)
        self.scroll_pos: int = 0
        # カーソル(再生位置)の秒数。Noneなら非表示
        self.cursor_time: float = None

        # スクラブドラッグ機能
        self.enable_scrub_drag: bool = False
        self._is_dragging: bool = False

    # ----------------------------------------------------------------
    #  1) Public API
    # ----------------------------------------------------------------
    def set_audio_data(self, audio_array: np.ndarray, sample_rate: int = 16000):
        """
        音声波形をセットし、描画を更新。
        audio_array は float32 モノラルを推奨 (内部で型変換あり)。
        """
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32, copy=False)

        self.audio_data = audio_array
        self.sample_rate = sample_rate

        self.scroll_pos = 0
        self.cursor_time = 0.0
        self.update()

    def set_zoom(self, samples_per_pixel: int):
        """
        水平ズーム (1ピクセルあたりサンプル数) を設定。
        小さいほど拡大表示。
        """
        if samples_per_pixel < 1:
            samples_per_pixel = 1
        self.samples_per_pixel = samples_per_pixel
        # スクロール位置が表示範囲を超えないよう再調整
        self._clamp_scroll_pos()
        self.update()

    def set_vertical_zoom(self, zoom: float):
        """
        垂直ズーム(振幅スケール)を設定。
        0.1以下にはしない。
        """
        if zoom < 0.1:
            zoom = 0.1
        self.vertical_zoom = zoom
        self.update()

    def set_scroll_position(self, scroll_samples: int):
        """
        水平スクロール位置(サンプル単位)を設定。
        """
        self.scroll_pos = scroll_samples
        self._clamp_scroll_pos()
        self.update()

    def set_cursor_time(self, time_sec: float):
        """
        再生カーソル(秒)を設定。音声長を超える場合はクランプ。
        """
        if time_sec < 0:
            time_sec = 0.0

        if self.audio_data is not None and len(self.audio_data) > 0:
            audio_duration_sec = len(self.audio_data) / float(self.sample_rate)
            if time_sec > audio_duration_sec:
                time_sec = audio_duration_sec

        self.cursor_time = time_sec
        self.update()

    def set_enable_scrub_drag(self, enable: bool):
        """
        左ドラッグ中に waveScrubbed を連続発行するかどうか設定。
        """
        self.enable_scrub_drag = enable

    # ----------------------------------------------------------------
    #  2) Internal & Helper Methods
    # ----------------------------------------------------------------
    def _clamp_scroll_pos(self):
        """
        scroll_pos が音声長を超えないようにクランプ。
        """
        if self.audio_data is None:
            self.scroll_pos = 0
            return

        max_scroll = max(0, len(self.audio_data) - self.visible_samples_count())
        self.scroll_pos = max(0, min(self.scroll_pos, max_scroll))

    def visible_samples_count(self) -> int:
        """
        ウィジェット幅 × samples_per_pixel で、描画可能なサンプル数を返す。
        """
        return self.width() * self.samples_per_pixel

    def _time_to_xpos(self, time_sec: float) -> float:
        """
        time_sec(秒) → 波形のX座標(px) への変換。
        """
        if self.audio_data is None or len(self.audio_data) == 0:
            return 0.0

        sample_index = time_sec * self.sample_rate
        local_sample = sample_index - self.scroll_pos
        return local_sample / self.samples_per_pixel

    def _xpos_to_time(self, x_px: float) -> float:
        """
        x座標(px) → time(秒) に逆変換。
        """
        if self.audio_data is None:
            return 0.0
        sample_index = (x_px * self.samples_per_pixel) + self.scroll_pos
        return sample_index / float(self.sample_rate)

    # ----------------------------------------------------------------
    #  3) paintEvent: 波形やカーソルを描画
    # ----------------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.audio_data is None or len(self.audio_data) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        mid_y = h // 2

        # 背景
        painter.fillRect(self.rect(), QBrush(QColor("#FFFFFF")))

        # 中央線
        painter.setPen(QPen(QColor("#AAAAAA"), 1, Qt.DashLine))
        painter.drawLine(0, mid_y, w, mid_y)

        # 可視範囲サンプルを取得
        start_sample = self.scroll_pos
        end_sample = start_sample + self.visible_samples_count()
        if end_sample > len(self.audio_data):
            end_sample = len(self.audio_data)
        visible_data = self.audio_data[start_sample:end_sample]

        # 波形を描画
        painter.setPen(QPen(QColor("#22AAEE"), 1))
        stride = self.samples_per_pixel

        x_px = 0
        idx = 0
        len_visible = len(visible_data)
        while idx < len_visible:
            chunk = visible_data[idx: idx + stride]
            cmax = float(np.max(chunk))
            cmin = float(np.min(chunk))

            y_max = mid_y - int(cmax * mid_y * self.vertical_zoom)
            y_min = mid_y - int(cmin * mid_y * self.vertical_zoom)
            painter.drawLine(x_px, y_min, x_px, y_max)

            x_px += 1
            idx += stride

        # 再生カーソル
        if self.cursor_time is not None:
            cursor_x = self._time_to_xpos(self.cursor_time)
            if 0 <= cursor_x <= w:
                painter.setPen(QPen(QColor("#FF0000"), 2))
                painter.drawLine(cursor_x, 0, cursor_x, h)

    # ----------------------------------------------------------------
    #  4) Mouse Events: クリックで waveClicked, ドラッグで waveScrubbed
    # ----------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            clicked_x = event.pos().x()
            t_sec = self._xpos_to_time(clicked_x)
            self.waveClicked.emit(t_sec)

            if self.enable_scrub_drag:
                self._is_dragging = True
                self.waveScrubbed.emit(t_sec)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and (event.buttons() & Qt.LeftButton):
            if self.enable_scrub_drag:
                dragged_x = event.pos().x()
                t_sec = self._xpos_to_time(dragged_x)
                self.waveScrubbed.emit(t_sec)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        """
        ウィンドウサイズが変わったとき、スクロール位置が有効範囲を超えないよう調整。
        """
        super().resizeEvent(event)
        self._clamp_scroll_pos()
        self.update()


# -----------------------------------
# デモ用ウィンドウ: WaveformWidget のテスト
# -----------------------------------
if __name__ == "__main__":
    from PyQt5.QtWidgets import QScrollBar, QVBoxLayout, QHBoxLayout, QPushButton

    class WaveformDemoWindow(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Waveform Demo")
            self.resize(800, 400)

            self.waveform = WaveformWidget()
            self.waveform.set_enable_scrub_drag(True)

            # ズームボタンなど
            self.btn_zoom_in = QPushButton("Zoom In")
            self.btn_zoom_out = QPushButton("Zoom Out")
            self.btn_vert_up = QPushButton("Vert +")
            self.btn_vert_down = QPushButton("Vert -")

            self.btn_zoom_in.clicked.connect(self._on_zoom_in)
            self.btn_zoom_out.clicked.connect(self._on_zoom_out)
            self.btn_vert_up.clicked.connect(self._on_vert_up)
            self.btn_vert_down.clicked.connect(self._on_vert_down)

            # スクロールバー
            self.scroll_bar = QScrollBar(Qt.Horizontal)
            self.scroll_bar.valueChanged.connect(self._on_scroll_changed)

            layout = QVBoxLayout(self)
            layout.addWidget(self.waveform, stretch=1)

            ctrl_layout = QHBoxLayout()
            ctrl_layout.addWidget(self.btn_zoom_in)
            ctrl_layout.addWidget(self.btn_zoom_out)
            ctrl_layout.addWidget(self.btn_vert_up)
            ctrl_layout.addWidget(self.btn_vert_down)
            layout.addLayout(ctrl_layout)

            layout.addWidget(self.scroll_bar)

            # サンプル音声データ
            dummy_data = np.sin(np.linspace(0, 100.0 * np.pi, 16000)).astype(np.float32)
            self.waveform.set_audio_data(dummy_data, sample_rate=16000)

            # シグナル受取
            self.waveform.waveClicked.connect(self._on_wave_clicked)
            self.waveform.waveScrubbed.connect(self._on_wave_scrubbed)

            # スクロールバー初期設定
            self._update_scroll_range()

        def _on_zoom_in(self):
            current = self.waveform.samples_per_pixel
            new_val = max(1, current // 2)
            self.waveform.set_zoom(new_val)
            self._update_scroll_range()

        def _on_zoom_out(self):
            current = self.waveform.samples_per_pixel
            new_val = min(2000, current * 2)
            self.waveform.set_zoom(new_val)
            self._update_scroll_range()

        def _on_vert_up(self):
            new_zoom = self.waveform.vertical_zoom + 0.2
            self.waveform.set_vertical_zoom(new_zoom)

        def _on_vert_down(self):
            new_zoom = self.waveform.vertical_zoom - 0.2
            if new_zoom < 0.1:
                new_zoom = 0.1
            self.waveform.set_vertical_zoom(new_zoom)

        def _on_scroll_changed(self, value: int):
            self.waveform.set_scroll_position(value)

        def _on_wave_clicked(self, time_sec: float):
            print(f"[DemoWindow] Clicked at {time_sec:.3f} sec.")

        def _on_wave_scrubbed(self, time_sec: float):
            print(f"[DemoWindow] Scrubbing at {time_sec:.3f} sec.")

        def _update_scroll_range(self):
            """
            波形の表示サンプル数が変わったり、リサイズ時にスクロールバーの最大値を更新。
            """
            if self.waveform.audio_data is None:
                return

            max_scroll = max(0, len(self.waveform.audio_data) - self.waveform.visible_samples_count())
            self.scroll_bar.setRange(0, max_scroll)
            current_scroll = self.scroll_bar.value()
            if current_scroll > max_scroll:
                self.scroll_bar.setValue(max_scroll)


    def demo_main():
        app = QApplication(sys.argv)
        demo = WaveformDemoWindow()
        demo.show()
        sys.exit(app.exec_())

    demo_main()
