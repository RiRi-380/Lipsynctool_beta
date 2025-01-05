#!/usr/bin/env bash
# ============================================================
# build_exe.sh
#
# Linux/Mac向けに PyInstaller を使ってビルドするサンプル。
# 実際には python3, pip3 コマンド名や仮想環境管理など環境に合わせて調整。
# ============================================================

echo "[build_exe] Unix系ビルド開始..."

# (1) 必要に応じて仮想環境をactivateする例:
# source venv/bin/activate

# (2) ライブラリを最新化
echo "[build_exe] pip install --upgrade -r ../../requirements.txt"
pip3 install --upgrade -r ../../requirements.txt

echo "[build_exe] PyInstaller でビルド開始"
python3 -m PyInstaller \
  --name "LipSyncTool" \
  --onefile \
  --noconsole \
  --icon ../../assets/app_icon.ico \
  ../../main/ui/main_app.py

# 出力物は dist/LipSyncTool (実行ファイル) あたりに生成される
echo "[build_exe] ビルド完了。"
