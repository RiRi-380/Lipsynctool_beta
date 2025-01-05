# -*- coding: utf-8 -*-
"""
rms_analysis.py

音声データに対するRMS (Root Mean Square) 値を解析するモジュール。
Cython拡張としてビルドされた `rms_fast` モジュールを利用し、
大量データでも高速にRMSを算出できるようにする。

想定される追加要件:
- チャンク処理による長尺音声への対応
- ステレオ→モノラル変換、サンプリングレート変換
- GPU使用フラグ (実際はCPUで十分だが将来に備えて設計)
"""

import os
import wave
import numpy as np

# ここで、コンパイル済みのCython拡張モジュール `rms_fast` をインポート
# パスを変更する場合は、プロジェクト構成に合わせて修正
from main.optimizations import rms_fast


def compute_rms_from_array(audio_data: np.ndarray, use_gpu: bool = False) -> float:
    """
    受け取った音声波形データ（float32配列）からRMSを計算。
    Cython拡張の `rms_fast.calculate_rms_fast` を利用して高速に求める。

    Args:
        audio_data (np.ndarray): float32の1次元配列 (PCMなどをロードしたもの)
        use_gpu (bool): GPU使用フラグ（将来拡張用）

    Returns:
        float: 計算されたRMS値
    """
    if audio_data.dtype != np.float32:
        raise ValueError("[rms_analysis] audio_dataはfloat32である必要があります。")

    # GPU対応は将来の拡張イメージ。ここではダミーの分岐例。
    # 実際にGPU実装するときには cuda/cupy等を使った実装を追加。
    if use_gpu:
        # 例: GPU対応のrms_fast.calculate_rms_fast_gpu(audio_data) がある想定
        # return rms_fast.calculate_rms_fast_gpu(audio_data)
        pass

    rms_value = rms_fast.calculate_rms_fast(audio_data)
    return rms_value


def compute_rms_in_chunks(
    wav_file_path: str,
    chunk_size: int = 65536,
    force_mono: bool = True,
    use_gpu: bool = False
) -> float:
    """
    チャンク処理を用いて長尺WAVファイルのRMSを計算する。
    音声データを一度にすべて読み込まずに、chunk_size単位で分割してRMSを計算・集約する。

    Args:
        wav_file_path (str): 入力WAVファイルのパス
        chunk_size (int): 1回あたりに読み込むフレーム数（サンプル数）
        force_mono (bool): Trueの場合、ステレオ→モノラル変換を行う
        use_gpu (bool): GPU使用フラグ（将来拡張用）

    Returns:
        float: WAVファイルのRMS値
    """
    if not os.path.exists(wav_file_path):
        raise FileNotFoundError(f"[rms_analysis] WAVファイルが見つかりません: {wav_file_path}")

    with wave.open(wav_file_path, 'rb') as wf:
        num_channels = wf.getnchannels()
        samp_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        total_frames = wf.getnframes()

        # 16bit(2byte)PCM想定
        if samp_width != 2:
            raise ValueError("[rms_analysis] 本サンプルは16bit(2byte)PCMを想定しています。")

        # --- チャンクごとにRMSを計算し、二乗平均の総和を集約する ---
        sum_of_squares = 0.0
        total_samples = 0

        frames_read = 0
        while frames_read < total_frames:
            # 読み出すフレーム数を計算
            frames_to_read = min(chunk_size, total_frames - frames_read)
            raw_data = wf.readframes(frames_to_read)
            frames_read += frames_to_read

            # raw_data -> int16 配列
            audio_np_int16 = np.frombuffer(raw_data, dtype=np.int16)

            # ステレオ→モノラル変換
            if force_mono and num_channels > 1:
                audio_np_int16 = audio_np_int16.reshape((-1, num_channels))
                audio_np_int16 = audio_np_int16.mean(axis=1).astype(np.int16)

            # -1.0 ~ 1.0 に正規化 → float32変換
            audio_data_float32 = (audio_np_int16 / 32768.0).astype(np.float32)

            # チャンク単位で RMS = sqrt( mean( audio^2 ) ) を計算する代わりに、
            # sum_of_squares とサンプル総数から最終的な RMS を求める。
            # RMS = sqrt( (sum of x^2) / N )
            # -> sum_of_squares += sum(x^2), total_samples += N
            # ここで x^2 の計算を Cython拡張に任せたい場合、rms_fast の別APIを用意する手もある。

            # 例: chunk_rms = compute_rms_from_array(audio_data_float32, use_gpu=use_gpu)
            #     sum_of_squares += (chunk_rms**2 * len(audio_data_float32))
            # でも chunk_rms^2 * N = sum(x^2) なので、
            #   chunk_rms^2 * N = (mean(x^2) * N) * N = ...
            #   → 少々混乱を招く。直接 x^2 の総和を取得できるAPIがあればベスト。

            # ここでは Pythonで簡易的に x^2 の総和を計算:
            # GPU対応ならcupy等を使う余地あり
            squares_sum_chunk = np.sum(audio_data_float32 * audio_data_float32)
            sum_of_squares += squares_sum_chunk
            total_samples += len(audio_data_float32)

        if total_samples == 0:
            return 0.0

        overall_mean = sum_of_squares / total_samples
        overall_rms = float(np.sqrt(overall_mean))

        return overall_rms


def compute_rms_from_wav(
    wav_file_path: str,
    force_mono: bool = True,
    desired_samplerate: int = None,
    use_gpu: bool = False
) -> float:
    """
    WAVEファイルを一括読み込みしてRMSを算出するサンプル実装。
    ファイルサイズが大きい場合は `compute_rms_in_chunks` の使用を推奨。

    Args:
        wav_file_path (str): WAVファイルのパス
        force_mono (bool): Trueならステレオ→モノラル変換
        desired_samplerate (int, optional): リサンプリング先のサンプルレート。Noneなら変換しない
        use_gpu (bool): GPU使用フラグ（将来拡張用）

    Returns:
        float: WAVファイルのRMS値
    """
    if not os.path.exists(wav_file_path):
        raise FileNotFoundError(f"[rms_analysis] WAVファイルが見つかりません: {wav_file_path}")

    with wave.open(wav_file_path, 'rb') as wf:
        num_channels = wf.getnchannels()
        samp_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        num_frames = wf.getnframes()

        if samp_width != 2:
            raise ValueError("[rms_analysis] 本サンプルは16bit(2byte)PCMを想定しています。")

        raw_data = wf.readframes(num_frames)

    # int16配列へ変換
    audio_np_int16 = np.frombuffer(raw_data, dtype=np.int16)

    if force_mono and num_channels > 1:
        # モノラルダウンミックス
        audio_np_int16 = audio_np_int16.reshape((-1, num_channels))
        audio_np_int16 = audio_np_int16.mean(axis=1).astype(np.int16)

    # -1.0 ~ 1.0 に正規化 → float32変換
    audio_data_float32 = (audio_np_int16 / 32768.0).astype(np.float32)

    # --- 将来のリサンプリング例 (librosa等が必要) ---
    # if desired_samplerate is not None and desired_samplerate != sample_rate:
    #     # import librosa
    #     # audio_data_float32 = librosa.resample(audio_data_float32, orig_sr=sample_rate, target_sr=desired_samplerate)
    #     # sample_rate = desired_samplerate
    #     pass

    # Cython拡張（またはGPU）を利用してRMS計算
    rms_value = compute_rms_from_array(audio_data_float32, use_gpu=use_gpu)
    return rms_value


def main():
    """
    簡易動作テスト用のサンプル。
    大きなファイルを試す場合は compute_rms_in_chunks を使ってみるとよい。
    """
    test_wav = "sample.wav"  # 実在するWAVファイルを指定
    try:
        print("[rms_analysis] --- 単発読み込みで計算 ---")
        rms_val = compute_rms_from_wav(
            wav_file_path=test_wav,
            force_mono=True,
            desired_samplerate=None,
            use_gpu=False
        )
        print(f"  RMS値 (一括読み込み): {rms_val:.5f}")

        print("[rms_analysis] --- チャンク処理で計算 ---")
        chunk_rms_val = compute_rms_in_chunks(
            wav_file_path=test_wav,
            chunk_size=65536,
            force_mono=True,
            use_gpu=False
        )
        print(f"  RMS値 (チャンク処理): {chunk_rms_val:.5f}")

    except Exception as e:
        print(f"[rms_analysis] エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
