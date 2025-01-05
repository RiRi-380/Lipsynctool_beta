# main/utils/vmd_converter.py
# -*- coding: utf-8 -*-

"""
vmd_converter.py

MMD(MikuMikuDance)向けモーションファイル (VMD) を作成・編集するためのモジュール。

【ポイント】
1. VMD形式はバイナリ形式で以下を含む:
   (1) ヘッダ文字列 "Vocaloid Motion Data 0002" (30byte)
   (2) モデル名(20byte, Shift-JIS)
   (3) ボーンアニメ数(uint32) + そのデータ(ボーン名15byte + frame + pos + rot + 補間)
   (4) モーフアニメ数(uint32) + モーフデータ(表情名15byte + frame + weight)
   (5) カメラアニメ数(uint32) + ...
   (6) 照明アニメ数(uint32) + ...
   (7) セルフ影数(uint32) + ...
   (8) IK数(uint32) + ...
2. 実際のMMDで読ませるには、Shift-JISの厳密な長さ制限、補間曲線(64byte)の対応などが必要。
3. ここではモーフアニメを中心に扱い、**ボーンキーやカメラキーもダミー構造として追加**し、
   VMDの最小構造を示す。
"""

import os
import struct
import json


class MmdVmdConverter:
    """
    LipSyncGenerator が生成した lip_sync_data (音素と時系列情報) を元に、
    VMDファイルを作成するコンバータクラス。

    - ボーンアニメ (bone_tracks)
    - モーフアニメ (morph_tracks)
    - カメラアニメ (camera_tracks) など

    ここでは lip_sync_data からモーフアニメだけ生成する例。
    """

    DEFAULT_HEADER_STR = "Vocaloid Motion Data 0002"

    def __init__(self, model_name="SomeModel"):
        """
        Args:
            model_name (str): VMDのモデル名 (20byte, Shift-JIS前提)
        """
        self.model_name = model_name
        self.header_str = self.DEFAULT_HEADER_STR

        # 3種類のトラックをそれぞれリストで保持する例
        self.bone_tracks = []   # [ { "bone_name":..., "frame":..., "pos":(x,y,z), "rot":(qx,qy,qz,qw), ... }, ... ]
        self.morph_tracks = []  # [ { "frame":..., "morph_name":..., "weight":... }, ... ]
        self.camera_tracks = [] # [ { "frame":..., "distance":..., "pos":(x,y,z), "rot":(rx,ry,rz), ... }, ... ]

    # -----------------------------------------------------------------------
    # API: モーフキーを追加（lip_sync用）
    # -----------------------------------------------------------------------
    def add_morph_key(self, frame_number: int, morph_name: str, weight: float):
        """
        モーフキーを1件追加する。
        Args:
            frame_number (int): フレーム番号
            morph_name (str): モーフ名 (Shift-JIS 15byte上限)
            weight (float): モーフ値 (0.0 ~ 1.0想定)
        """
        self.morph_tracks.append({
            "frame": frame_number,
            "morph_name": morph_name,
            "weight": weight
        })

    def from_lip_sync_data(self, lip_sync_data: dict, fps: int = 30):
        """
        lip_sync_data (lip_sync_frames) からモーフキーを生成。
        """
        self.morph_tracks.clear()

        frames_info = lip_sync_data.get("lip_sync_frames", [])
        for frame_info in frames_info:
            phoneme = frame_info.get("phoneme", "a")
            start_sec = frame_info.get("start", 0.0)
            end_sec = frame_info.get("end", start_sec + 0.1)

            mid_sec = (start_sec + end_sec) * 0.5
            frame_number = int(mid_sec * fps)

            avg_rms = frame_info.get("avg_rms", 0.0)
            weight = min(1.0, avg_rms * 2.0)  # 適当にスケール

            self.add_morph_key(frame_number, phoneme, weight)

    def sort_tracks(self):
        """
        ボーン / モーフ / カメラ各トラックをフレーム順にソートする。
        """
        self.bone_tracks.sort(key=lambda x: x["frame"])
        self.morph_tracks.sort(key=lambda x: x["frame"])
        self.camera_tracks.sort(key=lambda x: x["frame"])

    # -----------------------------------------------------------------------
    # 実際にVMDバイナリを書き出す
    # -----------------------------------------------------------------------
    def export_vmd_binary(self, output_path: str):
        """
        VMDバイナリとして書き出す。
        - ボーンキーは self.bone_tracks
        - モーフキーは self.morph_tracks
        - カメラキーは self.camera_tracks
        """
        self.sort_tracks()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as f:
            # 1) header (30byte)
            header_bytes = self._encode_sjis_with_nullfill(self.header_str, 30)
            f.write(header_bytes)

            # 2) model_name (20byte)
            model_bytes = self._encode_sjis_with_nullfill(self.model_name, 20)
            f.write(model_bytes)

            # 3) ボーンキー数
            bone_count = len(self.bone_tracks)
            f.write(struct.pack("<I", bone_count))

            # 4) ボーンキー列
            for bone in self.bone_tracks:
                # bone_name(15byte, shift-jis), frame(uint32)
                bname = bone.get("bone_name", "dummy_bone")
                frame_no = bone.get("frame", 0)
                name_bytes = self._encode_sjis_with_nullfill(bname, 15)
                f.write(name_bytes)
                f.write(struct.pack("<I", frame_no))

                # pos(x,y,z) float32, rot(x,y,z) quaternion/オイラー? => MMD仕様は回転(四元数)
                # ここではダミー: pos=(0,0,0), rot=(0,0,0,1)
                pos = bone.get("pos", (0.0, 0.0, 0.0))
                rot = bone.get("rot", (0.0, 0.0, 0.0, 1.0))

                f.write(struct.pack("<3f", *pos))
                f.write(struct.pack("<4f", *rot))

                # 補間データ(64byte)
                # MMDではX軸/Y軸/Z軸/回転の4要素それぞれにbezier8byteがある
                # ここでは全てゼロ埋め(定速)
                f.write(b"\x00" * 64)

            # 5) モーフキー数
            morph_count = len(self.morph_tracks)
            f.write(struct.pack("<I", morph_count))

            # 6) モーフキー列
            for morph in self.morph_tracks:
                mname = morph.get("morph_name", "a")
                frame_no = morph.get("frame", 0)
                weight = morph.get("weight", 0.0)

                mname_bytes = self._encode_sjis_with_nullfill(mname, 15)
                f.write(mname_bytes)
                f.write(struct.pack("<I", frame_no))
                f.write(struct.pack("<f", weight))

            # 7) カメラキー数
            cam_count = len(self.camera_tracks)
            f.write(struct.pack("<I", cam_count))

            # 8) カメラキー列
            # カメラデータ構造: frame(uint32), distance(float), pos(3f), rot(3f), 24byteの補間, view_angle(uint32), perspective_disable(uint8)
            for cam in self.camera_tracks:
                frame_no = cam.get("frame", 0)
                distance = cam.get("distance", 0.0)
                pos = cam.get("pos", (0.0, 0.0, 0.0))
                rot = cam.get("rot", (0.0, 0.0, 0.0))
                view_angle = cam.get("view_angle", 30)
                perspective_off = cam.get("perspective_off", 0)  # 0=on,1=off

                f.write(struct.pack("<I", frame_no))
                f.write(struct.pack("<f", distance))
                f.write(struct.pack("<3f", *pos))
                f.write(struct.pack("<3f", *rot))

                # カメラ補間(24byte)
                f.write(b"\x00" * 24)

                f.write(struct.pack("<I", view_angle))
                f.write(struct.pack("<B", perspective_off))

            # 9) Lightキー数 (0)
            f.write(struct.pack("<I", 0))
            # 10) Self Shadow数 (0)
            f.write(struct.pack("<I", 0))
            # 11) IKキー数 (0)
            f.write(struct.pack("<I", 0))

        print(f"[MmdVmdConverter] バイナリVMDを '{output_path}' に出力しました。 (拡張実装)")

    # -----------------------------------------------------------------------
    # テキスト/JSON 出力 (デバッグ用)
    # -----------------------------------------------------------------------
    def export_vmd_text(self, output_path: str):
        """
        デバッグ用に、現在のトラック情報を JSON 形式で書き出す。
        MMD では読み込めないが、内部構造確認に利用。
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        data = {
            "header_str": self.header_str,
            "model_name": self.model_name,
            "bone_tracks": self.bone_tracks,
            "morph_tracks": self.morph_tracks,
            "camera_tracks": self.camera_tracks,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[MmdVmdConverter] テキスト形式のVMDデータを '{output_path}' に出力しました。")

    # -----------------------------------------------------------------------
    # ヘルパー: Shift-JISエンコード + 長さ合わせ(null埋め)
    # -----------------------------------------------------------------------
    def _encode_sjis_with_nullfill(self, text: str, length: int) -> bytes:
        """
        Shift-JIS エンコードし、lengthバイト以内に収めて末尾を null 埋めまたは切り捨て。
        """
        encoded = text.encode("shift_jis", errors="replace")
        if len(encoded) >= length:
            encoded = encoded[:length]
        else:
            encoded += b"\x00" * (length - len(encoded))
        return encoded


def demo():
    """
    デモ用: ダミーlip_sync_data からモーフアニメを作成し、VMD書き出し。
    """
    # lip_sync_dataの例
    lip_sync_data_example = {
        "lip_sync_frames": [
            {"start": 0.0,  "end": 0.2,  "phoneme": "a", "avg_rms": 0.4},
            {"start": 0.2,  "end": 0.4,  "phoneme": "i", "avg_rms": 0.2},
            {"start": 0.4,  "end": 0.6,  "phoneme": "u", "avg_rms": 0.7},
            {"start": 0.6,  "end": 0.8,  "phoneme": "a", "avg_rms": 0.9},
        ]
    }

    converter = MmdVmdConverter(model_name="MyTestModel")
    converter.from_lip_sync_data(lip_sync_data_example, fps=30)
    # 追加でダミーのボーンアニメやカメラアニメを入れてみても良い
    # converter.bone_tracks.append({
    #    "bone_name": "センター",
    #    "frame": 15,
    #    "pos": (0.0, 10.0, 0.0),
    #    "rot": (0.0, 0.0, 0.0, 1.0),
    # })
    # converter.camera_tracks.append({
    #    "frame": 30,
    #    "distance": 30.0,
    #    "pos": (0.0, 15.0, -25.0),
    #    "rot": (0.0, 0.0, 0.0),
    #    "view_angle": 30,
    #    "perspective_off": 0
    # })

    # バイナリVMD出力
    out_vmd = "./output/test_lipsync_expanded.vmd"
    converter.export_vmd_binary(out_vmd)

    # テキスト/JSON形式でデバッグ用出力
    out_json = "./output/test_lipsync_expanded_debug.json"
    converter.export_vmd_text(out_json)


if __name__ == "__main__":
    demo()
