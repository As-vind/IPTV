@echo off
chcp 65001 >nul
title Installation - IPTV Player (par Asvind)
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopy
%PY% installer.py
if errorlevel 1 pause
goto :eof
:nopy
echo Python 3 64 bits est introuvable.
echo Installez-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH", puis relancez.
pause
