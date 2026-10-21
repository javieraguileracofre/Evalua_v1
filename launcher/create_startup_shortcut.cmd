@echo off
setlocal EnableExtensions
title EvaluaERP - inicio automatico
cd /d "%~dp0"

echo.
echo  Esto es OPCIONAL. Hara que EvaluaERP arranque al iniciar sesion.
echo  No se necesitan permisos de administrador.
echo.

if /I "%~1"=="-Remove" goto :remove
if /I "%~1"=="/Remove" goto :remove

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_startup_shortcut.ps1"
goto :done

:remove
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_startup_shortcut.ps1" -Remove

:done
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo  No se pudo actualizar el inicio automatico. Codigo %ERR%.
  pause
)
endlocal
exit /b %ERR%
