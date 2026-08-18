# Codex–Claude 수집 워크플로우

*개정 2026-08-18 — Claude Opus 5 메타검토 반영*

이 프로젝트는 검토 횟수가 아니라 서로 다른 산출물을 검토하는 데 예산을 쓴다.

1. Codex가 `API_FINDINGS`의 각 실측을 `evidence/claims.jsonl`과 연결한다.
2. Claude가 계획을 1회 독립 검토한다.
3. Codex가 지적을 반영하고 Claude가 폐쇄 여부만 1회 확인한다.
4. 표본 규칙·자료원 우선순위·공개범위는 교수가 결정한다.
5. Codex가 수집기·정규화·검증기·테스트를 구현한다.
6. 모든 PR에서 pytest, compile, dry-run 예산 계산을 실행한다.
7. `ai-review` 라벨이 있는 PR의 구현을 Claude가 1회 검토한다.
8. 교수의 `kra-collection` environment 승인 뒤에만 수집한다.
9. 같은 `snapshot_id`의 페이지 ledger와 파일 해시가 맞으면 마지막 완료 `pageNo` 다음부터
   재개하며, 완료된 논리 요청은 매니페스트로 건너뛴다.
10. 수집 뒤 경주＋승식＋조합 business key 중복 0, key 합집합=`totalCount`, 다음 페이지 0행,
    원응답·정규화 해시를 재검사한다.
11. 매니페스트와 품질보고서는 별도 PR로 영구 보존하고 원응답은 라이선스 게이트
    전에는 Git에 넣지 않는다.
12. Claude가 매니페스트와 품질보고서만 읽어 산출물 검토를 1회 수행한다.
13. 라이선스·공개등급·main 병합·전 역사 확장은 교수가 승인한다.

모든 실제 호출은 UTC 일자별 quota ledger에 먼저 기록한다. 개발계정 공식 한도
3,000회의 5/6인 2,500회를 기본 운영상한으로 사용하며, preflight는 이미 쓴 호출,
자격·승인 probe, 예상 수집 호출과 운영일수를 함께 보고한다. 각 endpoint·pool probe의
실제 첫 행으로 business key alias를 계산할 수 있어야만 수집을 허용하고, 관측 alias,
business-key SHA-256, 원응답 SHA-256을 preflight 보고서에 남긴다.

원응답은 공개 Actions artifact에 올리지 않고 AES-256 대칭암호화해
`kra-private-archive` draft release에만 보존한다. secret scan이 실패한 실행도 같은
비공개 암호화 경로에 quarantine하며 공개 산출물은 만들지 않는다. 이 draft release는
공개해서는 안 된다. 수집 직후 `<snapshot>-run-<run_id>.tar.gz.gpg` 이름으로 중단
복구용 체크포인트와 당일 quota ledger를 먼저 저장하고, 같은 실행 ID의 scan JSON에
`interrupted`, `success`, `failure` 판정을 기록한다. `failure` quarantine은 수동 조사 전
자동 복원하지 않으며, `interrupted` 체크포인트는 다음 실행에서 복원한 뒤 다시 검사한다.
실행별 세대를 덮어쓰지 않으므로 업로드 실패가 직전의 정상 체크포인트를 지우지 않는다.

최초 실행 전 저장소에 두 Actions secret이 필요하다. `kra-collection` environment는
별도로 교수 승인 게이트를 제공한다.

```bash
gh secret set DATA_GO_KR_SERVICE_KEY --repo Joocheol/korea-horse-racing-data
openssl rand -base64 48 | gh secret set KRA_ARCHIVE_PASSPHRASE --repo Joocheol/korea-horse-racing-data
```

두 번째 명령은 새 암호를 생성해 GitHub로 바로 전달하므로 터미널 화면이나 셸 변수에
암호 원문을 남기지 않는다. 해당 암호를 잃으면 암호화 archive는 복원할 수 없다.

`core_transport_verified`는 10번의 전송·무결성 검사만 통과했다는 뜻이다.
API26 출주두수, API5×API29 복승, API214 착순, 환급률·오버라운드, 시행/시험 기록
분류가 아직 실행되지 않았다면 `pilot_promotion_ready=false`를 유지한다.
