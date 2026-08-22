# 2016–2025 coverage gap 감사

*감사일: 2026-08-23*

## 결론

coverage gap은 수집 실패와 구조적 비판매를 분리해서 해석해야 한다. 최종 corrected research bundle
(`kra-research-2016-2025-corrected`, Actions run `32603481704`)을 기준으로 전수 감사한 결과,
확인 대상은 다음 세 유형으로 정리된다.

1. **API179 sales source gap: 145경주**
   - 해당 경주는 `sales-all` 행이 하나도 없지만 적어도 3개 이상의 odds 승식이 존재한다.
   - 따라서 경주 미시행/전체 미판매가 아니라 API179 source-level coverage gap으로 분류한다.
   - 이 중 17경주(2020-02-23 서울 11 + 부경 6)는 PLC odds도 함께 비어 있어 별도의 odds source gap을 동반한다.
2. **2025-10-17 single/double odds source gap: 16경주**
   - 제주 8경주 + 부경 8경주.
   - sales는 존재하고 TLA/TRI odds도 존재하지만 WIN/PLC/QNL/EXA/QPL odds가 동시에 없다.
   - 2025 source artifact에서 해당 날짜의 `single-all`, `double-qnl`, `double-exa`, `double-qpl` normalized 행이 0임을 확인했다.
   - 같은 artifact에서 `triple-tla`, `triple-tri`, `sales-all`은 해당 날짜 행이 정상 존재한다.
3. **구조적 비판매/제도 변화**
   - TRI: 2016-06-10 도입 전 1,210경주에서 sales/odds가 모두 없다. 이는 정상적인 pre-introduction gap이다.
   - 2020-06-19~2021-09-05 사이 1,276경주에서 EXA/QPL/TLA/TRI가 sales/odds 모두 없고 WIN/PLC/QNL만 존재하는 동일 패턴이 나타난다.
     당시 무고객 경마에서 단승·연승·복승만 발매했다는 시행 기록과 일치하므로 COVID 제한 승식 regime으로 분류한다.

따라서 **현재 확인된 coverage gap 중 재수집으로 해결해야 할 race-level 수집 실패는 발견되지 않았다.**
다만 API179 145경주와 2020-02-23 PLC 17경주, 2025-10-17 single/double 16경주는
향후 source API 또는 HTML 원자료와 비교할 때 명시적 source anomaly로 표시해야 한다.

## 승식별 sales / odds 조합

| pool | sales=0, odds=0 | sales=0, odds=1 | sales=1, odds=0 | sales=1, odds=1 | 해석 |
| --- | ---: | ---: | ---: | ---: | --- |
| WIN | 0 | 145 | 16 | 24,275 | sales 145는 API179 gap, odds 16은 2025-10-17 source gap |
| PLC | 17 | 128 | 16 | 24,275 | 17은 2020-02-23 동반 odds gap |
| QNL | 0 | 145 | 16 | 24,275 | 동일 |
| EXA | 1,276 | 118 | 16 | 23,026 | 1,276은 COVID 제한 승식 |
| QPL | 1,276 | 118 | 16 | 23,026 | 1,276은 COVID 제한 승식 |
| TLA | 1,276 | 118 | 0 | 23,042 | 1,276은 COVID 제한 승식 |
| TRI | 2,486 | 105 | 0 | 21,845 | 1,210 pre-introduction + 1,276 COVID 제한 승식 |

## API179 sales source gap 145경주: 연도 × 경마장

| year | Seoul | Jeju | Busan-Gyeongnam | total |
| --- | ---: | ---: | ---: | ---: |
| 2016 | 3 | 15 | 1 | 19 |
| 2017 | 0 | 1 | 0 | 1 |
| 2018 | 0 | 5 | 0 | 5 |
| 2019 | 0 | 10 | 11 | 21 |
| 2020 | 33 | 3 | 7 | 43 |
| 2021 | 0 | 7 | 0 | 7 |
| 2022 | 0 | 11 | 0 | 11 |
| 2023 | 11 | 18 | 0 | 29 |
| 2024 | 1 | 0 | 0 | 1 |
| 2025 | 0 | 7 | 1 | 8 |
| **total** | **48** | **77** | **20** | **145** |

특히 같은 날짜·경마장의 여러 경주가 동시에 빠지는 cluster가 있다.

- 2020-08-09 서울: 12/12경주 sales 전체 미제공
- 2019-11-29 부경: 11/11경주
- 2020-02-23 서울: 11/11경주
- 2020-02-23 부경: 6/6경주
- 2023-01-14 제주: 7/7경주
- 2023-05-06 서울: 9/10경주

이 패턴도 개별 경주 취소보다 API179 날짜/경마장 단위 source gap 해석을 지지한다.

## 외부 시행 근거

- 한국마사회는 2016-06-10부터 삼쌍승식을 신규 도입했다.
  - 스포츠경향, 2016-06-09, “한국마사회, 10일부터 ‘삼쌍승식’ 신규 도입”
  - https://sports.khan.co.kr/article/201606091609003
- 2020-06-19부터 무고객 경마가 재개되었고, 당시 보도에는 마주만 제한적으로 입장한다고 명시되어 있다.
  - 연합뉴스, 2020-06-17, “한국마사회, 19일부터 경마 재개…마주만 입장 허용”
  - https://www.yna.co.kr/view/AKR20200617126300007
- 당시 무고객 경마 운영 안내에는 발매 승식을 단승·연승·복승으로 제한했다고 기록되어 있다.
  - 강운마권, 2020-06-19, “한국마사회 무관중 경마 재개…”
  - https://wordpress.kimtaku.com/archives/13976

## 재현·운영 정책

- `coverage.jsonl.gz`의 boolean은 “해당 source row가 research universe 안에 존재하는가”를 뜻한다.
- `False`를 자동으로 수집 실패나 0매출로 해석하지 않는다.
- 구조적 비판매는 `structural_not_offered`, source endpoint 공백은 `source_gap`으로 구별한다.
- 상세 race-level anomaly 161건(145 sales gap + 별도 16 odds gap)은
  `docs/coverage-anomalies-2016-2025.csv`에 보존한다.
- 2020-02-23의 17경주는 sales gap과 PLC odds gap을 동시에 가지므로 CSV에서 복합 분류한다.
