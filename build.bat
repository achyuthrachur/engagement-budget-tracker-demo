@echo off
setlocal
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name budget_tracker --add-data "schema.sql;." --add-data "templates;templates" --add-data "static;static" app.py
if errorlevel 1 exit /b 1
copy /Y dist\budget_tracker.exe budget_tracker.exe >nul
if not exist release mkdir release
copy /Y budget_tracker.exe release\budget_tracker.exe >nul
copy /Y launch.bat release\launch.bat >nul
copy /Y install.bat release\install.bat >nul
copy /Y QUICK_START.md release\QUICK_START.md >nul
>release\VERSION.txt echo B2A Budget Tracker 3.0.0
echo Built release package in release\
