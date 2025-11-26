@echo off
REM Build Windows .exe for the SQF -> TCL IDE tool
REM Requirements:
REM   pip install pyinstaller
REM Run this file from the project root (same folder as icon.ico).

echo Building SQF -> TCL Converter IDE...

REM Build from the GUI script (absolute imports in gui.py handle the package)
pyinstaller ^
  --noconsole ^
  --onefile ^
  --name "SQF_to_TCL_Converter" ^
  --icon "icon.ico" ^
  sqf_to_tcl\gui.py

echo.
echo Build finished. You can find SQF_to_TCL_Converter.exe in the dist folder.
pause


