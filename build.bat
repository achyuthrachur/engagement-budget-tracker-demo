@echo off
setlocal
for /f %%V in ('python -c "from version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%V"
if not defined APP_VERSION exit /b 1

if not exist release mkdir release
del /Q release\budget_tracker.exe 2>nul
del /Q release\QUICK_START.md 2>nul
del /Q release\B2A_Budget_Tracker_*.zip 2>nul

python scripts\build_instructions_doc.py "release\B2A_Budget_Tracker_Instructions.docx"
if errorlevel 1 exit /b 1

if not exist frontend\node_modules (
  pushd frontend
  call npm ci
  popd
)
pushd frontend
call npm run build
popd
if errorlevel 1 exit /b 1
if not exist frontend_dist\index.html (
  echo Frontend build missing: frontend_dist\index.html not found after npm run build
  exit /b 1
)

python -m PyInstaller --noconfirm --clean --onefile --noconsole --name B2A_Budget_Tracker --add-data "schema.sql;." --add-data "templates;templates" --add-data "static;static" --add-data "demo_seed.db;." --add-data "frontend_dist;frontend_dist" app.py
if errorlevel 1 exit /b 1

copy /Y dist\B2A_Budget_Tracker.exe release\B2A_Budget_Tracker.exe >nul
copy /Y launch.bat release\launch.bat >nul
copy /Y install.bat release\install.bat >nul
>release\VERSION.txt echo B2A Budget Tracker %APP_VERSION%

powershell -NoProfile -Command "$files=@('release\B2A_Budget_Tracker.exe','release\B2A_Budget_Tracker_Instructions.docx','release\install.bat','release\launch.bat','release\VERSION.txt'); Compress-Archive -LiteralPath $files -DestinationPath 'release\B2A_Budget_Tracker_%APP_VERSION%.zip' -Force"
if errorlevel 1 exit /b 1

echo Built shareable executable: release\B2A_Budget_Tracker.exe
echo Built complete ZIP: release\B2A_Budget_Tracker_%APP_VERSION%.zip
