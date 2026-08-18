# Evidence registry

`claims.jsonl`은 `docs/API_FINDINGS.md`의 주요 실측 주장과 보존 원응답을 연결한다.
2026-08-18 사전조사 당시 원응답 해시가 보존됐는지 확인되지 않은 주장은 값을
추정해 채우지 않고 `reproduce_required=true`로 둔다. 파일럿 preflight와 수집에서
재현한 뒤 요청키·시각·원응답 SHA-256을 새 레코드로 추가한다.

재현 레코드는 `status=verified`, `observed_at`, `run_id`, `endpoint_version`,
`request_key`, `raw_sha256`을 모두 가진다. 같은 `claim_id`의 새 레코드는
`supersedes`에 앞 레코드의 `(claim_id, observed_at)` 식별자를 기록한다. 유효 상태는
각 `claim_id`에서 `observed_at`이 가장 늦은 레코드이며, 동률이면 파일의 마지막
레코드다. 0행 주장은 성공 응답의 원문 해시와 HTTP 상태가 함께 있어야
`verified_empty`로 승격할 수 있다.
