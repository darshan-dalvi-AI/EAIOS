@echo off
cd /d "%~dp0"
echo ============================================
echo  Sync EAIOS to GitHub (darshan-dalvi-AI)
echo ============================================
rem clear a stale lock left by an interrupted git process
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
git rm -r --cached --ignore-unmatch backend/eaios.db-shm backend/eaios.db-wal backend/eaios.db >nul 2>&1
git rm -r --cached --ignore-unmatch "Enterprise AI Operating System" >nul 2>&1
git add -A
git commit -m "Update EAIOS" 2>nul
git push -u origin main
echo.
echo When you see "main -^> main" above, the upload succeeded.
pause
