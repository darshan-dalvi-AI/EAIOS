@echo off
title EAIOS Frontend Retry
start "EAIOS Frontend" /d "%~dp0frontend" cmd /k "npm install && npm run dev"
exit
