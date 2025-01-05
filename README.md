LipsyncBeta
日本語音声を解析し、口の動き（リップシンク用データ）を自動生成するPythonベースのプロジェクトです。
MMD (VMDファイル) や Garry's Mod 用 JSONなどへのエクスポートを視野に、音素解析・RMS解析・タイムライン編集・分散処理・PyQt5 GUI といった機能を統合的に扱います。

主な特徴
リップシンク自動生成
日本語音声を解析し、「あ」「い」「う」「え」「お」などの音素区間を自動抽出。
短区間ごとの音量（RMS）も同時に解析し、口の開き具合を可視化・制御可能。
多彩な出力形式
JSON形式で解析結果を保存したり、MikuMikuDance(VMDファイル)やGarry’s Mod向けJSONに変換したりできます。
※現状、VMDエクスポートは補間カーブなど未完成部分あり。
PyQt5によるGUI
音声ファイル選択、解析実行、タイムライン編集、波形プレビューなどを1つのアプリで操作。
Undo/Redoやドラッグ操作で音素ブロックを調整できるため、細かい修正が容易。
分散処理・高速化
Celeryによる大量ファイルの並列解析、Cython (rms_fast.pyx) によるRMS計算の高速化に対応。
GPU(CUDA)があればOpenAI Whisperなどでの音声認識を高速化できる（任意）。
拡張性重視
コードを analysis / pipeline / ui / utils などにモジュール分割し、保守しやすい設計。
MeCabやOpenJTalkを導入すれば、より高精度な日本語音素解析に対応可能。
使用例（概要）
環境セットアップ
Python 3.7 以上推奨
必要なライブラリのインストール（pip install -r requirements.txt など）
GUIを起動
python main_app.py
音声ファイルやテキストを指定 → 解析ボタンを押す → タイムラインでリップシンクを編集
エクスポート
GUIまたはコマンドラインから JSON / VMD / GMod用ファイルへの書き出しを実行
VMD出力は補間カーブやモーフ名の管理に注意が必要
今後の課題
VMDエクスポートの機能強化
モーフ名の扱い・補間カーブ設定・Shift-JIS文字制限などへの対応が不十分
多言語対応・高精度化
MeCabやOpenJTalk導入、英語等の音素解析対応など
リアルタイム処理
Vtuber配信等に応用する場合は、低遅延な音声認識・口パク生成手法を検討中
テスト・ドキュメント充実
CI環境や包括的テスト、ユーザ向けチュートリアルの整備が必要
ライセンス
本プロジェクトは GNU General Public License v3.0 (GPL-3.0) の下で配布されています。
MeCab / ipadic など追加ライセンスにも留意してください。
リンク
https://github.com/akazdayo/AutoYukkuri
参考： AutoYukkuri (by あかず様)