@echo off
setlocal
cd /d "%~dp0"

echo.
echo ===============================================
echo  Difusion Legion - generar EXE en carpeta
echo ===============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python Launcher py.exe no esta instalado.
    pause
    exit /b 1
)

py -m ensurepip --upgrade
py -m pip install --upgrade pip
py -m pip install -r requirements_build.txt
if errorlevel 1 (
    echo ERROR: no se pudieron instalar dependencias de compilacion.
    pause
    exit /b 1
)

if exist "tools\crear_icono.py" (
    py tools\crear_icono.py
)

if not exist "assets\icon.ico" (
    echo ERROR: no existe assets\icon.ico.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

py -m PyInstaller "Difusion Legion.spec"

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller no pudo generar el exe.
    pause
    exit /b 1
)

if not exist "dist\Difusion Legion\data" mkdir "dist\Difusion Legion\data"
if not exist "dist\Difusion Legion\data\sessions" mkdir "dist\Difusion Legion\data\sessions"
if not exist "dist\Difusion Legion\data\logs" mkdir "dist\Difusion Legion\data\logs"
if not exist "dist\Difusion Legion\data\flyers" mkdir "dist\Difusion Legion\data\flyers"

echo.
echo LISTO.
echo EXE generado en:
echo %CD%\dist\Difusion Legion\Difusion Legion.exe
echo.
echo Para llevarlo a otra PC, copia la carpeta completa:
echo dist\Difusion Legion
echo.
pause
