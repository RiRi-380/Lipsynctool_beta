# main/pipeline/lip_sync_generator.py
# -*- coding: utf-8 -*-

"""
lip_sync_generator.py (高度な時間調整付き)

- 短い無音をつぶして母音を被せる、長い無音はそのままにする…など、時間軸の再調整を行う例。
- generate_lip_sync() 内で _smooth_phoneme_segments() を呼び出し、
  phoneme_segments の start/end_time を微調整してから _merge_phonemes_and_rms() へ渡す。
"""

import os
import json
import numpy as np
import traceback

# hatsuon.py があればインポート、なければ None でダミー実装へ
try:
    from main.analysis import hatsuon
except ImportError:
    hatsuon = None

# overlap_utils があればオーバーラップ処理可
try:
    from main.utils import overlap_utils
except ImportError:
    overlap_utils = None

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "lip_sync_config.json")


class LipSyncGenerator:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"[LipSyncGenerator] 設定ファイル読み込みエラー: {e}")
        else:
            print(f"[LipSyncGenerator] 設定ファイルが見つかりません: {config_path}")

        # processing_options
        processing_opts = self.config.get("processing_options", {})
        self.use_gpu = processing_opts.get("enable_gpu", False)
        self.rms_threshold = processing_opts.get("rms_threshold", 0.02)
        self.allow_asr = processing_opts.get("allow_asr", False)
        self.phoneme_timing_mode = processing_opts.get("phoneme_timing_mode", "naive")
        self.overlap_ratio = processing_opts.get("overlap_ratio", 0.2)

        # オプションで gap_threshold を config から取り出し (なければデフォルト0.05)
        self.default_gap_threshold = processing_opts.get("gap_threshold", 0.05)

        # ASR設定
        asr_conf = self.config.setdefault("asr", {})
        self.asr_model_size = asr_conf.get("model_size", "large")
        if self.asr_model_size not in ["small", "medium", "large"]:
            self.asr_model_size = "large"

        # export_options
        self.export_options = self.config.get("export_options", {})

        # 解析結果を保持する辞書
        self.lip_sync_data = {
            "phoneme_segments": [],
            "rms_timeline": [],
            "lip_sync_frames": []
        }

    def generate_lip_sync(
        self,
        audio_data: np.ndarray,
        text: str,
        sample_rate: int = 16000,
        gap_threshold: float = None
    ) -> dict:
        """
        音声データ + テキストからリップシンク用データを生成。
        gap_threshold: この秒数未満の無音があったら、音素区間を少し被せるように調整。
                       Noneの場合は self.default_gap_threshold が使われる。
        """
        if gap_threshold is None:
            gap_threshold = self.default_gap_threshold

        if self.use_gpu:
            print("[LipSyncGenerator] GPUフラグON (※本サンプルではCPUで処理)")

        # テキスト正規化
        debug_text = text.replace("\n", "\\n").replace("\r", "\\r")
        print(f"[LipSyncGenerator] Raw user text = '{debug_text}'")

        text_normalized = (
            text.replace("\u3000", " ")
                .replace("\n", " ")
                .replace("\r", " ")
                .strip()
        )
        print(f"[LipSyncGenerator] normalized text = '{text_normalized}'")

        # テキストが空 → ASR or ダミー
        if not text_normalized:
            if self.allow_asr:
                print(f"[LipSyncGenerator] テキストが実質空。Whisperダミーを試みます。(model_size={self.asr_model_size})")
                try:
                    text_asr_result = self._fake_asr_whisper(audio_data, sample_rate)
                    if not text_asr_result:
                        print("[LipSyncGenerator] Whisper(ダミー)が空 → ダミー音素使用")
                        return self._dummy_lip_sync(audio_data, sample_rate)
                    else:
                        print(f"[LipSyncGenerator] Whisper(ダミー)結果: {text_asr_result}")
                        text_normalized = text_asr_result
                except Exception as e:
                    print("[LipSyncGenerator] Whisper(ダミー)呼び出しでエラー:", e)
                    return self._dummy_lip_sync(audio_data, sample_rate)
            else:
                print("[LipSyncGenerator] テキスト空 & ASR不可 → ダミー音素を使用")
                return self._dummy_lip_sync(audio_data, sample_rate)

        # --- テキストがある → 通常フロー
        total_duration = len(audio_data) / float(sample_rate)
        phoneme_segments = self._analyze_phonemes(text_normalized, total_duration)

        # 短いgapを自動で被せる処理
        phoneme_segments_smoothed = self._smooth_phoneme_segments(phoneme_segments, gap_threshold)

        # RMS解析
        rms_timeline = self._analyze_rms(audio_data, sample_rate)

        # マージ
        lip_sync_frames = self._merge_phonemes_and_rms(phoneme_segments_smoothed, rms_timeline)

        # overlap_utils があればオーバーラップ処理
        if overlap_utils is not None:
            print("[LipSyncGenerator] overlap_utils でオーバーラップ処理を適用します。")
            lip_sync_frames = overlap_utils.apply_overlap_easing(
                lip_sync_frames, self.overlap_ratio
            )
        else:
            print("[LipSyncGenerator] overlap_utils が無いためオーバーラップ処理はスキップ。")

        # 結果を保持
        self.lip_sync_data["phoneme_segments"] = phoneme_segments_smoothed
        self.lip_sync_data["rms_timeline"] = rms_timeline
        self.lip_sync_data["lip_sync_frames"] = lip_sync_frames

        return self.lip_sync_data

    def _smooth_phoneme_segments(self, segments, gap_threshold=0.05):
        """
        短いgapを被せる簡易処理:
         - segmentsを (start_time) 順にソート
         - 各音素 i の end_time と 次音素 i+1 の start_time の差 (gap) が gap_threshold 未満なら
           → i の end_time と i+1 の start_time を2つの中間(mid)へ寄せて重ねる
        """
        if not segments:
            return segments

        # 時間順に並べる
        sorted_segs = sorted(segments, key=lambda x: x[1])  # x=(phoneme, start, end)

        smoothed = []
        i = 0
        while i < len(sorted_segs):
            if i == len(sorted_segs) - 1:
                # 最後の音素はそのまま
                smoothed.append(sorted_segs[i])
                break

            ph, st, ed = sorted_segs[i]
            nxt_ph, nxt_st, nxt_ed = sorted_segs[i+1]
            gap = nxt_st - ed

            if 0 < gap < gap_threshold:
                # gapが短い → 2つの間を被せる
                mid = 0.5 * (ed + nxt_st)
                new_ed = mid
                new_nxt_st = mid

                smoothed.append((ph, st, new_ed))
                # 次音素を更新して、すぐにi+1をスキップしないよう再設定
                sorted_segs[i+1] = (nxt_ph, new_nxt_st, nxt_ed)
                i += 1  # 次へ
            else:
                # gapが大きい or 負(すでに被ってる)
                smoothed.append(sorted_segs[i])
                i += 1

        # もしまだ要素が残っている場合をケア (上のループでbreakした状態など)
        if len(smoothed) < len(sorted_segs):
            smoothed.append(sorted_segs[-1])

        return smoothed

    def apply_timeline_edits(self, timeline_json_path: str):
        """
        タイムラインエディタの修正JSONを反映。
        """
        if not os.path.exists(timeline_json_path):
            print(f"[LipSyncGenerator] timeline_json not found: {timeline_json_path}")
            return

        try:
            with open(timeline_json_path, 'r', encoding='utf-8') as f:
                timeline_data = json.load(f)
        except Exception as e:
            print(f"[LipSyncGenerator] timeline_json読み込み失敗: {e}")
            return

        # phoneme_segments の上書き
        seg_list = timeline_data.get("phoneme_segments", [])
        if seg_list:
            new_segments = []
            for seg in seg_list:
                ph = seg.get("phoneme", "a")
                st = seg.get("start_time", 0.0)
                ed = seg.get("end_time", st + 0.2)
                new_segments.append((ph, st, ed))
            self.lip_sync_data["phoneme_segments"] = new_segments

        # overlap_rate があれば更新
        new_ol = timeline_data.get("overlap_rate", None)
        if new_ol is not None:
            self.overlap_ratio = new_ol
            print(f"[LipSyncGenerator] overlap_ratio updated to {new_ol}")

        # 再マージ
        phoneme_segments = self.lip_sync_data["phoneme_segments"]
        rms_timeline = self.lip_sync_data["rms_timeline"]
        frames = self._merge_phonemes_and_rms(phoneme_segments, rms_timeline)
        if overlap_utils is not None:
            frames = overlap_utils.apply_overlap_easing(frames, self.overlap_ratio)

        self.lip_sync_data["lip_sync_frames"] = frames
        print("[LipSyncGenerator] apply_timeline_edits: done.")

    def export_lip_sync(self, export_format="json", output_path="./output/lipsync_result.json"):
        if not self.lip_sync_data["lip_sync_frames"]:
            print("[LipSyncGenerator] lip_sync_frames が空です。解析実行しましたか？")
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if "json" in export_format.lower():
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(self.lip_sync_data, f, indent=2, ensure_ascii=False)
            print(f"[LipSyncGenerator] JSON出力 -> {output_path}")

        elif "vmd" in export_format.lower():
            # ダミーVMD出力（本来は exporter_vmd.py を使う想定）
            print("[LipSyncGenerator] VMDダミー出力します。本来は exporter_vmd に委譲するのがおすすめ。")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("// VMD dummy file\n")
                json.dump(self.lip_sync_data, f, indent=2, ensure_ascii=False)
            print(f"[LipSyncGenerator] ダミーVMD出力 -> {output_path}")
        else:
            print(f"[LipSyncGenerator] 未対応の形式です: {export_format}")

    # ----------------------------------------------------------------
    # 内部メソッド: ASRダミー, ダミー音素, hatsuon 等
    # ----------------------------------------------------------------
    def _fake_asr_whisper(self, audio_data: np.ndarray, sr: int) -> str:
        print(f"[LipSyncGenerator] [fake_asr_whisper] model_size={self.asr_model_size}, gpu={self.use_gpu}")
        import random
        if random.random() < 0.5:
            return ""
        return f"Whisper({self.asr_model_size})ダミー結果"

    def _dummy_lip_sync(self, audio_data: np.ndarray, sr: int) -> dict:
        print("[LipSyncGenerator] ダミー音素解析を行います。(a->i->u)")
        dummy_segments = [
            ("a", 0.0, 1.0),
            ("i", 1.0, 2.0),
            ("u", 2.0, 3.0),
        ]

        rms_timeline = self._analyze_rms(audio_data, sr)
        frames = self._merge_phonemes_and_rms(dummy_segments, rms_timeline)

        if overlap_utils is not None:
            frames = overlap_utils.apply_overlap_easing(frames, self.overlap_ratio)

        self.lip_sync_data["phoneme_segments"] = dummy_segments
        self.lip_sync_data["rms_timeline"] = rms_timeline
        self.lip_sync_data["lip_sync_frames"] = frames
        return self.lip_sync_data

    def _analyze_phonemes(self, text: str, total_duration: float) -> list:
        if hatsuon is not None:
            print("[LipSyncGenerator] hatsuon を使って音素解析中...")
            engine = hatsuon.HatsuonEngine(language="ja", overlap_ratio=self.overlap_ratio)
            segs = engine.text_to_phoneme_timing(text, total_duration=total_duration)
            phoneme_segments = []
            for s in segs:
                ph = s["phoneme"]
                st = s["start"]
                ed = s["end"]
                phoneme_segments.append((ph, st, ed))
            return phoneme_segments
        else:
            # ダミー: 0.2秒ずつ a,i,u を繰り返し
            print("[LipSyncGenerator] hatsuon.py が無いのでダミー音素を生成します。(a,i,uループ)")
            tokens = list(text.replace(" ", ""))  # 空白除去
            n_tok = len(tokens)
            if n_tok == 0:
                return []

            seg_len = total_duration / n_tok
            segs = []
            t0 = 0.0
            for i, ch in enumerate(tokens):
                ph = ["a", "i", "u"][i % 3]
                segs.append((ph, t0, t0 + seg_len))
                t0 += seg_len
            return segs

    def _analyze_rms(self, audio_data: np.ndarray, sr: int) -> list:
        hop_length = int(sr * 0.01)  # 10ms
        frames = []
        t = 0.0

        idx = 0
        while idx < len(audio_data):
            chunk = audio_data[idx : idx + hop_length]
            if len(chunk) == 0:
                break
            val = float(np.sqrt(np.mean(chunk ** 2)))
            if val < self.rms_threshold:
                val = 0.0
            frames.append((t, val))
            idx += hop_length
            t += 0.01

        return frames

    def _merge_phonemes_and_rms(self, phoneme_segments: list, rms_timeline: list) -> list:
        frames = []
        rms_index = 0
        len_rms = len(rms_timeline)

        for (ph, st, ed) in phoneme_segments:
            seg_rms = []
            while rms_index < len_rms and rms_timeline[rms_index][0] < ed:
                (time_t, val) = rms_timeline[rms_index]
                if time_t >= st:
                    seg_rms.append(val)
                rms_index += 1
                if time_t > ed:
                    break

            avg_val = sum(seg_rms) / len(seg_rms) if seg_rms else 0.0
            frames.append({
                "start": st,
                "end": ed,
                "phoneme": ph,
                "avg_rms": avg_val
            })

        return frames


def main():
    import librosa

    audio_file = "path/to/test.wav"
    text_data = "こんにちは"

    if not os.path.exists(audio_file):
        print("[Error] サンプル用ファイルが存在しません。終了。")
        return

    audio, sr = librosa.load(audio_file, sr=16000, mono=True)
    audio = audio.astype(np.float32, copy=False)

    gen = LipSyncGenerator()
    # 例: gap_thresholdを None にしておけば、 lip_sync_config.json の "gap_threshold" を使う
    result = gen.generate_lip_sync(audio, text_data, sr, gap_threshold=None)

    print("=== lip_sync_frames ===")
    print(json.dumps(result.get("lip_sync_frames", []), indent=2, ensure_ascii=False))

    out_path = "./output/test_lipsync.json"
    gen.export_lip_sync("json", out_path)
    print("[Done]")
