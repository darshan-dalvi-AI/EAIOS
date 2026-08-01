@echo off
rem ============================================================
rem  Install frontend dependencies (Monaco editor, Yjs CRDT)
rem  Run this after pulling changes that add new npm packages.
rem ============================================================
cd /d "%~dp0frontend"
echo.
echo Installing frontend packages in:
echo   %CD%
echo.
echo This pulls in the Monaco editor (large) - allow a few minutes.
echo.
call npm install --no-audit --no-fund
if errorlevel 1 goto :retry
goto :done

:retry
echo.
echo ============================================================
echo  Install failed. Clearing node_modules and retrying once -
echo  this fixes the cross-platform binary problem.
echo ============================================================
echo.
if exist node_modules rmdir /s /q node_modules
if exist package-lock.json del /f /q package-lock.json
call npm install --no-audit --no-fund
if errorlevel 1 goto :failed

:done
echo.
echo ============================================================
echo  DONE. Frontend packages installed.
echo  Start the dev server with:  npm run dev
echo ============================================================
echo.
pause
exit /b 0

:failed
echo.
echo ============================================================
echo  STILL FAILING. Copy the red error text above and send it
echo  to Claude - do not send any keys or passwords.
echo ============================================================
echo.
pause
exit /b 1
