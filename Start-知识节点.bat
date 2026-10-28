@echo off
chcp 65001 >nul
cd /d "%~dp0"
py app\main.py
if errorlevel 1 (
    echo.
    echo 程序异常退出：请把上面的报错信息完整复制或截图，发给 AI。
    pause
)
