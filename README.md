# LipsyncBeta

日本語音声を解析し、口の動き（リップシンク用データ）を自動生成する Python ベースのプロジェクトです。  
MikuMikuDance (VMD ファイル) や Garry's Mod 用 JSON などへのエクスポートを視野に、**音素解析**・**RMS解析**・**タイムライン編集**・**分散処理**・**PyQt5 GUI** といった機能を統合的に扱います。

---

## 特徴

### 1. リップシンク自動生成
- 日本語音声を解析し、「あ」「い」「う」「え」「お」などの音素区間を自動抽出  
- 短区間ごとの音量（RMS）も同時に解析し、口の開き具合を可視化・制御可能

### 2. 多彩な出力形式
- JSON 形式で解析結果を保存  
- MikuMikuDance (VMD ファイル) への出力  
- Garry’s Mod 向け JSON への変換  
> ※現状、VMD エクスポートは補間カーブなど未完成部分あり

### 3. PyQt5 による GUI
- 音声ファイル選択、解析実行、タイムライン編集、波形プレビューなどを 1 つのアプリで操作  
- Undo/Redo やドラッグ操作で音素ブロックを調整できるため、細かい修正が容易

### 4. 分散処理・高速化
- Celery による大量ファイルの並列解析  
- Cython (`rms_fast.pyx`) による RMS 計算の高速化  
- GPU (CUDA) があれば OpenAI Whisper などでの音声認識を高速化可能（任意）

### 5. 拡張性重視
- コードを `analysis` / `pipeline` / `ui` / `utils` などにモジュール分割し、保守しやすい設計  
- MeCab や OpenJTalk を導入すれば、より高精度な日本語音素解析が可能  

---

## 使用例（概要）

### 1. 環境セットアップ
- Python 3.7 以上を推奨  
- 必要なライブラリをインストール
  ```bash
  pip install -r requirements.txt
  
## 2. GUI を起動

```bash
python -m main.ui.main_app
```
音声ファイルやテキストを指定
解析ボタンを押す


### ライセンス
本プロジェクトは GNU General Public License v3.0 (GPL-3.0) の下で配布されています。
MeCab / ipadic など追加ライセンスにも留意してください。

### リンク
プロジェクト GitHub リポジトリ
参考: AutoYukkuri (by あかず様)
