# 의존성 감사 예외

의존성 취약점은 원칙적으로 고정 버전으로 갱신해 해결합니다. 아직 수정 릴리스가 없는 경우에만 정확한 취약점 ID, 보완 통제, 제거 조건과 재검토 기한을 함께 기록한 뒤 CI에서 해당 ID 하나만 예외 처리합니다.

## CVE-2026-44405 / PYSEC-2026-2858

| 항목 | 내용 |
| --- | --- |
| 의존성 | Paramiko 4.0.0 |
| 영향 | `ssh-rsa` 식별자를 통한 RSA/SHA-1 서명 허용 |
| 최초 검토 | 2026-08-24 |
| 다음 재검토 기한 | 2026-09-24 또는 Paramiko 수정 릴리스 공개 시점 중 빠른 날 |
| 공개 수정 근거 | Paramiko commit `a4489456b6f65281e172380cc4826cee5e851dbb` |
| CI 예외 | `CVE-2026-44405` 하나만 허용 |

현재 PyPI에는 취약점 데이터베이스가 인식하는 수정 버전이 없습니다. 애플리케이션은 다음 보완 통제를 적용합니다.

- 서버 키를 가져오는 사전 probe와 실제 Netmiko 연결 모두에 `disabled_algorithms={"keys": ["ssh-rsa"], "pubkeys": ["ssh-rsa"]}`를 전달합니다.
- Paramiko `SSHClient`에는 RSA 항목이 든 `known_hosts`를 직접 로드하지 않습니다. 맞춤 `PinnedHostKeyPolicy`가 SHA2-only key exchange 뒤, 자격 증명 인증 전에 앱 전용 파일의 키 재료를 직접 비교해 Paramiko 4.0의 RSA 우선순위 재설정을 우회합니다.
- 따라서 RSA 키 재료를 사용하더라도 SHA-1 서명은 협상하지 않고 RSA-SHA2를 지원하는 장비만 허용합니다.
- 서버 키는 별도 SHA-256 지문 확인 후 앱 전용 `known_hosts`에 고정하고 변경 키를 자동 교체하지 않습니다.
- SSH 실패를 Telnet으로 자동 전환하지 않습니다.
- 회귀 테스트에서 SSH 연결 인자와 사전 probe의 SHA-1 비활성화를 확인합니다.

수정된 Paramiko 릴리스가 공개되면 잠금 파일을 갱신하고 전체 테스트·Windows 패키지 smoke·의존성 감사를 다시 통과시킨 뒤 이 예외와 CI의 `--ignore-vuln`을 같은 PR에서 제거합니다. 기한이 지나도록 수정 릴리스가 없으면 영향과 보완 통제를 다시 검토하며, 근거 없이 예외를 연장하지 않습니다.

근거:

- <https://github.com/paramiko/paramiko/commit/a4489456b6f65281e172380cc4826cee5e851dbb>
- <https://github.com/advisories/GHSA-r374-rxx8-8654>
