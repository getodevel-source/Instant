@echo off
REM Diagnostico rapido: NO levanta el daemon, solo lo inspecciona.
echo == proceso ==
tasklist /FI "IMAGENAME eq instant.exe" | findstr /I "instant.exe" >nul
if %ERRORLEVEL%==0 (
  echo instant.exe vivo: SI
) else (
  echo instant.exe vivo: NO
)
echo.
echo == log: ultimas 15 lineas de %%APPDATA%%\instant\instant.log ==
powershell -NoProfile -Command "Get-Content \"$env:APPDATA\instant\instant.log\" -Tail 15"
echo.
echo == config: %%APPDATA%%\instant\config.json ==
type "%APPDATA%\instant\config.json"
