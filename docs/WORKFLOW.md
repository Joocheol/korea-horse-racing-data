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
9. 같은 `snapshot_id`의 기존 매니페스트와 파일 해시가 맞으면 완료 요청을 건너뛴다.
10. 수집 뒤 페이지 교집합 0, 중복제거 행 수=`totalCount`, 다음 페이지 0행,
    원응답·정규화 해시를 재검사한다.
11. 매니페스트와 품질보고서는 별도 PR로 영구 보존하고 원응답은 라이선스 게이트
    전에는 Git에 넣지 않는다.
12. Claude가 매니페스트와 품질보고서만 읽어 산출물 검토를 1회 수행한다.
13. 라이선스·공개등급·main 병합·전 역사 확장은 교수가 승인한다.

`core_transport_verified`는 10번의 전송·무결성 검사만 통과했다는 뜻이다.
API26 출주두수, API5×API29 복승, API214 착순, 환급률·오버라운드, 시행/시험 기록
분류가 아직 실행되지 않았다면 `pilot_promotion_ready=false`를 유지한다.
