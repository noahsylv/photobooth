@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
mpremote connect COM3 fs cp pico_main.py :main.py
mpremote connect COM3 reset
python app.py
if errorlevel 1 (
    echo.
    echo Photobooth exited with an error. Press any key to close...
    pause >nul
)
