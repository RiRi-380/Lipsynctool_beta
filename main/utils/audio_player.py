# main/utils/audio_player.py
# -*- coding: utf-8 -*-

"""
audio_player.py

オーディオファイルの再生・一時停止・停止・シークなどを扱うクラス。
PyQt5のQMediaPlayerを利用したシンプルなラッパとして機能します。

[依存ライブラリ例]
    pip install PyQt5

変更ポイント:
1. positionChanged, on_finished シグナルを使ってGUI側と連携しやすく
2. set_rate(再生速度)や set_mute(ミュート)などを整理
3. 不要なコードや重複処理を削除し、最小限のオーディオ再生管理機能に集中
4. ロード失敗時のハンドリングを若干わかりやすく
"""

import os
from PyQt5.QtCore import QUrl, pyqtSignal, QObject
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent


class AudioPlayer(QObject):
    """
    PyQt5 の QMediaPlayer を使って音声ファイルを再生するためのラッパクラス。
    機能例:
        - load_audio_file(file_path): 音声ファイルを読み込み準備
        - play(), pause(), stop()
        - set_volume(0~100), set_mute(True/False), set_rate(速度倍率)
        - set_position(ms), get_position(), get_duration()
        - シグナル:
            - on_finished: 再生完了時に発火 (EndOfMedia)
            - positionChanged(int): 再生位置(ミリ秒)が変化したら発火
    """

    on_finished = pyqtSignal()
    positionChanged = pyqtSignal(int)  # 再生位置が変わるたびにミリ秒単位で通知

    def __init__(self, parent=None):
        super().__init__(parent)

        # QMediaPlayer の初期化
        self._player = QMediaPlayer(parent, QMediaPlayer.StreamPlayback)
        self._player.stateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        # 再生位置が変わった際に自前のシグナルを発行
        self._player.positionChanged.connect(self._on_position_changed_internal)

        # デフォルト音量 (0~100)
        self._player.setVolume(80)

    # ---------------------------
    # 1) メディアロード & 再生制御
    # ---------------------------
    def load_audio_file(self, file_path: str) -> bool:
        """
        指定した音声ファイルを読み込み、再生可能な状態にする。

        Args:
            file_path (str): ローカル音声ファイルのパス

        Returns:
            bool: 音声の読み込みが成功したかどうか
        """
        if not os.path.exists(file_path):
            print(f"[AudioPlayer] File not found: {file_path}")
            return False

        media_url = QUrl.fromLocalFile(file_path)
        if not media_url.isValid():
            print(f"[AudioPlayer] Invalid QUrl from: {file_path}")
            return False

        self._player.setMedia(QMediaContent(media_url))
        return True

    def play(self):
        """再生開始(または再開)"""
        if self._player.mediaStatus() == QMediaPlayer.NoMedia:
            print("[AudioPlayer] No media loaded. Cannot play.")
            return
        self._player.play()

    def pause(self):
        """一時停止"""
        if self._player.state() == QMediaPlayer.PlayingState:
            self._player.pause()

    def stop(self):
        """再生を停止し、頭出し状態にする"""
        self._player.stop()

    # ---------------------------
    # 2) 音量・ミュート・再生速度
    # ---------------------------
    def set_volume(self, volume: int):
        """
        音量を 0~100 で設定
        """
        volume_clamped = max(0, min(100, volume))
        self._player.setVolume(volume_clamped)

    def set_mute(self, mute: bool):
        """
        ミュートオン/オフ
        """
        self._player.setMuted(mute)

    def is_muted(self) -> bool:
        """ミュート中か"""
        return self._player.isMuted()

    def set_rate(self, rate: float):
        """
        再生速度倍率 (例: 0.5=半速, 2.0=2倍)
        """
        if rate <= 0.0:
            rate = 0.1
        elif rate > 4.0:
            rate = 4.0

        self._player.setPlaybackRate(rate)

    # ---------------------------
    # 3) 再生位置操作 & 取得
    # ---------------------------
    def set_position(self, position_ms: int):
        """
        再生位置をミリ秒単位で設定
        """
        self._player.setPosition(position_ms)

    def get_position(self) -> int:
        """
        現在の再生位置 (ms)
        """
        return self._player.position()

    def get_duration(self) -> int:
        """
        メディア全体の長さ (ms)
        """
        return self._player.duration()

    # ---------------------------
    # 4) 状態確認
    # ---------------------------
    def is_playing(self) -> bool:
        """再生中か"""
        return self._player.state() == QMediaPlayer.PlayingState

    def is_paused(self) -> bool:
        """一時停止中か"""
        return self._player.state() == QMediaPlayer.PausedState

    def is_stopped(self) -> bool:
        """停止中か"""
        return self._player.state() == QMediaPlayer.StoppedState

    # ---------------------------
    # 5) 内部シグナルハンドラ
    # ---------------------------
    def _on_state_changed(self, new_state):
        """
        QMediaPlayer の stateChanged シグナル
        """
        # 再生が終わった後にStoppedStateへ移行するときにもここが呼ばれるが、
        # 完全な終了タイミングは mediaStatusChanged で EndOfMedia を見る方が正確
        pass

    def _on_media_status_changed(self, status):
        """
        mediaStatusChanged シグナル
        """
        from PyQt5.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.EndOfMedia:
            self.on_finished.emit()
            print("[AudioPlayer] Playback finished.")

    def _on_position_changed_internal(self, position_ms: int):
        """
        positionChanged シグナルハンドラ
        """
        self.positionChanged.emit(position_ms)
        # ここでprintを出すと多量に出る可能性があるため省略
        # print(f"[AudioPlayer] position = {position_ms} ms")
