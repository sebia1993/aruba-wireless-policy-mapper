# Release 운영 기준

이 문서는 `wlc-role-acl-collector`의 공개 Release를 언제 만들고, 무엇을 검증하고, 어떤 정보를 Release notes에 포함할지 정의합니다.

## Release 원칙

공개 Release는 **문서 수정이나 내부 정리만으로 자동 생성하지 않습니다.**

GitHub Actions의 `Release` workflow를 수동 실행하며, 다음과 같이 사용자가 체감하는 변경이 충분히 검증된 경우에만 배포합니다.

- WLC 수집 명령 또는 Parser 동작 변경
- SSID / AAA / Role / ACL / Alias 관계 해석 변경
- Access Check 판정 로직 변경
- Excel / CSV / HTML 결과 의미 또는 구조 변경
- GUI / Web 실행 방식 변경
- Windows 패키지 또는 통합 ZIP 구조 변경
- 운영상 중요한 오류 수정
- 호환성에 영향을 줄 수 있는 의존성 변경

오탈자, README 정리, 주석, 내부 코드 정리 등은 다음 기능 Release에 함께 포함합니다.

## 배포 산출물

일반 사용자용 실행 파일은 Windows 통합 ZIP으로 제공하며, SHA-256 체크섬과 Python 의존성 SBOM을 함께 공개합니다.

```text
wlc-role-acl-collector_v0.4.1_windows.zip
wlc-role-acl-collector_v0.4.1_windows.zip.sha256
wlc-role-acl-collector_v0.4.1_sbom.cdx.json
```

GitHub가 자동 표시하는 `Source code (zip)`과 `Source code (tar.gz)`는 실행용 배포 파일이 아닙니다.

통합 ZIP에는 다음 경로가 포함되어야 합니다.

```text
README_START_HERE_KO.txt
gui/
  WlcRoleAclCollectorGUI.exe
  USER_GUIDE_KO.md
  USER_GUIDE_KO.html
  DEVELOPER_GUIDE_KO.md
  DEVELOPER_GUIDE_KO.html
  ERROR_CODES_KO.md
  ERROR_CODES_KO.html
  DIAGNOSTIC_MODE_KO.md
  DIAGNOSTIC_MODE_KO.html
  SECURITY_MODEL_KO.md
  SECURITY_MODEL_KO.html
  DEPENDENCY_AUDIT_EXCEPTIONS_KO.md
  DEPENDENCY_AUDIT_EXCEPTIONS_KO.html
  config/
web/
  start_webapp.cmd
  webapp_settings.cmd
  README_WEBAPP_KO.txt
  python/
  app/app.py
  config/
```

SHA-256은 Release notes와 별도 `.sha256` asset에 기록합니다. CycloneDX JSON SBOM과 GitHub build provenance도 함께 공개합니다. SBOM의 목록 범위는 `requirements-web-lock.txt`에 고정한 Python 의존성입니다.

Paramiko 수정 릴리스가 아직 없는 `CVE-2026-44405`는 정확히 한 건만 감사 예외로 고정합니다. 서버 키 probe와 실제 연결에서 RSA/SHA-1을 비활성화하고 맞춤 고정 키 policy로 인증 전에 키 재료를 검증하며, 근거·제거 조건·재검토 기한은 `docs/DEPENDENCY_AUDIT_EXCEPTIONS_KO.md`에 공개합니다.

## Release 전 검증

릴리스 준비 변경의 PR Validation이 성공한 상태에서 병합한 `main` 커밋에 수동 Release workflow를 실행합니다. Release workflow는 해당 커밋의 자동 검사와 Windows 패키지 검증을 다시 수행한 뒤 공개 자산을 발행합니다.

Release workflow와 같은 Python 3.11, Node.js 22 환경을 준비하고 잠금 의존성을 먼저 설치합니다. Python 통합 검사도 Node.js와 JSDOM을 사용하므로 `pytest` 전에 JavaScript 의존성 설치를 완료해야 합니다.

```powershell
python -m pip install --require-hashes -r requirements-lock.txt
python -m pip install --no-deps --no-build-isolation -e .
npm ci --ignore-scripts
```

기본 검증:

```powershell
python -m pytest -q
python -m compileall -q src tests tools
python -m pip check
python -m pip_audit -r requirements-lock.txt --strict --ignore-vuln CVE-2026-44405
python -m pip_audit -r requirements-web-lock.txt --strict --ignore-vuln CVE-2026-44405
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
npm test
```

Windows GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_gui_exe.ps1
python .\tools\verify_release_package.py --dist .\dist
```

Streamlit portable:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_streamlit_portable.ps1
python .\tools\verify_streamlit_portable_package.py --dist .\dist --smoke
```

통합 ZIP:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_combined_release.ps1
python .\tools\verify_combined_release_package.py --dist .\dist --smoke
```

최종 Release asset은 계산된 SHA-256을 다시 입력해 통합 ZIP 검증을 한 번 더 수행합니다.

## Release notes 구성

Release 첫 화면에서는 구현 세부사항보다 **사용자가 업그레이드 여부를 판단할 정보**를 먼저 보여줍니다.

권장 순서:

1. 이번 릴리즈의 핵심 변경
2. 운영 영향
3. 검증 결과
4. 다운로드 파일과 SHA-256
5. 알려진 기능 범위
6. 세부 커밋

자동 생성 본문도 이 순서를 따릅니다.

## 운영 영향 작성 기준

다음 내용을 명확히 구분합니다.

- 장비 설정 변경 여부
- 기존 결과 파일 호환성 영향
- 수집/Parser/판정 의미 변화
- 사용자가 다시 확인해야 할 설정
- 부분 완료 또는 데이터 신뢰도에 미치는 영향

단순 UI 문구 변경이나 문서 변경에 습관적으로 `보안` 항목을 붙이지 않습니다.

`보안`은 다음과 같이 실제 보안 경계가 바뀌는 경우에만 별도로 표시합니다.

- 자격 증명 처리
- SSH/Telnet 접근 범위
- 민감정보 마스킹
- 웹앱 원격 접근
- 패키지 무결성
- 의존성 취약점

## 공개하지 않는 정보

Release notes와 asset에는 다음 정보를 포함하지 않습니다.

- 실제 WLC 주소 / Hostname
- 장비 계정과 비밀번호
- 실제 SSID / Role / ACL / Alias 이름과 원문
- 내부 VLAN / 서브넷 / Role 대역표
- ClearPass/RADIUS 내부 구성
- 실제 `show` 명령 출력
- 고객명, 사이트명, 운영망 식별 정보
- 실제 운영 보고서

문서 예시는 비식별 샘플만 사용합니다.

## 현재 알려진 범위

- ClearPass/RADIUS 서버에서 동적 Role을 직접 조회하지 않습니다.
- 모든 service object를 TCP/UDP 포트 번호까지 완전 해석하지 않습니다.
- Streamlit 자체 사용자 로그인/권한 관리 기능은 없습니다.
- 코드서명, installer, MSIX는 현재 범위가 아닙니다.
- Windows EXE는 Windows runner 또는 Windows PC에서 검증합니다.
- PDF 저장은 별도 브라우저 인쇄 창에서 `PDF로 저장`을 선택하는 방식입니다.
- 이번 주석 기능의 실제 회사 장비·Windows 사용자 환경·인쇄 결과 수동 검증은 사용자의 별도 범위입니다.
