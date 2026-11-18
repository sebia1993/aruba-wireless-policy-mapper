# WLC Role ACL Collector 진단 모드

진단 모드는 회사 내부망 PC에서 실행해도 원본 장비 출력을 저장하지 않는 확인 모드입니다.

## 실행 방식

GUI에서 실행:

1. `WlcRoleAclCollectorGUI.exe` 실행
2. WLC IP, protocol, port, username, password 입력
3. `고급 옵션 표시` 클릭
4. `안전 진단` 클릭. SSH 최초 접속은 지문 확인창이 나타나며, 별도 경로로 SHA-256 지문을 검증한 뒤에만 승인합니다. 기존 승인 키는 자동 검사하고 변경 키는 차단합니다.
5. 완료 후 `HTML 보고서 열기` 또는 `결과 폴더 열기` 클릭

Python 소스 환경에서는 의존성을 설치한 후 저장소 루트에서 같은 GUI를 엽니다.

```powershell
python gui_launcher.py
```

## 산출물

```text
outputs\<timestamp>\
  diagnostic_summary.json
  diagnostic_summary.html
  diagnostic_run.log
  diagnostic_status.json
```

진단 산출물에는 다음을 저장하지 않습니다.

- 원본 장비 명령 출력
- 실제 IP 주소
- 실제 호스트명
- 계정, 비밀번호, secret, token
- 사용자 MAC 주소

`diagnostic_status.json`은 세 진단 파일의 묶음 저장 상태를 기록합니다. `status=completed`일 때만 완료본이며, `writing` 또는 `failed` 상태의 JSON/HTML/log는 외부 분석 자료로 사용하지 않습니다.

## 단계

| 단계 | 의미 |
| --- | --- |
| DGN-BOOT | 프로그램 실행 환경 확인 |
| DGN-INPUT | 입력값 검증 |
| DGN-NET | TCP 연결 시도 |
| DGN-AUTH | 로그인 결과 |
| DGN-PROMPT | 프롬프트 탐지 |
| DGN-CMD | 필수 명령 실행 |
| DGN-PARSE | Role/ACL/Alias 파싱 |
| DGN-REPORT | 안전 진단 리포트 생성 |
| DGN-SEC | 민감정보 마스킹 self-test |

## Mock 서버 사용

개발 PC에서 테스트 의존성을 설치한 후 저장소 루트에서 다음 명령을 실행합니다.

```powershell
python -m pytest -q tests/test_mock_server.py tests/test_diagnostic_mode.py
```

Mock 서버 테스트는 loopback의 임시 포트를 열어 합성 SSH·Telnet 응답을 읽고 서버를 닫습니다. 진단 테스트는 합성 결과로 진단 단계와 산출물을 확인합니다.
