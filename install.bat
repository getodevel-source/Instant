@echo off
REM Instalador de Instant en un comando (Windows, todo en espanol).
REM Sin dependencias del sistema: solo necesita Python 3.11+ en PATH.
REM Hace dos cosas: 1) instala el paquete `instant`, 2) descarga TODO JUNTO
REM (Parakeet v3 int8 ~670 MB + Silero VAD ~1 MB, espanol unico) con `instant setup --yes`.
REM Uso: doble clic, o desde terminal:  install.bat

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
  echo [Instant] No se encontro Python. Instala Python 3.11+ desde https://www.python.org/downloads/ y reintenta.
  exit /b 1
)

echo [Instant] 1/2 Instalando el paquete instant...
call python -m pip install -e "%~dp0dictado"
if %ERRORLEVEL% neq 0 (
  echo [Instant] Fallo `pip install -e dictado`. Revisa tu conexion y reintenta.
  exit /b 1
)

echo [Instant] 2/2 Descargando modelos en espanol (~670 MB, una sola vez)...
where instant >nul 2>nul
if %ERRORLEVEL%==0 (
  call instant setup --yes
) else (
  REM `instant` aun no esta en PATH en esta terminal: mismo fallback que instant-setup.bat.
  call python -m instant_app setup --yes
)
if %ERRORLEVEL% neq 0 (
  echo [Instant] `instant setup` no termino bien. Reintenta con: instant setup
  exit /b 1
)

echo.
echo [Instant] Listo. Para dictar usa: instant-setup.bat una vez si quieres
echo cambiar microfono o tecla, y luego instant-run.bat para arrancar.
echo Solo se te pedira microfono y tecla si corres `instant setup` interactivo;
echo el idioma es fijo: espanol.
