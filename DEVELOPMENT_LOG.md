# 개발 이력

## 2026-11-16 — 오프라인 주석 작업·재사용·보고서 개발 마무리

### 목표와 작업 범위

HTML에서 Role 설명과 ACL 행별 주석을 편집하고, 수집 결과와 주석을 JSON 작업 파일로 함께 보관한다. 다음 수집에서는 이전 설명을 정책 내용과 장비 범위로 대조해 재사용하며, 동일한 보고 범위와 최신 주석으로 PDF·Excel을 출력한다.

- 요구사항: [기능 명세](docs/superpowers/specs/2026-11-16-annotation-project.md)
- 작업 순서와 가중치: [구현 계획](docs/superpowers/plans/2026-11-16-annotation-project.md)
- 개발 브랜치: `feature/annotation-project-reuse-export`
- 변경 검토: [PR #23](https://github.com/sebia1993/aruba-wireless-policy-mapper/pull/23)
- 실제 회사 장비·회사 파일·Windows 사용자 환경·인쇄 결과 확인은 사용자가 수행하며 개발 완료율에 포함하지 않는다.

### 기존 구현 확인

기능 구현 `8f2d9d3`, Windows UTF-8 검사 수정 `3c93b56`, 빌드 의존성 수정 `6473fb2`를 기준으로 후속 작업을 시작했다. 저장·열기, 기존 HTML 가져오기, 장비별 재사용, 미연결 주석 보존, 복구, PDF·Excel 출력과 오프라인 자산이 이미 구현되어 있었다.

후속 수정 전 기존 자동 검사는 Python 215개와 JavaScript 63개가 모두 통과했다. 독립 코드 리뷰에서는 아래 PDF 대상 식별 문제 한 건을 확인했다.

### 발견한 문제와 선택한 수정

여러 컨트롤러의 표시 이름과 Role·ACL·규칙 이름이 같으면 PDF 상세 표의 대상 열도 같게 출력됐다. 원본 모델과 Excel에는 장비 식별자가 남아 있었지만, PDF 변환 단계에서 표시할 열을 추리는 과정에서 빠져 각 주석의 소속 장비를 구분하기 어려웠다.

PDF의 Role·ACL·변경 사항·Alias 상세 행마다 컨트롤러 식별자와 주소·포트·설정 범위를 함께 출력하도록 수정했다. Role·규칙·Alias 식별자도 대상 열에 포함해 보고서의 개별 행을 작업 데이터와 대조할 수 있게 했다. 주소 정보가 없는 이전 자료는 장비 이름으로 주소를 추정하지 않는다.

작업 JSON의 형식 버전과 주석 연결 방식은 그대로 사용한다. 이번 수정은 PDF에서 장비와 정책을 표시하는 단계에 적용되며, 수집기나 장비 명령에는 변경이 없다.

### 수정 근거와 자동 검사

추가한 회귀 검사 `PDF detail rows keep same-named controllers and policy occurrences distinguishable`는 같은 이름을 가진 두 WLC에 같은 Role·ACL·규칙을 배치하고, 서로 다른 주소·포트·설정 범위·주석을 넣는다. 생성된 인쇄용 HTML의 네 상세 표에서 각 행이 자기 장비와 정책 식별자를 갖는지 확인한다.

1. 수정 전에는 `Role 설명 target must identify controller-a`로 실패했다.
2. PDF 변환을 수정한 뒤 동일한 검사가 통과했다.
3. 전체 Python 검사 `python -m pytest -q`: **215 passed**.
4. 전체 JavaScript 검사 `npm test`: **64 passed**, 실패·건너뛰기 없음.
5. `git diff --check`: 통과.

Python 검사는 해당 작업 소스 경로와 기존 격리 환경을 사용했고, Node 검사는 설치된 JSDOM을 사용했다. 실장비 연결이나 실제 사용자 PC의 실행 검증은 수행하지 않았다. 원격 Windows 빌드 결과는 PR Checks의 해당 커밋 실행 결과로 별도 확인한다.

### 문서와 다음 단계

사용자 설명서의 Markdown·HTML, 변경 기록, 검증 보고서를 갱신했다. 개발 결과는 기존 PR #23에 후속 커밋으로 관리한다. 독립 리뷰에서 확인된 추가 필수 구현 항목이나 보류한 경미한 수정 항목은 없다.

이번 개발 범위의 완료 기준은 기능 구현·자동 회귀·문서·개발 브랜치 반영이다. `main` 병합과 정식 릴리스 발행은 별도 배포 단계다.

## 2026-11-16 — v0.3.0 정식 릴리스 준비

### 추가 승인과 배포 범위

개발 마무리 이후 사용자가 `main` 병합과 정식 릴리스 발행을 명시적으로 승인하여 배포 준비를 시작했다. 앞선 기록의 개발 범위는 당시 이력으로 유지하고, 이번 배포 단계에서 주석 작업·재사용·보고서 기능과 기존 미발행 변경을 `v0.3.0`으로 묶는다.

실제 회사 장비·회사 파일·Windows 사용자 환경·인쇄 결과의 수동 확인은 계속 사용자의 별도 검증 범위다. Windows CI의 자동 빌드·smoke 결과는 이 현장 검증과 구분한다.

### 릴리스 준비 내용

- 프로젝트 메타데이터와 실행 코드의 버전을 `0.3.0`으로 맞추고, 현재 배포 파일 안내와 변경 기록을 갱신한다. `0.2.0`의 변경 이력과 당시 화면 캡처 정보는 보존한다.
- Release workflow에 PR 검증과 같은 Node.js 22, `npm ci --ignore-scripts`, `npm test`를 적용한다. Python 통합 검사에서 JSDOM을 사용하므로 JavaScript 의존성 설치도 Python 검사 전에 수행한다.
- 자동 Release notes에 주석 편집, JSON 작업 보관, 이전 설명 재사용, 장비별 구분, 실제 XLSX와 브라우저 인쇄를 통한 PDF 저장을 반영한다.
- Windows 통합 ZIP, SHA-256 sidecar, `requirements-web-lock.txt` 기준 Python 의존성 CycloneDX SBOM과 GitHub build provenance를 배포 산출물로 유지한다.

### 검증 근거와 후속 확인

릴리스 준비 시작 시점의 기능 브랜치 커밋은 `5ee95afa917166bbfe44447ad1bffc1ca89b35cf`다. 해당 PR의 [Windows 검증 실행 43837938414](https://github.com/sebia1993/aruba-wireless-policy-mapper/actions/runs/43837938414)에서 Python 215개, JavaScript 64개 검사와 GUI/CLI·Streamlit portable·통합 ZIP 빌드 및 smoke 검증이 통과했다.

릴리스 준비 변경의 PR 검사를 확인한 뒤 병합한 `main` 커밋에 Release workflow를 실행한다. Release workflow에서 해당 커밋의 자동 검사와 Windows 패키지 검증을 다시 수행하며, `main` push 검증도 별도로 실행된다. 태그가 병합한 `main` 커밋을 가리키는지, 공개 자산 세 개와 최종 ZIP의 SHA-256이 일치하는지 확인하는 것을 발행 완료 기준으로 삼는다. 이 항목은 배포 준비 기록이며 병합·발행 완료 결과는 해당 실행과 공개 Release에서 확인한다.
