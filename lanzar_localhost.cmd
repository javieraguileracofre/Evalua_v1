@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title EvaluaERP - localhost

if exist "env\Scripts\python.exe" (
  set "PY=env\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo.
echo  EvaluaERP — arranque local
echo  Carpeta: %CD%
echo  Python:  %PY%
echo  Host/puerto: valores de .env (UVICORN_HOST / UVICORN_PORT)
echo  Abrir:   http://127.0.0.1:8001
echo  (si cambiaste UVICORN_PORT en .env, usa ese puerto)
echo.
echo  Ctrl+C para detener.
echo.

"%PY%" main.py
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo ERROR: la aplicacion termino con codigo %ERR%.
  pause
)
endlocal
exit /b %ERR%
