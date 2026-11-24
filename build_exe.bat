@echo off
cd /d "%~dp0"
echo Building 夢境神明桌寵.exe ...
python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "夢境神明桌寵" ^
  --add-data "chibi_base.png;." ^
  --add-data "fonts/Cubic_11.ttf;fonts" ^
  --add-data "fonts/OFL.txt;fonts" ^
  fairy_pet.pyw
if errorlevel 1 exit /b 1
echo.
echo Done: dist\夢境神明桌寵.exe
