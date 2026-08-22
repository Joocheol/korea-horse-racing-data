# API 형식·호출량·Dropbox 경로 결정

*확정 2026-08-21, normalized 계층 규칙 보강 2026-08-23*

## 1. 대상 API와 원본 형식

| 논리 이름 | 서비스 | 원본 형식 | 일일 한도 |
| --- | --- | --- | ---: |
| `single` | `API28_1` | JSON | 3,000 |
| `double` | `API29_1` | JSON | 3,000 |
| `triple` | `API30_1` | JSON | 3,000 |
| `sales` | `API179_1` | JSON | 3,000 |
| `entries` | `API26_2` | JSON | 3,000 |
| `results` | `API227` | XML | 3,000 |
| `race_record` | `API4_3` | XML | 3,000 |
| `quinella_crosscheck` | `API5` | JSON | 3,000 |

JSON이 가능한 서비스는 JSON으로 받고 `API227`과 `API4_3`은 XML을 사용한다. raw 파일은
응답 바이트를 변형하지 않고 페이지별 확장자 `.json` 또는 `.xml`로 저장한다.
공통 JSONL 변환은 staged/normalized 계층에서만 수행한다.

## 2. 호출 예산

한도는 8개 서비스를 합친 3,000회가 아니라 서비스별 3,000회다. 재시도와 추가
페이지도 실제 호출이므로 예산에 포함한다. `used_json`은 `API28_1` 같은 서비스
ID를 키로 사용한다.

### API227은 실제 경주일만 호출한다

`API227`의 공식 요청 단위는 `meet + rc_date`다. `rc_month`는 공식 요청변수가
아니므로 월 조회 시간초과를 "월 데이터가 너무 커서 실패"로 해석하지 않는다.

운영 수집은 다음 두 단계로 수행한다.

1. `API4_3`을 포함한 월 단위 API를 먼저 모두 수집한다.
2. 요청 기간의 모든 `API4_3` meet-month가 `complete`인지 확인한다.
3. staged `API4_3`에서 `unique(meet, rcDate)`를 만든다.
4. 그 날짜에 대해서만 `API227`을 호출한다. `rc_no`는 생략해 해당 경마일 전체를 받는다.
5. 발견된 API227 요청 수에 10% 안전여유를 더해 서비스별 3,000회 한도를 다시 검사한다.

2020·2021 완전수집본으로 이 전략을 사후 검증했다.

| 항목 | 기존 달력 전수 방식 | 실제 경주일 방식 |
| --- | ---: | ---: |
| API227 요청 단위 | 2,193 | 396 |
| 빈 날짜 호출 | 1,797 | 0 |
| API4_3이 발견한 `(meet, date)` | - | 396 |
| API227 양수 날짜 중 API4_3 누락 | - | 0 |

또한 `(meet, date, rcNo, chulNo, hrNo)` 기준으로 API4_3과 API227을 비교했을 때
41,749개 출전마 결과 키가 정확히 일치했다. 따라서 이 2년 표본에서는 API4_3을
경주일 인덱스로 사용해도 API227 누락이 없었다.

2016-2025의 실제 시행일수에 기반한 사전 추정치는 API227 약 2,723회다. 다만
수집기는 이 숫자를 하드코딩하지 않고 매 실행마다 API4_3 staged 데이터에서 실제
요청 수를 계산한다. 10% 안전여유를 적용할 때 단일 일일 배치의 최대 실제 요청 수는
2,727개다. 이를 넘으면 API227 단계는 차단하고 기간을 나누어 실행한다.

과거 2020·2021 파일럿의 2,913개 unit 계획은 재현성을 위해 legacy planner에
보존한다. 운영 CLI와 preflight는 더 이상 빈 달력 날짜를 API227 대상으로 만들지 않는다.

월간 삼쌍승이 100,000행을 넘을 수 있어 `API30_1`의 TRI 단위에는 보수적으로
2페이지를 예약한다.

세부 검증 근거는 [API227_RACE_DAY_PLANNING.md](API227_RACE_DAY_PLANNING.md)를 본다.

## 3. Dropbox

사용자에게 보이는 기준 경로는 **`/앱/kra-data/`**다. 기존
`/앱/kra-actions-lab-joocheol/` 아래에 중첩하지 않는다.

```text
/앱/kra-data/
  raw/
  normalized/
  manifests/
  quarantine/
  docs/
```

## 4. raw / normalized / research 경계

`normalized`는 코드 내부의 `staged/`와 같은 논리 계층이다. 여기서 수행하는 정규화는
**구조적 정규화(structural normalization)**에 한정한다.

- raw: API 응답 원본 바이트를 그대로 보존한다.
- normalized/staged: JSON 또는 XML의 각 source item을 JSONL 한 행으로 만든다.
- research: 여러 API를 `race_id`로 연결하고 `meet`, `pool_code` 등을 의미적으로 통일한다.

normalized에서는 source field 이름과 source-native 자료형을 보존한다. 따라서 XML API의
숫자형 값이 문자열인 경우 이를 숫자로 강제 변환하지 않는다. `race_id` 추가, 승식 코드 통일,
연구 race universe 필터, 결측 0 대체도 normalized에서는 하지 않는다.

`API5`의 복승 자료는 `API29_1` QNL과 중복되더라도 validation evidence로 raw/normalized에
유지한다. canonical research odds에는 `API29_1` QNL만 사용한다.

실제 artifact 감사 결과와 재현 명령은 [NORMALIZED_LAYER_AUDIT.md](NORMALIZED_LAYER_AUDIT.md)에
정리한다.
