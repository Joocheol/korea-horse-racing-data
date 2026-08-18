# KRA 공개 경마데이터 재수집 계획

## 1. 범위와 산출물

v1은 **2020-01-01~2021-12-31**의 KRA 경주를 처음부터 다시 수집해 공백을
복구한다. 다른 연도는 동일한 파이프라인을 쓰되 별도 릴리스로 다룬다. 수집의
정본은 공공데이터포털 KRA OpenAPI이며, API로 판정할 수 없는 필수 사실만 KRA
공식 사이트·공식 공고에서 보완한다.

수집 모집단과 분석 표본을 분리한다. 수집층에는 시행·무발매·불완전·증거부족
상태를 모두 1급 레코드로 공개하고, 분석층은 연구 질문별 포함·제외 규칙을 별도
버전으로 선언한다. 무발매나 증거부족 레코드를 조용히 삭제하지 않는다.

각 경주에 대해 다음을 서로 다른 변수로 기록한다.

- 예정 여부와 근거
- 실제 시행 여부와 근거
- 국내 승식별 매출 존재 여부
- 승식별 전체 조합격자 존재 여부
- 격자 값의 의미론: `unknown`, `prediction`, `final`

경주가 시행됐으나 국내 발매가 없었던 경우는 결측이나 수집 실패가 아니다.

## 2. 2026-08-18 동결 API 사양

실제 호출 근거의 정본은 `docs/API_FINDINGS.md`다. 저장소를 읽거나 검토할 때
README 요약만 사용하지 않고 이 파일을 명시적으로 먼저 읽는다.

Base URL은 `https://apis.data.go.kr/B551015`이다. 공통 파라미터 후보는 다음과
같다.

- `serviceKey`
- `pageNo`
- `numOfRows`: 100,000까지 실제 수용 확인; 실제 hard cap은 미확인
- `_type=json`
- `meet`: 1 서울, 2 제주, 3 부산경남, 4 영천
- `rc_date`: YYYYMMDD
- `rc_month`: YYYYMM
- `rc_no`
- `pool`: API29·API30에서 사용; endpoint별 `required|optional|prohibited`는 레지스트리로 고정

Decoding 서비스키를 HTTP 클라이언트가 한 번만 URL 인코딩한다. 최종 전송값은
Decoding 키의 1회 퍼센트 인코딩과 바이트 단위로 같아야 하고 `%25`가 없어야 하며,
키 안의 `+`, `/`, `=`는 각각 인코딩되어야 한다. Encoding 키를 다시 인코딩하는
경로는 테스트에서 실패시킨다.

### 2.1 배당 격자와 교차검증

| 자료 | 엔드포인트 | 승식 | v1 역할 |
|---|---|---|---|
| 단일마 격자 | `API28_1/singlePredictionRateInfo_1` | 단승·연승 | 실측 검증된 전체 조합 1차 수집원 |
| 두 마리 격자 | `API29_1/doublePredictionRateInfo_1` | EXA·QNL·QPL | 실측 검증된 전체 조합 1차 수집원 |
| 세 마리 격자 | `API30_1/triplePredictionRateInfo_1` | TLA·TRI | 실측 검증된 전체 조합 1차 수집원 |
| 복승 중복자료 | `API5/quinellaOddsInfo` | 복승 | 교차검증 |
| 종합 확정배당 | `API301/Dividend_rate_total` | 전체 승식 | 경로 확인 뒤 선택적 교차검증 |
| 경주일정 | `API72_2/racePlan_2` | 일정 | 경로 확인 뒤 독립 분모 우선후보 |

2026-08-18 실측에서 11두 API28 단일 호출은 단승 11+연승 11=22행, API29
단일 호출은 EXA 110+QNL 55+QPL 55=220행이었다. API30은 pool별 호출로 TLA
165행과 TRI 990행이었다. TRI는 10두 720행, 11두 990행, 12두
1,320행으로 전체 순서조합 수와 일치했고 `9999.9` 상한도 확인됐다. 2025-03-08
서울 복승은 취소마 제외 뒤 하루 520셀이 경주별 \(\sum\binom{n_r}{2}\)와
일치했다. 무작위 시드 20260818 복승 804셀의 API/HTML 소수점 값도 804/804
일치했다. 이 실측은 요청키·시각·원응답 해시와 함께 evidence 레지스트리에 둔다.

API28~30의 전체격자성은 `docs/API_FINDINGS.md`의 실측으로 검증됐다. 회귀검사에서는
각 `(endpoint, pool)`에서 서로 다른 출주두수 \(n\) 3개 이상에 대해 반환행 수와
이론 support를 대조하고 한 응답이 여러 pool을 함께 반환하는지 확인한다.
같은 과거 경주를 서로 다른 날짜에 두 번 받아 바이트 또는 정규화 값의 안정성도
확인하며 sentinel은 endpoint×pool별로 열거한다. 다만 operation명의
`PredictionRate`만으로 확정/예상을 단정하지 않는다. 조종 수집에서 같은 경주의
적중조합을 API179·API214 및 경로 확인 뒤 API301의 확정배당과 비교하고 응답의 시각·확정 플래그를
기록한 뒤 `odds_semantics`를 확정한다. 의미론이 다르면 수치 충돌이 아니라 별도
측정치로 보존한다. 충돌키는 `(경주키, 승식, 조합, 필드, 자료원,
source_observed_at)`이다.

### 2.2 부가자료

| 엔드포인트 | 수집 내용 |
|---|---|
| `API179_1/salesAndDividendRate_1` | 승식별 매출액 `amt`, 당첨조합, 확정배당; 통상 경주당 7행 |
| `API26_2/entrySheet_2` | 출전표와 등록두수 `dusu`; 하루 단위 응답 |
| `API214_1/RaceDetailResult_1` | 착순, 날씨, 주로, 단승·연승 배당 |
| `API4_3/raceResult_3` | 경주기록 |

2020·2021년 자료의 정상 반환은 존재 probe로 확인됐지만, 날짜·경주장·경주번호와
원응답 해시를 evidence 레지스트리에 남기기 전에는 전 기간·전 경주장에 일반화하지
않는다.

### 2.3 엔드포인트 레지스트리

수집 전에 `config/endpoints.yml`에서 각 operation을 다음 스키마로 동결한다.

```yaml
service: API30_1
operation: triplePredictionRateInfo_1
supported_grains: [month, date, race]
collection_grain: month
required_params: [meet, rc_month, pool, pageNo, numOfRows, _type]
optional_params: [rc_date, rc_no]
response_root: response.body.items.item
success_codes: ["00", "0000"]
pagination: {page: pageNo, size: numOfRows, total: totalCount, tested_size: 100000, page_size: 100000}
expected_pages: ceil(totalCount / page_size)
response_format: json
pool_param: required
market_field: pool
market_codes: {TLA: trio_unordered, TRI: trifecta_ordered}
comparison_rules: {odds_abs_tolerance: "verify_in_pilot", version: v1}
```

위 값은 예시이며, 각 엔드포인트의 필수·선택 파라미터, 날짜/월/경주 입도,
응답 루트, 성공코드, 코드사전과 실제 서버 상한을 조종 단계에서 실측해 확정한다.
서비스명과 operation의 `_1` 접미사도 문자 그대로 저장한다. `response_format`은
endpoint별 실제 JSON 또는 XML로 동결하며 해당 parser와 schema를 연결한다.
재개키는 `(snapshot_id, endpoint_id, canonical_params_without_serviceKey, pageNo)`이고
`canonical_params_without_serviceKey`의 SHA-256만 무결성 필드로 둔다. 경주 단위
요청에는 `rc_no`가 반드시 포함된다.

## 3. 자료원 우선순위와 독립 분모

1. API72 실제 경로를 먼저 확인하고, 가능하면 일정 분모로 수집한다.
2. API72가 없거나 불완전하면 API26의 하루 단위 개최정보를 사용하고 KRA 공식
   시행계획·변경/취소·발매중지 공고로 날짜×경주장의 열거 분모를 보완한다.
3. API26·API214·API4로 경주 목록과 실제 시행 여부를 구축한다.
4. API179로 국내 발매와 승식별 매출 존재를 판정한다.
5. API28·API29·API30으로 전체 조합격자를 월×경주장×pool 우선으로 수집한다.
6. API5·API179·API214와 적중조합 정보를 교차검증하고 API301은 경로 확인 뒤 추가한다.
7. 필수 사실이 관련 API에서 실제 누락된 경우에만 KRA 사이트를 조회한다.

API72와 공식 공고는 배당 정본이 아니라 API 결측을 탐지하기 위한 독립적인 열거
분모다. 조종 시작 전 API72 경로와 2020·2021년 각 경주장의 공고 URL·검색 가능 여부를
확인한다. 공고를 찾지 못한 범위도 수집은 계속하되 `universe_quality=api_only`로
표시하고 Release에 완전성 보장이 약함을 명시한다. 공고 분모가 있으면
`universe_quality=independent_official`이다. 제3자 자료는 정본으로 사용하지 않는다.
공식 자료끼리 충돌하면 어느 한쪽도 덮어쓰지 않고 원문·시점·충돌상태를 보존한다.

`meet=4` 영천은 API 문서 코드 레지스트리에는 보존하되 2019~2026년 다섯 API
(API28·API29·API30·API179·API26) 모두 `totalCount=0`이었다. 2020·2021년 활성
경주장이라고 가정하지 않으며, 공식 일정 또는 API 경주
존재가 확인될 때만 해당 기간의 분모에 넣는다. 그 전에는
`inactive_or_unverified`다.

## 4. 상태모형과 증거

서로 다른 grain을 하나의 enum에 섞지 않는다.

| 축 | grain | 값 |
|---|---|---|
| 시행상태 | `(rc_date, meet, rc_no)` | `scheduled`, `not_held`, `held`, `evidence_insufficient` |
| 시장상태 | `(race_key, pool)` | `no_domestic_market`, `market_complete`, `api_incomplete`, `evidence_insufficient` |
| 자료충돌 | `(race_key, pool, combination, field, source, source_observed_at)` | `has_source_conflict` + 상세 레코드 |
| 요청상태 | `(snapshot_id, endpoint, params, page)` | `success`, `retryable`, `unresolved_transport` |

자료충돌과 요청오류는 시행·시장상태와 동시에 존재할 수 있다. 수치 비교 허용오차와
반올림 규칙은 필드별로 `config/comparison-rules.yml`에 버전 고정한다.

시행상태는 경주 grain의 다음 evidence ladder로 판정한다. 날짜 단위 신호는 경주
후보를 찾는 집계 보조일 뿐 시행상태를 직접 결정하지 않는다.

| 코드 | 경주 grain 증거 | 시행상태 |
|---|---|---|
| `R1_RESULT_ORDER` | API214/API4의 해당 `race_key` 착순 또는 공식 결과 존재 | `held` |
| `R2_OFFICIAL_HELD_NOTICE` | 공식 공고가 시행을 명시 | `held` |
| `R3_OFFICIAL_CANCEL_NOTICE` | 공식 공고가 취소를 명시하고 착순 없음 | `not_held` |
| `R4_PRESTART_CANCEL` | 발주 전 취소 플래그와 착순 없음 | `not_held` |
| `R5_POST_BET_CANCEL_REFUND` | `amt>0`, 착순 없음, 공식 취소·반환 근거 | `not_held` + `betting_opened_then_cancelled=true` |
| `R6_CONFLICT_OR_ABSENCE` | 위 조건이 성립하지 않거나 증거 충돌 | `evidence_insufficient` |

R5는 시행되지 않은 경주로 분모에서 제외하되, 이미 시장이 열렸던 사실·매출·반환은
별도 시장 예외 레코드로 보존한다. 취소/제외 필드가 없는 경우 추정하지 않고 R6다.

시장 evidence는 다음 코드로 저장한다.

| 코드 | 증거 |
|---|---|
| `E1_NOTICE_NO_SALE` | 공식 공고가 해당 경주/승식의 국내 무발매를 명시 |
| `E2_TURNOVER_ZERO` | 정산된 경주의 API179 해당 pool 행이 있고 `amt=0` |
| `E3_POOL_ROW_ABSENT` | 같은 경주의 sibling pool 행은 정상인데 해당 pool 행만 없음 |
| `E4_TURNOVER_POSITIVE` | API179 해당 pool 행의 `amt>0` |
| `E5_REFUND_OR_NO_WINNER` | 발매는 있었으나 반환 또는 적중자 없음이 공식 필드로 확인됨 |
| `E6_HELD_ALL_POOLS_ABSENT` | API214/API4로 시행은 확인됐으나 정산된 월의 모든 API179 pool 행이 없음 |

규칙 v1에서 E1 또는 E2는 `no_domestic_market`의 충분증거다. E3·E6 단독은 API
누락을 배제할 수 없어 `evidence_insufficient`다. E4·E5는 시장이 존재한 것이므로
무발매가 아니다. preflight는 E6 경주 수와 전체 시행경주 대비 비율을 연도·경주장별로
보고한다.

E6는 조건부 사이트 조회의 시행·발매 분모 게이트를 자동 생성한다. 2020·2021년
공식 무관중·발매중지 기간을 공고에서 먼저 열거하고 E6와 결합한다. E1을 찾은 E6는
`no_domestic_market`, 찾지 못한 E6는 `evidence_insufficient`로 남으며 분석표본에서는
기본 제외한다.
HTTP 2xx, 0행, API179 행 부재만으로 무발매를 선언하지 않는다. 판정 결과에는
evidence 코드와 규칙 버전을 함께 저장한다.

## 5. 수집 단계

### 5.1 경주 인벤토리

1. API72, API26 하루 정보, 공식 시행계획·변경 공고를 우선순위에 따라
   날짜×경주장 분모로 동결한다.
2. 날짜×경주장별 API26·API214·API4 자료를 수집한다.
3. `(rc_date, meet, rc_no)` 경주키를 정규화한다.
4. 등록·출전예정·발주·발매전취소·발매후제외·실격·낙마·중지를 별도 플래그로 둔다.
5. API179로 승식별 매출행과 `amt`를 확인한다.
6. 날짜별 `has_positive_turnover`, `has_result_order`, `has_entry_sheet`,
   `has_all_expected_markets`, `listed_in_official_calendar`를 만든다. 양수 매출과
   착순이 모두 있으면 요일과 무관하게 실제 경주다. 착순은 있으나 매출이 전부
   없는 COVID 후보는 시행경주로 보존하고 E6로 시장상태를 따로 판정한다.
7. 매출·착순이 모두 없거나 신호가 서로 모순되는 소규모 기록만
   `calendar_anomaly` 후보로 격리한다. 요일은 `weekday_flag` 참고값일 뿐 자동
   제외·격리 조건으로 사용하지 않는다.
8. 연도×월×경주장×시장상태별 경주 수를 동결한다.

`started_set`은 착순 유무가 아니라 발주 참가를 나타내는 공식 필드로 정의한다.
실격·낙마·경주중지는 발주했다면 제외하지 않는다. 사용할 필드와 코드의 실제
의미는 엔드포인트 레지스트리에 근거와 함께 고정한다.

격리 레코드는 삭제하지 않고 원자료·다섯 신호·판정 근거·규칙 버전과 함께
`quarantine/calendar-anomalies.parquet`에 보존한다. 2016년 7개 의심 개최일은
매출·착순·출전표 0과 불완전 승식으로 시험 기록임이 3차 조사에서 확인됐다.
2009-03-11·2009-04-01·2007-01-09는 같은 패턴이지만 직접 확인 전까지
`suspected_test_record`로 둔다. 분석표본에서는 기본 제외하되
추가 매출·착순·공식 일정 근거가 생기면 새 규칙 버전에서 재분류한다.

### 5.2 조종 수집

각 연도×경주장의 첫·마지막 날짜와 최소 2개 발매일을 포함하고 다음 층을 의도적으로
표집한다.

- 발매·무발매·증거부족
- 발매전취소·발매후제외·실격·낙마
- 소두수·중간·대두수 경주와 승식 미제공 사례
- `9999.9`, 0, null, 조합행 부재 사례
- API28~30 적중조합과 확정배당 자료의 비교 가능 사례
- 100,000행을 넘는 월 격자: 2025-03 서울 TRI `totalCount=115,356`

2019년 말과 2022년 초의 기존 아카이브 표본도 참고 비교하되, 해당 아카이브는
개최일 누락 전수감사가 끝나지 않았으므로 검증 정답으로 쓰지 않는다. 조종 종료 전
다음을 확정한다.

- API28~30 격자의 시점 의미와 0표 조합 표현 방식
- `numOfRows` 1·100·1,000·3,000·100,000 결과 합집합의 동일성
- 2025-03 서울 TRI 월 응답으로 100,000행 경계의 다중 페이지 동작과
  `totalCount=115,356` 재현
- 엔드포인트별 실제 HTTP 상태, content-type, 성공·인증오류·점검·쿼터 코드
- API179가 지원하는 최대 query grain과 필수 파라미터
- API72와 API301의 실제 서비스/operation 경로; API72가 확인되면 웹 공고보다 우선
- API214 또는 API4에서 취소·제외를 독립 판정할 필드와 실제 취소 경주 1건의 재현;
  찾지 못하면 해당 경주의 support 검사를 `non_independent`로 표시
- 일일 한도의 적용 단위와 호출예산 계수

한도초과를 만들기 위해 운영 키의 쿼터를 고의 소진하지 않는다. 공식 오류규격,
기존 오류 fixture 또는 격리된 최소 요청으로 확인하고 미확인 항목은 미확인으로
남긴다.

### 5.3 응답 봉투와 페이지네이션

정상 응답은 다음 네 조건을 모두 만족해야 한다.

1. HTTP 2xx
2. 레지스트리의 `response_format`과 일치하는 content-type 및 파싱 가능한 본문
3. 레지스트리의 성공 `resultCode`
4. 엔드포인트 스키마 검증 통과

HTTP 200의 한도초과·키 오류·점검 코드, JSON으로 선언된 endpoint의 XML 오류,
HTML 오류와 스키마 불일치는 0행으로 바꾸지 않고 `unresolved_transport` 경로로
보낸다. XML-only endpoint는 XML parser와 schema를 가진 정상 자료원으로 취급한다.
재시도 가능 코드와 즉시 중단할 인증오류는 레지스트리에서 구분한다.

페이지별 원응답을 저장하며 다음을 검사한다.

- 모든 페이지의 `totalCount`가 동일함; 변하면 요청 전체를 새 스냅샷으로 재수집
- 실제 반환 행 수와 페이지 번호로 진행하고 같은 요청키의 페이지 교집합이 0건임
- 합집합 행 수가 `totalCount`와 같고 정규화키 중복이 0건임
- 계산된 마지막 페이지 다음 한 페이지가 정상 0행임

support 완전성은 단일 페이지가 아니라 모든 페이지를 중복제거한 합집합에서
`(race, pool)`별로 계산한다.

### 5.4 조합 support

격자 행에는 승식·조합·배당·경주키가 있어야 하고 조합 안에 같은 마번이 반복되면
안 된다. 이론 support의 기준 집합은 각 경주·`odds_observed_at` 시점의 취소/제외 플래그로
계산하는 함수다. 조종에서 확인한 API 격자 생성 규칙과 함수 버전을 함께 저장한다.

| 승식 | 이론 support |
|---|---:|
| 단승·연승 | 각 \(n\) |
| 복승·복연승 | 각 \(\binom{n}{2}\) |
| 쌍승 | \(n(n-1)\) |
| 삼복승 | \(\binom{n}{3}\) |
| 삼쌍승 | \(n(n-1)(n-2)\) |

승식 제공 여부는 두수만으로 추정하지 않고 API179의 승식행·매출과 공식 규칙으로
판정한다. 발매전취소와 발매후제외에 대해 영향 조합이 `present`,
`present_with_refund`, `absent` 중 무엇인지 `config/support-rules.yml`에 조종 종료
전에 확정한다. 연승 지급두수, 복연승 제공과 같은 field-size regime도 경주별
변수로 둔다.
API28·29·30의 기본 완전성 불변식은
`observed_support = theoretical_support`다. 2026-08-18 실측은 상한 셀을 포함한
전체 조합행이 반환됨을 확인했으므로 shortfall은 수집 결함으로 조사한다. `⊆`는
발매후제외 등 조종에서 근거가 확인된 `(race, pool, snapshot_id)` 예외에만 허용하고,
예외코드·근거·누락조합을 품질보고서에 기록한다.

### 5.5 매출·환급률·검열·충돌 검증

- API179의 승식별 매출과 격자 존재를 대조한다.
- 실제 적중조합이 전체 격자에 존재하는지 확인한다.
- 동일 의미론·시점의 미검열 적중배당은 API179·API214와 비교하고 API301은 실제
  경로 확인 뒤 선택적으로 추가한다.
- 정상값, 상한검열 `9999.9`, 0, null, 행 부재를 별도 sentinel로 저장하고 조종에서
  의미를 확정한다.
- 배당에서 마권수를 역산할 때 모든 값은 절사·반올림·최저배당 때문에 구간추정으로
  취급한다. `9999.9`는 실제값이 아닌 상한 sentinel이며 식별 가능한 경계만 보고한다.
- `(race, pool, snapshot_id)`별 `censored_count`와 `censored_fraction`을 정규화 표와
  품질보고서에 내고, `analysis-rules`가 검열 처리방법을 반드시 선언하게 한다.
- `(race, pool)`별 오버라운드 \(\sum(1/O)\)를 적용 환급률과 대조한다. `9999.9`
  검열셀 때문에 정확한 등식이 불가능한 경우 검열이 만드는 상·하한을 계산한 bounded
  check로 보고하고 범위를 벗어날 때만 실패시킨다.

환급률 메타데이터는 `(승식, 적용시작일, 적용종료일, 값, 공식 근거문서 식별자,
확인일, 반환 차감 전후 기준, 절사단위, 최저배당)`로 저장한다. 역산 검사는 계획
본문의 상수를 쓰지 않고 `(pool, race_date)`에 적용되는 검증된 메타데이터 행을
읽는다. 해당 행이 없으면 실패가 아니라 `rate_unverified`로 중단하며, 최저배당
구속·반환·절사 사례는 예외 플래그로 남긴다.

환급률·절사·최저배당 규정은 공식 경마시행규정·고시에서 수집한다. 문서 식별자,
적용기간, URL, 조회일과 이용조건을 `config/takeout-rules.yml`에 기록하며,
`docs/API_FINDINGS.md`의 실측 역산값은 규정값을 대체하지 않고 회귀검증에만 쓴다.

### 5.6 조건부 KRA 사이트 조회

다음 네 게이트 중 하나를 만족할 때만 공식 사이트를 조회한다.

- 시행·발매 분모 게이트: 공식 API만으로 예정/시행/발매 여부를 판정할 수 없음
- 자료 보완 게이트: 시행과 양수 매출은 확인됐으나 관련 API가 필수 필드를 완전하게
  제공하지 않고, 서로 다른 시점의 재조회로 일시 장애가 아님
- 분모 구축 게이트: 2020·2021 공식 시행계획·변경·취소·발매중지 공고의 URL과
  검색 가능 여부를 확인함
- 규정 메타데이터 게이트: 2020·2021 승식별 환급률·반환·절사·최저배당의 공식
  규정 문서와 적용기간을 확인함

조회 전에 robots 정책과 해당 페이지 이용조건을 기록한다. 차단·인증을 우회하지
않고, 식별 가능한 User-Agent, 동시 1개, 요청 간 최소 2초, 초기 상한 100회/일을
적용하며 403·429에는 중단한다. 분모 공고는 조종에서 실제 URL 수를 센 뒤 별도
요청예산을 배정하고 100회/일 상한 안에서 수집한다. 전체 URL 대신 비밀값을 뺀
정규화 파라미터와
파라미터 해시, 조회시각, 응답상태, 원문 SHA-256을 기록한다.

이용조건이 확인되지 않은 HTML·PDF·이미지는 비공개 격리 저장소에서 최대 90일만
보존하고 공개하지 않는다. 확인 뒤 허용된 원문만 공개하며, 그렇지 않으면 검증된
사실값·provenance·추출 규칙만 유지하고 원문은 보존기간 종료 뒤 폐기한다.

### 5.7 수집기 필수 요구사항

수집 구현을 시작하기 전에 `docs/API_FINDINGS.md` 10절의 체크리스트를 다음의
실행 가능한 테스트·완료 게이트로 옮긴다.

1. 경주별 행 수가 승식별 이론 조합 수 \(n\), \(n(n-1)\),
   \(\binom{n}{2}\), \(\binom{n}{3}\), \(n(n-1)(n-2)\)와 일치함
2. 출주두수를 API26의 `dusu`와 취소마 정보로 독립 산출함
3. 복승을 API5와 API29 양쪽에서 받아 셀 단위 대조함
4. 승식별 오버라운드 \(\sum(1/O)\)가 적용 환급률과 정합함
5. 매출액에서 역산한 마권 수의 정수·절사 허용구간 검사를 통과함
6. 개최일을 매출액·착순 존재로 판별하고 요일을 판정식에 사용하지 않음
7. 일부 승식만 존재하는 날짜에 승식 불완전 플래그를 남김
8. 걸러낸 날짜를 삭제하지 않고 격리표에 보존함
9. 월×경주장×endpoint×pool `totalCount`를 매니페스트에 저장해 재수집 때 대조함
10. 모든 보존 원응답의 바이트와 SHA-256이 일치함

각 항목은 테스트 ID, 입력 fixture, 합격조건과 실패 시 상태를 가져야 하며 10개가
모두 구현되기 전에는 조종 수집을 본수집으로 승격하지 않는다.

## 6. 호출예산, 오류처리와 재시작

- 개발계정 실측 한도: API179 일일 3,000회, 나머지 필수 API는 각각 일일 10,000회
- 운영단계 상향은 심의승인이며 자동 전환으로 가정하지 않음
- endpoint별 운영 상한은 공식 한도의 5/6이며 나머지 1/6을 재시도·검증에 유보
- 최대 동시 요청 2개
- 성공 원응답 저장 뒤에만 ledger 완료 처리
- HTTP 429·5xx·timeout과 레지스트리의 재시도 가능 본문코드는 지수형 재시도하고
  `Retry-After`를 지킨다.
- 인증·스키마 오류는 무한 재시도하지 않고 중단한다.

v1 총호출은 인벤토리 뒤 endpoint별 벡터로 동결한다.

\[
C_e = C_{calendar,e}+\sum_{g\in grain(e)}\sum_{p\in pools(e)}P_{e,g,p}
+C_{pilot,e}+C_{crosscheck,e}
+C_{retry,e}
\]

`grain(e)`는 레지스트리의 day/month/race 입도이고 `pools(e)`는 endpoint가 단일
호출에서 multiplex하는 pool 집합 또는 pool별 요청 집합이다. 각 \(P\)는 실제 페이지
수다. API5·72·301, 오류 확인과 다음 빈 페이지도 포함한다. API72·301은 경로가 확인될 때만
예산에 넣는다. 재시도 예산은 quota unit별
1/6 유보분 하나로만 계산해 이중 예약하지 않는다. 예상 최소 운영일은 quota unit
각각의 `ceil(C_e / operating_cap_e)` 중 최댓값이다. 조종에서 필수 8개 endpoint가
현재 키에 각각 승인돼 있는지도 확인한다. `docs/API_FINDINGS.md`의 전 역사 약
3,700회는 비교 기준일 뿐이고 v1은 2020·2021 범위만 별도 계산한다. 경주 수,
엔드포인트별 페이지 분포, `C`, 예상 운영일과 저장용량을 승인 가능한 preflight
보고서로 만들기 전에는 본수집을 시작하지 않는다. 전 기간 재수집은 v1 예산에
포함하지 않는다.

preflight에는 endpoint별 계정 tier, 현재 승인상태, 운영단계 심의 예상 lead time을
포함한다. 상향승인이 일정 전에 나오지 않으면 개발계정 한도를 넘기지 않고
`ceil(C_e / operating_cap_e)`만큼 경과일을 늘린다. 승인 미획득을 실패나 무발매로
분류하지 않는다.

저장된 요청의 재개키는 `(snapshot_id, endpoint_id,
canonical_params_without_serviceKey, pageNo)`다. 같은 키의 완료 ledger가 있고 저장된
원문이 존재하며 그 바이트 해시가 ledger 값과 일치할 때만 네트워크 호출을
건너뛴다. 공식 정정·심판변경, 스키마 버전 변경, 명시적 재수집, 수집 중
`totalCount` 변경은 새 `snapshot_id`를 발급하는 트리거다.

파라미터 무결성 해시도 `canonical_params_without_serviceKey`로만 계산한다. 비밀
키의 원문·해시·파생값은 어떤 저장·공개 산출물에도 넣지 않고, 키 교체 추적이
필요하면 비밀과 무관한 `key_id`만 별도 저장한다.

## 7. 저장, 무결성과 공개

### 7.1 GitHub 저장소

코드·설정·테스트·계획·매니페스트·보고서만 Git에 버전관리한다.

```text
src/                    수집·정규화·검증 코드
config/                 엔드포인트·오류코드·스키마·support 규칙
tests/                  단위·속성·회귀테스트와 비밀누출 테스트
plans/                  동결 계획
manifests/              파일·행·호출·개별 원응답 체크섬 목록
reports/                품질·누락·충돌·preflight 보고서
evidence/               실측·판정근거 레지스트리와 reproduce_required 상태
quarantine/             삭제하지 않는 시험·이상 개최일 정규화 표
```

### 7.2 공개 Release 자산

```text
raw-openapi-YYYY-vN.tar.zst       공개가능한 verbatim 성공 API 응답 body
normalized-YYYY-vN.parquet        정규화 표
manifest-YYYY-vN.json             요청키·개별 원응답 SHA-256·행·스키마·provenance·삭제기록
SHA256SUMS                         배포파일 전송 무결성용 해시
DATA-LICENSE-YYYY-vN.txt          해당 파티션의 적용 이용조건·출처
analysis-rules-YYYY-vN.yml        분석표본 포함·제외 규칙
evidence-YYYY-vN.parquet          상태·실측 evidence 레지스트리
quarantine-YYYY-vN.parquet        시험·이상 개최일과 제외 근거
```

정본 무결성은 매니페스트의 `request_key → raw byte SHA-256`이다. 아카이브 해시는
전송 편의용이다. tar는 경로 정렬, 고정 mtime, uid/gid 0과 정규화 권한을 사용하고,
zstd 버전·레벨과 생성 명령을 매니페스트에 기록한다.

매니페스트에는 `(year_month, meet, endpoint, pool)`별 `totalCount`, 페이지 수와
정규화 행 수도 넣어 이번 v1을 이후 재수집의 고정 기준선으로 만든다. 파티션별로
`collection_method`와 `completeness_audit_status`를 기록한다. 2020·2021 API 수집은
`openapi_monthly`; 기존 2019·2022 아카이브 비교는 날짜단위 누락감사가 끝나지 않은
`legacy_archive_partially_audited`로 표시해 경계 비교의 정답으로 사용하지 않는다.

evidence와 quarantine은 라이선스가 확인된 사실값·provenance만 공개 Release에
포함한다. 재배포 권리가 없는 웹 원문은 연결하지 않고 비공개 격리 규칙을 따른다.
2026-08-18 사전 실측 중 당시 원응답 보존이 문서로 확인되지 않은 항목은 임의 해시를
채우지 않고 `reproduce_required=true`로 등록하며, 조종에서 재호출한 원응답은
`rerun_at`과 새 해시를 별도로 기록한 뒤 레지스트리를 동결한다.

원응답은 append-only다. 정정 때 새 스냅샷을 추가하고 이전 판을 삭제하지 않으며,
릴리스 매니페스트에 `supersedes` 관계와 재수집 사유를 둔다. 단, 공개 권리가 없는
KRA 웹 원문은 이 append-only 공개 규칙의 대상이 아니다.

매니페스트에는 `code_commit`, `config_hash`, `rules_version`도 둔다. API 응답 body는
서버가 보낸 바이트를 변경하지 않고 해시한다. 요청 URL·헤더·로그에는 serviceKey를
저장하지 않는다. body에 비밀값이 탐지되면 원본은 비공개 격리하고
`redacted=true`, 원본/공개본 해시를 함께 기록한 파생본만 공개한다. 따라서 해당
레코드는 verbatim 공개 주장에 포함하지 않는다. 공개 전 커밋 이력과 모든 Release
자산을 비밀문자열 스캔한다. 로컬 경로·Dropbox 경로·Secret은 공개하지 않는다.

## 8. 라이선스·출처 게이트

코드는 MIT License다. 데이터는 프로젝트가 임의로 일괄 재라이선스하지 않고,
각 원자료의 공식 이용허락범위와 출처표시 조건을 승계한다. 연도 파티션에 기여한
모든 엔드포인트에 대해 `(endpoint, portal use scope, 공공누리/출처표시 유형,
bulk raw 재배포, normalized facts 재배포, 확인일, terms hash, 다음 확인일,
catalog URL)`이 확인되고 허용돼야 공개한다. 하나라도 미확인이면 그 source에
의존한 레코드를 공개에서 보류한다. source를 뺄 수 있는 파생상태는 나머지
evidence만으로 다시 계산하고 불충분하면 `evidence_insufficient`로 강등한다.
재계산할 수 없는 경우 파티션을 보류한다.

각 Release의 `DATA-LICENSE`에 가장 제한적인 적용조건, KRA·공공데이터포털 출처,
확인일과 카탈로그 URL을 기록한다. KRA 웹 원문은 별도 허용이 확인되기 전 공개
Release에서 제외한다.

공개 등급은 두 가지다. 같은 OpenAPI 게시 경로 밖의 공식 시행계획·변경·취소·발매
중지 공고로 일정 분모를 확인한 파티션만 `final`이다. API72와 API26은 효율적인
열거원이나 같은 OpenAPI 계열이므로 개최일 통누락에 대한 독립 분모로 인정하지
않는다. API72·API26만 확보한 파티션은 `provisional_api_only`로만 공개하며,
매니페스트와 DATA-LICENSE 첫머리에 “개최일 통누락을 독립적으로 탐지할 수 없음”을
표시한다. 이후 외부 공고 분모가 확인되면 새 final 릴리스가 provisional을
`supersedes`한다. API72 경로가 끝내 미확인이어도 API26+공고 경로로 수집은 진행한다.

bulk raw 재배포 권리만 미확인이고 normalized facts 재배포는 확인된 경우에는
정규화 표·매니페스트·보고서만 공개할 수 있다. 필수 source의 normalized facts
재배포 권리가 미확인이면 해당 레코드 또는 파티션 공개를 보류한다.

## 9. 품질보증과 완료 기준

다음을 모두 만족해야 연도 파티션을 공개한다.

1. 선택된 열거 분모의 모든 대상에 시행상태·evidence·provenance가 있고 API-only
   범위는 `provisional_api_only`로만 공개됨
2. 양수 매출 승식에 검증된 support 규칙상의 완전한 격자 또는 명시적 예외가 있음
3. `(race, pool)`별 E1~E6 evidence와 규칙 버전으로 무발매·증거부족을 재현할 수
   있고 요청오류는 별도 request grain에 있음
4. 성공 봉투, 원응답 행 수, 정규화 행 수와 매니페스트 행 수가 일치함
5. 경주·조합키 중복은 0건이며 자료원 충돌은 field별 허용오차·규칙 버전과 함께
   조합 grain 충돌표에 보존됨
6. 취소·제외·실격·낙마 규칙과 support 검사가 일치함
7. API179와 배당 API의 시장 존재 판정이 일치하거나 충돌표에 남음
8. `9999.9`·0·null·행 부재 sentinel이 구별됨
9. 모든 보존 원응답과 공개 자산의 SHA-256 검증이 통과하고, 폐기한 비공개 웹
   원문은 해시·provenance·폐기일이 매니페스트에 남음
10. 네트워크 없는 한 명령으로 정규화·품질보고서가 재생성됨
11. 2020·2021년과 정상연도의 제도 차이가 데이터 변수로 보존됨
12. 기여한 모든 엔드포인트의 재배포 조건이 확인됨
13. 공개 커밋·로그·매니페스트·Release의 비밀문자열 스캔이 통과함
14. 수집 모집단과 분석 표본의 포함·제외 규칙이 별도 산출물로 존재함
15. Claude Opus 5의 필수 지적이 해결되거나 저자결정으로 명시됨
16. 월×경주장×endpoint×pool `totalCount`와 파티션 수집방법·감사상태가 매니페스트에 있음
17. API5와 API29 복승 셀의 조합·배당이 허용오차 안에서 일치하거나 충돌표에 있음
18. 승식별 오버라운드 bounded check가 적용 환급률 메타데이터와 정합함

## 10. Claude 독립검토

검토 모델은 `claude-opus-5`이며 총 검토예산은 계획 2회·구현 1회·산출물 1회로
나눈다. 실패한 Actions 실행은 횟수에 포함하지 않는다.

- 계획 1회차: API 사양·경주 우주·발매/무발매·공개범위의 독립 검토
- 계획 2회차: 1회차 미해결 지적의 폐쇄 여부와 회귀만 검토
- 구현 1회: `src/`·`tests/`·수집/CI workflow의 실제 동작 검토
- 산출물 1회: 매니페스트·품질보고서·evidence만 읽고 실제 검증범위를 판정

Claude는 파일 수정·커밋·병합을 하지 않는다. HIGH 지적은 status check를 실패시키며,
수정하지 않고 수용하려면 교수의 명시적 저자결정을 PR에 기록한다. 수집은 push로
시작하지 않고 `workflow_dispatch`와 `kra-collection` environment 승인 뒤에만
실행한다. `core_transport_verified`는 파일전송·페이지네이션·해시 검증만 통과했다는
뜻이며, 9절 전체가 통과하기 전에는 파일럿 완료나 공개 준비로 표현하지 않는다.
