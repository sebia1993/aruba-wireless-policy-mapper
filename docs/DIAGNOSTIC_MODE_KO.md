# WLC Role ACL Collector 진단 모드

진단 모드는 회사 내부망 PC에서 실행해도 원본 장비 출력을 저장하지 않는 확인 모드입니다.

## 실행 방식

GUI에서 실행:

1. `WlcRoleAclCollectorGUI.exe` 실행
2. WLC IP, protocol, port, username, password 입력
3. `고급 옵션 표시` 클릭
4. `안전 진단` 클릭
5. 완료 후 `HTML 보고서 열기` 또는 `결과 폴더 열기` 클릭

CLI에서 실행:

```powershell
WlcRoleAclCollectorCLI.exe diagnose --controllers config\controllers.example.csv --output-dir outputs
```

Python 소스 환경에서 실행:

```powershell
python -m wlc_role_acl_collector diagnose --controllers config\controllers.example.csv --output-dir outputs
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

실제 장비 없이 개발 PC에서 테스트할 때:

```powershell
WlcRoleAclCollectorCLI.exe mock-server --protocol telnet --scenario config\mock_scenarios\success_minimal.json
```

다른 터미널에서 해당 로컬 포트를 대상으로 수집 또는 진단을 실행합니다.

같은 `MockWlcServer` 객체를 중복 시작할 수 없으며, 종료 시 listener와 worker thread를 정리합니다. 반복 테스트에서는 `start()`와 `stop()`을 한 쌍으로 사용하십시오.
