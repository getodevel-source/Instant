@echo off
REM Arranca el daemon hold-to-talk. Sin args -> `run`. Acepta args (ej. --help).
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
