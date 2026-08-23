# WLC Role ACL Collector 보안 모델

이 도구는 외부 개발 PC와 회사 내부망 PC를 분리해 사용하는 흐름을 전제로 합니다.

## 금지 원칙

- 실제 장비 raw log를 외부 개발 환경으로 가져오지 않습니다.
- 실제 IP, 호스트명, 정책명, 사용자 정보가 포함된 파일을 외부로 공유하지 않습니다.
- 문제 분석 시 원본 로그 대신 오류 코드와 안전 진단 리포트를 사용합니다.

## 저장 정책

일반 수집 모드는 운영 보고서를 만들기 때문에 WLC 설정, ACL, Alias 정보가 포함될 수 있습니다. GUI에서 사내 Role 대역표를 선택한 경우에는 실제 내부 네트워크 대역과 WLC 비교 상태도 포함됩니다. 외부 공유 전 반드시 내용을 확인해야 하며, 사내 Role 대역표가 포함된 보고서는 내부망 전용으로 취급합니다.

진단 모드는 다음 값만 저장합니다.

- 단계명
- 오류 코드
- command_id
- 안전 메시지
- retry 가능 여부

## 마스킹 대상

- IPv4 주소
- MAC 주소
- WLC/Controller 계열 호스트명
- password, secret, token, api key, community
- URL 안의 credential
- 네트워크 장비 설정 안의 secret/community 계열 값
- 진단 command ID와 `show rights`/`show netdestination` 오류에 포함된 실제 Role/Alias 이름

## 웹앱 접속 정책

- Streamlit portable 주소는 `127.0.0.1`로 고정하며 실행 PC에서만 접속합니다.
- `0.0.0.0` 등 외부 인터페이스 바인딩은 인증·TLS가 없어 실행 단계와 앱 단계에서 차단합니다.
- 원격 HTTP 모드는 예외 설정을 포함해 지원하지 않습니다. 여러 사용자가 쓰는 서버로 배포하지 않습니다.
- 같은 WLC에 대한 웹 수집은 한 번에 하나만 실행합니다.
- 브라우저에는 Python traceback을 직접 표시하지 않습니다.

## 장비 접속 정책

- SSH는 앱 전용 `known_hosts`에 승인된 서버 키만 허용합니다.
- 최초 SSH 접속 전 `trust_host_key.cmd` 또는 `trust-host-key` 명령으로 SHA-256 지문을 별도 관리 경로와 대조한 뒤 정확히 `TRUST`를 입력합니다.
- 저장된 키와 현재 키가 다르면 자동 교체하거나 우회하지 않고 자격 증명을 보내기 전에 연결을 차단합니다.
- Paramiko 4.0에서 공개된 RSA/SHA-1 경로는 서버 키 probe와 실제 Netmiko 연결 모두에서 `ssh-rsa` 서명 알고리즘을 비활성화합니다. 실제 연결은 SHA2-only 교환 뒤 인증 전에 맞춤 policy로 앱 전용 고정 키의 재료를 비교하므로 RSA known_hosts 항목이 SHA-1을 다시 우선하도록 두지 않습니다. RSA 키 재료는 RSA-SHA2를 지원하는 장비에서만 사용합니다.
- Telnet은 계정과 장비 출력이 평문으로 전송됩니다. 격리된 관리망에서 위험을 승인한 경우에만 직접 선택합니다.
- SSH 실패를 Telnet으로 자동 전환하지 않습니다.
- WLC 출력에서 발견한 Alias와 Role 이름은 허용 문자 검증을 통과한 경우에만 추가 조회 명령에 사용합니다.

의존성 감사의 고정 예외, 보완 통제, 재검토 기한은 [의존성 감사 예외](DEPENDENCY_AUDIT_EXCEPTIONS_KO.md)에 기록합니다. 새 고정 버전이 나오면 예외를 연장하지 않고 우선 업그레이드합니다.

## 개발 규칙

- 새 로그나 리포트를 만들 때는 allowlist 기반으로 안전 필드만 저장합니다.
- 원문을 저장한 뒤 나중에 지우는 방식은 사용하지 않습니다.
- 테스트 fixture와 mock scenario에는 실제 회사 출력이나 실제 주소를 넣지 않습니다.
