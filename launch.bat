@echo off
setlocal

for %%P in (5000 5001 5002 5003 5004) do (
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod -TimeoutSec 1 http://127.0.0.1:%%P/api/health; if($r.data.status -eq 'ok'){exit 0}else{exit 1} } catch { exit 1 }"
  if not errorlevel 1 (
    start "" http://127.0.0.1:%%P/dashboard
    exit /b 0
  )
)

set PORT=
for %%P in (5000 5001 5002 5003 5004) do (
  netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul
  if errorlevel 1 if not defined PORT set PORT=%%P
)

if not defined PORT (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Ports 5000 through 5004 are already in use. Close another local application and try again.','B2A Budget Tracker')"
  exit /b 1
)

set BUDGET_TRACKER_PORT=%PORT%
start "" "%~dp0budget_tracker.exe"

for /L %%I in (1,1,20) do (
  timeout /t 1 /nobreak >nul
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod -TimeoutSec 1 http://127.0.0.1:%PORT%/api/health; if($r.data.status -eq 'ok'){exit 0}else{exit 1} } catch { exit 1 }"
  if not errorlevel 1 (
    start "" http://127.0.0.1:%PORT%/dashboard
    exit /b 0
  )
)

powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('The tracker did not start. Contact support and provide the application version.','B2A Budget Tracker')"
exit /b 1
