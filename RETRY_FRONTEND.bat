@echo off
title K-OS Frontend Retry
start "K-OS Frontend" /d "%~dp0frontend" cmd /k "npm install && npm run dev"
exit
