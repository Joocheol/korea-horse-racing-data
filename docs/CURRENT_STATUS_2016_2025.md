# 2016-2025 현재 보존·검증 상태

*확인일: 2026-08-22*

이 문서는 2016-2025년 10개년 KRA 공개 API 수집물의 현재 보존, 병합, 검증 상태를
요약한다. 2020·2021년은 이미 수집 완료된 GitHub Actions artifact를 사용하며,
재수집하지 않는다.

## 1. 범위

대상 API는 `API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API227`,
`API4_3`, `API5`이다.

| 연도 | 출처 | 상태 |
| --- | --- | --- |
| 2016, 2017, 2018, 2019 | backfill archive | 기술 감사 통과, Dropbox 업로드 성공 기록 존재 |
| 2020, 2021 | 기존 `kra-collection-state` artifact | 재수집 없이 기술 감사 통과, Dropbox 보존 재시도 성공 기록 존재 |
| 2022, 2023, 2024, 2025 | backfill archive | 기술 감사 통과, Dropbox 업로드 성공 기록 존재 |

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
- source digest: `sha256:f1136a397093e3d62594960d4047987de373af94d1d38fdf9a61fdccf8a0d4f5`
- archive run: `32559614706`
- Dropbox upload status: `success`
- 기술 감사: 2,913 / 2,913 complete, 오류 0건

이전 2020·2021 Dropbox 패키지 업로드 실패 원인은 Dropbox API header의 한글 경로
인코딩 오류(`UnicodeEncodeError`)였고, workflow의 `Dropbox-API-Arg` JSON 직렬화를
ASCII escaping 방식으로 고쳐 해결했다. 수정 commit은
`958ee92e761b16b7639a503d739b2010c7014f0f`이다.

직접 Dropbox 목록 조회에서는 `/앱/kra-data/raw`, `/앱/kra-data/normalized`,
`/앱/kra-data/manifests` 아래 기존 2020·2021 run folder와 분할 보존물
(`*.b64part`), `ledger.json`, `technical-audit.json`, `SHA256SUMS`가 확인된다.
새 archive run이 기록한 단일 `kra-*-2020-2021.tar.gz` 업로드는 GitHub 감사
JSON에는 성공으로 남아 있으나, 같은 Dropbox connector의 즉시 목록 조회에서는
별도 파일로 보이지 않았다. 따라서 Dropbox 상태는 감사 JSON의 성공 기록과 직접
목록 확인 결과를 함께 보존한다.

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

## 5. 경주 ID 정합성 점검

2020·2021 staged 파일에서 `(year, meet, rcDate, rcNo)` 기준 경주 ID를 만들고
핵심 경주 테이블을 대조했다. `meet`은 `서울/1`, `제주/2`, `부경/부산경남/3`으로
정규화했다.

핵심 경주 universe는 일치한다.

- `race_record`, `entries`, `results`: 각 41,749 rows
- unique race IDs: 3,659
- 핵심 3개 테이블 간 누락 race ID: 0건

승식·매출 API는 핵심 경주 universe와 coverage 차이가 남아 있다.

| 파일/계층 | rows | race IDs | race_record에 없는 race IDs | race_record 대비 누락 race IDs |
| --- | ---: | ---: | ---: | ---: |
| `single` | 83,973 | 3,719 | 60 | 0 |
| `double` | 675,081 | 3,719 | 60 | 0 |
| `quinella_crosscheck` | 222,490 | 3,718 | 59 | 0 |
| `sales` | 20,267 | 3,609 | 0 | 50 |
| `triple` | 3,529,911 | 2,438 | 55 | 1,276 |

이 coverage 차이는 현재 기준으로 재수집 실패로 분류하지 않는다. 2020·2021년은
코로나 중단과 비정상 개최일이 포함되므로, 승식별 제공 범위·취소·매출 존재 여부를
별도 의미 검증으로 분리해 설명해야 한다.

## 6. 현재 판정

기술적 보존과 ledger 기준 완전성은 2016-2025 전 기간에 대해 통과 상태다.
2020·2021은 기존 artifact를 사용했으며 재수집하지 않았다. 실패했던 Dropbox 업로드는
workflow 수정 뒤 성공 run을 남겼다.

다만 최종 연구용 완전성 판정은 아직 `완료`로 고정하지 않는다. 남은 작업은 경주 ID
coverage 차이를 승식별 제공 범위, 취소·중단, 매출 존재 여부와 대조하여 의미적으로
설명하는 것이다. 이 단계가 끝나야 2016-2025 전체 데이터셋을 기술·의미 양쪽에서
완전하다고 선언할 수 있다.
