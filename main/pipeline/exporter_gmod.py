# main/pipeline/exporter_gmod.py
# -*- coding: utf-8 -*-

"""
exporter_gmod.py (改良版)

- GMod (Garry's Mod) 用のリップシンクファイル(JSON)を出力するためのクラス。
- lip_sync_data["lip_sync_frames"] に対して音素セグメント単位 or フレーム単位で書き出しを選択。
- fade_out=True なら音素終了タイミングで weight=0 (口を閉じる) を追加。
- ファイル名の禁止文字を置換するなど `_sanitize_filename` を導入。
- JSON先頭にmetadataとして version, overlap_rate などを追加。
"""

import os
import json
import re

class GModExporter:
    """
    lip_sync_data から GMod用のリップシンク情報(JSON形式)を
    書き出すサンプルクラス。
    """

    FORBIDDEN_CHARS_PATTERN = r'[\\/:*?"<>|]'  # Windowsで禁止されている文字

    def __init__(self, version="1.0"):
        """
        Args:
            version (str): 出力JSON内のバージョン番号(文字列)
        """
        self.version = version
        # GMod向けに書き出すデータ
        # 例: [{ "time": 0.00, "phoneme": "a", "weight": 0.7 }, ...]
        self.frames_data = []
        # JSON出力に含めるメタ情報（overlap_rate など）
        self.metadata = {
            "version": self.version,
            "generator": "LipSyncTool"
        }

    def from_lip_sync_data(
        self,
        lip_sync_data: dict,
        fps: int = 30,
        granularity: str = "segment",
        fade_out: bool = False
    ):
        """
        lip_sync_data から self.frames_data を構築する。
        Args:
            lip_sync_data (dict):
                例) {
                  "lip_sync_frames": [
                     { "start":0.0, "end":0.2, "phoneme":"a", "avg_rms":0.4},
                     ...
                  ],
                  "export_options": { "overlap_rate": 0.1, ...}
                }
            fps (int): フレームレート（frame granularityを使う場合に参照）
            granularity (str): "segment" か "frame"
              - "segment": 従来通り start/end 単位のブロックで出力
              - "frame": fpsに従って時間をステップ分割し、各フレームごとに phoneme, weight を出力
            fade_out (bool): Trueなら、音素終了で weight=0 (口が閉じる)キーを追加
        """

        self.frames_data.clear()

        # export_options などから overlap_rate を拾う例
        export_opts = lip_sync_data.get("export_options", {})
        overlap_rate = export_opts.get("overlap_rate", 0.0)
        self.metadata["overlap_rate"] = overlap_rate

        lip_sync_frames = lip_sync_data.get("lip_sync_frames", [])

        if granularity == "segment":
            # 音素セグメント単位で JSON化
            for seg in lip_sync_frames:
                start_t = seg.get("start", 0.0)
                end_t   = seg.get("end", start_t + 0.2)
                phoneme = seg.get("phoneme", "a")
                avg_rms = seg.get("avg_rms", 0.0)
                weight  = min(1.0, avg_rms * 2.0)  # 例

                # 開始の時点: weight
                seg_item = {
                    "start": start_t,
                    "end": end_t,
                    "phoneme": phoneme,
                    "weight": weight
                }
                self.frames_data.append(seg_item)

                if fade_out:
                    # 終了フレーム付近でも weight=0
                    fade_item = {
                        "start": end_t,
                        "end":   end_t,  # 同じ時間(口が閉じるキー)
                        "phoneme": phoneme,
                        "weight": 0.0
                    }
                    self.frames_data.append(fade_item)

        elif granularity == "frame":
            # フレーム単位に分割
            # 1) lip_sync_frames を結合して 全体のstart~endを取得
            if not lip_sync_frames:
                return
            total_start = lip_sync_frames[0].get("start", 0.0)
            total_end   = lip_sync_frames[-1].get("end", 0.0)

            current_time = total_start
            time_step = 1.0 / fps

            while current_time <= total_end:
                # いまの time がどの音素セグメントに該当するか探索
                phoneme = None
                weight  = 0.0
                for seg in lip_sync_frames:
                    s = seg["start"]
                    e = seg["end"]
                    if s <= current_time < e:
                        # このセグメント上にある
                        phoneme = seg.get("phoneme", "a")
                        avg_rms = seg.get("avg_rms", 0.0)
                        weight  = min(1.0, avg_rms * 2.0)
                        break

                # fade_out ならセグメント終了近くで weight=0 (ただし連続する音素がある場合は重なる)
                # ここでは簡易的に "終了フレーム±1" などで weight=0 を打つ省略例。
                # (実装任意)

                # frame_data
                self.frames_data.append({
                    "time": round(current_time, 4),
                    "phoneme": phoneme if phoneme else "none",
                    "weight": weight
                })

                current_time += time_step

        else:
            print(f"[GModExporter] 未知のgranularity: {granularity} → 'segment'を使用します。")
            self.from_lip_sync_data(lip_sync_data, fps, granularity="segment", fade_out=fade_out)

    def export_gmod_json(self, output_path: str):
        """
        実際にJSONをファイル出力。
        書き出す構造:
        {
          "metadata": {
             "version": "1.0",
             "generator": "LipSyncTool",
             "overlap_rate": 0.1,
             ...
          },
          "lip_sync": [...]
        }
        """
        output_path = self._sanitize_filename(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        out_data = {
            "metadata": self.metadata,
            "lip_sync": self.frames_data
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)

        print(f"[GModExporter] GMod用JSONを {output_path} に出力しました。")

    # -----------------------------------------
    # 内部ユーティリティ
    # -----------------------------------------
    def _sanitize_filename(self, filename: str) -> str:
        """ Windows禁止文字の置換 + ASCII以外が含まれていたら注意を促す例 """
        base, ext = os.path.splitext(filename)
        sanitized_base = re.sub(self.FORBIDDEN_CHARS_PATTERN, "_", base)

        # ASCII以外(日本語など)を検出
        if re.search(r'[^\x00-\x7F]', sanitized_base):
            print(f"[GModExporter] 注意: ファイル名にUnicode文字が含まれています: {sanitized_base}")

        # デフォルト拡張子を .json にしたいなら
        if not ext:
            ext = ".json"

        new_name = sanitized_base + ext
        dir_name = os.path.dirname(filename)
        return os.path.join(dir_name, new_name)


def demo_main():
    """
    サンプル: lip_sync_data (ダミー) から JSONをエクスポート
    """
    lip_sync_data_example = {
        "export_options": {
            "overlap_rate": 0.1
        },
        "lip_sync_frames": [
            {"start": 0.0,  "end": 0.2,  "phoneme": "a", "avg_rms": 0.4},
            {"start": 0.2,  "end": 0.4,  "phoneme": "i", "avg_rms": 0.2},
            {"start": 0.4,  "end": 0.6,  "phoneme": "u", "avg_rms": 0.7},
            {"start": 0.6,  "end": 0.8,  "phoneme": "a", "avg_rms": 0.9},
        ]
    }

    exporter = GModExporter(version="1.2")

    # 1) 音素セグメント単位 (fade_out=False)
    exporter.from_lip_sync_data(lip_sync_data_example, fps=30, granularity="segment", fade_out=False)
    exporter.export_gmod_json("./output/gmod_segment.json")

    # 2) フレーム単位 + fade_out=True
    exporter.from_lip_sync_data(lip_sync_data_example, fps=30, granularity="frame", fade_out=True)
    exporter.export_gmod_json("./output/gmod_frame.json")


if __name__ == "__main__":
    demo_main()
