# PROJECT_ROOT/main/ui/preview_3d.py
# -*- coding: utf-8 -*-

"""
preview_3d.py

タイムラインエディタなどで利用する3Dプレビューウィジェットを提供するモジュール。
MMDモデル・GMod向けモデルなどを読み込み、アニメーションをプレビューできる構成を想定。

変更点:
1. Stopボタンを追加し、再生位置のリセットと再描画を行う。
2. ミュートフラグを保持し、音声再生との連動に備える。
3. set_time(), set_frame() により、好きな時刻/フレームへシーク可能
4. play() / pause() / stop() 内部で QTimer を使って自動更新するが、
   外部からも「現在時刻を指定 → 3Dモデル更新」という同期が行える。

このサンプルでは実際に MMD/GMod モデルやアニメをレンダリングする処理は
ダミーとして省略しています。OpenGLやPyOpenGLを用いた最低限の描画のみを行い、
フレーム単位での更新箇所を示す実装例です。

依存:
    PyQt5, PyOpenGL
    (実際のMMD/GMod読み込みには PyMMD, Assimp など別途ライブラリが必要です)
"""

import sys
import math
from typing import Optional

from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QFileDialog, QApplication,
    QLabel, QDoubleSpinBox
)
from PyQt5.QtOpenGL import QGLWidget, QGLFormat

# PyOpenGL
try:
    from OpenGL import GL
except ImportError:
    print("PyOpenGL がインストールされていません。3D描画には PyOpenGL が必要です。")


class GLViewport(QGLWidget):
    """
    OpenGL描画を行うウィジェット。3Dモデルのレンダリングやアニメーション表示を担当。
    以下はサンプルとして回転する三角形を描画するのみ。
    """

    def __init__(self, parent=None):
        gl_format = QGLFormat()
        gl_format.setSampleBuffers(True)
        super(GLViewport, self).__init__(gl_format, parent)
        self.setMinimumSize(400, 300)

        # アニメーション関連ステート
        self.current_time = 0.0       # 現在のアニメーション時刻 (秒)
        self.playback_speed = 1.0     # 再生速度 (1.0 = 等倍)
        self.animation_playing = False

        # 3Dモデル用のダミープロパティ
        self.model_path = None
        self.anim_path = None
        self.rotation_angle = 0.0     # 回転アニメ用の内部カウンタ (ダミー)

        # ミュートフラグ (音声連動する場合に備えて保持するのみ)
        self.is_muted = False

        # 1フレームあたり約16msでタイマーを回す (60fps目安)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_update_frame)
        self.timer.setInterval(16)

    def initializeGL(self):
        GL.glClearColor(0.15, 0.15, 0.15, 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def resizeGL(self, w, h):
        GL.glViewport(0, 0, w, h)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        # 適当な透視投影
        GL.glFrustum(-0.1, 0.1, -0.1 * h / w, 0.1 * h / w, 0.2, 100.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)

    def paintGL(self):
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glLoadIdentity()

        # カメラ的に少し手前に引く
        GL.glTranslatef(0.0, 0.0, -3.0)

        # 回転を適用 (ダミー)
        GL.glRotatef(self.rotation_angle, 0.0, 1.0, 0.0)

        # 簡易な三角形を描画
        GL.glBegin(GL.GL_TRIANGLES)
        GL.glColor3f(1.0, 0.0, 0.0)
        GL.glVertex3f(-0.5, -0.5, 0.0)
        GL.glColor3f(0.0, 1.0, 0.0)
        GL.glVertex3f(0.5, -0.5, 0.0)
        GL.glColor3f(0.0, 0.0, 1.0)
        GL.glVertex3f(0.0, 0.5, 0.0)
        GL.glEnd()

    def _on_update_frame(self):
        """
        タイマーによる自動更新で再生中のアニメーションフレームを進める処理。
        playback_speed で現在時刻を進め、モデルの姿勢を更新するなど行う想定。
        """
        if not self.animation_playing:
            return

        # 時間を進める (等倍速度で16ms、再生速度があれば× playback_speed)
        delta_sec = 0.016 * self.playback_speed
        self.current_time += delta_sec

        # 回転アニメの簡易例
        self.rotation_angle += 1.0 * self.playback_speed
        if self.rotation_angle >= 360.0:
            self.rotation_angle -= 360.0

        # 実際には self.current_time を元に、モデルやモーションを更新する
        self.update()

    # ----------------------------
    #  モーション再生制御系
    # ----------------------------
    def play(self):
        """再生開始"""
        self.animation_playing = True
        self.timer.start()

    def pause(self):
        """一時停止"""
        self.animation_playing = False
        self.timer.stop()

    def stop(self):
        """停止(時刻リセット)"""
        self.animation_playing = False
        self.timer.stop()
        self.current_time = 0.0
        self.rotation_angle = 0.0
        self.update()

    def load_model(self, model_path: str):
        """
        MMDやGModモデルの読み込みを想定。
        """
        self.model_path = model_path
        print(f"[GLViewport] load_model: {model_path}")
        # TODO: 実際の読み込み処理 (PyMMD, Assimp など)

    def load_animation(self, anim_path: str):
        """
        VMD/JSONなどのモーションデータを読み込む想定。
        """
        self.anim_path = anim_path
        self.current_time = 0.0
        self.rotation_angle = 0.0
        print(f"[GLViewport] load_animation: {anim_path}")
        # TODO: モーションデータを解析・フレームリスト保持など

    # ----------------------------
    #  外部からの同期用メソッド
    # ----------------------------
    def set_playback_speed(self, speed: float):
        """
        再生速度を指定 (0.5 = half, 2.0 = doubleなど)
        """
        self.playback_speed = max(speed, 0.0)
        print(f"[GLViewport] set_playback_speed: {self.playback_speed}")

    def set_time(self, time_sec: float):
        """
        タイムラインの時刻に同期するように外部から指定。
        """
        self.current_time = max(time_sec, 0.0)
        print(f"[GLViewport] set_time: {self.current_time:.3f}s")
        # (ダミー) rotation_angle を current_time に応じて変える
        self.rotation_angle = (self.current_time * 60.0) % 360.0
        self.update()

    def set_frame(self, frame_index: int, fps: int = 30):
        """
        フレーム番号でジャンプする例
        """
        time_sec = frame_index / float(fps)
        self.set_time(time_sec)

    def set_mute(self, mute: bool):
        """
        ミュート状態をセット。実際の音声再生は AudioPlayer だが、
        ここでは「3Dプレビュー側のミュート状態」を保持するだけ。
        """
        self.is_muted = mute
        print(f"[GLViewport] set_mute: {mute}")


class ThreeDPreviewWidget(QWidget):
    """
    3Dプレビューを含むUI。以下の機能を追加:
      - 再生速度、ミュートフラグなどを設定
      - set_time(), set_frame() などタイムライン連動メソッドへの簡易アクセス
    """

    def __init__(self, parent=None):
        super(ThreeDPreviewWidget, self).__init__(parent)
        self.setWindowTitle("3D Preview (Updated)")
        self.layout_main = QVBoxLayout(self)
        self.setLayout(self.layout_main)

        self.gl_viewport = GLViewport(parent=self)
        self.layout_main.addWidget(self.gl_viewport)

        # ボタン類: モデル・アニメ読み込み + 再生/停止
        ctrl_layout = QHBoxLayout()

        self.btn_load_model = QPushButton("Load Model")
        self.btn_load_model.clicked.connect(self._on_click_load_model)
        ctrl_layout.addWidget(self.btn_load_model)

        self.btn_load_anim = QPushButton("Load Animation")
        self.btn_load_anim.clicked.connect(self._on_click_load_anim)
        ctrl_layout.addWidget(self.btn_load_anim)

        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self.gl_viewport.play)
        ctrl_layout.addWidget(self.btn_play)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.gl_viewport.pause)
        ctrl_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.gl_viewport.stop)
        ctrl_layout.addWidget(self.btn_stop)

        self.layout_main.addLayout(ctrl_layout)

        # 下部コントロール: 再生速度 / シーク / ミュート
        bottom_ctrl = QHBoxLayout()

        self.speed_label = QLabel("Speed:")
        bottom_ctrl.addWidget(self.speed_label)

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.0, 10.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.valueChanged.connect(self._on_speed_changed)
        bottom_ctrl.addWidget(self.speed_spin)

        self.btn_mute = QPushButton("Mute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.toggled.connect(self._on_mute_toggled)
        bottom_ctrl.addWidget(self.btn_mute)

        self.layout_main.addLayout(bottom_ctrl)

    def _on_click_load_model(self):
        """
        3Dモデルを選択して読み込む。
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select 3D Model",
            "", "3D Model Files (*.pmx *.pmd *.mdl *.fbx *.obj);;All Files (*)"
        )
        if file_path:
            self.gl_viewport.load_model(file_path)

    def _on_click_load_anim(self):
        """
        アニメーション(VMD/JSONなど)を選択して読み込む。
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Animation",
            "", "Animation Files (*.vmd *.json);;All Files (*)"
        )
        if file_path:
            self.gl_viewport.load_animation(file_path)

    def _on_speed_changed(self, val: float):
        """
        スピンボックスで再生速度を変えたとき
        """
        self.gl_viewport.set_playback_speed(val)

    def _on_mute_toggled(self, checked: bool):
        """
        ミュートボタンが押されたとき
        """
        self.gl_viewport.set_mute(checked)

    # -------------------------------------------------------------
    # 以下、タイムラインエディタなどから呼ばれる想定の補助メソッド例
    # -------------------------------------------------------------
    def set_time(self, time_sec: float):
        """
        タイムライン上の現在時刻に合わせてプレビューを更新する例。
        外部から呼ばれることを想定。
        """
        self.gl_viewport.set_time(time_sec)

    def set_frame(self, frame_index: int, fps: int = 30):
        """
        フレーム番号で同期する場合の例。
        """
        self.gl_viewport.set_frame(frame_index, fps)


def demo_main():
    app = QApplication(sys.argv)
    window = ThreeDPreviewWidget()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    demo_main()
