@echo off
cd /d "%~dp0\.."
python tools\l2d_split_to_psd.py %*
pause
