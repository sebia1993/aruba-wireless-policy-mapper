# WLC Role / ACL Collector 검증 보고서

이 문서는 자동 테스트, 패키지 검증, 운영 환경 검증을 **서로 다른 증거 수준으로 구분**해 관리하기 위한 기준입니다.

실제 WLC 주소, Hostname, 계정, Role/ACL 원문, 내부 대역표와 생성된 운영 보고서는 공개 저장소에 기록하지 않습니다.

## 1. 현재 공개 검증 상태

| 구분 | 상태 | 공개 근거 |
|---|---|---|
| Parser / ACL 평가 단위 테스트 | ✅ | `tests/` 및 PR Validation |
| Mock WLC / fixture 수집 | ✅ | `config/mock_scenarios/`, 테스트 코드 |
| GUI / CLI / Web 공통 수집 상태 | ✅ | 자동 회귀 테스트 |
| 부분 완료 / 영향 Role·SSID 계산 | ✅ | 자동 회귀 테스트 |
| 60 Role / 1,200 ACL 보고서 | ✅ | 대량 데이터 회귀 테스트 |
| 100 Role / 4,000 ACL HTML 경로 | ✅ | 렌더링 검증 경로 |
| Windows GUI / CLI 패키지 | ✅ | GitHub Actions Windows runner |
| Streamlit portable 패키지 | ✅ | GitHub Actions Windows runner |
| GUI + Web 통합 ZIP | ✅ | GitHub Actions Windows runner |
| 실제 운영 환경 검증 | 비식별 요약만 공개 | 실제 운영 정보는 외부 공개 대상 아님 |

> 자동 테스트가 실제 WLC 검증을 대체한다고 표현하지 않습니다. 실제 운영 환경에서 확인한 결과가 있더라도 공개 저장소에는 장비별 원문 증거를 올리지 않습니다.

## 2. 검증 대상 기능

### 수집 경로

| 번호 | 항목 | 합격 기준 |
|---:|---|---|
| 1 | WLC 접속 | 선택한 SSH/Telnet 방식으로 정상 세션 수립 |
| 2 | Enable 처리 | 필요한 환경에서만 정상 전환, 실패 시 별도 오류 분류 |
| 3 | SSID / AAA 수집 | 관계 구성에 필요한 항목이 Parser 입력으로 전달 |
| 4 | Role 수집 | 기본 Role과 Role ACL 관계를 구성 |
| 5 | Alias / NetDestination | 참조 Alias를 실제 정의까지 연결 |
| 6 | VLAN / 사용자 관측 | 보조 근거를 보고서 모델에 반영 |
| 7 | 일부 명령 실패 | 전체 성공으로 숨기지 않고 부분 완료로 표시 |
| 8 | 전체 시간 제한 | live 수집이 상한을 넘겨 무한 대기하지 않음 |
| 9 | 취소 | 다음 작업을 중단하고 세션 정리 경로로 이동 |

### 정책 분석

| 번호 | 항목 | 합격 기준 |
|---:|---|---|
| 1 | SSID → AAA | SSID와 AAA Profile 관계를 일관되게 구성 |
| 2 | 기본 Role 구분 | initial/mac-default/dot1x-default를 혼합하지 않음 |
| 3 | Role → ACL | Role별 ACL 목록과 규칙을 연결 |
| 4 | ACL → Alias | Alias 참조와 NetDestination 정의를 연결 |
| 5 | 동적 Role 경계 | RADIUS/ClearPass 가능성을 직접 수집값처럼 표시하지 않음 |
| 6 | Access Check | 필요한 선행 정보가 없으면 `판정 불가` 처리 |
| 7 | 영향 범위 | 실패 명령이 영향을 주는 Role/SSID를 제한적으로 표시 |
| 8 | 대량 데이터 | 많은 Role/ACL에서도 ID 충돌·렌더링 실패 없이 결과 생성 |

### 결과물

| 번호 | 항목 | 합격 기준 |
|---:|---|---|
| 1 | Excel | 수집/분석 결과와 상태 정보를 열 수 있는 통합문서로 생성 |
| 2 | 생성 상태 JSON | `report_status.json`에서 파일 생성 상태와 수집 상태를 구분 |
| 3 | HTML | 관리자 요약과 Role/ACL 상세를 브라우저에서 확인 가능 |
| 4 | Access Check | 보고서 내부에서 입력값에 대한 정책 평가 가능 |
| 5 | Role PNG | 선택 Role의 ACL 내용을 이미지로 저장 가능 |
| 6 | 부분 완료 결과 | 실패가 있어도 정상 수집 영역과 영향 범위를 구분 |
| 7 | 원자적 저장 | 중간 실패가 완성된 기존 결과를 무조건 덮어쓰지 않음 |

## 3. 자동 검증

기본 테스트:

```powershell
python -m pytest
```

통합 검증:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
```

PR Validation에서는 Windows runner에서 다음까지 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_gui_exe.ps1
python .\tools\verify_release_package.py --dist .\dist --smoke-cli

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_streamlit_portable.ps1
python .\tools\verify_streamlit_portable_package.py --dist .\dist --smoke

powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_combined_release.ps1
python .\tools\verify_combined_release_package.py --dist .\dist --smoke
```

검증 과정에서 실제 운영 WLC 접속을 요구하지 않도록 fixture와 Mock scenario를 사용합니다.

## 4. 운영 환경 검증 체크리스트

실제 환경에서 검증할 때는 조직 정책과 승인 범위 안에서 다음을 확인합니다.

| 항목 | 확인 내용 |
|---|---|
| 접속 | 허가된 계정으로 WLC 조회 성공 |
| 장비 영향 | 설정 변경 및 서비스 영향 없음 |
| SSID/AAA 관계 | 수동 CLI 확인 결과와 주요 매핑 일치 |
| 기본 Role | initial/mac-default/dot1x-default 관계 확인 |
| Role/ACL | 수동 조회와 보고서의 주요 관계 일치 |
| Alias | NetDestination 범위 해석 일치 |
| 동적 Role | 기본 Role과 동적 Role 가능성 표시가 혼동되지 않음 |
| 부분 실패 | 의도적으로 실패 조건을 만들었을 때 영향 범위 표시 확인 |
| 결과 파일 | Excel/HTML 정상 열림 |
| Access Check | 대표 허용/차단/판정불가 조건을 수동 정책과 대조 |
| 반복 실행 | 이전 실행의 임시 상태가 다음 실행을 오염시키지 않음 |
| 종료/취소 | 열린 세션과 임시 작업이 정리됨 |

## 5. 공개 가능한 운영 검증 요약

운영 환경에서 검증이 완료된 경우에도 공개 자료에는 아래 수준만 기록합니다.

```text
운영 환경 검증
- 대상: Aruba AOS8 WLC
- SSID → AAA → Role → ACL 관계 수집: 확인
- Alias / NetDestination 해석: 확인
- Excel / HTML 보고서: 확인
- 부분 완료 및 오류 분류: 확인
- 장비 설정 변경: 없음 확인
- 실제 주소·장비명·정책 원문: 비공개
```

다음 정보는 공개하지 않습니다.

- 실제 WLC IP / Hostname
- 사용자 ID와 인증 정보
- 실제 SSID 이름
- 실제 Role / ACL / Alias 이름과 원문
- VLAN / 내부 대역
- ClearPass/RADIUS 내부 구성
- 실제 운영 보고서 원본
- 고객/사이트/건물 등 조직 식별 정보

## 6. 검증과 기능 범위의 경계

검증 완료는 현재 구현 범위가 의도대로 동작한다는 의미이며, 다음 기능이 구현되었다는 의미는 아닙니다.

- ClearPass/RADIUS 서버에서 동적 Role 직접 조회
- 모든 service object의 TCP/UDP 포트 정밀 해석
- Streamlit 자체 사용자 인증/권한 관리
- 코드서명과 SmartScreen 평판

README와 Release Notes에서는 이 경계를 유지합니다.
