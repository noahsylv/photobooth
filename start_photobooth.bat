@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python app.py
if errorlevel 1 (
    echo.
    echo Photobooth exited with an error. Press any key to close...
    pause >nul
)
