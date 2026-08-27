# API-only canonical 이관 — 2026-08-27

## 결론

2025-10-17 제주·부경의 기존 HTML backfill 3,866행과 공급기관이 복구한 API
3,866행은 자연키와 배당값이 전부 일치했다. 이를 근거로 HTML source 행을 폐기하고
API-only canonical 29,196,005행을 재빌드해 Dropbox에 원자적으로 승격했다.

## HTML–API 전수 대조

자연키는 `(race_id, pool_code, h1, h2, h3)`이다. QNL·QPL은 마번을 정렬하고 EXA는
순서를 보존했다. 배당은 10진수로 비교했다.

| 검증 항목 | 결과 |
| --- | ---: |
| HTML 고유 키 | 3,866 |
| API 고유 키 | 3,866 |
| 공통 키 | 3,866 |
| HTML에만 있는 키 | 0 |
| API에만 있는 키 | 0 |
| 배당값 불일치 | **0** |

HTML evidence SHA-256:
`4da85fae81b69d14e81373ecfecf78a69096b16a48db73bc306f8a978b0b0fd3`

## canonical 산식

```text
29,192,211  기존 API-only odds
      - 72  2023-03-17 실제 경주의 출전표 밖 행 제거
   + 3,866  2025-10-17 공급기관 복구 API 행 추가
-----------
29,196,005  최종 API-only canonical odds
```

2023년 비경주 9–12경주 128행은 `race_record` universe 밖이므로 기존과 마찬가지로
canonical에 들어오지 않는다. 2025년 16경주의 WIN·PLC·QNL·EXA·QPL coverage는
모두 `true`로 갱신했다.

## GitHub Actions 증거

| 항목 | 값 |
| --- | --- |
| run | `33032964636` |
| canonical artifact | `9631057131` |
| migration evidence | `9631057426` |
| Dropbox evidence | `9631069376` |
| job | `build-validate-publish: success` |

canonical artifact digest:
`sha256:19094bbba127d417e5c464561f46c76f7c98ef0422e940400f047710fd76df5f`

## Dropbox 승격 증거

canonical 경로는 `/앱/kra-data/research/2016-2025`이다. 새 bundle을 staging에
업로드한 뒤 8개 파일의 크기와 Dropbox content hash를 로컬 값과 대조하고, 기존
canonical을 backup으로 이동한 후 staging을 승격했다. 승격 후 canonical을 다시
조회해 동일성을 확인했다.

- `old_moved = true`
- `new_promoted = true`
- `canonical_verified = true`
- `rollback = null`
- `backup_cleanup = success`

최종 `odds.jsonl.gz`는 177,663,413 bytes이며 SHA-256은
`c0dee9784c1479f5bf73aee1b2211bcb3e4c06dde07cf4d6bd2d65d5980a0d22`다.
