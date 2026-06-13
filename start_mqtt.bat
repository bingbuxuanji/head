@echo off
cd /d "%~dp0"
title 智能头盔 MQTT 服务器

REM 杀掉旧的占用 1883 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :1883 ^| findstr LISTENING') do (
    echo 正在关闭旧进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ============================================================
echo         智能头盔 MQTT 服务器 v1.0
echo         Smart Helmet MQTT Broker
echo ============================================================
echo.
echo   监听地址: 0.0.0.0:1883
echo   穿透地址: frp-run.com:18830
echo   数据管道: validate - threshold_check - console_report - persist
echo.
echo   按 Ctrl+C 停止服务器
echo ============================================================
echo.

chcp 65001 >nul 2>&1
python -m mqtt_server.run 2>&1
pause
