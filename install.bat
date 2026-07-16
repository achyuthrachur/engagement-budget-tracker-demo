@echo off
setlocal
set "INSTALL_DIR=%LOCALAPPDATA%\Crowe\B2A Budget Tracker\App"

if not exist "%~dp0budget_tracker.exe" (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('budget_tracker.exe must be in the same folder as install.bat.','B2A Budget Tracker')"
  exit /b 1
)

tasklist /FI "IMAGENAME eq budget_tracker.exe" 2>nul | find /I "budget_tracker.exe" >nul
if not errorlevel 1 (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Save any open work and select OK. The installer will stop the running tracker before updating it.','B2A Budget Tracker')"
  taskkill /IM budget_tracker.exe /F >nul 2>&1
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
copy /Y "%~dp0budget_tracker.exe" "%INSTALL_DIR%\budget_tracker.exe" >nul
if errorlevel 1 (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('The application could not be copied. Restart Windows and run install.bat again.','B2A Budget Tracker')"
  exit /b 1
)
copy /Y "%~dp0launch.bat" "%INSTALL_DIR%\launch.bat" >nul

powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\B2A Budget Tracker.lnk'); $s.TargetPath='%INSTALL_DIR%\launch.bat'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.Save()"
if errorlevel 1 exit /b 1

powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Installation complete. Use the B2A Budget Tracker shortcut on your desktop.','B2A Budget Tracker')"
start "" "%INSTALL_DIR%\launch.bat"
