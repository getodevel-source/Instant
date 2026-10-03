@echo off
REM instant-update: aplica una version descargada y verificada.
REM Uso: instant-update.bat <nuevo-Instant.exe> <sha256>
REM Re-verifica el hash (cierra el TOCTOU de %TEMP%), frena el daemon,
REM cierra las ventanas Instant, respalda dist\Instant.exe como .bak,
REM lo reemplaza y vuelve a arrancar. Sin hash no instala.
setlocal
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
if not exist "%~1" goto :missing
set "DST=%~dp0dist\Instant.exe"
if /I "%~f1"=="%DST%" goto :selfcopy

echo [1/5] Verificando SHA256...
for /f "skip=1 tokens=1" %%H in ('certutil -hashfile "%~1" SHA256 2^>nul') do (
  if /I not "%%H"=="%~2" goto :hashfail
  goto :hashok
)
goto :hashfail
:hashok
echo Hash OK.

echo [2/5] Frenando daemon...
call "%~dp0instant-stop.bat" >nul 2>&1

echo [3/5] Cerrando ventanas Instant...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name=''pythonw.exe'' AND CommandLine LIKE '%%instant_app%%' AND NOT CommandLine LIKE '%%instant_app run%%' AND NOT CommandLine LIKE '%%test%%' AND NOT CommandLine LIKE '%%pytest%%' | Invoke-CimMethod -MethodName Terminate" >nul 2>&1
ping -n 3 127.0.0.1 >nul 2>nul

echo [4/5] Respaldando y reemplazando...
if exist "%DST%" (
  del "%~dp0dist\Instant.exe.bak" 2>nul
  ren "%DST%" "Instant.exe.bak" 2>nul
  if exist "%DST%" goto :locked
)
copy /Y "%~1" "%DST%" >nul
if errorlevel 1 goto :copyfail

echo [5/5] Arrancando daemon...
call "%~dp0instant-run.bat"
echo Listo: %DST% actualizado.
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
