@echo off
REM Instala Instant en un entorno virtual del repositorio y abre el asistente.
setlocal
if not defined DICTADO_DATA set "DICTADO_DATA=%~dp0models"

where python >nul 2>nul
if errorlevel 1 (
  echo [Instant] Falta Python 3.12 o posterior en PATH.
  echo Instala Python desde https://www.python.org/downloads/ y reintenta.
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
  echo [Instant] Se requiere Python 3.12 o posterior.
  exit /b 1
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
  echo [Instant] Creando entorno virtual...
  python -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo [Instant] No se pudo crear .venv.
    exit /b 1
  )
)

echo [Instant] Instalando Instant y sus dependencias...
call "%VENV_PYTHON%" -m pip install "%~dp0dictado"
if errorlevel 1 (
  echo [Instant] Fallo la instalacion del paquete. Revisa tu conexion y reintenta.
  exit /b 1
)

set "SETUP_ARGS="
if defined INSTANT_UNATTENDED set "SETUP_ARGS=--yes"
if /i "%INSTANT_AUTOSTART%"=="1" set "SETUP_ARGS=%SETUP_ARGS% --autostart"

echo [Instant] Configurando modelos, microfono y tecla...
pushd "%~dp0"
if defined INSTANT_UNATTENDED (
  call "%VENV_PYTHON%" -m instant_app setup %SETUP_ARGS%
) else (
  if exist "%~dp0.venv\Scripts\pythonw.exe" (
    call "%~dp0.venv\Scripts\pythonw.exe" -m instant_app setup %SETUP_ARGS%
  ) else (
    call "%VENV_PYTHON%" -m instant_app setup %SETUP_ARGS%
  )
)
set "SETUP_RC=%ERRORLEVEL%"
popd
if not "%SETUP_RC%"=="0" (
  echo [Instant] La configuracion no termino correctamente. Reintenta con instant-setup.bat.
  exit /b %SETUP_RC%
)

echo.
echo [Instant] Instalacion completa. Arranca con instant-run.bat.
