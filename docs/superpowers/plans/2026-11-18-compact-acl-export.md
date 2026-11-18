# B안 ACL 간단·상세 보고서 선택형 개발

## 사용자 결정
- 간단 보고서를 기본으로 한다.
- Excel/PDF의 간단 보고에는 컨트롤러/Role/ACL 맥락과 규칙 순서, 출발지/목적지/서비스/동작 및 ACL 행별 주석만 노출한다.
- 기존 5개 시트 상세 Excel과 기술 부록 포함 PDF를 '상세 보고서 (기존)'으로 유지한다.
- 기존 주석 저장, 재사용, 수집 원본, 정책 판정, 공통 ACL 분류, 현재 보고 범위 선택은 수정하지 않는다.
- main 병합 및 GitHub Release 발행을 승인 전까지 보류한다.

## 구현 분리
- `annotation_editor.js`: 보고서 구성 선택(간단 기본/상세), 다운로드 파일명 분리.
- `annotation_export.js`: 간단 시트 생성, 내부 장문 주석 조각 정보는 숨김 열에 보관. 상세 5개 시트 로직 원형 유지.
- `annotation_pdf.js`: 간단 A4 가로 표/그룹 출력. 상세 A4 세로 기존 레이아웃 유지.
- `annotation_core.js` 및 annotation project schema: 변경 없음.

## 안정성 및 수용 기준
1. 기존 ACL의 순서/반복 발생, 주석 원문(한글/이모지/32767자 이상) 보존.
2. Excel 주석은 수식으로 실행되지 않으며, 숨김 열을 제외한 화면에는 아홉 필드만 표시.
3. PDF 한글 검색/복사 및 직접 다운로드 유지, 인쇄창 없음.
4. 보고 범위(all/selected/review)와 공통 ACL/다중 컨트롤러 ID 매칭은 기존 단일 export model로 처리.
5. 수집 불완전 경고는 간단 PDF에서도 유지.
6. 상세 보고서의 5개 시트/7개 PDF 섹션은 그대로 유지.
7. 원본 수집/주석 JSON을 내보내기 과정에서 수정하지 않음.

## 검증
- `npm ci --ignore-scripts && npm test`
- `python -m pytest` (Windows CI의 별도 검증 경로 포함)
- PR Validation: Windows GUI/Web/통합 ZIP 빌드 확인
- 사내 실제 WLC 및 Windows 현장 검증은 사용자가 수행. 코드 단계에서 검사 완료로 주장하지 않음.
