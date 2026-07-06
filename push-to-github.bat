@echo off
cd /d "%~dp0"
echo ============================================
echo  Sync EAIOS to GitHub (darshan-dalvi-AI)
echo ============================================
git add -A
git commit -m "Update EAIOS" 2>nul
git push -u origin main
echo.
echo When you see "main -^> main" above, the upload succeeded.
pause
