# 개발 및 유지관리 가이드

이 문서는 `wlc-role-acl-collector` 저장소의 개발·검증·배포 원칙을 정리합니다.

## 프로젝트 목적

이 프로젝트는 Aruba AOS8 WLC에서 SSID, AAA Profile, User Role, ACL, Alias/NetDestination 관계를 수집하고 Excel/HTML 보고서로 구조화합니다.

개발 시 가장 중요한 기준은 다음과 같습니다.

1. 실제 운영 데이터를 저장소에 남기지 않는다.
2. 수집한 사실과 추정 가능한 범위를 구분한다.
3. 일부 수집 실패를 전체 성공으로 숨기지 않는다.
4. 장비 설정을 변경하는 기능을 추가하지 않는다.
5. Windows 배포물이 소스 실행과 동일한 동작을 하는지 검증한다.

## 주요 경로

| 경로 | 역할 |
|---|---|
| `src/wlc_role_acl_collector/` | 수집기, Parser, ACL 평가, 진단, GUI, 보고서 |
| `app.py` | Streamlit 웹앱 진입점 |
| `cli_launcher.py` | CLI 실행 진입점 |
| `gui_launcher.py` | GUI 실행 진입점 |
| `config/` | 비식별 예제, Role 대역 템플릿, Mock scenario |
| `tests/` | Parser/수집/ACL 평가/진단/GUI/보고서 회귀 테스트 |
| `tools/` | 검증 및 패키지 확인 도구 |
| `docs/` | 사용자·개발·오류·보안·검증 문서 |
| `design_screenshots/` | 비식별 디자인/보고서 검토 화면 |

## 로컬 개발

Python 3.11 이상을 사용합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

GUI 실행:

```powershell
python -m wlc_role_acl_collector.gui_app
```

CLI 확인:

```powershell
wlc-role-acl-collector --help
```

웹앱 실행:

```powershell
streamlit run app.py --server.address 127.0.0.1 --server.port 8763
```

## 검증

기본 검증:

```powershell
python -m pytest
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
```

Windows 배포 경로를 변경했다면 다음까지 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_gui_exe.ps1
python .\tools\verify_release_package.py --dist .\dist --smoke-cli

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_streamlit_portable.ps1
python .\tools\verify_streamlit_portable_package.py --dist .\dist --smoke

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_combined_release.ps1
python .\tools\verify_combined_release_package.py --dist .\dist --smoke
```

Pull Request에서는 GitHub Actions의 Windows runner가 동일한 배포 경로를 검증합니다.

## 네트워크 데이터 취급 원칙

다음 정보는 저장소, Issue, PR, Release notes에 넣지 않습니다.

- 실제 WLC IP와 Hostname
- 사용자 계정과 비밀번호
- 실제 Role / ACL / Alias 원문
- 내부 VLAN, 서브넷, 사내 Role 대역표
- 실제 `show` 명령 출력
- 고객명·사이트명·건물명 등 운영망 식별 정보
- 생성된 실제 운영 보고서

예시는 RFC 5737 문서용 주소나 명시적인 샘플 이름만 사용합니다.

```text
192.0.2.10
sample-controller
sample-role
10.10.10.0/24
```

## 수집/분석 변경 원칙

### 수집

- 실제 장비 연결이 필요 없는 Parser/fixture 테스트를 우선합니다.
- SSH/Telnet 명령 실패는 단계와 명령 단위로 구분합니다.
- 수집 중 일부 실패가 발생해도 정상 수집한 데이터까지 폐기하지 않습니다.
- 반대로 누락된 정보를 정상 수집된 것처럼 채우지 않습니다.

### Role / ACL 분석

- 기본 Role과 RADIUS/ClearPass 동적 Role 가능성을 구분합니다.
- Alias 정의가 불완전하면 실제 목적지 범위를 임의 추정하지 않습니다.
- Access Check는 필요한 선행 정보가 부족하면 `판정 불가`로 반환합니다.
- 역할/ACL 관계 변경 시 대량 데이터 회귀 테스트를 함께 확인합니다.

### 안전

- 설정 모드나 구성 변경 명령을 기능 범위에 추가하지 않습니다.
- 진단 정보는 기본적으로 비식별·비민감 형태로 유지합니다.
- Timeout과 전체 수집 시간의 상한을 제거하지 않습니다.

## 문서 변경 원칙

기능 또는 사용 방법이 바뀌면 다음 문서를 함께 확인합니다.

- `README.md`
- `CHANGELOG.md`
- `RELEASE_NOTES.md`
- 관련 `docs/*.md`

README는 프로젝트의 전체 구현 세부사항을 복제하는 문서가 아니라 **운영 목적, 핵심 설계, 검증 근거와 빠른 시작**을 설명하는 문서로 유지합니다.

세부 구현은 개발자 가이드, 오류 코드는 오류 문서, 보안 경계는 보안 문서로 분리합니다.

## Release 원칙

문서 수정, 오탈자, 내부 리팩터링만으로 새 공개 Release를 만들지 않습니다.

공개 Release는 다음과 같이 사용자가 체감하는 변경을 충분히 검증한 뒤 수동 실행합니다.

- 수집 대상/명령 또는 Parser 동작 변경
- 보고서 구조나 의미 변경
- Windows 배포 방식 변경
- 운영상 중요한 오류 수정
- 기존 Release와 호환성에 영향을 주는 변경

Release 전에는 PR 검증과 Windows 통합 패키지 검증이 모두 성공해야 합니다.
