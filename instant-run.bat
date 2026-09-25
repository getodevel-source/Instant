@echo off
REM Arranca el daemon hold-to-talk. Sin args -> `run`. Acepta args (ej. --help).
REM Modelos: %~dp0models (relativo al repo). Solo default, respeta DICTADO_DATA previa.
if not defined DICTADO_DATA set "DICTADO_DATA=%~dp0models"
where instant.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  if "%~1"=="" (
    instant.exe run
  ) else (
    instant.exe %*
  )
) else (
  set "EXE=C:\Users\juans\AppData\Roaming\Python\Python314\Scripts\instant.exe"
  if exist "%EXE%" (
    if "%~1"=="" (
      "%EXE%" run
    ) else (
      "%EXE%" %*
    )
  ) else (
    if "%~1"=="" (
      python -m instant_app run
    ) else (
      python -m instant_app %*
    )
  )
)
