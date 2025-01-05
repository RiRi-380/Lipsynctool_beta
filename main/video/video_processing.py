# -*- coding: utf-8 -*-
"""
video_processing.py

動画から音声を抽出したり、GPUアクセラレーションによる処理などを行うユーティリティクラス。

[主な機能]
  - 動画ファイルに含まれる音声トラックを .wav 等に抽出
  - moviepy または ffmpeg コマンドを直接呼び出して音声を取り出す
  - キャッシュ機能により、同じファイル名の出力が既にあれば再抽出をスキップ (オプション)
  - オプション: 音量正規化や余分なサイレンスの除去などのポストプロセス

[依存ライブラリ]
  - moviepy (pip install moviepy)
    ※特定バージョンでエラーが出る場合は以下のようにバージョンを指定してインストールすると改善することがあります:
       pip install "moviepy==1.0.3"
  - ffmpeg がコマンドとして使える状態 (PATH 通過 or フルパス指定)
  - Python >= 3.6 などを想定

[追加の拡張例]
  - lip_sync_config.json (もし存在すれば) から 'processing_options' や 'video_settings' を読み込んで
    音声抽出のサンプルレート / チャンネル数 / コーデックを自動設定
  - 音声抽出後に音量正規化を行う関数 _post_process_audio()

[使い方の例]
  from main.video.video_processing import VideoProcessor

  video_path = "input_video.mp4"
  vp = VideoProcessor(
      output_audio_dir="./audio_output",
      enable_cache=True,
      use_ffmpeg_direct=False,
      gpu_accel=False
  )
  extracted_audio_path = vp.extract_audio_from_video(video_path)
  print("抽出された音声ファイル:", extracted_audio_path)
"""

import os
import subprocess
import logging

# moviepy.editor のインポート部分でバージョン差によるエラーが出る場合は、
# pip install --upgrade moviepy などを試すか、
# pip install "moviepy==1.0.3" などバージョン固定で回避を試してください。
from moviepy.editor import VideoFileClip

try:
    # 設定ファイルを読み込みたい場合 (任意)
    import json
except ImportError:
    pass


class VideoProcessor:
    def __init__(
        self,
        output_audio_dir: str = "./audio_output",
        enable_cache: bool = True,
        use_ffmpeg_direct: bool = False,
        gpu_accel: bool = False,
        audio_codec: str = "pcm_s16le",
        audio_sample_rate: int = 44100,
        audio_channels: int = 2,
        enable_normalization: bool = False,
        config_path: str = ""
    ) -> None:
        """
        VideoProcessor クラスの初期化

        Args:
            output_audio_dir (str): 抽出した音声ファイルを保存するディレクトリ
            enable_cache (bool): Trueの場合、同名ファイルが存在すれば再抽出をスキップ
            use_ffmpeg_direct (bool): Trueの場合、moviepyを経由せずにffmpegコマンドを直接呼び出し
            gpu_accel (bool): Trueの場合、GPUアクセラレーション付きエンコーダ/デコーダを使用 (環境依存)
            audio_codec (str): 音声抽出時に使用するコーデック (ffmpegコマンドでの指定; 例: "pcm_s16le")
            audio_sample_rate (int): 抽出時のサンプリングレート (Hz)
            audio_channels (int): 抽出時のチャンネル数 (例: 2でステレオ)
            enable_normalization (bool): Trueの場合、抽出後に簡易的な音量正規化を行う
            config_path (str): (任意) lip_sync_config.json等のパスを指定すると、そこから設定を読み込む例
        """
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.output_audio_dir = output_audio_dir
        self.enable_cache = enable_cache
        self.use_ffmpeg_direct = use_ffmpeg_direct
        self.gpu_accel = gpu_accel

        self.audio_codec = audio_codec
        self.audio_sample_rate = audio_sample_rate
        self.audio_channels = audio_channels
        self.enable_normalization = enable_normalization

        # 出力フォルダが存在しない場合は作成
        if not os.path.exists(self.output_audio_dir):
            os.makedirs(self.output_audio_dir, exist_ok=True)

        # (オプション) 設定ファイルの読み込みを行う例
        # config_path があれば、audio_codec, audio_sample_rate等を上書きしても良い
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                video_settings = config_data.get("video_settings", {})
                # 例: config内に "video_settings": { "audio_codec": "pcm_s16le", "sample_rate": 22050 } があれば反映
                if "audio_codec" in video_settings:
                    self.audio_codec = video_settings["audio_codec"]
                if "sample_rate" in video_settings:
                    self.audio_sample_rate = video_settings["sample_rate"]
                if "channels" in video_settings:
                    self.audio_channels = video_settings["channels"]
                self.logger.debug(f"[VideoProcessor] configより設定を読み込みました: {video_settings}")
            except Exception as e:
                self.logger.warning(f"[VideoProcessor] config読み込み失敗: {e}")

    def extract_audio_from_video(self, video_file: str) -> str:
        """
        動画ファイルから音声を抽出するメインメソッド。

        Args:
            video_file (str): 動画ファイルのパス

        Returns:
            str: 抽出された音声ファイル(.wavなど)のパス
        
        Raises:
            FileNotFoundError: 動画ファイルが見つからない場合
            RuntimeError: 抽出に失敗した場合
        """
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"[VideoProcessor] 動画ファイルが見つかりません: {video_file}")

        # 出力先ファイル名を生成
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        audio_file = os.path.join(self.output_audio_dir, f"{base_name}.wav")

        # キャッシュ機能 (同名ファイルが存在すればスキップ)
        if self.enable_cache and os.path.exists(audio_file):
            self.logger.debug(f"[VideoProcessor] キャッシュを使用します: {audio_file}")
            return audio_file

        if self.use_ffmpeg_direct:
            # ffmpeg コマンドを直接実行して抽出
            self._extract_with_ffmpeg(video_file, audio_file)
        else:
            # moviepy を使って抽出
            self._extract_with_moviepy(video_file, audio_file)

        if self.enable_normalization:
            self._post_process_audio(audio_file)

        return audio_file

    def _extract_with_moviepy(self, video_file: str, audio_file: str) -> None:
        """
        moviepy を用いて音声抽出を行う内部メソッド。

        Args:
            video_file (str): 入力動画ファイル
            audio_file (str): 出力音声ファイルパス
        
        Raises:
            ValueError: 映像に音声トラックが存在しない場合
            RuntimeError: 抽出処理に失敗した場合
        """
        try:
            with VideoFileClip(video_file) as clip:
                # 音声が存在しない場合
                if clip.audio is None:
                    raise ValueError("[VideoProcessor] 動画に音声トラックが存在しません。")

                # moviepy による音声抽出
                # pcm_s16le コーデック、44100Hz、16bit (nbytes=2) ステレオで出力
                self.logger.debug(f"[VideoProcessor] moviepyで音声抽出: {video_file} -> {audio_file}")
                clip.audio.write_audiofile(
                    audio_file,
                    fps=self.audio_sample_rate,
                    nbytes=2,
                    codec=self.audio_codec
                )
        except Exception as e:
            raise RuntimeError(f"[VideoProcessor] moviepy経由の音声抽出に失敗: {e}")

    def _extract_with_ffmpeg(self, video_file: str, audio_file: str) -> None:
        """
        ffmpeg コマンドを直接実行して音声を抽出する内部メソッド。

        Args:
            video_file (str): 入力動画ファイル
            audio_file (str): 出力音声ファイルパス

        Raises:
            RuntimeError: ffmpeg コマンドが失敗した場合
        """
        cmd = [
            "ffmpeg",
            "-y",  # 上書き許可
            "-i", video_file,
            "-vn",  # 映像無し (音声のみを抽出)
            "-acodec", self.audio_codec,
            "-ar", str(self.audio_sample_rate),
            "-ac", str(self.audio_channels),
            audio_file
        ]

        if self.gpu_accel:
            # 例えばハードウェアデコードを使いたい場合 (要 ffmpegビルド設定):
            # cmd.insert(1, "-hwaccel")
            # cmd.insert(2, "cuda")
            pass

        self.logger.debug(f"[VideoProcessor] ffmpegコマンド実行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                err_msg = result.stderr.strip()
                raise RuntimeError(
                    f"[VideoProcessor] ffmpeg音声抽出に失敗 (returncode={result.returncode}): {err_msg}"
                )
        except FileNotFoundError:
            raise RuntimeError("[VideoProcessor] ffmpeg がインストールされていない可能性があります。")
        except Exception as e:
            raise RuntimeError(f"[VideoProcessor] ffmpeg音声抽出中にエラー: {e}")

    def _post_process_audio(self, audio_file: str) -> None:
        """
        (例) 抽出した音声ファイルに対して簡易的な音量正規化を行う。
        実際には pydub / ffmpeg / sox などを利用するとより柔軟。

        Raises:
            RuntimeError: 正規化に失敗した場合
        """
        self.logger.debug(f"[VideoProcessor] 音量正規化 (簡易): {audio_file}")

        # ここでは ffmpeg を用いたダミー実装例（loudnorm フィルタなど）
        # ffmpeg -i input.wav -af loudnorm output_norm.wav
        norm_file = os.path.splitext(audio_file)[0] + "_norm.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_file,
            "-af", "loudnorm",
            norm_file
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                err_msg = result.stderr.strip()
                raise RuntimeError(f"[VideoProcessor] 音量正規化に失敗: {err_msg}")

            # 正規化版を元のファイル名に上書き
            os.remove(audio_file)
            os.rename(norm_file, audio_file)
            self.logger.debug(f"[VideoProcessor] 正規化ファイルを上書き保存しました: {audio_file}")
        except Exception as e:
            self.logger.warning(f"[VideoProcessor] 音量正規化に失敗: {e}")


def _demo():
    """
    このモジュールを単独で実行した場合に動作するデモ用関数。
    例: python video_processing.py
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python video_processing.py <video_file>")
        return

    test_video_path = sys.argv[1]  # コマンドライン引数から動画パスを取得
    processor = VideoProcessor(
        output_audio_dir="./audio_output",
        enable_cache=True,
        use_ffmpeg_direct=False,
        gpu_accel=False,
        audio_codec="pcm_s16le",
        audio_sample_rate=44100,
        audio_channels=2,
        enable_normalization=True  # 音量正規化を有効にしてみる
    )

    try:
        extracted_audio = processor.extract_audio_from_video(test_video_path)
        print(f"[_demo] 抽出された音声ファイル -> {extracted_audio}")
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"デモ中にエラー: {e}")


if __name__ == "__main__":
    _demo()
