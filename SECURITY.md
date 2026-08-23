# 보안 및 민감정보 처리 원칙

이 저장소는 Aruba AOS8 WLC의 SSID·AAA Profile·Role·ACL·Alias 관계를 분석하는 네트워크 운영 자동화 도구입니다. 공개 저장소와 배포물은 실제 운영망 정보를 포함하지 않는 것을 원칙으로 합니다.

## 공개하지 않는 정보

다음 정보는 Issue, Pull Request, Release notes, 테스트 fixture, 문서 화면에 올리지 않습니다.

- 실제 WLC IP, Hostname, 사이트·건물명
- 사용자 ID, 비밀번호, Enable password
- SSH 장비 지문과 내부 인증 정보
- 실제 SSID, Role, ACL, Alias 이름과 원문
- VLAN, 내부 IP 대역, Role 대역표
- ClearPass/RADIUS 내부 구성
- 실제 `show` 명령 원문과 운영 보고서

문서와 테스트에는 비식별 샘플과 Mock 데이터를 사용합니다.

## 장비 접근 경계

- 이 프로젝트의 목적은 조회·분석이며 장비 설정 변경 기능을 제공하지 않습니다.
- 실제 WLC 접속은 운영자가 승인된 계정과 네트워크에서 명시적으로 실행해야 합니다.
- SSH는 장비 계정을 보내기 전에 SHA-256 서버 키 지문을 확인하고 앱 전용 `known_hosts`에 고정합니다.
- Paramiko 4.0의 RSA/SHA-1 취약 경로는 host key와 public-key 인증 알고리즘 양쪽에서 `ssh-rsa`를 비활성화해 차단합니다. 고정된 감사 예외의 근거와 제거 조건은 [`docs/DEPENDENCY_AUDIT_EXCEPTIONS_KO.md`](docs/DEPENDENCY_AUDIT_EXCEPTIONS_KO.md)에 공개합니다.
- 승인되지 않은 SSH 키와 변경된 키를 차단하며, 기존 키는 자동 교체하지 않습니다.
- Telnet은 평문 전송이므로 격리된 관리망에서 위험을 승인해 직접 선택한 경우에만 사용하며 SSH 실패 시 자동 전환하지 않습니다.
- GUI/Web/CLI의 자동 테스트와 CI는 실제 운영 장비에 접속하지 않습니다.
- 로컬 Streamlit 웹앱은 loopback 주소에만 바인딩하며 외부 인터페이스 실행을 차단합니다.
- 일부 명령 실패나 불완전한 Alias/ACL 정보는 정상 결과로 숨기지 않고 `부분 완료` 또는 `판정 불가`로 표시합니다.

## 자격 증명과 진단정보

- 장비 계정과 비밀번호를 소스 코드·샘플 설정·일반 로그에 저장하지 않습니다.
- 안전 진단 보고서는 주소·계정·Role/ACL 원문 등 운영 식별정보를 제거한 상태만 공유 대상으로 봅니다.
- 실제 운영 보고서와 내부 Role 대역표는 공개 저장소에 커밋하지 않습니다.

## 취약점 또는 민감정보 노출 발견 시

공개 Issue에 자격 증명, 실제 장비 정보, 내부 정책 원문을 게시하지 마십시오. 먼저 민감정보를 제거한 재현 절차와 영향 범위를 정리한 뒤 저장소 소유자에게 비공개 채널로 전달하는 것을 권장합니다.

이미 공개 커밋이나 Release에 민감정보가 들어갔다면 단순 파일 삭제만으로 해결됐다고 간주하지 말고, 해당 자격 증명·토큰·키를 즉시 폐기 또는 교체한 뒤 Git 이력과 Release asset까지 별도로 점검해야 합니다.

## 검증과 운영 안전

자동 검증 범위와 실제 운영 환경 검증의 경계는 [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md), 상세 보안 모델은 [`docs/SECURITY_MODEL_KO.md`](docs/SECURITY_MODEL_KO.md)를 참고하십시오.
