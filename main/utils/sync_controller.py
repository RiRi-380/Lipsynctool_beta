# main/utils/sync_controller.py
# -*- coding: utf-8 -*-

"""
sync_controller.py

音声プレイヤー (AudioPlayer)、タイムラインエディタ (TimelineEditor)、波形 (WaveformWidget)、
3Dプレビュー (Preview3DWidget) など複数コンポーネントを time 軸で同期させるためのコントローラ。

[主な想定役割]
 1) 再生/停止/シークなどの入力があったら、AudioPlayer と各ビュー（タイムライン, 波形, 3Dプレビュー）に対して
    一元的に時間位置を更新
 2) AudioPlayer の再生進捗 (positionChanged) を受け取り、タイムラインや波形上のカーソルを動かす
 3) Undo/Redo などは直接扱わないが、Time 軸に関する「再生位置変更」の統括を行う

[依存]
 - Python 3.7+
 - PyQt5
 - main.utils.audio_player.AudioPlayer (positionChanged, on_finished シグナル)
 - main.ui.timeline_editor.TimelineEditorWindow 等を呼び出す想定
 - main.ui.waveform_widget.WaveformWidget なども同様に set_cursor_time() メソッド想定
 - main.ui.preview_3d.ThreeDPreviewWidget などにも set_time() メソッドがある想定

[使い方 (例)]
    from main.utils.sync_controller import SyncController
    from main.utils.audio_player import AudioPlayer
    from main.ui.timeline_editor import TimelineEditorWindow
    from main.ui.waveform_widget import WaveformWidget
    from main.ui.preview_3d import ThreeDPreviewWidget

    audio_player = AudioPlayer()
    timeline_editor = TimelineEditorWindow(...)
    waveform = WaveformWidget(...)
    preview_3d = ThreeDPreviewWidget(...)

    sync_ctrl = SyncController(
        audio_player=audio_player,
        timeline_editor=timeline_editor,
        waveform=waveform,
        preview_3d=preview_3d
    )

    # 再生位置が変化 -> on_audio_position_changed -> set_playhead_time / set_cursor_time / set_time
    # GUI上で再生/停止 -> sync_ctrl.play() / sync_ctrl.pause() -> audio_player.play() / ...
    
"""

from typing import Optional

class SyncController:
    """
    AudioPlayer と Timeline/波形/3Dプレビューを時間軸で同期させるコントローラ。
    AudioPlayer から positionChanged シグナルを受け取り、各ビューのカーソルを更新。
    逆に Timeline 上でクリックして再生位置を変えたい場合は set_position() を呼んで
    AudioPlayer 側もシークする。
    """

    def __init__(
        self,
        audio_player=None,          # main.utils.audio_player.AudioPlayer のインスタンス
        timeline_editor=None,       # main.ui.timeline_editor.TimelineEditorWindow
        waveform=None,              # main.ui.waveform_widget.WaveformWidget
        preview_3d=None,            # main.ui.preview_3d.ThreeDPreviewWidget
    ):
        self.audio_player = audio_player
        self.timeline_editor = timeline_editor
        self.waveform = waveform
        self.preview_3d = preview_3d

        # AudioPlayer の positionChanged シグナルを受け取る -> self.on_audio_position_changed
        if self.audio_player and hasattr(self.audio_player, "positionChanged"):
            self.audio_player.positionChanged.connect(self.on_audio_position_changed)
        if self.audio_player and hasattr(self.audio_player, "on_finished"):
            self.audio_player.on_finished.connect(self.on_audio_finished)

        # タイムラインエディタ側でユーザが再生位置を変更する仕組みがあるなら
        #  例: timeline_editor.set_playhead_callback(self.on_timeline_scrub)
        #  などでコールバックを登録して同期させる想定（今回はサンプルに留める）

        # 波形側で waveClicked シグナルがあれば connect する例（オプション）
        # if self.waveform and hasattr(self.waveform, "waveClicked"):
        #     self.waveform.waveClicked.connect(self.on_wave_clicked)

    # -----------------------------------------------------------
    # AudioPlayer 側のシグナルを受け取り、時間位置をビューに反映
    # -----------------------------------------------------------
    def on_audio_position_changed(self, position_ms: int):
        """
        AudioPlayer.positionChanged シグナル受信時。
        全ての関連ビューに対して再生位置を同期する。
        """
        current_sec = position_ms / 1000.0

        # タイムラインエディタ
        if self.timeline_editor and hasattr(self.timeline_editor, "set_playhead_time"):
            self.timeline_editor.set_playhead_time(current_sec)

        # 波形
        if self.waveform and hasattr(self.waveform, "set_cursor_time"):
            self.waveform.set_cursor_time(current_sec)

        # 3Dプレビュー
        if self.preview_3d and hasattr(self.preview_3d, "set_time"):
            self.preview_3d.set_time(current_sec)

    def on_audio_finished(self):
        """
        Audioが最後まで再生された (EndOfMedia) 時の処理。
        例: タイムラインを頭出しに戻すなど。
        """
        # 頭出しにする場合
        if self.timeline_editor and hasattr(self.timeline_editor, "set_playhead_time"):
            self.timeline_editor.set_playhead_time(0.0)

        if self.waveform and hasattr(self.waveform, "set_cursor_time"):
            self.waveform.set_cursor_time(0.0)

        if self.preview_3d and hasattr(self.preview_3d, "set_time"):
            self.preview_3d.set_time(0.0)

    # -----------------------------------------------------------
    # 外部 (タイムラインや波形クリック) から再生位置を変更したいとき
    # -----------------------------------------------------------
    def set_position(self, time_sec: float):
        """
        タイムライン or 波形クリック などでユーザが再生位置を指定した場合、
        AudioPlayer 側をシークし、他ビューも更新する。
        """
        if not self.audio_player:
            return
        pos_ms = int(time_sec * 1000)
        self.audio_player.set_position(pos_ms)
        # on_audio_position_changed が呼ばれて同期される

    # -----------------------------------------------------------
    # 再生・停止・停止などをまとめて行うメソッド (オプション)
    # -----------------------------------------------------------
    def play(self, rate=1.0, mute=False):
        """
        例: ユーザが再生ボタンを押したときに呼ばれる。
        AudioPlayerを再生し、レートやミュートを設定。
        """
        if self.audio_player:
            self.audio_player.set_rate(rate)
            self.audio_player.set_mute(mute)
            self.audio_player.play()

    def pause(self):
        if self.audio_player:
            self.audio_player.pause()

    def stop(self):
        if self.audio_player:
            self.audio_player.stop()
            # 全ビューを頭出しに戻す or 音声位置が0に戻ったら on_audio_position_changed()で連動

    # -----------------------------------------------------------
    # 例: 波形がクリックされた場合のコールバック (scrub)
    # -----------------------------------------------------------
    def on_wave_clicked(self, time_sec: float):
        """
        WaveformWidget.waveClicked -> ここでAudioPlayerシークなど
        """
        self.set_position(time_sec)

    def on_timeline_scrub(self, time_sec: float):
        """
        タイムラインのドラッグ操作などで再生位置を変えたときの例。
        """
        self.set_position(time_sec)
