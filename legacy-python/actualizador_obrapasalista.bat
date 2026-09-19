@echo off
setlocal enabledelayedexpansion
title ObraPasaLista - Actualizar version

echo ============================================================
echo   ObraPasaLista - actualizador
echo ============================================================
echo.
echo   Este .bat sustituye ObraPasaLista.exe por una version nueva
echo   SIN tocar las carpetas data\ (base de datos) ni docs\
echo   (documentacion subida). Tus partes de fichaje no se pierden.
echo.

cd /d "%~dp0"

if not exist "ObraPasaLista_nuevo.exe" (
    echo [ERROR] No encuentro ObraPasaLista_nuevo.exe en esta carpeta.
    echo         Copia aqui el .exe de la version nueva con ese nombre
    echo         exacto, junto a este actualizador, y vuelve a intentarlo.
    pause
    exit /b 1
)

if not exist "ObraPasaLista.exe" (
    echo [AVISO] No hay ninguna instalacion previa en esta carpeta.
    echo         Esto sera una instalacion nueva, no una actualizacion:
    echo         no hay datos anteriores que conservar.
    echo.
)

rem --- Cerrar la app si esta abierta ------------------------------------
echo [1/3] Comprobando si ObraPasaLista esta abierto...
tasklist /FI "IMAGENAME eq ObraPasaLista.exe" 2>nul | find /I "ObraPasaLista.exe" >nul
if !errorlevel!==0 (
    echo       Esta abierto: se cierra para poder actualizar...
    taskkill /IM "ObraPasaLista.exe" /F >nul 2>nul
    timeout /t 2 /nobreak >nul
) else (
    echo       No estaba abierto.
)

rem --- Guardar copia de la version anterior ------------------------------
if exist "ObraPasaLista.exe" (
    echo [2/3] Guardando la version actual como ObraPasaLista_anterior.exe
    echo       ^(por si hay que volver atras^)...
    copy /Y "ObraPasaLista.exe" "ObraPasaLista_anterior.exe" >nul
) else (
    echo [2/3] Nada que respaldar.
)

rem --- Instalar la version nueva ------------------------------------------
echo [3/3] Instalando la version nueva...
move /Y "ObraPasaLista_nuevo.exe" "ObraPasaLista.exe" >nul
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo reemplazar ObraPasaLista.exe.
    echo         Puede que siga abierto: cierralo a mano desde el
    echo         Administrador de tareas e intenta de nuevo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Actualizacion completada.
echo ============================================================
echo   - data\ y docs\ no se han tocado: tus datos siguen ahi.
echo   - La version anterior quedo guardada como
echo     ObraPasaLista_anterior.exe por si necesitas volver atras
echo     (para eso: cierra la app, borra ObraPasaLista.exe y renombra
echo     ObraPasaLista_anterior.exe a ObraPasaLista.exe).
echo.
set /p ABRIR="Quieres abrir ObraPasaLista ahora? (S/N): "
if /I "!ABRIR!"=="S" start "" "ObraPasaLista.exe"

pause
endlocal