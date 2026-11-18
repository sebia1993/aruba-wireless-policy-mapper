# 의존성 감사 예외

개발용 `requirements-lock.txt`와 Web용 `requirements-web-lock.txt`는 모두 예외 없이 `pip-audit --strict`로 검사합니다.

## 종료한 예외

| 항목 | 내용 |
| --- | --- |
| 취약점 | CVE-2026-44405 / PYSEC-2026-2858 |
| 영향 | Paramiko 5.0.0 미만에서 RSA/SHA-1 서명을 허용 |
| 이전 잠금 버전 | Netmiko 4.7.0과 Paramiko 4.0.0 |
| 교체 버전 | Netmiko 4.8.0과 Paramiko 5.0.0 |
| 상태 | 두 잠금 파일 갱신 및 감사 예외 제거 |

[GitHub 보안 권고](https://github.com/advisories/GHSA-r374-rxx8-8654)는 5.0.0을 최초 수정 버전으로 명시합니다. Paramiko 5.0.0은 RSA/SHA-1 서명과 SHA-1 키 교환 지원을 제거했습니다. [Paramiko 변경 이력](https://www.paramiko.org/changelog.html#5.0.0)

Netmiko 4.8.0의 기본 의존성은 Paramiko 5.0.0과 호환됩니다. [Netmiko 4.8.0 배포 메타데이터](https://pypi.org/pypi/netmiko/4.8.0/json)

앱은 장비 인증 전에 서버 키를 앱 전용 `known_hosts`와 비교합니다. 미승인 키와 변경된 키는 연결을 차단합니다. RSA 장비 키를 사용할 때는 장비가 RSA-SHA2 서명을 지원해야 합니다. SSH 실패 시 Telnet으로 자동 전환하지 않습니다.
