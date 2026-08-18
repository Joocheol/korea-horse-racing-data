# Evidence registry

`claims.jsonl`은 `docs/API_FINDINGS.md`의 주요 실측 주장과 보존 원응답을 연결한다.
2026-08-18 사전조사 당시 원응답 해시가 보존됐는지 확인되지 않은 주장은 값을
추정해 채우지 않고 `reproduce_required=true`로 둔다. 파일럿 preflight와 수집에서
재현한 뒤 요청키·시각·원응답 SHA-256을 새 레코드로 추가한다.
