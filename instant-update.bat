@echo off
REM instant-update: aplica una version descargada y verificada.
REM Uso: instant-update.bat <nuevo-Instant.exe> <sha256>
REM Re-verifica el hash (cierra el TOCTOU de %TEMP%), frena el daemon,
REM cierra las ventanas Instant, respalda dist\Instant.exe como .bak,
REM lo reemplaza, verifica que el nuevo daemon levante (si no, restaura)
REM y reabre la ventana. Sin hash no instala.
setlocal
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
if not exist "%~1" goto :missing
set "DST=%~dp0dist\Instant.exe"
set "PIDFILE=%APPDATA%\instant\instant.pid"
if /I "%~f1"=="%DST%" goto :selfcopy

echo [1/6] Verificando SHA256...
for /f "skip=1 tokens=1" %%H in ('certutil -hashfile "%~1" SHA256 2^>nul') do (
  if /I not "%%H"=="%~2" goto :hashfail
  goto :hashok
)
goto :hashfail
:hashok
echo Hash OK.

echo [2/6] Frenando daemon...
call "%~dp0instant-stop.bat" >nul 2>&1

echo [3/6] Cerrando ventanas Instant...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name=''pythonw.exe'' AND CommandLine LIKE '%%instant_app%%' AND NOT CommandLine LIKE '%%instant_app run%%' AND NOT CommandLine LIKE '%%test%%' AND NOT CommandLine LIKE '%%pytest%%' | Invoke-CimMethod -MethodName Terminate" >nul 2>&1
ping -n 3 127.0.0.1 >nul 2>nul

echo [4/6] Respaldando y reemplazando...
if exist "%DST%" (
  del "%~dp0dist\Instant.exe.bak" 2>nul
  ren "%DST%" "Instant.exe.bak" 2>nul
  if exist "%DST%" goto :locked
)
copy /Y "%~1" "%DST%" >nul
if errorlevel 1 goto :copyfail

echo [5/6] Arrancando daemon nuevo...
call "%~dp0instant-run.bat" >nul 2>&1
ping -n 9 127.0.0.1 >nul 2>nul
set "NEWPID="
if exist "%PIDFILE%" set /p NEWPID=<"%PIDFILE%"
if not defined NEWPID goto :rollback
tasklist /FI "PID eq %NEWPID%" /FO TABLE /NH 2>nul | findstr /I "instant.exe python.exe pythonw.exe" >nul
if not errorlevel 1 goto :healthy
:rollback
echo ADVERTENCIA: el nuevo exe no levanto; restaurando el anterior...
copy /Y "%~dp0dist\Instant.exe.bak" "%DST%" >nul
call "%~dp0instant-run.bat" >nul 2>&1
echo Se restauro la version anterior. Revisa el log en %APPDATA%\instant.
goto :reopen
:healthy
echo Daemon nuevo en marcha.

:reopen
echo [6/6] Reabriendo ventana...
start "" "%~dp0dist\Instant.exe" setup
echo Listo: Instant actualizado. Esta ventana ya se puede cerrar.
pause
exit /b 0

:usage
echo Uso: instant-update.bat ^<exe descargado^> ^<sha256 del sidecar^>
exit /b 1
:missing
echo ERROR: no existe "%~1".
exit /b 1
:selfcopy
echo ERROR: el origen es el propio destino; nada que instalar.
exit /b 1
:hashfail
echo ERROR: SHA256 no coincide; no se instala nada.
exit /b 1
:locked
echo ERROR: dist\Instant.exe sigue en uso; cerra Instant y reintenta.
exit /b 1
:copyfail
echo ERROR: no se pudo copiar "%~1" a dist.
exit /b 1
