@echo off
REM Diagnostico rapido: NO levanta el daemon, solo lo inspecciona.
echo == proceso ==
tasklist /FI "IMAGENAME eq instant.exe" | findstr /I "instant.exe" >nul
if %ERRORLEVEL%==0 (
  echo instant.exe vivo: SI
) else (
  echo instant.exe vivo: NO
)
echo == modelos ==
echo DICTADO_DATA=%DICTADO_DATA%
if defined DICTADO_DATA (
  if exist "%DICTADO_DATA%\parakeet-v3-int8\encoder.int8.onnx" (
    echo dir DICTADO_DATA: OK ^(encoder.int8.onnx presente^)
  ) else (
    echo dir DICTADO_DATA: VACIO o sin modelos ^(revisa la ruta^)
  )
) else (
  echo var vacia: el exe usaria el default %LOCALAPPDATA%\instant\models
  if exist "%LOCALAPPDATA%\instant\models\parakeet-v3-int8\encoder.int8.onnx" (
    echo default %LOCALAPPDATA%\instant\models: OK
  ) else (
    echo default %LOCALAPPDATA%\instant\models: VACIO -^> fija DICTADO_DATA o usa instant-run.bat
  )
)
echo.
echo == log: ultimas 15 lineas de %%APPDATA%%\instant\instant.log ==
powershell -NoProfile -Command "Get-Content \"$env:APPDATA\instant\instant.log\" -Tail 15"
echo.
echo == config: %%APPDATA%%\instant\config.json ==
type "%APPDATA%\instant\config.json"
