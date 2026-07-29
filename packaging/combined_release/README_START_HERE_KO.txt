WLC Role ACL Collector 실행 안내
================================

이 ZIP 하나에 Windows GUI/CLI 실행 파일과 Python 설치 없는 Streamlit 웹앱이 함께 들어 있습니다.
일반 사용자는 GitHub Release에서 이 windows.zip 파일 하나만 다운로드하면 됩니다.

GitHub 화면에 보이는 Source code (zip), Source code (tar.gz)는 GitHub가 자동으로 붙이는 소스 코드 파일입니다.
일반 실행용 파일이 아니므로 다운로드하지 않아도 됩니다.

1. GUI로 실행하기
----------------

1) ZIP 파일을 원하는 폴더에 압축 해제합니다.
2) gui 폴더로 이동합니다.
3) gui\WlcRoleAclCollectorGUI.exe 를 더블클릭합니다.

CLI가 필요한 경우 gui\WlcRoleAclCollectorCLI.exe 를 사용합니다.

2. 웹앱으로 실행하기
-------------------

1) ZIP 파일을 원하는 폴더에 압축 해제합니다.
2) web 폴더로 이동합니다.
3) web\start_webapp.cmd 를 더블클릭합니다.
4) 실행 창은 닫지 않습니다. 이 창을 닫으면 웹앱도 종료됩니다.
5) 브라우저에서 아래 주소로 접속합니다.

- 실행한 PC에서 접속: http://127.0.0.1:8763
- 기본 설정에서는 다른 PC 접속 불가

웹앱은 ZIP 안에 포함된 내장 Python으로 실행됩니다.
Windows PC에 Python을 별도로 설치할 필요가 없습니다.
웹앱 첫 실행은 내장 Python과 Streamlit 초기화 때문에 GUI보다 느릴 수 있습니다.
반드시 ZIP 압축을 완전히 푼 뒤 로컬 폴더에서 실행하세요.
같은 PC에서 접속할 때는 http://127.0.0.1:8763 주소를 사용하면 됩니다.

3. 웹앱 포트 변경
----------------

기본 포트는 8763입니다.
포트를 바꾸려면 web\webapp_settings.cmd 파일을 메모장으로 열고 WLC_WEB_PORT 값을 변경합니다.

수집 결과 상태
--------------

- 정상 완료: 모든 수집 명령 성공
- 부분 완료: 보고서는 생성됐지만 일부 명령 실패. 영향 Role/SSID 확인 필요
- 수집 실패: 필수 설정 데이터 없음. 보고서를 정책 판단에 사용하지 않음

GUI의 실행 취소는 현재 명령의 응답 또는 Timeout 후 장비 세션을 안전하게 닫습니다.
명령 Timeout은 5~600초이며 전체 수집은 최대 60분입니다.

4. Role 대역 Excel
-----------------

예제 파일은 아래 두 위치에 들어 있습니다.

- gui\config\role_networks.example.xlsx
- web\config\role_networks.example.xlsx

Excel에 Role_Networks Sheet가 있으면 해당 Sheet를 우선 사용하고, 없으면 첫 번째 Sheet를 사용합니다.

5. 주의사항
-----------

이 도구는 인터넷 공개용 서비스가 아닙니다.
접속 주소를 아는 사내 사용자는 웹앱 화면에 접근할 수 있습니다.
장비 계정, 비밀번호, 내부 대역 정보는 코드나 파일에 저장하지 말고 실행 화면에서만 입력하세요.
웹앱 기본 주소는 127.0.0.1입니다. 0.0.0.0 원격 모드는 TLS와 접근통제가 승인된 경우에만 사용하세요.
