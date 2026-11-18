# 포트폴리오 검토 안내: 무선 정책 관계와 판단 한계

이 프로젝트에서 검토할 역량은 **SSID·AAA·Role·ACL·Alias를 연결하고, 수집 누락이 접근 정책 판단에 미치는 영향을 설명하는 능력**입니다. 보고서 화면과 함께 아래 구현·테스트를 읽으면 판단 근거를 확인할 수 있습니다.

## 코드로 확인하는 설계 판단

| 검토 질문 | 구현 근거 | 재현 근거 |
|---|---|---|
| 장비 접속과 오프라인 분석을 분리했는가? | [collector.py](../src/wlc_role_acl_collector/collector.py), [web_logic.py](../src/wlc_role_acl_collector/web_logic.py) | [test_web_logic.py](../tests/test_web_logic.py)의 `test_run_web_collection_offline_returns_preview_and_downloads` |
| SSID에서 기본 Role과 ACL까지 어떻게 연결하는가? | [aos8_parser.py](../src/wlc_role_acl_collector/aos8_parser.py), [models.py](../src/wlc_role_acl_collector/models.py) | [sample_controller fixture](../tests/fixtures/sample_controller/), [test_parser.py](../tests/test_parser.py) |
| 선행 ACL의 Alias를 수집하지 못하면 후속 permit으로 통과시키는가? | [acl_evaluator.py](../src/wlc_role_acl_collector/acl_evaluator.py) | [test_acl_evaluator.py](../tests/test_acl_evaluator.py)의 `test_evaluate_access_stops_at_potential_match_when_alias_detail_is_missing`는 `unknown`을 확인 |
| 일부 명령 실패를 전체 성공과 구분하는가? | [collection_health.py](../src/wlc_role_acl_collector/collection_health.py) | [test_collection_health.py](../tests/test_collection_health.py)의 필수 출력 누락·선택 명령 실패 사례 |
| Excel과 HTML 저장 중 오류가 나면 어떻게 표시하는가? | [report.py](../src/wlc_role_acl_collector/report.py), [atomic_io.py](../src/wlc_role_acl_collector/atomic_io.py) | [test_report.py](../tests/test_report.py), [test_atomic_io.py](../tests/test_atomic_io.py) |

Access Check는 수집된 정책 모델의 평가입니다. 실제 패킷 전달, ClearPass/RADIUS가 반환한 동적 Role, 모든 service object의 포트 해석을 증명하지 않습니다. 이 경계는 [보안 모델](SECURITY_MODEL_KO.md)과 [검증 보고서](VALIDATION_REPORT.md)를 함께 읽어 확인합니다.

## 장비 없이 보고서 재현하기

Windows PowerShell과 Python 3.11에서 저장소 루트 기준으로 실행합니다. 의존성 설치에는 인터넷이 필요할 수 있습니다. 데모는 loopback의 Mock WLC에서 합성 응답을 수집합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest -q tests/test_web_logic.py tests/test_acl_evaluator.py tests/test_collection_health.py
.\.venv\Scripts\python.exe -m streamlit run portfolio_demo/app.py --server.address 127.0.0.1
```

브라우저에서 **정상 수집**을 선택하고 **수집 실행**을 누른 뒤 결과 요약과 다운로드 파일을 확인합니다. **부분 수집 실패** 시나리오에서는 보고서에 표시된 실패 명령과 영향 범위도 확인할 수 있습니다.

| 파일 | 확인할 내용 |
|---|---|
| HTML | SSID → AAA → 기본 Role → ACL 관계와 Access Check의 경고 |
| Excel | 보고서의 구조화된 표와 수집 상태 |
| CSV | SSID와 기본 Role의 연결 관계 |

보고서 생성에 성공해도 일부 명령 수집은 실패할 수 있습니다. 결과 요약에서 수집 상태와 실패 명령을 함께 확인합니다. 실제 수집의 raw 출력과 생성 보고서는 내부 정책 정보이므로 공개 샘플로 전용하지 않습니다.

## 검증 근거와 후속 과제

- [Windows PR Validation](https://github.com/sebia1993/aruba-wireless-policy-mapper/actions/workflows/pr-validation.yml)의 **검토한 커밋 SHA에 해당하는 완료 결과**를 확인합니다. [정의](../.github/workflows/pr-validation.yml)는 Windows GUI, Streamlit portable, 통합 ZIP과 공개 데모 시나리오를 검증합니다.
- [Releases](https://github.com/sebia1993/aruba-wireless-policy-mapper/releases)의 바이너리는 해당 태그와 자산을 별도로 검토합니다. 현재 소스의 CI 결과만으로 다른 태그의 검증 상태를 대신하지 않습니다.
- 남은 실증은 펌웨어별 출력, 실제 SSID/기본 Role 관계의 수동 대조, 동적 Role 적용 환경에서의 오해 방지, 합성 규모 테스트와 실제 장비 지연의 차이입니다.
- 공개 데모와 Windows 웹앱은 같은 Web 잠금 파일을 사용합니다. Netmiko 4.8.0과 Paramiko 5.0.0으로 교체한 근거와 이전 감사 예외 이력은 [의존성 감사 기록](DEPENDENCY_AUDIT_EXCEPTIONS_KO.md)에서 확인할 수 있습니다.

면접에서는 허용/차단 예시뿐 아니라 **왜 누락된 Alias에서 판정을 멈추는지**를 테스트 입력과 결과로 설명하는 것이 이 프로젝트의 핵심입니다.
