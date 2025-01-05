# main/analysis/hatsuon.py
# -*- coding: utf-8 -*-

"""
hatsuon.py

日本語テキストの発音表記（音素列）を取得するためのモジュール。
簡易なひらがな→ローマ字変換や、オーバーラップを考慮した音素区間生成などを扱う。

想定用途:
  1. テキストを入力すると、音素列 (["a", "i", "u", ...]) を返す
  2. text_to_phoneme_timing(text, total_duration) で
     各音素の開始/終了時刻 (start, end) を計算して返す
  3. overlap_ratio を指定することで、音素区間をやや重ねる等の処理

依存:
 - Python 3.7 以上
 - re, logging (標準ライブラリ)
 - 追加ライブラリが必要なら随時

注意:
 - 正確な日本語音素解析には OpenJTalk や MeCab + 音韻辞書が必要になる場合もあるが、
   ここではデモ/簡易実装としてダミー変換を使う。
 - 将来的に英語対応したい場合は language="en" などの分岐を追加できる。
   (ここではダミー対応として、英語ならそのままスペルを音素扱いするなど)
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class HatsuonEngine:
    """
    日本語テキスト → 音素列 の変換を行い、
    必要に応じてオーバーラップ付きの "start","end" を計算するためのクラス。

    例:
        engine = HatsuonEngine(overlap_ratio=0.2)
        # overlap_ratio=0.2 なら音素の区間を 20% 程度重ねるようなタイミング生成（簡易例）
    """

    def __init__(
        self,
        dictionary_path: str = "",
        language: str = "ja",
        overlap_ratio: float = 0.2
    ):
        """
        Args:
            dictionary_path (str): 独自辞書がある場合のパス (使わないなら空でOK)
            language (str): "ja" (日本語), "en" (英語) など将来拡張を想定
            overlap_ratio (float): 次の音素が前の音素にどれだけ重なるか (0.0~1.0)
        """
        self.dictionary_path = dictionary_path
        self.language = language.lower()
        self.overlap_ratio = overlap_ratio

        self._init_dictionary()

    def _init_dictionary(self):
        """
        独自辞書のロード処理 (ここではダミー)。
        実際には MeCab + IPAdic / OpenJTalk辞書などを使う可能性がある。
        """
        if self.dictionary_path:
            logger.info(f"[HatsuonEngine] Loading dictionary from: {self.dictionary_path}")
            # TODO: 実際に辞書を読み込む処理
        else:
            logger.debug("[HatsuonEngine] No custom dictionary. Using default rules.")

    def text_to_phonemes(self, text: str) -> List[str]:
        """
        テキストを音素列に変換 (発音順の文字列リスト)。
        - 現状は日本語(ja)向けの簡易実装とし、それ以外の言語はダミー化。
        
        Returns:
            List[str]: 例 ["a", "i", "u", ...]
        """
        text = text.strip()
        if not text:
            logger.warning("[HatsuonEngine] text is empty -> returning empty phonemes.")
            return []

        # 言語別に分岐 (現時点は日本語のみ本格→それ以外はダミー)
        if self.language == "ja":
            return self._text_to_phonemes_japanese(text)
        else:
            logger.warning(f"[HatsuonEngine] 未対応の言語: {self.language}, ダミー音素にフォールバックします。")
            # ざっくり英語風に、1文字1音素扱い
            return [ch for ch in text.replace(" ", "")]

    def text_to_phoneme_timing(self, text: str, total_duration: float) -> List[Dict]:
        """
        テキストを音素列に変換し、各音素の (start, end) を付与した
        リストを返す。overlap_ratio を考慮して隣接音素を多少重ねるなどの処理を行う。

        例:
            input: text="こんにちは", total_duration=2.0
            output: [
                {"phoneme":"ko", "start":0.0,   "end":0.4},
                {"phoneme":"n",  "start":0.36,  "end":0.7},  # overlap=0.04
                ...
            ]

        Args:
            text (str): 入力テキスト
            total_duration (float): 音声全体の長さ(秒) (仮に既知とする)

        Returns:
            List[Dict]: 1音素ごとに {"phoneme":..., "start":..., "end":...} を含む
        """
        phonemes = self.text_to_phonemes(text)
        n_ph = len(phonemes)
        if n_ph == 0 or total_duration <= 0:
            return []

        base_dur = total_duration / n_ph
        timeline = []

        for i, ph in enumerate(phonemes):
            if i == 0:
                start_t = 0.0
            else:
                prev_end = timeline[-1]["end"]
                overlap_t = base_dur * self.overlap_ratio
                candidate_start = prev_end - overlap_t
                start_t = max(candidate_start, 0.0)

            end_t = start_t + base_dur
            timeline.append({
                "phoneme": ph,
                "start": start_t,
                "end": end_t
            })

        return timeline

    # ------------------------------------------------------------------------
    # 内部で使う簡易的な日本語 → ローマ字変換例 (ダミー)
    # ------------------------------------------------------------------------
    def _text_to_phonemes_japanese(self, text_jp: str) -> List[str]:
        """
        シンプル: ひらがな/カタカナ/漢字入り文章 → ローマ字音素リスト (ダミー)。
        """
        # 前処理(正規化)
        normalized = self._normalize_text(text_jp)

        # 全角カナ/漢字が含まれる場合は、とりあえずひらがなに変換するか省略
        # -> ここでは簡単に "ふりがな化" は省略し、カタカナ/漢字はそのままローマ字化
        #   (実際には MeCabなどでふりがな取得する必要がある)
        roman_str = self._hiragana_to_roman(normalized)

        # ローマ字列 → 音素配列
        phoneme_list = self._split_roman_to_phonemes(roman_str)
        return phoneme_list

    def _normalize_text(self, text: str) -> str:
        """
        文字正規化:
         - 全角スペース→半角
         - 改行やタブ→空白
         - 連続空白を1つに
        """
        text = text.replace("\u3000", " ")
        text = re.sub(r"[\r\n\t]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _hiragana_to_roman(self, text_jp: str) -> str:
        """
        ひらがな→簡易ローマ字(ダミー)。
        カタカナ/漢字は適当に１文字ずつ "X" に置き換えるなど省略的に実装してもOK。
        """
        hira_map = {
            'あ': 'a','い': 'i','う': 'u','え': 'e','お': 'o',
            'か': 'ka','き': 'ki','く': 'ku','け': 'ke','こ': 'ko',
            'さ': 'sa','し': 'shi','す': 'su','せ': 'se','そ': 'so',
            'た': 'ta','ち': 'chi','つ': 'tsu','て': 'te','と': 'to',
            'な': 'na','に': 'ni','ぬ': 'nu','ね': 'ne','の': 'no',
            'は': 'ha','ひ': 'hi','ふ': 'fu','へ': 'he','ほ': 'ho',
            'ま': 'ma','み': 'mi','む': 'mu','め': 'me','も': 'mo',
            'や': 'ya','ゆ': 'yu','よ': 'yo',
            'ら': 'ra','り': 'ri','る': 'ru','れ': 're','ろ': 'ro',
            'わ': 'wa','を': 'wo','ん': 'n',

            # 小文字
            'ぁ': 'a','ぃ': 'i','ぅ': 'u','ぇ': 'e','ぉ': 'o',
            'ゃ': 'ya','ゅ': 'yu','ょ': 'yo',
            'っ': 'xtsu',  # 促音(簡易)
        }

        result_chars = []
        for ch in text_jp:
            if ch in hira_map:
                result_chars.append(hira_map[ch])
            elif 'ァ' <= ch <= 'ヶ':
                # カタカナの場合の簡易処理(例: 全部 "ka"など)
                # 実際にはカタカナ -> ひらがな ->上記Mapで変換が自然
                # ここではデモ的に "?" としておく
                result_chars.append("?")
            elif ch in (' ', ',', '。', '、', '！', '？'):
                # 記号/スペースは無視 or 分割に
                continue
            else:
                # 漢字やその他文字は1文字ごとに "X" とする(ダミー)
                result_chars.append("X")

        return "".join(result_chars)

    def _split_roman_to_phonemes(self, roman_str: str) -> List[str]:
        """
        ローマ字列を音素配列に分割するダミー。
        例: "konnnichiwa" -> ["ko", "n", "ni", "chi", "wa"]
        """
        text = roman_str.lower()

        patterns = [
            "xtsu","chi","shi","tsu","kyo","kya","kyu",
            "sho","sha","shu","cho","cha","chu",
            "nn","n",  # n周りを先に
            "ko","ki","ka","ku","wa","wo","na","ni","nu","no","ta","te","to","su",
            "ma","mi","mo","chi","a","i","u","e","o"
            # ...
        ]
        # 長いもの優先でマッチ
        patterns = sorted(patterns, key=len, reverse=True)

        result = []
        idx = 0
        while idx < len(text):
            matched = False
            for p in patterns:
                if text[idx:].startswith(p):
                    result.append(p)
                    idx += len(p)
                    matched = True
                    break
            if not matched:
                # 合致しない文字は1文字切り出し
                result.append(text[idx])
                idx += 1

        return result


def main():
    engine = HatsuonEngine(overlap_ratio=0.3)
    text_input = "こんにちは世界"
    total_dur = 2.0  # 2秒に割り当てる

    p_list = engine.text_to_phonemes(text_input)
    print("[DEBUG] phonemes:", p_list)

    timeline = engine.text_to_phoneme_timing(text_input, total_dur)
    print("[DEBUG] phoneme_timing with overlap:")
    for seg in timeline:
        print(f"  {seg['phoneme']} : start={seg['start']:.3f}, end={seg['end']:.3f}")


if __name__ == "__main__":
    main()
