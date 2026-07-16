@echo off
setlocal enabledelayedexpansion
title Build ObraPasaLista.exe

echo ================================
echo   Build ObraPasaLista.exe
echo ================================
echo.

rem Nos aseguramos de estar en la carpeta del script
cd /d "%~dp0"

rem Activar entorno virtual
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activando entorno virtual .venv...
    call ".venv\Scripts\activate.bat"
) else (
    echo [ERROR] No se encuentra .venv\Scripts\activate.bat
    echo Crea el venv en este proyecto antes de compilar (python -m venv .venv).
    pause
    exit /b 1
)

rem Comprobar / instalar PyInstaller
pyinstaller --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller no esta instalado en este venv, instalando...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Fallo instalando PyInstaller en el venv.
        pause
        exit /b 1
    )
) else (
    echo [OK] PyInstaller ya instalado en el venv.
)

rem Nombre del script principal de la app (AJUSTA ESTO SI HACE FALTA)
set "APP_MAIN=ObraPasaLista.py"

if not exist "%APP_MAIN%" (
    echo [ERROR] No se encuentra %APP_MAIN% en esta carpeta.
    echo Edita build_obrapasalista.bat y pon el nombre correcto del .py principal.
    pause
    exit /b 1
)

rem Construir argumentos --add-data dinamicamente
set "ADD_DATA_ARGS="

if exist "templates" (
    echo [INFO] Incluyendo carpeta templates en el ejecutable...
    set "ADD_DATA_ARGS=%ADD_DATA_ARGS% --add-data ""templates;templates"""
)

if exist "static" (
    echo [INFO] Incluyendo carpeta static en el ejecutable...
    set "ADD_DATA_ARGS=%ADD_DATA_ARGS% --add-data ""static;static"""
)

if exist "db" (
    echo [INFO] Incluyendo carpeta db (SQLite, etc.) en el ejecutable...
    set "ADD_DATA_ARGS=%ADD_DATA_ARGS% --add-data ""db;db"""
)

echo [INFO] Lanzando PyInstaller...
echo pyinstaller --clean --noconfirm --onefile --windowed --name ObraPasaLista %ADD_DATA_ARGS% "%APP_MAIN%"
echo.

pyinstaller --clean --noconfirm ^
    --onefile --windowed ^
    --name ObraPasaLista ^
    %ADD_DATA_ARGS% ^
    "%APP_MAIN%"

if errorlevel 1 (
    echo [ERROR] PyInstaller ha fallado al crear el ejecutable.
    echo Revisa el log en la consola y corrige rutas / imports.
    pause
    exit /b 1
)

rem Copiar ejecutable a la raiz
if exist "dist\ObraPasaLista.exe" (
    echo [OK] Ejecutable generado: dist\ObraPasaLista.exe
    echo [INFO] Copiando ObraPasaLista.exe a la carpeta actual...
    copy /Y "dist\ObraPasaLista.exe" ".\ObraPasaLista.exe" >nul
    echo [OK] ObraPasaLista.exe listo para enviar a un Windows virgen.
) else (
    echo [WARN] dist\ObraPasaLista.exe no encontrada. Algo ha ido mal en la build.
)

echo.
echo [INFO] Fin del proceso de build.
pause
endlocal