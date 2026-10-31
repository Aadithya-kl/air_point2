@echo off
title AirPoint Gesture Engine
cd /d "%~dp0"
echo ===================================================
echo Starting AirPoint Gesture Engine...
echo Window: VIRTUAL POINTER will open shortly
echo Press 'q' in the camera window to stop
echo ===================================================
.\.venv\Scripts\python.exe main.py
pause
