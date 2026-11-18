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
| `gui_launcher.py` | GUI 실행 진입점 |
| `config/` | 비식별 예제와 Role 대역 템플릿 |
| `config/mock_scenarios/` | 실제 WLC 접속 없이 사용하는 비식별 Mock 시나리오 |
| `tests/` | Parser/수집/ACL 평가/진단/GUI/보고서 회귀 테스트 |
| `tools/` | 검증 및 패키지 확인 도구 |
| `docs/` | 사용자·개발·오류·보안·검증 문서 |
| `design_screenshots/` | 비식별 디자인/보고서 검토 화면 |

## 로컬 개발

Python 3.11 이상을 사용하고, 주석 편집기 테스트에는 Node.js 20 이상을 사용합니다.

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

웹앱 실행:

```powershell
streamlit run app.py --server.address 127.0.0.1 --server.port 8763
```

## 검증

기본 검증:

```powershell
npm ci --ignore-scripts
python -m pytest
npm test
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
```

Windows 배포 경로를 변경했다면 다음까지 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_gui_exe.ps1
python .\tools\verify_release_package.py --dist .\dist

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_streamlit_portable.ps1
python .\tools\verify_streamlit_portable_package.py --dist .\dist --smoke

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_combined_release.ps1
python .\tools\verify_combined_release_package.py --dist .\dist --smoke
```

Pull Request에서는 GitHub Actions의 Windows runner가 Node 22에서 `npm ci --ignore-scripts`로 의존성을 먼저 설치하고 Python 검증 이후 `npm test`를 한 번 실행한 뒤 동일한 배포 경로를 검증합니다. `tools/validate.ps1`의 기존 JavaScript 문법 검사만으로 주석 기능의 Node 회귀를 대신하지 않습니다. 실제 회사 장비·사내 파일·Windows 사용자 브라우저·인쇄 환경의 수동 검증은 사용자 범위이며 자동 테스트 통과와 구분합니다.

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

### 오프라인 주석과 보고서

- `annotation_project.py`는 허용된 수집 데이터로 `aruba-policy-annotations` schemaVersion 1 DTO를 만듭니다. 계정·비밀번호와 user-table 원문과 내보내기에 동의하지 않은 내부 대역은 포함하지 않습니다.
- `static/annotation_core.js`는 엄격한 검증·안전 복사, 컨트롤러별 보수적 설명 재사용, DOM과 독립적인 보고 범위를 담당합니다. 정확한 계약은 [명세](docs/superpowers/specs/2026-11-16-annotation-project.md)를 참고합니다.
- `annotation_editor.js`는 파일·편집·복구, `annotation_import.js`는 실행 없는 HTML 읽기, `annotation_export.js`는 공통 모델의 실제 XLSX/인쇄 HTML 변환을 담당합니다. 브라우저에서 필요한 ExcelJS와 라이선스를 로컬 정적 자산으로 묶습니다.
- JSON 작업이 수집본과 메모·확인 상태·출처를 보관하는 기준입니다. 브라우저 저장소는 사용자가 선택하는 복구용이며 기존 파일을 자동 덮어쓰지 않습니다. Excel/PDF는 보고용이며 재가져오기 편집 원본이 아닙니다.
- 원문 suffix·내부 공백, 중복 규칙, 동명 컨트롤러, Alias/순서 변경, 부분 수집, 현재 빈 메모·미연결 출처 보존, 손상된 파일, 임시저장 실패와 보고 범위 일치를 회귀에 포함합니다.

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
