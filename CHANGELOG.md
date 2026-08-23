# Changelog

이 문서는 `wlc-role-acl-collector`의 **사용자와 네트워크 운영에 의미 있는 변경**을 기록합니다.

세부 구현 커밋을 모두 나열하기보다 수집 범위, 정책 해석, 결과물, 안전성, 배포 방식이 어떻게 달라졌는지 중심으로 정리합니다.

## Unreleased

## 0.2.0

### 접속 안전성

- SSH는 앱 전용 `known_hosts`와 Netmiko strict 검증을 사용하며, 승인되지 않은 키와 변경된 키를 차단합니다.
- 장비 계정을 입력하기 전에 SHA-256 서버 키 지문을 확인·승인하는 `trust-host-key` 명령을 추가했습니다.
- SSH 실패를 Telnet으로 자동 전환하지 않으며, Telnet은 운영자가 직접 선택한 경우에만 사용합니다.
- Streamlit은 `localhost`, `127.0.0.1`, `::1` 이외 주소에서 실행을 중단합니다.

### 명령 안전성

- 설정에서 발견한 Role·Alias 이름을 중앙 검증기로 확인한 뒤에만 `show rights`와 `show netdestination` 명령을 생성합니다.
- 따옴표, 명령 연결 문자, 줄바꿈, 제어문자가 포함된 이름은 장비로 보내지 않고 안전 오류로 기록합니다.
- 자격 증명 객체의 문자열 표현에서 ID·비밀번호·Enable password가 노출되지 않도록 차단했습니다.

### 검증과 배포

- PR뿐 아니라 `main` push에서도 Windows 패키지 검증을 실행합니다.
- SemVer `v0.2.0`, SHA-256 sidecar, CycloneDX SBOM, GitHub build provenance를 릴리스 계약으로 추가했습니다.
- MIT License와 채용 담당자용 포트폴리오 요약을 추가했습니다.

### 문서 / 운영 체계

- README를 `운영 문제 → 설계 판단 → 분석 구조 → 검증 → 빠른 시작` 순서로 재구성했습니다.
- 기존 비식별 GUI/HTML 보고서 화면을 README에서 바로 확인할 수 있도록 연결했습니다.
- 자동 테스트와 실제 운영 검증의 증거 수준을 구분하는 `docs/VALIDATION_REPORT.md`를 추가했습니다.
- 저장소 개발 규칙을 일반적인 `DEVELOPMENT.md`로 정리했습니다.
- 문서나 내부 정리만으로 공개 Release가 자동 생성되지 않도록 Release workflow를 수동 실행 방식으로 변경했습니다.
- Release notes를 핵심 변경, 운영 영향, 검증 결과, 다운로드, 알려진 범위 중심으로 생성하도록 정리했습니다.

## 0.1.0

### 수집 / 정책 관계

- Aruba AOS8 WLC에서 SSID, AAA Profile, 기본 Role, Role ACL, Alias 정보를 수집합니다.
- `initial-role`, `mac-default-role`, `dot1x-default-role`을 구분합니다.
- ACL의 Alias 참조를 NetDestination 정의까지 연결해 접근 범위를 구조화합니다.
- `show ip interface brief`와 `show user-table`을 이용해 Role 대역 추정 근거와 관측 사용자 정보를 보조 데이터로 제공합니다.
- ClearPass/RADIUS 동적 Role은 직접 조회하지 않고 `동적 Role 가능성`으로 구분합니다.

### 상태 / 신뢰도

- CLI, GUI, Web에서 `정상 완료 / 부분 완료 / 수집 실패` 공통 상태 모델을 사용합니다.
- 실패한 명령을 수집된 관계와 연결해 영향 Role/SSID와 수집 신뢰도를 표시합니다.
- WLC 주소, Port, Timeout 입력을 검증하고 명령 Timeout을 5~600초로 제한합니다.
- 전체 live 수집에는 60분 상한을 적용합니다.
- GUI 취소 및 창 종료 시 worker와 장비 세션 정리 경로를 사용합니다.
- CLI 다중 WLC 수집은 한 대상의 실패가 나머지 수집을 중단시키지 않도록 격리합니다.

### ACL 분석 / Access Check

- Role별 ACL 상세를 HTML 보고서에서 확인할 수 있습니다.
- Alias/name 기반 정책 관계를 Access Check에서 평가합니다.
- 필요한 선행 Alias/ACL 정보가 불완전하면 뒤 규칙으로 임의 추정하지 않고 `판정 불가`로 처리합니다.
- 특수문자가 포함된 서로 다른 Role 이름이 같은 HTML ID로 충돌하지 않도록 안정 ID를 사용합니다.

### 보고서

- Excel, SSID/Role CSV, HTML 보고서를 생성합니다.
- HTML 보고서에서 ACL 주석과 Role 설명을 관리할 수 있습니다.
- 선택한 Role의 ACL 내용을 PNG로 저장할 수 있습니다.
- Excel/HTML은 staging에서 완성한 뒤 함께 반영하고 실패 시 기존 결과를 보호합니다.
- `report_status.json`에 파일 생성 상태와 수집 상태를 분리해 기록합니다.
- 내부 Role 대역 Excel을 선택적으로 입력해 WLC 추정값과 비교할 수 있습니다.

### 진단 / 민감정보

- 안전 진단 모드는 민감정보를 마스킹한 HTML/JSON 진단 결과를 생성합니다.
- Role/Alias command ID는 안정 라벨로 치환합니다.
- 실제 WLC 주소, 계정, 원문 출력, 내부 Role 대역표는 저장소나 공개 Release에 포함하지 않습니다.
- Streamlit 바인딩을 loopback 주소로 강제하고 외부 인터페이스 실행을 차단합니다.

### 검증

- Parser, 수집기, ACL 평가, 진단, GUI, 보고서, Mock server 회귀 테스트를 제공합니다.
- 60개 Role / 1,200개 ACL 보고서 생성 회귀를 검증합니다.
- 100개 Role / 4,000개 ACL HTML 렌더링 경로를 검증합니다.
- Access Check와 Role PNG JavaScript 문법을 자동 검증합니다.
- Windows GUI/CLI 패키지, Streamlit portable 패키지, 통합 ZIP을 GitHub Actions에서 빌드·smoke 검증합니다.

### Windows 배포

- 일반 사용자용 Release는 GUI/CLI와 Streamlit portable 웹앱을 하나의 Windows 통합 ZIP으로 제공합니다.
- Python이 설치되지 않은 Windows PC에서도 GUI와 로컬 웹앱을 실행할 수 있습니다.
- 통합 ZIP의 필수 실행 파일, 문서, config, Mock scenario와 smoke 실행을 검증합니다.
- 최종 ZIP의 SHA-256을 Release notes에 기록합니다.

### 현재 제외 범위

- ClearPass/RADIUS 서버의 동적 Role 직접 조회
- 모든 service object의 TCP/UDP 포트 정밀 해석
- Streamlit 자체 사용자 로그인/권한 관리
- 코드서명 / installer / MSIX
- macOS에서 Windows EXE를 직접 생성하는 공식 빌드 경로
