@echo off
REM 必要なら chcp 65001 などで文字コードを設定

echo [build_exe] Windowsビルド開始...

REM (1) conda を使うなら、conda activate などを先にやってもOK
REM call "C:\Users\takay\anaconda3\Scripts\activate.bat"

REM (2) ライブラリを最新化 (PyInstaller 等)
echo [build_exe] pip install --upgrade -r ..\..\requirements.txt
pip install --upgrade -r ..\..\requirements.txt

echo [build_exe] PyInstaller でビルド開始
REM ↓Anacondaのpython.exe で PyInstaller を呼ぶ
"C:\Users\takay\anaconda3\python.exe" -m PyInstaller ^
  --name "LipSyncTool" ^
  --onefile ^
  --noconsole ^
  --icon ..\..\assets\app_icon.ico ^
  ..\..\main\ui\main_app.py

echo [build_exe] ビルド完了。
pause
