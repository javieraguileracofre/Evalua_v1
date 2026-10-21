@echo off
setlocal EnableExtensions
title EvaluaERP - crear acceso directo
cd /d "%~dp0"

echo.
echo  Se va a crear el icono "Iniciar Aplicacion" en su escritorio.
echo  No se necesitan permisos de administrador.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo  No se pudo crear el acceso directo. Codigo %ERR%.
  pause
)
endlocal
exit /b %ERR%
