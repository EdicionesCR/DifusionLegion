@echo off
setlocal
cd /d "%~dp0"

echo.
echo ===============================================
echo  Difusion Legion - generar EXE de un solo archivo
echo ===============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en PATH.
    echo En esta PC de desarrollo si hace falta Python para construir el exe.
    pause
    exit /b 1
)

python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -r requirements_build.txt
if errorlevel 1 (
    echo ERROR: no se pudieron instalar dependencias de compilacion.
    pause
    exit /b 1
)

python tools\crear_icono.py
if errorlevel 1 (
    echo ERROR: no se pudo preparar assets\icon.ico.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Difusion Legion.spec" del /q "Difusion Legion.spec"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "Difusion Legion" ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  app.py

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller no pudo generar el exe.
    pause
    exit /b 1
)

if not exist "dist\data" mkdir "dist\data"
if not exist "dist\data\sessions" mkdir "dist\data\sessions"
if not exist "dist\data\logs" mkdir "dist\data\logs"
if not exist "dist\data\flyers" mkdir "dist\data\flyers"

echo.
echo LISTO.
echo EXE generado en:
echo %CD%\dist\Difusion Legion.exe
echo.
echo Para llevarlo a otra PC, copia el archivo:
echo dist\Difusion Legion.exe
echo.
echo La primera vez en otra PC deberas conectar WhatsApp con QR.
echo.
pause
