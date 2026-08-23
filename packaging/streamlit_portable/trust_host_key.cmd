@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
set "PYTHON_EXE=%~dp0python\python.exe"
set "PYTHONPATH=%~dp0python\Lib\site-packages;%~dp0app;%PYTHONPATH%"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 내장 Python 실행 파일을 찾을 수 없습니다.
    exit /b 1
)

set "WLC_HOST=%~1"
if "%WLC_HOST%"=="" set /p "WLC_HOST=WLC IP 또는 Host: "
if "%WLC_HOST%"=="" (
    echo [ERROR] WLC IP 또는 Host를 입력하세요.
    exit /b 2
)

set "WLC_PORT=%~2"
if "%~1"=="" set /p "WLC_PORT=SSH Port [22]: "
if "%WLC_PORT%"=="" set "WLC_PORT=22"

"%PYTHON_EXE%" -m wlc_role_acl_collector.cli trust-host-key --host "%WLC_HOST%" --port "%WLC_PORT%"
exit /b %ERRORLEVEL%
