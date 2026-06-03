@echo off
REM Launches the local transcription tool on Windows, then opens your browser.
REM Close this window (or press Ctrl+C) to stop.
cd /d "%~dp0"
set PORT=8000
echo.
echo   Audio Transcription tool
echo   ------------------------
echo   Opening:  http://localhost:%PORT%/
echo   Stop:     close this window
echo.
start "" "http://localhost:%PORT%/"
py -m http.server %PORT% 2>nul || python -m http.server %PORT%
