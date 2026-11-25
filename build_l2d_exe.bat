@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building 朵莉姆桌寵.exe ...
python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "朵莉姆桌寵" ^
  --icon "assets/icons/moonflower.ico" ^
  --add-data "assets/pixel64;assets/pixel64" ^
  --add-data "assets/icons;assets/icons" ^
  --add-data "fonts/Cubic_11.ttf;fonts" ^
  --add-data "fonts/OFL.txt;fonts" ^
  --distpath "dist\朵莉姆桌寵" ^
  l2d_pet.pyw
if errorlevel 1 exit /b 1
if exist "unity\Build\DreamGodGames.exe" (
  echo Copying Unity mini-games ...
  robocopy "unity\Build" "dist\朵莉姆桌寵\unity\Build" /E /NFL /NDL /NJH /NJS >nul
)
echo.
echo Done: dist\朵莉姆桌寵\朵莉姆桌寵.exe
exit /b 0
