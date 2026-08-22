# 2020-2021 의미 완전성 감사

*확인일: 2026-08-22*

이 문서는 기존 `kra-collection-state` artifact(run `32340684155`, artifact `9396629882`)를
재수집 없이 직접 분석하여, 2020·2021년 경주 ID coverage 차이가 수집 실패인지
원천 API의 제공 범위 차이인지 판정한다.

## 1. 기준 경주 universe

`race_record`, `entries`, `results`를 `(year, meet, rcDate, rcNo)`로 정규화해 대조했다.
`meet`은 서울=1, 제주=2, 부경/부산경남=3으로 통일했다.

- `race_record`: 41,749 rows, 3,659 unique race IDs
- `entries`: 41,749 rows, 3,659 unique race IDs
- `results`: 41,749 rows, 3,659 unique race IDs
- 세 핵심 테이블 간 race ID 차이: 0

따라서 실제 시행 경주의 기준 universe는 3,659경주로 고정한다.

## 2. 배당 API의 기준 universe 밖 기록

기준 경주 universe와 비교하면 다음과 같다.

- `single`: 기준 밖 race ID 60개, 기준 경주 누락 0개
- `double`: 기준 밖 race ID가 있으나 기준 경주 누락은 0개
- `quinella_crosscheck`: 기준 밖 race ID 59개, 기준 경주 누락 0개

`single`의 기준 밖 60개 race ID는 모두 `sales`가 0건이고, `race_record`, `entries`,
`results`에도 존재하지 않는다. 날짜별로는 2020-02-24 10개, 2020-05-07 22개,
2020-12-16 4개, 2021-09-09 21개, 2021-10-13 2개, 2021-11-27 1개다.

즉 이들은 실제 시행 경주를 놓친 것이 아니라 배당 계층에만 남은 비경주/예비·취소·시험성
기록으로 취급한다. 분석용 race universe에는 포함하지 않고 raw에는 그대로 보존한다.

## 3. triple 1,276경주 coverage 차이

`API30_1`(삼복승·삼쌍승)에는 기준 3,659경주 중 2,383경주가 존재하고 1,276경주가 없다.
이 차이는 무작위가 아니라 특정 시행 기간에 집중되어 있다.

핵심 검증은 `API179_1`의 실제 승식별 매출 행과의 대조다.

| triple API 상태 | 경주 수 | sales에 삼복/삼쌍 존재 | sales에 삼복/삼쌍 없음 |
| --- | ---: | ---: | ---: |
| triple 존재 | 2,383 | 2,360 | 23 |
| triple 없음 | 1,276 | 0 | 1,276 |

**triple API가 없는 1,276경주는 단 한 경주도 sales에 삼복·삼쌍 승식이 존재하지 않는다.**
그중 1,249경주는 `sales`에 단식·연식·복식만 있고, 27경주는 `sales` 행 자체가 없다.

반대로 triple API가 존재하는 경주 중 sales 행이 있는 2,360경주는 모두
단식·연식·복식·쌍식·복연·삼복·삼쌍 7개 승식이 확인된다.

예시:

- 2021-09-03: `sales`에 단식·연식·복식만 존재, triple API 없음
- 2021-09-10: `sales`에 7개 승식 모두 존재, triple API도 존재

따라서 1,276경주의 triple 부재는 **수집 실패가 아니라 당시 해당 승식이 판매되지 않은
경주의 원천 coverage 특성**으로 판정한다.

## 4. sales 50경주 부재

기준 3,659경주 중 `sales`는 3,609경주에 존재하고 50경주에는 행이 없다.
이 50경주는 `race_record`와 `results`가 존재하므로 실제 시행 경주다.

- 27경주: triple도 없음
- 23경주: triple은 존재

현재 artifact의 ledger 기준으로 `API179_1`의 모든 월·경마장 단위는
`totalCount = raw rows = unique rows`이고 중복 0이다. 따라서 이 50경주는
수집기의 누락으로 보지 않고 **원천 `API179_1`이 해당 경주에 매출 행을 반환하지 않은
source-level coverage gap**으로 분류한다.

연구용 데이터에서는 `sales_missing=true`로 다루고, 매출액을 0으로 임의 대체하지 않는다.

## 5. 최종 판정

2020·2021에 대해 다음을 동시에 확인했다.

1. 실제 시행 경주 universe는 `race_record = entries = results`로 3,659경주 완전 일치한다.
2. ledger 2,913개 논리 수집 단위는 모두 complete이고 오류 0이다.
3. 모든 group에서 `totalCount = raw rows = unique rows`, duplicate rows=0이다.
4. 배당 API의 기준 밖 기록은 실제 시행 경주 누락이 아니라 분석 universe 밖 기록이다.
5. triple의 1,276경주 부재는 해당 경주의 삼복·삼쌍 매출 부재와 정확히 대응한다.
6. sales의 50경주 부재는 수집 누락이 아니라 원천 API coverage gap으로 보존한다.

따라서 **2020·2021 수집본은 공개 API가 제공한 범위에 대해 기술적·의미적으로 완전한
수집본으로 판정한다.** 다만 `sales` 50경주처럼 원천 API 자체가 제공하지 않는 값까지
존재한다고 해석해서는 안 된다.

## 6. 2016-2025 전체 데이터셋에 대한 의미

2020·2021은 기존 artifact를 재사용했고 Dropbox archive run `32559614706`에서
raw/normalized/manifests/quarantine/docs 패키지 업로드 성공이 기록되어 있다.
나머지 8개년은 별도 backfill archive의 기술 감사와 Dropbox 보존 감사가 완료되어 있다.

이에 따라 2016-2025 10개년 데이터셋은 **KRA 공개 API 기준 수집·보존 작업 완료**로
판정할 수 있다. 이후 작업은 수집 자체가 아니라 연구용 통합 테이블 구축, 변수 정의,
source-level coverage flag 적용의 단계다.
