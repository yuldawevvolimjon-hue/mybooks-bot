@echo off
rem Navo Music botini Windows kompyuterda ishga tushirish.
rem Ikki marta bosing. Birinchi safar BotFather bergan tokenni so'raydi.
chcp 65001 >nul
cd /d "%~dp0"
title Navo Music bot
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set UYDA=1

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python o'rnatilmagan. https://www.python.org/downloads/ dan o'rnating
  echo va o'rnatishda "Add python.exe to PATH" belgisini qo'ying.
  echo.
  pause
  exit /b
)

if exist token.txt goto token_bor
echo.
set /p BOT_TOKEN=BotFather bergan tokenni kiriting va Enter bosing: 
>token.txt echo %BOT_TOKEN%
:token_bor
set /p BOT_TOKEN=<token.txt

echo.
echo Kerakli dasturlar o'rnatilmoqda (birinchi safar 1-2 daqiqa)...
python -m pip install -q -U "yt-dlp[default]" static-ffmpeg deno

:qayta
echo.
echo Bot ishlayapti. Bu oynani yopmang!
python bot.py
echo Bot to'xtadi, 5 soniyadan keyin qayta ishga tushadi...
timeout /t 5 >nul
goto qayta
