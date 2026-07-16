@echo off
setlocal
set PORT=5000
for %%P in (5000 5001 5002 5003 5004) do (
  netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul
  if errorlevel 1 (
    set PORT=%%P
    goto found_port
  )
)
:found_port
set BUDGET_TRACKER_PORT=%PORT%
start "" "%~dp0budget_tracker.exe"
timeout /t 2 /nobreak >nul
start http://localhost:%PORT%
