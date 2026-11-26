@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building Doriimu桌寵.exe ...
python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "Doriimu桌寵" ^
  --icon "assets/icons/moonflower.ico" ^
  --add-data "assets/pixel64;assets/pixel64" ^
  --add-data "assets/icons;assets/icons" ^
  --add-data "assets/six_views/l2d_psd;assets/six_views/l2d_psd" ^
  --add-data "fonts/Cubic_11.ttf;fonts" ^
  --add-data "fonts/OFL.txt;fonts" ^
  --distpath "dist\Doriimu桌寵" ^
  l2d_pet.pyw
if errorlevel 1 exit /b 1
if exist "unity\Build\DreamGodGames.exe" (
  echo Copying Unity mini-games ...
  robocopy "unity\Build" "dist\Doriimu桌寵\unity\Build" /E /NFL /NDL /NJH /NJS >nul
)
echo.
echo Done: dist\Doriimu桌寵\Doriimu桌寵.exe
exit /b 0
