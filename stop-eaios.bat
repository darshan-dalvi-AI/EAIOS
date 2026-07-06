@echo off
title EAIOS Stop
taskkill /fi "WINDOWTITLE eq EAIOS Backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq EAIOS Frontend*" /t /f >nul 2>&1
echo EAIOS servers stopped.
timeout /t 2 >nul
