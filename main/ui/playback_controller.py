# main/ui/playback_controller.py
# -*- coding: utf-8 -*-

"""
playback_controller.py

音声再生(AudioPlayer)、3Dプレビュー(ThreeDPreviewWidget)、タイムラインや波形表示など
複数の要素をまとめて制御し、同期をとるためのコントローラクラス。

[主な役割]
1. AudioPlayer での音声再生位置を監視し、再生中は定期的に 3Dプレビューや
   WaveformWidget・TimelineGraphicsView などに「現在の再生位置」を反映する。
2. 再生速度・ミュート設定を一括で扱い、AudioPlayer と 3Dプレビューの両方に反映する。
3. 再生完了時（音声が最後まで再生された）に 3Dプレビューを停止状態に戻す。など。
4. 再生ヘッド（現在の時刻）をユーザーが動かしたときのシーク処理も一元管理する。

[依存]
- PyQt5
- main.utils.audio_player.AudioPlayer
- main.ui.preview_3d.ThreeDPreviewWidget
- main.ui.waveform_widget.WaveformWidget (任意)
- あるいは timeline_editor 内の QGraphicsScene など (任意)

[使い方の例]
    from main.ui.playback_controller import PlaybackController
    from main.utils.audio_player import AudioPlayer
    from main.ui.preview_3d import ThreeDPreviewWidget
    from main.ui.waveform_widget import WaveformWidget

    audio_player = AudioPlayer()
    preview_3d = ThreeDPreviewWidget()
    waveform = WaveformWidget()

    controller = PlaybackController(
        audio_player=audio_player,
        preview_3d=preview_3d,
        waveform=waveform
    )

    # 音声ファイルを読み込み
    audio_player.load_audio_file("sample.wav")

    # 3Dアニメファイルを読み込み
    preview_3d.gl_viewport.load_model("model.pmx")
    preview_3d.gl_viewport.load_animation("motion.vmd")

    # 再生
    controller.play()

"""

import sys
from typing import Optional

from PyQt5.QtCore import (
    QObject, QTimer, pyqtSlot
)

# AudioPlayer: QMediaPlayer のラッパ (main/utils/audio_player.py)
from main.utils.audio_player import AudioPlayer

# 3Dプレビューウィジェット (main/ui/preview_3d.py)
from main.ui.preview_3d import ThreeDPreviewWidget

# 波形ウィジェット (main/ui/waveform_widget.py) - 任意
# 存在しない場合は None でも動くようにOptionalで扱う
from main.ui.waveform_widget import WaveformWidget


class PlaybackController(QObject):
    """
    複数のUI要素・プレイヤーを同期させるためのコントローラ。
    例:
      - AudioPlayer を再生開始すると同時に 3Dプレビューをplay()
      - positionChanged などのシグナル or タイマーで、現在時刻を3Dに set_time()
      - WaveformWidget にも現在位置のカーソルを描画 (要実装)
      - ユーザがUI操作(再生速度変更, mute, シーク)したら AudioPlayer と 3Dプレビュー双方に反映
    """

    def __init__(
        self,
        audio_player: AudioPlayer,
        preview_3d: Optional[ThreeDPreviewWidget] = None,
        waveform: Optional[WaveformWidget] = None,
        parent=None
    ):
        super().__init__(parent)

        self.audio_player = audio_player
        self.preview_3d = preview_3d
        self.waveform = waveform

        # 内部ステート
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(30)  # 30ms ~ 33fps程度
        self._playback_timer.timeout.connect(self._on_update_playback_position)

        # AudioPlayer のシグナル (再生完了検出)
        self.audio_player.on_finished.connect(self._on_audio_finished)

        # 初期値
        self.playback_speed = 1.0
        self.is_muted = False

    # ----------------------------------------------------------------
    # 公開メソッド: 再生・一時停止・停止・シークなど
    # ----------------------------------------------------------------
    def play(self):
        """再生開始"""
        if not self.audio_player.is_playing():
            self.audio_player.play()
        # 3Dプレビュー開始
        if self.preview_3d and not self.preview_3d.gl_viewport.animation_playing:
            self.preview_3d.gl_viewport.play()

        # タイマー開始
        if not self._playback_timer.isActive():
            self._playback_timer.start()

    def pause(self):
        """一時停止"""
        self.audio_player.pause()
        if self.preview_3d:
            self.preview_3d.gl_viewport.pause()

        if self._playback_timer.isActive():
            self._playback_timer.stop()

    def stop(self):
        """停止（再生位置を頭に戻す）"""
        self.audio_player.stop()
        if self.preview_3d:
            self.preview_3d.gl_viewport.stop()

        if self._playback_timer.isActive():
            self._playback_timer.stop()

    def set_playback_speed(self, speed: float):
        """再生速度を設定 (0.5=半速, 2.0=2倍速など)。"""
        self.playback_speed = max(0.01, speed)
        # AudioPlayer 側にも再生レートを設定
        self.audio_player.set_rate(self.playback_speed)
        # 3Dプレビューにも再生速度を設定
        if self.preview_3d:
            self.preview_3d.gl_viewport.set_playback_speed(self.playback_speed)

    def set_mute(self, mute: bool):
        """ミュート/非ミュートを設定。"""
        self.is_muted = mute
        volume = 0 if mute else 80  # お好みの初期値
        self.audio_player.set_volume(volume)

        if self.preview_3d:
            self.preview_3d.gl_viewport.set_mute(mute)

    def seek_to_time(self, time_sec: float):
        """
        任意の秒数位置へジャンプ。
        AudioPlayer と 3Dプレビューを同期させる例。
        """
        # AudioPlayer: positionはミリ秒単位
        ms = int(time_sec * 1000)
        self.audio_player.set_position(ms)

        # 3Dプレビュー
        if self.preview_3d:
            self.preview_3d.gl_viewport.set_time(time_sec)

        # 波形描画カーソルなどもアップデートしたければ行う
        if self.waveform:
            # 例: waveform内に「再生ヘッド位置」を示す仕組みがあれば呼び出す
            pass

    # ----------------------------------------------------------------
    # 内部スロット: 再生中の位置を定期更新
    # ----------------------------------------------------------------
    @pyqtSlot()
    def _on_update_playback_position(self):
        """
        タイマーによって定期的に呼ばれ、AudioPlayerの再生位置を取得し、
        3DプレビューやWaveformに同期する例。
        """
        current_ms = self.audio_player.get_position()
        current_sec = current_ms / 1000.0

        # 3Dプレビューに同期
        if self.preview_3d:
            self.preview_3d.gl_viewport.set_time(current_sec)

        # Waveformにも現在位置を反映するならここで行う
        if self.waveform:
            # 例: wave_cursor などがあれば移動
            # waveform.set_playhead_position(current_sec) のような実装もアリ
            pass

    @pyqtSlot()
    def _on_audio_finished(self):
        """
        音声ファイルの最後まで再生が終わったときに呼ばれるスロット。
        3Dプレビューも停止させるなどの処理を行う。
        """
        # 3Dプレビューを停止
        if self.preview_3d:
            self.preview_3d.gl_viewport.stop()

        # タイマー停止
        if self._playback_timer.isActive():
            self._playback_timer.stop()

        print("[PlaybackController] Audio playback finished. Everything stopped.")
