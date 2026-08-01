@echo off
title K-OS Stop
taskkill /fi "WINDOWTITLE eq K-OS Backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq K-OS Frontend*" /t /f >nul 2>&1
echo K-OS servers stopped.
timeout /t 2 >nul
