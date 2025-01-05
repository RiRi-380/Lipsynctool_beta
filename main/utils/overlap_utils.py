# main/utils/overlap_utils.py
# -*- coding: utf-8 -*-

"""
overlap_utils.py

音素のオーバーラップやタイミング調整、イージング計算などをまとめたユーティリティモジュール。

使いどころ:
  - テキスト→音素列の後、音素と音素の区間をどう割り当てるか(開始/終了時刻)
  - overlap_ratio (0~1) に基づき、前の音素が終わる前に次の音素が始まるような調整
  - シンプルなイージング処理などはオプション扱い

依存:
  - Python 3.7 以上
  - numpy 等 (必要に応じて)
  - メインの lip_sync_generator や hatsuon.py から呼び出される想定
"""

from typing import List, Dict

def apply_overlap_easing(lip_sync_frames: List[Dict], overlap_ratio: float = 0.2) -> List[Dict]:
    """
    lip_sync_frames に対して、前後の音素を overlap_ratio のぶんだけ重ねるように調整を行う。

    Args:
        lip_sync_frames (List[Dict]): 例: [
            {"start": 0.0, "end": 0.3, "phoneme": "a", "avg_rms": 0.4},
            {"start": 0.3, "end": 0.6, "phoneme": "i", "avg_rms": 0.7},
            ...
        ]
        overlap_ratio (float): 0.0~1.0 の範囲で、重ねる割合を指定。
            たとえば 0.2 なら、各音素区間の 20%ぶんだけ前の音素に食い込ませるイメージ。

    Returns:
        List[Dict]: overlap 適用後の lip_sync_frames（start/end/phoneme/avg_rms 構造は同じ）
    """
    if not lip_sync_frames or overlap_ratio <= 0.0:
        return lip_sync_frames

    # コピーして編集
    adjusted = []
    adjusted.append(dict(lip_sync_frames[0]))  # 最初の音素はそのまま

    for i in range(1, len(lip_sync_frames)):
        prev_frame = adjusted[-1]
        current_frame = dict(lip_sync_frames[i])

        base_duration = current_frame["end"] - current_frame["start"]
        overlap_time = base_duration * overlap_ratio

        # 前の音素終了時刻
        prev_end = prev_frame["end"]
        # 今の音素の開始時刻(オリジナル)
        curr_start = current_frame["start"]

        # 前音素の終了時刻より overlap_time だけ先行して開始させるイメージ
        # 例: もし curr_start == prev_end なら overlap_time 分だけ食い込ませたい => curr_start - overlap_time
        new_start = curr_start - overlap_time

        # ただし new_start が前音素の end を超えないように、あるいは
        # いろいろな条件に応じて微調整するのが本来は理想。
        # ここでは簡易に「new_start < prev_end の場合だけ重ねる」ような処理
        if new_start < prev_end:
            # 前音素の end と今の start に overlap_time 分のオーバーラップをつくる
            # → 余りがマイナスになりすぎるなら制限
            # ここでは半分ずつ妥協して前音素を少し縮める/後ろを前にずらすなど
            delta = prev_end - new_start
            # 例: 余りがあるなら前音素の end を overlap_time*0.5 分だけ手前に詰める
            #     (実運用の要件次第でロジックを変える)
            shift_amt = min(delta, overlap_time) * 0.5

            prev_frame["end"] -= shift_amt
            new_start += shift_amt
        else:
            # new_start >= prev_end なら、そもそも重ならないので何もしない
            pass

        current_frame["start"] = new_start
        current_frame["end"] = new_start + base_duration

        adjusted[-1] = prev_frame  # 更新
        adjusted.append(current_frame)

    return adjusted

# ------------------------------------------------------
#  以下、テスト用の簡易デモ or サンプル
# ------------------------------------------------------
if __name__ == "__main__":
    # ダミーの lip_sync_frames
    lip_sync_frames_example = [
        {"start": 0.0, "end": 0.5, "phoneme": "a", "avg_rms": 0.4},
        {"start": 0.5, "end": 1.0, "phoneme": "i", "avg_rms": 0.2},
        {"start": 1.0, "end": 1.5, "phoneme": "u", "avg_rms": 0.7},
    ]

    print("[Before overlap easing]")
    for f in lip_sync_frames_example:
        print(f)

    new_frames = apply_overlap_easing(lip_sync_frames_example, overlap_ratio=0.2)

    print("\n[After overlap easing]")
    for f in new_frames:
        print(f)
