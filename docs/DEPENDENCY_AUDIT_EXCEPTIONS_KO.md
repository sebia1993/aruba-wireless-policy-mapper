# 의존성 감사 예외

의존성 취약점은 검증한 정식 버전으로 갱신해 해결합니다. 이 문서는 아직 제거하지 못한 감사 예외의 정확한 ID, 보완 통제, 제거 조건과 재검토 기한을 기록합니다. 예외나 보완 통제는 취약점 해소를 의미하지 않습니다.

## CVE-2026-44405 / PYSEC-2026-2858

| 항목 | 내용 |
| --- | --- |
| 의존성 | Paramiko 4.0.0 |
| 영향 | `ssh-rsa` 식별자를 통한 RSA/SHA-1 서명 허용 |
| 최초 검토 | 2026-08-24 |
| 공개 자료 재확인 | 2026-09-08 |
| 다음 재검토 기한 | 2026-09-24 또는 Paramiko 수정 릴리스 공개 시점 중 빠른 날 |
| 공개 수정 근거 | Paramiko commit `a4489456b6f65281e172380cc4826cee5e851dbb` |
| CI 예외 | `CVE-2026-44405` 하나만 허용 |

2026-09-08 재확인 결과 [PyPI의 Paramiko 5.0.0](https://pypi.org/project/paramiko/5.0.0/)이 공개되어 있고, [공식 변경 이력](https://www.paramiko.org/changelog.html#5.0.0)은 RSA/SHA-1 서명과 SHA-1 key exchange 지원 제거를 명시합니다. 같은 날 [GitHub Advisory](https://github.com/advisories/GHSA-r374-rxx8-8654)의 `Patched versions`는 `None`으로 표시됩니다. Advisory의 필드만으로 수정 후보 배포가 없다고 판단하지 않습니다.

현재 저장소는 4.0.0 잠금 파일을 사용하며 5.0.0 교체·SSH 회귀·Windows 통합 패키지 검증은 완료되지 않았습니다. 잠긴 Netmiko 4.7.0의 [PyPI 메타데이터](https://pypi.org/pypi/netmiko/4.7.0/json)는 `paramiko<5.0,>=3.5.0`을 요구하므로 Paramiko만 5.0.0으로 바꿀 수 없습니다. Netmiko 호환 버전, 서명 외 KEX 지원 변경, 맞춤 호스트 키 정책을 함께 검토해야 합니다. 이 미해결 상태에서 애플리케이션이 적용하는 임시 보완 통제는 다음과 같습니다.

- 서버 키를 가져오는 사전 probe와 실제 Netmiko 연결 모두에 `disabled_algorithms={"keys": ["ssh-rsa"], "pubkeys": ["ssh-rsa"]}`를 전달합니다.
- Paramiko `SSHClient`에는 RSA 항목이 든 `known_hosts`를 직접 로드하지 않습니다. 맞춤 `PinnedHostKeyPolicy`가 SHA2-only key exchange 뒤, 자격 증명 인증 전에 앱 전용 파일의 키 재료를 직접 비교해 Paramiko 4.0의 RSA 우선순위 재설정을 우회합니다.
- 따라서 RSA 키 재료를 사용하더라도 SHA-1 서명은 협상하지 않고 RSA-SHA2를 지원하는 장비만 허용합니다.
- 서버 키는 별도 SHA-256 지문 확인 후 앱 전용 `known_hosts`에 고정하고 변경 키를 자동 교체하지 않습니다.
- SSH 실패를 Telnet으로 자동 전환하지 않습니다.
- 회귀 테스트에서 SSH 연결 인자와 사전 probe의 SHA-1 비활성화를 확인합니다.

검토 후보 5.0.0에 대해 두 잠금 파일을 함께 갱신하고 전체 테스트·Windows 패키지 smoke·의존성 감사를 통과시킨 뒤 이 예외와 CI의 `--ignore-vuln`을 같은 PR에서 제거해야 합니다. 후보가 확인되었으므로 재검토 기한을 기다리지 않고 업그레이드 검증을 후속 과제로 다룹니다. 이 문서 변경만으로 경고를 닫거나 예외 기한을 연장하지 않습니다.

근거:

- <https://github.com/paramiko/paramiko/commit/a4489456b6f65281e172380cc4826cee5e851dbb>
- <https://github.com/advisories/GHSA-r374-rxx8-8654>
