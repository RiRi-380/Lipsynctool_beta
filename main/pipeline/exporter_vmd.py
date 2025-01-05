# main/pipeline/exporter_vmd.py
# -*- coding: utf-8 -*-

"""
exporter_vmd.py (高度なリップシンク処理付き)

- 3点キー(フェードイン→ピーク→フェードアウト)を打つ。
- 次音素開始との間隔(gap)が短い場合はクロスフェードして
  「完全に閉じずに次の音素へ移行」できるようにする。
- gapが長ければ口をしっかり閉じる(weight=0)。
- phoneme → morph_name は従来どおり phoneme_mapping で対応。

追加要素:
- 同じフレーム・同じモーフで weight=0→0 のキーが乱立するのを防ぐため、
  add_morph_key() 内で「重複キー」の排除ロジックを入れる。
- 外部JSON (configs/phoneme_to_morph_map.json) があれば読み込み、マッピングをマージ
"""

import os
import struct
import json
import re

class VMDExporter:
    DEFAULT_HEADER_STR = "Vocaloid Motion Data 0002"
    DEFAULT_MODEL_NAME = "SomeModel"
    FORBIDDEN_CHARS_PATTERN = r'[\\/:*?"<>|]'  # Windowsで禁止されている文字

    def __init__(
        self,
        header_str: str = None,
        model_name: str = None,
        phoneme_mapping: dict = None
    ):
        """
        Args:
            header_str (str): VMDファイルのヘッダ文字列 (30バイト相当, Shift-JIS)
            model_name (str): デフォルトのモデル名 (20バイト相当, Shift-JIS)
            phoneme_mapping (dict): 音素→モーフ名マッピング。
                例: {"a":"あ", "i":"い", "u":"う", "e":"え", "o":"お"}
                未指定の場合は {"a":"a", "i":"i", "u":"u", "e":"e", "o":"o"}。
                "_fallback": "a" なども追加可能。
        """
        if header_str is None:
            header_str = self.DEFAULT_HEADER_STR
        if model_name is None:
            model_name = self.DEFAULT_MODEL_NAME

        self.header_str = header_str
        self.model_name = model_name
        # モーフキーフレームを貯める配列
        self.morph_tracks = []

        # デフォルトマッピング (a,i,u,e,o のみ)
        default_mapping = {
            "a": "a",
            "i": "i",
            "u": "u",
            "e": "e",
            "o": "o",
        }

        # 1) 外部JSON (configs/phoneme_to_morph_map.json) があれば読み込み
        external_map = {}
        external_map_path = os.path.join("configs", "phoneme_to_morph_map.json")
        if os.path.exists(external_map_path):
            try:
                with open(external_map_path, "r", encoding="utf-8") as fm:
                    external_map = json.load(fm)
            except Exception as e:
                print(f"[VMDExporter] 外部マッピングJSONの読み込み失敗: {e}")
                external_map = {}

        # 2) マッピングをまとめてマージ
        merged_map = default_mapping.copy()

        # ユーザ指定のphoneme_mappingがあれば上書き
        if phoneme_mapping is not None:
            merged_map.update(phoneme_mapping)

        # 外部JSONのマッピングがあればさらに上書き
        if external_map:
            merged_map.update(external_map)

        # 最終的に self.phoneme_mapping に設定
        self.phoneme_mapping = merged_map

    def clear_morph_tracks(self):
        """モーフキーフレーム一覧をクリア。"""
        self.morph_tracks.clear()

    def add_morph_key(self, frame_number: int, morph_name: str, weight: float):
        """
        モーフフレーム(表情キー)を追加する。
        ここで「同じフレーム + 同じモーフ」で weight が重複するケースを排除して
        不要なキーを減らす工夫を入れる。
        """
        # もし既に最後に追加したキーが同じフレーム・同じモーフなら、上書き or スキップ
        if self.morph_tracks:
            last_key = self.morph_tracks[-1]
            if (last_key["frame"] == frame_number
                and last_key["morph_name"] == morph_name):
                # 重複キーを上書き or 変化量がなければスキップ
                if abs(last_key["weight"] - weight) < 1e-6:
                    # weight変化がないなら何もしない
                    return
                else:
                    # weightが変わるなら上書き
                    last_key["weight"] = weight
                    return

        # 通常ケース: 追加
        self.morph_tracks.append({
            "frame": frame_number,
            "morph_name": morph_name,
            "weight": weight
        })

    def from_lip_sync_data(
        self,
        lip_sync_data: dict,
        fps: int = 30,
        fade_in: bool = True,
        fade_out: bool = True,
        crossfade_threshold: float = 0.1,
        min_weight: float = 0.0
    ):
        """
        lip_sync_data からモーフキーフレームを生成(3点キー方式 + クロスフェード)。

        Args:
            lip_sync_data: {
              "export_options": {...},
              "lip_sync_frames": [{"phoneme":..., "start":..., "end":..., "avg_rms":...}, ...]
            }
            fps (int): MMDモーションのFPS (デフォルト30)
            fade_in (bool): Trueなら各音素の開始フレームで 0→peak のフェードインキーを打つ
            fade_out (bool): Trueなら音素の終了フレームで peak→0 のフェードアウトキーを打つ
            crossfade_threshold (float): 次音素までの時間差(gap)がこの値[秒]未満なら
                                         「口を完全に閉じずにクロスフェード」する
            min_weight (float): クロスフェード時に完全0に落とさず、ここまで落とす (例:0.2とか)

        説明:
          - 3点キー:
            Start(口を開き始め), Peak(中間), End(閉じorクロスフェード)
          - gap < crossfade_threshold のときは、Endフレームで weightを min_weight までしか落とさない。
            → 次音素のStartキーと重なり、滑らかに移行 (完全に閉じない)
        """
        self.clear_morph_tracks()

        # 1) model_name 上書き (export_optionsやlip_sync_data 直下の model_name)
        export_opts = lip_sync_data.get("export_options", {})
        maybe_model = export_opts.get("model_name") or lip_sync_data.get("model_name")
        if maybe_model:
            self.model_name = maybe_model

        frames_info = lip_sync_data.get("lip_sync_frames", [])
        # 時間順ソート
        frames_info = sorted(frames_info, key=lambda x: x.get("start", 0.0))

        # 次音素の開始時刻リスト (gap計算用)
        start_times = [fi.get("start", 999999) for fi in frames_info]
        next_start_times = []
        for i in range(len(start_times) - 1):
            next_start_times.append(start_times[i+1])
        # 最後はもう次が無いので大きめの値を代入
        next_start_times.append(999999.0)

        # メインループ
        for i, seg in enumerate(frames_info):
            ph = seg.get("phoneme", "a")
            st = seg.get("start", 0.0)
            ed = seg.get("end", st + 0.2)
            avg_rms = seg.get("avg_rms", 0.0)

            # morph名取得
            morph_name = self._map_phoneme(ph)

            # 3点キーの基本時刻: start_f, mid_f, end_f
            mid_sec = (st + ed) * 0.5
            start_f = int(st  * fps)
            mid_f   = int(mid_sec * fps)
            end_f   = int(ed  * fps)

            # RMS→peakWeight (簡易ロジック)
            peak_weight = min(1.0, avg_rms * 2.0)

            # 次音素開始との間隔
            next_start = next_start_times[i]
            gap = next_start - ed  # 連続する音素までの無音

            # [1] Startフレーム (フェードイン)
            if fade_in:
                self.add_morph_key(start_f, morph_name, 0.0)

            # [2] Peakフレーム
            self.add_morph_key(mid_f, morph_name, peak_weight)

            # [3] Endフレーム (フェードアウト or クロスフェード)
            if fade_out:
                if gap < crossfade_threshold:
                    # gapが小さい → 次音素と被せたい → 最低限のweightまでしか下げない
                    self.add_morph_key(end_f, morph_name, min_weight)
                else:
                    # gapが大きい → 完全に閉じる
                    self.add_morph_key(end_f, morph_name, 0.0)

    def _map_phoneme(self, ph: str) -> str:
        """
        音素 → モーフ名 の変換。
        未定義の音素は _fallback か "a" とする。
        """
        if ph in self.phoneme_mapping:
            return self.phoneme_mapping[ph]
        return self.phoneme_mapping.get("_fallback", "a")

    # -----------------------------------------
    # 以下、バイナリ/テキストのVMD出力処理
    # -----------------------------------------
    def export_vmd_binary(self, output_path: str):
        if not output_path:
            print("[VMDExporter] 警告: 出力ファイルが指定されていません。中断します。")
            return

        dir_name = os.path.dirname(output_path)
        if not dir_name:
            dir_name = "."
        if not os.path.exists(dir_name):
            print(f"[VMDExporter] 出力先フォルダが存在しないため作成します: {dir_name}")
            os.makedirs(dir_name, exist_ok=True)

        output_path = self._sanitize_filename(output_path)
        self.morph_tracks.sort(key=lambda x: x["frame"])

        with open(output_path, "wb") as f:
            # ヘッダ(30byte, shift_jis)
            header_bytes = self._encode_sjis_with_nullfill(self.header_str, 30)
            f.write(header_bytes)

            # モデル名(20byte, shift_jis)
            model_bytes = self._encode_sjis_with_nullfill(self.model_name, 20)
            f.write(model_bytes)

            # ボーンモーション数=0
            f.write(struct.pack("<I", 0))

            # モーフキーフレーム数
            morph_count = len(self.morph_tracks)
            f.write(struct.pack("<I", morph_count))

            # モーフフレーム本体
            for entry in self.morph_tracks:
                name_bytes = self._encode_sjis_with_nullfill(entry["morph_name"], 15)
                f.write(name_bytes)
                frame_num = max(0, entry["frame"])
                f.write(struct.pack("<I", frame_num))
                weight_val = float(entry["weight"])
                f.write(struct.pack("<f", weight_val))

            # カメラ=0, 照明=0, セルフ影=0, IK=0
            f.write(struct.pack("<I", 0))  # camera
            f.write(struct.pack("<I", 0))  # light
            f.write(struct.pack("<I", 0))  # self_shadow
            f.write(struct.pack("<I", 0))  # IK

        print(f"[VMDExporter] バイナリVMDを {output_path} に書き出しました。")

    def export_vmd_text(self, output_path: str):
        if not output_path:
            print("[VMDExporter] 警告: テキスト出力ファイルが指定されていません。中断します。")
            return

        dir_name = os.path.dirname(output_path)
        if not dir_name:
            dir_name = "."
        if not os.path.exists(dir_name):
            print(f"[VMDExporter] 出力フォルダが無いので作成: {dir_name}")
            os.makedirs(dir_name, exist_ok=True)

        output_path = self._sanitize_filename(output_path)
        self.morph_tracks.sort(key=lambda x: x["frame"])

        data_dict = {
            "Header": {
                "FileSignature": self.header_str,
                "ModelName": self.model_name
            },
            "BoneMotion": {
                "Count": 0,
                "Data": []
            },
            "Face": {
                "Count": len(self.morph_tracks),
                "Data": []
            },
            "Camera": {
                "Count": 0,
                "Data": []
            },
            "Light": {
                "Count": 0,
                "Data": []
            },
            "SelfShadow": {
                "Count": 0,
                "Data": []
            },
            "IK": {
                "Count": 0,
                "Data": []
            }
        }

        for track in self.morph_tracks:
            data_dict["Face"]["Data"].append({
                "FrameNo": track["frame"],
                "Name": track["morph_name"],
                "Weight": track["weight"]
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)

        print(f"[VMDExporter] テキスト(デバッグ用)として {output_path} に書き出しました。")

    # -----------------------------------------
    # ユーティリティ
    # -----------------------------------------
    def _encode_sjis_with_nullfill(self, text: str, length: int) -> bytes:
        encoded = text.encode("shift_jis", errors="replace")
        if len(encoded) >= length:
            encoded = encoded[:length]
        else:
            encoded += b"\x00" * (length - len(encoded))
        return encoded

    def _sanitize_filename(self, filename: str) -> str:
        base, ext = os.path.splitext(filename)
        sanitized_base = re.sub(self.FORBIDDEN_CHARS_PATTERN, "_", base)
        if re.search(r'[^\x00-\x7F]', sanitized_base):
            print(f"[VMDExporter] 注意: ファイル名に全角やUnicode文字が含まれています -> {sanitized_base}")
        new_name = sanitized_base + ext
        dir_name = os.path.dirname(filename)
        return os.path.join(dir_name, new_name)


def demo_main():
    """
    デモ用。
    """
    lip_sync_data_example = {
        "export_options": {
            "model_name": "MyMMDModel"
        },
        "lip_sync_frames": [
            {"start": 0.00, "end": 0.18, "phoneme": "a",  "avg_rms": 0.45},
            {"start": 0.18, "end": 0.35, "phoneme": "i",  "avg_rms": 0.30},
            {"start": 0.35, "end": 0.50, "phoneme": "u",  "avg_rms": 0.25},
            {"start": 0.50, "end": 1.00, "phoneme": "a",  "avg_rms": 0.10},
            # gap=0.05秒 → crossfade
            {"start": 1.05, "end": 1.20, "phoneme": "e",  "avg_rms": 0.40},
            # gap=0秒(連続) → 同じフレームに近い
            {"start": 1.20, "end": 1.50, "phoneme": "o",  "avg_rms": 0.60},
        ]
    }

    # 例: ユーザ指定の追加マッピング
    custom_map = {
        "a": "あ",
        "i": "い",
        "u": "う",
        "e": "え",
        "o": "お",
        "_fallback": "あ"
    }

    exporter = VMDExporter(
        model_name="DefaultModel",
        phoneme_mapping=custom_map
    )

    # 3点キー + クロスフェード設定
    exporter.from_lip_sync_data(
        lip_sync_data_example,
        fps=30,
        fade_in=True,
        fade_out=True,
        crossfade_threshold=0.1,
        min_weight=0.2
    )

    exporter.export_vmd_binary("./output/test_morph_crossfade.vmd")
    exporter.export_vmd_text("./output/test_morph_crossfade_debug.json")


if __name__ == "__main__":
    demo_main()
