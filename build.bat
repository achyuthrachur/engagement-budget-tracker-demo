@echo off
setlocal
python -m PyInstaller --noconfirm --clean --onefile --name budget_tracker --add-data "schema.sql;." --add-data "templates;templates" --add-data "static;static" app.py
if errorlevel 1 exit /b 1
copy /Y dist\budget_tracker.exe budget_tracker.exe >nul
echo Built budget_tracker.exe
