@echo off
cd /d "%~dp0"
if exist "dist\夢境神明桌寵.exe" (
  start "" "dist\夢境神明桌寵.exe"
  exit /b 0
)
if exist "夢境神明桌寵.exe" (
  start "" "夢境神明桌寵.exe"
  exit /b 0
)
start "" wscript //nologo "%~dp0tools\start_desktop_pet.vbs"
