@echo off

rem Streamlit 웹앱 접속 설정입니다.
rem 기본값은 장비 계정 보호를 위해 실행 PC에서만 접속 가능한 127.0.0.1:8763 입니다.
rem 다른 PC 접속은 TLS/접근통제 등 승인된 보안 구성이 있을 때만 0.0.0.0 으로 변경하세요.

set "WLC_WEB_ADDRESS=127.0.0.1"
set "WLC_WEB_PORT=8763"
