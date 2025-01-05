# main/utils/playback_controller.py
# -*- coding: utf-8 -*-

"""
playback_controller.py

音声再生やタイムライン・3Dプレビューとの同期を一元管理するクラス。

主な機能:
    1. AudioPlayer のロード/再生制御 (play, pause, stop, set_position など)
    2. TimelineGraphicsView および WaveformWidget への再生ヘッド位置を更新
    3. 3Dプレビュー (ThreeDPreviewWidget) の set_time() を呼び出し、モーション連動
    4. 再生速度やミュートの一括設定 (音声 + 3Dプレビュー)
    5. (オプション) QTimer または AudioPlayer の positionChanged シグナルで再生位置をポーリング/受け取り

注意点:
    - AudioPlayer や timeline_view, waveform_widget, three_d_preview は既に存在しインスタンス化済みとする
    - これらをコンストラクタに渡し、PlaybackController が接着剤として機能する
    - シンプルな例では positionChanged 信号を AudioPlayer 側で受け取るたびに各ビューを更新
"""

import os
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

# 他のモジュール例
# from main.utils.audio_player import AudioPlayer
# from main.ui.waveform_widget import WaveformWidget
# from main.ui.preview_3d import ThreeDPreviewWidget
# from main.ui.timeline_editor import TimelineGraphicsView

class PlaybackController(QObject):
    """
    音声再生とUIコンポーネントを同期させるコントローラクラス。
    - AudioPlayer から positionChanged を受け取り、タイムライン/波形/3Dプレビューを更新
    - ユーザ操作（波形クリック、タイムラインドラッグなど）で音声再生位置を変更
    - 再生速度やミュートの一括管理
    """

    def __init__(self, audio_player, timeline_view=None, waveform_widget=None, three_d_preview=None, parent=None):
        """
        Args:
            audio_player (AudioPlayer): 音声再生を行うラッパクラス
            timeline_view (TimelineGraphicsView): タイムライン描画用ビュー（再生ヘッドの更新に使用）
            waveform_widget (WaveformWidget): 音声波形の描画用ウィジェット
            three_d_preview (ThreeDPreviewWidget): 3Dプレビューのウィジェット
        """
        super().__init__(parent)
        self.audio_player = audio_player
        self.timeline_view = timeline_view
        self.waveform_widget = waveform_widget
        self.three_d_preview = three_d_preview

        self._playback_speed = 1.0
        self._is_muted = False

        # AudioPlayer からのシグナルを受け取り、再生位置をUIと同期
        if self.audio_player is not None:
            self.audio_player.positionChanged.connect(self._on_audio_position_changed)
            # on_finished シグナルなども処理したい場合
            self.audio_player.on_finished.connect(self._on_audio_finished)

        # WaveformWidget 側のクリックイベントで再生位置を合わせる例
        if self.waveform_widget is not None:
            self.waveform_widget.waveClicked.connect(self._on_waveform_clicked)

        # タイムライン（ドラッグで移動などがあれば）にもシグナルを用意していれば接続できる

    # ---------------------------------------------------------------------
    # 1) 音声ファイルのロードと制御
    # ---------------------------------------------------------------------
    def load_audio_file(self, file_path: str) -> bool:
        """
        音声ファイルをAudioPlayerにロード。
        Returns:
            bool: 成功すればTrue
        """
        if not os.path.exists(file_path):
            print(f"[PlaybackController] File not found: {file_path}")
            return False
        return self.audio_player.load_audio_file(file_path)

    def play(self):
        """
        再生開始。
        AudioPlayer → play()
        3Dプレビュー → 再生速度設定, set_mute
        """
        if self.audio_player is None:
            return

        # 音声再生
        self.audio_player.set_rate(self._playback_speed)
        self.audio_player.set_mute(self._is_muted)
        self.audio_player.play()

        # 3Dプレビューも開始 (ただし 3D側で自動再生するか、時間同期は positionChanged でやるか要調整)
        if self.three_d_preview:
            self.three_d_preview.gl_viewport.set_playback_speed(self._playback_speed)
            self.three_d_preview.gl_viewport.set_mute(self._is_muted)
            self.three_d_preview.gl_viewport.play()

    def pause(self):
        """
        一時停止。
        AudioPlayer → pause()
        3Dプレビュー → pause() (時間同期)
        """
        if self.audio_player:
            self.audio_player.pause()

        if self.three_d_preview:
            self.three_d_preview.gl_viewport.pause()

    def stop(self):
        """
        停止。
        AudioPlayer → stop()
        タイムライン/波形の表示も先頭へ戻す
        3Dプレビュー → stop()
        """
        if self.audio_player:
            self.audio_player.stop()
        if self.three_d_preview:
            self.three_d_preview.gl_viewport.stop()

        # 再生ヘッドを先頭(0.0)へ
        if self.timeline_view:
            self.timeline_view.update_playhead_position(0.0)
        if self.waveform_widget:
            self.waveform_widget.set_cursor_time(0.0)

    # ---------------------------------------------------------------------
    # 2) 再生位置をUIへ反映
    # ---------------------------------------------------------------------
    @pyqtSlot(int)
    def _on_audio_position_changed(self, position_ms: int):
        """
        AudioPlayer.positionChanged シグナルを受け取り、
        タイムラインや波形、3Dプレビューへ現在の再生時刻(秒)を反映。
        """
        current_time_sec = position_ms / 1000.0

        # Timeline
        if self.timeline_view:
            self.timeline_view.update_playhead_position(current_time_sec)

        # Waveform
        if self.waveform_widget:
            self.waveform_widget.set_cursor_time(current_time_sec)

        # 3D Preview
        if self.three_d_preview:
            self.three_d_preview.set_time(current_time_sec)

    @pyqtSlot()
    def _on_audio_finished(self):
        """
        再生終了(EndOfMedia)をAudioPlayerから受け取った時の処理。
        例: 自動で停止状態に戻す。
        """
        print("[PlaybackController] Audio playback finished.")
        # 3Dプレビューも止める
        if self.three_d_preview:
            self.three_d_preview.gl_viewport.stop()
        # 再生ヘッドを末尾にしておく or 先頭に戻す
        duration_ms = self.audio_player.get_duration() if self.audio_player else 0
        duration_sec = duration_ms / 1000.0
        if self.timeline_view:
            self.timeline_view.update_playhead_position(duration_sec)
        if self.waveform_widget:
            self.waveform_widget.set_cursor_time(duration_sec)

    # ---------------------------------------------------------------------
    # 3) ユーザが波形等をクリック→シーク
    # ---------------------------------------------------------------------
    @pyqtSlot(float)
    def _on_waveform_clicked(self, time_sec: float):
        """
        waveClicked(float) シグナルを受け取って、
        AudioPlayerの再生位置を time_sec にシークし、UIも同期。
        """
        if self.audio_player:
            # ミリ秒単位に変換
            position_ms = int(time_sec * 1000)
            self.audio_player.set_position(position_ms)

    # ---------------------------------------------------------------------
    # 4) 再生速度・ミュート関連
    # ---------------------------------------------------------------------
    def set_playback_speed(self, speed: float):
        """
        音声 + 3Dプレビュー に再生速度を適用。
        """
        if speed <= 0.0:
            speed = 0.1
        self._playback_speed = speed

        if self.audio_player:
            self.audio_player.set_rate(self._playback_speed)
        if self.three_d_preview:
            self.three_d_preview.gl_viewport.set_playback_speed(self._playback_speed)

    def set_mute(self, mute: bool):
        """
        音声 + 3Dプレビュー をミュート。
        """
        self._is_muted = mute
        if self.audio_player:
            self.audio_player.set_mute(mute)
        if self.three_d_preview:
            self.three_d_preview.gl_viewport.set_mute(mute)

    # ---------------------------------------------------------------------
    # 5) 任意の時刻(秒)にジャンプ (タイムラインのドラッグ操作など)
    # ---------------------------------------------------------------------
    def seek_to_time(self, time_sec: float):
        """
        コード上で任意の時刻(秒)に音声・プレビューを同期して移動。
        """
        if time_sec < 0.0:
            time_sec = 0.0

        # Audio
        if self.audio_player:
            position_ms = int(time_sec * 1000)
            self.audio_player.set_position(position_ms)

        # Timeline
        if self.timeline_view:
            self.timeline_view.update_playhead_position(time_sec)

        # Waveform
        if self.waveform_widget:
            self.waveform_widget.set_cursor_time(time_sec)

        # 3D
        if self.three_d_preview:
            self.three_d_preview.set_time(time_sec)
