# -*- coding: utf-8 -*-

"""
asr_whisper.py

WhisperベースのASRを利用して、音声データをテキストやタイムスタンプ情報に変換するためのモジュール。

【本格実装例】
 1) openai-whisper (pip install openai-whisper) を使用。
 2) GPU対応: use_gpu=True なら device="cuda" を使う（GPUが無い環境だとエラーの可能性あり）
 3) 音声データ (np.ndarray) を一時ファイルに書き出し、model.transcribe(...) で読み込む
 4) モデルサイズ: "tiny" / "base" / "small" / "medium" / "large" など
 5) 返り値:
    - デフォルトでは最終テキスト文字列を返す
    - オプションで詳細セグメントのリストを返す (timestamps)
 6) 失敗・空文字なら RuntimeErrorを投げて呼び出し元がフォールバック or エラー処理できるように
"""

import os
import tempfile
import numpy as np
import whisper  # openai-whisper ライブラリ


class WhisperASR:
    """
    Whisperを使ったASRクラスの例（本格実装風）。

    主な追加パラメータ:
      - language (str): Whisperに入力言語を指定 (例: "ja" で日本語を明示)
      - translate_mode (bool): Trueなら "translate" タスクで翻訳結果を得る（要: 英語モデル or multi言語モデル）
      - temperature (float): Whisperの推論温度（0.0 に近いほど確信度重視）
      - best_of / beam_size: サンプリング/ビームサーチの候補数
      - timestamps (bool): Trueにすると、セグメントごとの開始/終了など詳細情報を返す
    """

    VALID_SIZES = ["tiny", "base", "small", "medium", "large"]

    def __init__(
        self,
        use_gpu: bool = False,
        model_size: str = "large",
        language: str = None,
        translate_mode: bool = False,
        temperature: float = 0.0,
        best_of: int = 1,
        beam_size: int = 1,
        timestamps: bool = False,
    ):
        """
        Args:
            use_gpu (bool): GPUを使うかどうか
            model_size (str): Whisperモデルサイズ("tiny", "base", "small", "medium", "large"など)
            language (str): 'ja' や 'en' など指定可能。Noneなら自動判定
            translate_mode (bool): Trueなら 'translate' タスクを指定（日本語→英語翻訳など）
            temperature (float): 推論温度
            best_of (int): greedy search時の候補数
            beam_size (int): beam search時のビーム幅
            timestamps (bool): Trueで詳細セグメント情報も返す
        """
        self.use_gpu = use_gpu
        if model_size not in self.VALID_SIZES:
            print(f"[WhisperASR] 指定モデルサイズ '{model_size}' は無効のため 'large' にフォールバックします。")
            model_size = "large"
        self.model_size = model_size

        self.language = language
        self.translate_mode = translate_mode
        self.temperature = temperature
        self.best_of = best_of
        self.beam_size = beam_size
        self.return_timestamps = timestamps

        self._model = None
        self._device = "cpu"
        if self.use_gpu and self._gpu_is_available():
            self._device = "cuda"

        # Whisperからモデルをロード
        try:
            print(f"[WhisperASR] Loading whisper model='{model_size}', device='{self._device}'")
            self._model = whisper.load_model(model_size, device=self._device)
        except Exception as e:
            print(f"[WhisperASR] Whisperモデルのロードに失敗: {e}")
            self._model = None

    def _gpu_is_available(self) -> bool:
        """GPUが本当に利用可能かどうかを簡易チェック。"""
        import torch
        return torch.cuda.is_available()

    def transcribe(self, audio_data: np.ndarray, sample_rate: int):
        """
        NumPy形式の音声データを受け取り、Whisperで文字起こし or 翻訳を実行。
        エラー時や結果が空文字だった場合は RuntimeError を投げる。

        Returns:
            str または dict:
                - self.return_timestamps == False の場合: テキストのみ(str)
                - self.return_timestamps == True の場合:
                    {
                      "text": str,          # 全体の文字起こし
                      "segments": [         # セグメント情報
                        {
                          "id": int,
                          "start": float,   # セグメント開始秒
                          "end": float,     # セグメント終了秒
                          "text": str,
                          ...
                        },
                        ...
                      ]
                    }

        Raises:
            RuntimeError: モデル未ロード or 文字起こしに失敗・空文字の場合
        """
        if self._model is None:
            raise RuntimeError("[WhisperASR] Whisperモデルがロードされていません。(ロード失敗or未指定)")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_file = tmp.name

        try:
            self._save_wav(tmp_file, audio_data, sample_rate)

            # タスク: 普通は 'transcribe'、translate_mode=True なら 'translate'
            task_type = "translate" if self.translate_mode else "transcribe"

            # Whisperに渡すパラメータ例
            # ※ language=None でも自動判定されるが誤判定の可能性もある
            #   もし "ja" を指定したい場合 self.language="ja"
            result = self._model.transcribe(
                tmp_file,
                task=task_type,
                language=self.language,
                temperature=self.temperature,
                best_of=self.best_of,
                beam_size=self.beam_size,
                verbose=False,  # Falseでログ出力控えめ
            )

            text = result["text"].strip()

            if not text:
                raise RuntimeError("[WhisperASR] 文字起こし結果が空でした。")

            if self.return_timestamps:
                # セグメント情報も返す
                # result["segments"] は各区間の {"id","seek","start","end","text",...}
                return {
                    "text": text,
                    "segments": result.get("segments", []),
                }
            else:
                # テキストのみ返却
                return text

        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    def _save_wav(self, filename: str, audio_data: np.ndarray, sr: int):
        """
        NumPy配列をWAVファイルに書き出す。
        """
        import wave
        import struct

        int_data = np.clip(audio_data * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)        # モノラル
            wf.setsampwidth(2)       # 16bit
            wf.setframerate(sr)
            wf.writeframes(int_data.tobytes())


def demo_main():
    """
    簡易デモ:
      python -m main.pipeline.asr_whisper
    """
    import sys
    import librosa

    # テスト用音声ファイル
    sample_file = "path/to/sample.wav"
    if not os.path.exists(sample_file):
        print("[Error] テスト用音声ファイルがありません。終了。")
        return

    audio_data, sr = librosa.load(sample_file, sr=16000, mono=True)
    audio_data = audio_data.astype(np.float32, copy=False)

    # WhisperASR インスタンス
    asr = WhisperASR(use_gpu=False, model_size="medium", language="ja",
                     translate_mode=False, temperature=0.0,
                     best_of=1, beam_size=1, timestamps=True)

    try:
        result = asr.transcribe(audio_data, sr)
        if isinstance(result, dict):
            print("[ASR] text:", result["text"])
            for seg in result["segments"]:
                print(f"  seg#{seg['id']} start={seg['start']:.2f}s end={seg['end']:.2f}s text='{seg['text']}'")
        else:
            print("[ASR] text:", result)
    except RuntimeError as e:
        print(f"[ASR] Whisper失敗: {e}")


if __name__ == "__main__":
    demo_main()
