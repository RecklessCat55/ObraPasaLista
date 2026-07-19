@echo off
setlocal enabledelayedexpansion
title ObraPasaLista - generador de EXE

echo ============================================================
echo   ObraPasaLista - generador de EXE plug and play
echo ============================================================
echo.
echo   Este script se ejecuta UNA VEZ en tu ordenador de desarrollo
echo   (el que ya tiene Python). Genera dist\ObraPasaLista.exe, que
echo   es el UNICO fichero que hay que llevar al ordenador de obra
echo   (ese no necesita tener Python ni nada instalado).
echo.

cd /d "%~dp0"

if not exist "src\app.py" (
    echo [ERROR] No se encuentra src\app.py desde esta carpeta.
    echo         Coloca este .bat en la raiz del proyecto ObraPasaLista
    echo         ^(la misma carpeta donde esta ObraPasaLista.spec^).
    pause
    exit /b 1
)

if not exist "ObraPasaLista.spec" (
    echo [ERROR] No se encuentra ObraPasaLista.spec en esta carpeta.
    pause
    exit /b 1
)

rem --- Entorno virtual ---------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
    echo [OK] Entorno virtual .venv encontrado.
) else (
    echo [INFO] No existe .venv, lo creo ahora...
    where py >nul 2>nul
    if !errorlevel!==0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if not exist ".venv\Scripts\activate.bat" (
        echo [ERROR] No se pudo crear el entorno virtual.
        echo         Necesitas Python 3 instalado EN ESTE ordenador de
        echo         desarrollo ^(el ordenador final no lo necesitara^).
        echo         Descargalo de https://python.org
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo.
echo [1/4] Actualizando pip...
python -m pip install --upgrade pip -q

echo [2/4] Instalando dependencias del proyecto (src\requirements.txt)...
pip install -q -r src\requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo instalando requirements.txt
    pause
    exit /b 1
)

echo [3/4] Instalando PyInstaller...
pip install -q pyinstaller
if errorlevel 1 (
    echo [ERROR] Fallo instalando PyInstaller.
    pause
    exit /b 1
)

if not exist "src\static" (
    echo.
    echo [AVISO] No existe src\static en esta maquina: el .exe se generara
    echo         SIN los estilos de Bootstrap vendorizados. La app funcionara
    echo         pero se vera sin CSS. Si tienes esa carpeta en otro sitio,
    echo         copiala a src\static antes de compilar.
    echo.
)

echo [4/4] Compilando ObraPasaLista.exe (puede tardar 1-2 minutos)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
pyinstaller --noconfirm --clean ObraPasaLista.spec
if errorlevel 1 (
    echo.
    echo [ERROR] La compilacion ha fallado. Revisa el log de arriba.
    pause
    exit /b 1
)

if not exist "dist\ObraPasaLista.exe" (
    echo [ERROR] PyInstaller termino pero no genero dist\ObraPasaLista.exe
    pause
    exit /b 1
)

copy /Y "dist\ObraPasaLista.exe" "dist\ObraPasaLista_nuevo.exe" >nul

echo.
echo ============================================================
echo   LISTO: dist\ObraPasaLista.exe
echo ============================================================
echo.
echo   INSTALACION NUEVA (ordenador que nunca ha tenido la app):
echo     Copia dist\ObraPasaLista.exe solo, a cualquier carpeta de
echo     ese ordenador, y doble clic.
echo.
echo   ACTUALIZAR una instalacion que YA tiene datos:
echo     Copia dist\ObraPasaLista_nuevo.exe + actualizar_obrapasalista.bat
echo     a la carpeta donde ya esta instalado ObraPasaLista.exe, y
echo     doble clic en actualizar_obrapasalista.bat. Conserva data\ y docs\.
echo.
echo   En ambos casos, se abrira el navegador solo en http://127.0.0.1:5000
echo   Para cerrar la app, cierra la ventana negra de consola.
echo.
echo   La primera vez que se ejecuta, el .exe crea AHI MISMO (junto a
echo   el propio .exe) una carpeta "data" (base de datos y copias de
echo   seguridad) y otra "docs" (documentacion subida). No borres esas
echo   carpetas ni muevas el .exe sin moverlas tambien: son los datos
echo   reales de la obra.
echo.
pause
endlocal