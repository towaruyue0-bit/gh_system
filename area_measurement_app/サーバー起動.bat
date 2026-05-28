@echo off
chcp 65001 > nul
echo 図面 面積測定ツール を起動します...
echo.
echo ブラウザが開いたら http://localhost:8766 を開いてください
echo このウィンドウは閉じないでください（閉じるとアプリが止まります）
echo.
start "" "http://localhost:8766"
python -m http.server 8766
pause
