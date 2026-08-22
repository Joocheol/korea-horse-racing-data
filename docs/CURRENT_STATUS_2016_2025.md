# 2016-2025 현재 보존·검증 상태

*확인일: 2026-08-22*

이 문서는 2016-2025년 10개년 KRA 공개 API 수집물의 현재 보존, 병합, 검증 상태를
요약한다. 2020·2021년은 이미 수집 완료된 GitHub Actions artifact를 사용했으며
재수집하지 않았다.

## 1. 범위

대상 API는 `API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API227`,
`API4_3`, `API5`이다.

| 연도 | 출처 | 상태 |
| --- | --- | --- |
| 2016, 2017, 2018, 2019 | backfill archive | 기술 감사 통과, Dropbox 업로드 성공 |
| 2020, 2021 | 기존 `kra-collection-state` artifact | 기술·의미 감사 통과, Dropbox 보존 성공 |
| 2022, 2023, 2024, 2025 | backfill archive | 기술 감사 통과, Dropbox 업로드 성공 |

총 논리 수집 단위는 8,123개다. 이 중 2016·2017·2018·2019·2022·2023·2024·2025
backfill 단위가 5,210개이고, 2020·2021 pilot 단위가 2,913개다.

## 2. 지속 보존 증거

2016·2017·2018·2019·2022·2023·2024·2025는
`docs/backfill-audit-2016-2025.json`에 보존 감사 결과가 남아 있다.

- archive run: `32553067249`
- source run: `32544887677`
- source status: `success`
- Dropbox upload status: `success`
- 기술 감사: 5,210 / 5,210 complete, 오류 0건

2020·2021은 `docs/pilot-audit-2020-2021.json`에 보존 감사 결과가 남아 있다.

- source artifact: `9396629882` (`kra-collection-state`)
- source run: `32340684155`
- archive run: `32559614706`
- Dropbox upload status: `success`
- 기술 감사: 2,913 / 2,913 complete, 오류 0건

Dropbox archive에는 2020·2021 `raw`, `normalized`, `manifests`, `quarantine`, `docs`
패키지와 SHA256 manifest의 업로드 성공 경로·크기·content hash·revision이 기록되어 있다.

## 3. 기술 감사 결과

전체 8,123개 논리 수집 단위는 감사 기준상 `complete`이다.

| 구간 | 논리 단위 | 완료 | 오류 |
| --- | ---: | ---: | ---: |
| 2016 | 653 | 653 | 0 |
| 2017 | 648 | 648 | 0 |
| 2018 | 648 | 648 | 0 |
| 2019 | 648 | 648 | 0 |
| 2020 | 1,458 | 1,458 | 0 |
| 2021 | 1,455 | 1,455 | 0 |
| 2022 | 648 | 648 | 0 |
| 2023 | 657 | 657 | 0 |
| 2024 | 654 | 654 | 0 |
| 2025 | 654 | 654 | 0 |

2020·2021 artifact의 ledger 재검산 결과, 모든 group에서
`totalCount = raw rows = unique rows`가 성립했고 중복 row는 0건이다.

| 연도 | 논리 단위 | totalCount | raw rows | unique rows | duplicate rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 1,458 | 1,450,364 | 1,450,364 | 1,450,364 | 0 |
| 2021 | 1,455 | 3,206,605 | 3,206,605 | 3,206,605 | 0 |

## 4. 2020·2021 API별 행 수 검산

| 연도 | API | 논리 단위 | totalCount/raw/unique rows | duplicate rows |
| --- | --- | ---: | ---: | ---: |
| 2020 | `API179_1` | 36 | 7,353 | 0 |
| 2020 | `API227` | 1,098 | 17,962 | 0 |
| 2020 | `API26_2` | 36 | 17,962 | 0 |
| 2020 | `API28_1` | 36 | 36,389 | 0 |
| 2020 | `API29_1` | 108 | 227,152 | 0 |
| 2020 | `API30_1` | 72 | 1,030,582 | 0 |
| 2020 | `API4_3` | 36 | 17,962 | 0 |
| 2020 | `API5` | 36 | 95,002 | 0 |
| 2021 | `API179_1` | 36 | 12,914 | 0 |
| 2021 | `API227` | 1,095 | 23,787 | 0 |
| 2021 | `API26_2` | 36 | 23,787 | 0 |
| 2021 | `API28_1` | 36 | 47,584 | 0 |
| 2021 | `API29_1` | 108 | 447,929 | 0 |
| 2021 | `API30_1` | 72 | 2,499,329 | 0 |
| 2021 | `API4_3` | 36 | 23,787 | 0 |
| 2021 | `API5` | 36 | 127,488 | 0 |

## 5. 경주 ID 의미 감사

세부 결과는 `docs/SEMANTIC_AUDIT_2020_2021.md`에 기록했다.

핵심 경주 universe는 일치한다.

- `race_record`, `entries`, `results`: 각 41,749 rows
- unique race IDs: 3,659
- 핵심 3개 테이블 간 누락 race ID: 0건

배당 계층에는 기준 경주 universe 밖 기록이 일부 존재하지만, 이들은 `sales`,
`entries`, `results`, `race_record`가 없는 비경주/예비·취소·시험성 기록이며 분석용
race universe에서 제외하고 raw에는 보존한다.

`triple`의 기준 경주 대비 1,276경주 부재는 수집 실패가 아니다. 이 1,276경주는
**전부 `sales`에 삼복·삼쌍 승식이 존재하지 않는다.** 그중 1,249경주는
단식·연식·복식만 판매된 것으로 나타나고, 27경주는 sales 행 자체가 없다.
반대로 triple이 존재하면서 sales가 있는 2,360경주는 7개 승식이 모두 확인된다.

`sales`는 실제 시행 3,659경주 중 3,609경주에 존재하고 50경주에는 없다. ledger상
`API179_1`의 해당 월·경마장 단위는 모두 `totalCount = raw = unique`이므로, 이 50경주는
수집 누락이 아니라 원천 API의 source-level coverage gap으로 분류한다. 연구용 자료에서는
0으로 대체하지 않고 `sales_missing`으로 표시한다.

## 6. 최종 판정

**2016-2025 KRA 공개 API 수집·보존 작업은 완료로 판정한다.**

근거는 다음과 같다.

- 10개년 8,123개 논리 수집 단위 전부 complete, 오류 0
- 2020·2021 모든 group에서 `totalCount = raw rows = unique rows`, 중복 0
- 실제 경주 핵심 universe 3개 테이블 완전 일치
- 2020·2021 triple coverage 차이는 판매 승식 범위 차이와 정확히 대응
- source-level coverage gap은 별도 flag 대상으로 분리
- 10개년 raw/normalized/manifests 계층의 Dropbox 보존 감사 성공 기록 존재

따라서 이후 단계는 **재수집이 아니라 연구용 10개년 통합 테이블 구축**이다.
원천 API가 제공하지 않은 값은 결측 flag를 유지하고, 비경주/시험성 기록은 raw에 보존하되
분석 universe에서는 제외한다.
