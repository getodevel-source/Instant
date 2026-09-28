@echo off
REM instant-run: SIN args -> arranca el daemon OCULTO [sin ventana visible].
REM Con args -> passthrough en consola [ej. instant-run.bat --help, run, check].
REM Sin duplicados: si ya hay instancia viva [PID file o tasklist], avisa y sale.
REM Modelos: %~dp0models [relativo al repo]. Solo default, respeta DICTADO_DATA previa.
setlocal
if not defined DICTADO_DATA set "DICTADO_DATA=%~dp0models"
if not "%~1"=="" goto :foreground
set "PIDFILE=%APPDATA%\instant\instant.pid"
if exist "%PIDFILE%" goto :checkpid
goto :scan
:checkpid
set /p LEPID=<"%PIDFILE%"
if not defined LEPID goto :stale
tasklist /FI "PID eq %LEPID%" /FO TABLE /NH 2>nul | findstr /I "instant.exe python.exe pythonw.exe" >nul
if errorlevel 1 goto :stale
echo Ya hay instancia viva PID %LEPID%. No se lanza otra. Usa instant-status.bat.
exit /b 0
:stale
del "%PIDFILE%" 2>nul
:scan
tasklist /FI "IMAGENAME eq instant.exe" 2>nul | findstr /I "instant.exe" >nul
if not errorlevel 1 goto :dup_exe
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*instant*' }) { exit 1 } else { exit 0 }" >nul 2>nul
if errorlevel 1 goto :dup_pyw
goto :launch
:dup_exe
echo Ya hay instancia viva instant.exe sin PID file. No se lanza otra.
exit /b 0
:dup_pyw
echo Ya hay instancia viva pythonw oculto con instant. No se lanza otra.
exit /b 0
:launch
powershell -NoProfile -Command "$p=(Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source; if (-not $p -and (Test-Path 'C:\Python314\pythonw.exe')) { $p='C:\Python314\pythonw.exe' }; if ($p) { Start-Process -FilePath $p -ArgumentList '-m instant_app run' -WindowStyle Hidden -WorkingDirectory '%~dp0' } else { Start-Process -FilePath 'python.exe' -ArgumentList '-m instant_app run' -WindowStyle Hidden -WorkingDirectory '%~dp0' }"
if errorlevel 1 goto :fail
echo Daemon lanzado oculto sin ventana. Verifica con instant-status.bat; frena con instant-stop.bat.
exit /b 0
:fail
echo ERROR: no se pudo lanzar el daemon oculto.
exit /b 1
:foreground
where instant.exe >nul 2>nul
if %ERRORLEVEL%==0 goto :fg_exe
set "EXE=%APPDATA%\Python\Python314\Scripts\instant.exe"
if exist "%EXE%" goto :fg_abs
python -m instant_app %*
exit /b %ERRORLEVEL%
:fg_exe
instant.exe %*
exit /b %ERRORLEVEL%
:fg_abs
"%EXE%" %*
exit /b %ERRORLEVEL%
