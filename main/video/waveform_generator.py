import os
import numpy as np
import librosa
import matplotlib.pyplot as plt

# librosa.display は librosa>=0.7 以降で別モジュール化されているため、
# バージョンによっては import librosa.display でなく以下形式の場合も:
#   from librosa import display as librosa_display
# ここでは便宜上 'import librosa.display' とする。
import librosa.display

"""
waveform_generator.py

音声ファイルを読み込み、波形データの生成や可視化を行うユーティリティクラス。

[主な機能]
  - 音声データを読み込み (librosa使用)
  - 波形データ(配列)生成
  - 波形を画像としてプロット & 保存

[前提]
  - pip install librosa matplotlib
  - 16kHz, 44.1kHz 等々、音声ファイルのサンプリングレートを適宜想定
  - もしGPUがあるなら librosa の一部機能をGPU対応ライブラリで置き換えることも検討可

[使い方の例]
  from project_root.main.video.waveform_generator import WaveformGenerator

  generator = WaveformGenerator(normalize=True, sample_rate=16000)
  wave_data = generator.generate_waveform("path/to/audio.wav")

  # 波形データを確認
  print(wave_data)

  # 波形画像を保存
  generator.save_waveform_plot("path/to/audio.wav", "output_waveform.png")
"""


class WaveformGenerator:
    def __init__(
        self,
        normalize: bool = True,
        sample_rate: int = 16000,
        mono: bool = True
    ) -> None:
        """
        WaveformGenerator クラスの初期化

        Args:
            normalize (bool): 音声データを正規化するかどうか (librosa.util.normalize)
            sample_rate (int): 音声読み込み時にリサンプリングするサンプリングレート
            mono (bool): Trueの場合、モノラルに変換して読み込む (librosa.load のモード)
        """
        self.normalize = normalize
        self.sample_rate = sample_rate
        self.mono = mono

    def generate_waveform(self, audio_file: str) -> dict:
        """
        音声ファイルから波形データを生成して返す。

        Args:
            audio_file (str): 音声ファイルのパス

        Returns:
            dict: 時間 (float) -> 振幅 (float) のマッピングを辞書で返す
                  { 0.0: 0.123, 0.001: 0.456, ... } のように時間をキー、振幅を値とする

        Raises:
            FileNotFoundError: 音声ファイルが存在しない場合
            ValueError: 音声ファイルに問題がある場合 (読み込み失敗など)
        """
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"[WaveformGenerator] 音声ファイルが見つかりません: {audio_file}")

        try:
            # librosa で読み込み
            audio_data, sr = librosa.load(
                path=audio_file,
                sr=self.sample_rate,
                mono=self.mono
            )

            # 正規化が指定されている場合
            if self.normalize:
                audio_data = librosa.util.normalize(audio_data)

            # 時間軸を計算 (len(audio_data) 個の等間隔)
            # 注意: np.linspace は端点を含むため、サンプル数+1 相当の形になる。
            # → 同じ長さにするため、等差生成には np.arange を使うか linspace の引数調整。
            times = np.linspace(
                0, 
                len(audio_data) / float(sr),
                num=len(audio_data),
                endpoint=False
            )

            # 時刻をキー、小数点第3位程度に丸め、振幅を値にした辞書を生成
            waveform_data = {
                round(float(t), 3): round(float(a), 3)
                for t, a in zip(times, audio_data)
            }

            return waveform_data

        except Exception as e:
            raise ValueError(f"[WaveformGenerator] 波形データ生成中にエラー: {e}")

    def save_waveform_plot(self, audio_file: str, output_image: str) -> None:
        """
        波形データをプロットして画像ファイルに保存する。

        Args:
            audio_file (str): 音声ファイルのパス
            output_image (str): 保存先の画像ファイルパス (e.g. "output_waveform.png")

        Raises:
            FileNotFoundError: audio_file が存在しない場合
            RuntimeError: プロット保存中にエラーが起きた場合
        """
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"[WaveformGenerator] 音声ファイルが見つかりません: {audio_file}")

        try:
            # 音声ファイルを読み込み
            audio_data, sr = librosa.load(
                path=audio_file,
                sr=self.sample_rate,
                mono=self.mono
            )

            # 正規化
            if self.normalize:
                audio_data = librosa.util.normalize(audio_data)

            # プロット用の Figure
            plt.figure(figsize=(10, 4))

            # librosa.display で波形を可視化
            # y=audio_data, sr=sr
            librosa.display.waveshow(audio_data, sr=sr, x_axis='time', color='steelblue')
            plt.title("Waveform")
            plt.xlabel("Time [s]")
            plt.ylabel("Amplitude")
            plt.tight_layout()

            # 画像を保存
            plt.savefig(output_image, dpi=150)
            plt.close()
            print(f"[WaveformGenerator] 波形プロットを保存しました -> {output_image}")

        except Exception as e:
            raise RuntimeError(f"[WaveformGenerator] 波形プロット保存中にエラー: {e}")


def _demo():
    """
    モジュール単体で実行したときのデモコード。
    """
    demo_generator = WaveformGenerator(normalize=True, sample_rate=16000, mono=True)
    sample_audio_path = "example.wav"  # 例: サンプル音声ファイル
    output_image_path = "waveform_example.png"

    try:
        data = demo_generator.generate_waveform(sample_audio_path)
        print(f"[_demo] 波形データ: {len(data)} サンプル")
        # 先頭10サンプルを例示
        first_10 = list(data.items())[:10]
        print(f"  先頭10サンプル: {first_10}")

        # プロット画像保存
        demo_generator.save_waveform_plot(sample_audio_path, output_image_path)

    except (FileNotFoundError, ValueError, RuntimeError) as err:
        print(f"デモ実行エラー: {err}")


if __name__ == "__main__":
    _demo()
