@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ============================================================
REM  Compilador EXE para ObraPasaLista (Windows + PyInstaller)
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "APP_FILE=%PROJECT_DIR%src\ObraPasaLista v1.0 - app.py"
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
set "DIST_DIR=%PROJECT_DIR%dist"
set "BUILD_DIR=%PROJECT_DIR%build"
set "SPEC_DIR=%PROJECT_DIR%"
set "EXE_NAME=ObraPasaLista"

if not exist "%APP_FILE%" (
  echo [ERROR] No encuentro el archivo principal:
  echo         %APP_FILE%
  echo Coloca este .bat en la raiz del proyecto.
  pause
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo [ERROR] No encuentro el Python del entorno virtual:
  echo         %VENV_PY%
  echo Crea antes el .venv o corrige la ruta.
  pause
  exit /b 1
)

echo.
echo [1/5] Actualizando pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo [2/5] Instalando dependencias de build...
"%VENV_PY%" -m pip install pyinstaller flask jinja2
if errorlevel 1 goto :fail

echo.
echo [3/5] Limpiando compilaciones anteriores...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_DIR%%EXE_NAME%.spec" del /q "%SPEC_DIR%%EXE_NAME%.spec"

echo.
echo [4/5] Generando EXE...
"%VENV_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name "%EXE_NAME%" ^
  --hidden-import flask ^
  --hidden-import jinja2 ^
  --collect-all flask ^
  --collect-all jinja2 ^
  "%APP_FILE%"
if errorlevel 1 goto :fail

echo.
echo [5/5] Resultado:
if exist "%DIST_DIR%\%EXE_NAME%.exe" (
  echo EXE generado correctamente:
  echo   %DIST_DIR%\%EXE_NAME%.exe
) else (
  echo [ERROR] PyInstaller termino pero no encuentro el EXE.
  goto :fail
)

echo.
echo AVISO IMPORTANTE:
 echo - Tu app usa SQLite y backups locales.
 echo - Antes de repartir el EXE conviene revisar donde se guardan app.db y backups.
 echo - Si el EXE falla al arrancar, prueba primero sin --onefile o revisa rutas persistentes.

echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] La compilacion ha fallado.
pause
exit /b 1
