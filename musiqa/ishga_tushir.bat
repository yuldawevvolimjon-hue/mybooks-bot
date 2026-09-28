@echo off
rem Navo Music botini Windows kompyuterda ishga tushirish.
rem Ikki marta bosing. Birinchi safar BotFather bergan tokenni so'raydi.
chcp 65001 >nul
cd /d "%~dp0"
title Navo Music bot
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set UYDA=1

rem Python: oddiy o'rnatish (python) yoki yangi Python menejeri (py)
set PY=
python -c "import sys" >nul 2>nul && set PY=python
if not defined PY py -c "import sys" >nul 2>nul && set PY=py
if not defined PY (
  echo.
  echo Python topilmadi. https://www.python.org/downloads/ dan o'rnating
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
%PY% -m pip install -q -U "yt-dlp[default]" static-ffmpeg deno

:qayta
echo.
echo Bot ishlayapti. Bu oynani yopmang!
%PY% bot.py
echo Bot to'xtadi, 5 soniyadan keyin qayta ishga tushadi...
timeout /t 5 >nul
goto qayta
