# A complete combination-level dataset of the Korean pari-mutuel horse racing market, 2016–2026

**Draft — Data Descriptor for *Scientific Data* (Nature Portfolio)**

Status: working draft, 2026-08-18.
Sections marked `[TBD]` await completion of data collection.
Numbers marked `[n]` are placeholders to be filled from the final release.

Author: Joocheol Kim (Yonsei University), ORCID 0000-0002-4189-4827
`[TBD]` co-authors and contribution statement

---

## Background & Summary

Pari-mutuel betting markets are among the cleanest naturally occurring
laboratories in economics. Each race is a self-contained market that opens,
clears, and settles within a fixed window; participants' beliefs are expressed
directly in prices; the terminal state is publicly observed; and there is no
counterparty whose inventory or risk appetite mediates the price. These
properties have made horse racing markets a recurring testbed for work on
market efficiency, probability calibration, and the favourite–longshot bias.

Almost all of that work, however, rests on a thin slice of the available price
information. Studies typically use win odds — one price per runner — or the
realised payout on the winning combination. The far richer object, the full
combinatorial price vector across every possible finishing arrangement, is
rarely used, and to our knowledge has never been published as an openly
licensed research dataset.

The reason is not that such data do not exist. Racing authorities compute and
display them continuously: in a field of $n$ runners the trifecta board alone
carries $n(n-1)(n-2)$ prices, roughly a thousand cells for a typical field.
The obstacle is redistribution. In the two jurisdictions where combination-level
boards are most systematically archived, access runs either through a paid
subscription service whose licence restricts onward distribution, or through
scraping of commercial websites whose terms prohibit reuse. Neither route
produces a dataset that can be deposited in a repository under an open licence
and cited by others.

Korea is an exception. The Korea Racing Authority (KRA) publishes the full
dividend boards for all seven bet types through the national open data portal
under terms that place no restriction on redistribution. This dataset is
assembled from those APIs.

Two features distinguish it from existing racing datasets.

**Complete combination-level prices for seven pools.** For every race we
record the displayed dividend on every admissible combination in win, place,
quinella, exacta, quinella place, trio, and trifecta. For an eleven-runner
race this is 1,397 prices. `[n]` races and `[n]` price cells in total.

**Pool turnover alongside prices, which recovers bet quantities.** Under
pari-mutuel accounting the displayed dividend on combination $c$ is
$O_c = tS/(100 n_c)$, where $S$ is the pool turnover, $t$ the payback ratio,
and $n_c$ the number of tickets held on $c$. Because the dataset carries $S$
for every pool of every race, $n_c$ is recoverable exactly, and the recovered
values are integers. Prices reveal relative beliefs; prices together with
turnover reveal how much money actually stood behind each belief. We are not
aware of another public racing dataset that permits this.

The dataset also spans a policy discontinuity. Trifecta betting was introduced
in Korea on 10 June 2016 and the record begins at that date, so the panel
covers the entire life of the pool.

## Methods

### Data provenance

All records derive from public APIs operated by the Korea Racing Authority and
distributed through the Korean national open data portal (data.go.kr). Eight
endpoints contribute.

| Content | Service / operation | Portal dataset |
| --- | --- | --- |
| Win, place dividends | `API28_1/singlePredictionRateInfo_1` | 15059137 |
| Quinella, exacta, quinella-place dividends | `API29_1/doublePredictionRateInfo_1` | 15057397 |
| Trio, trifecta dividends | `API30_1/triplePredictionRateInfo_1` | 15058258 |
| Pool turnover and winning dividends | `API179_1/salesAndDividendRate_1` | 15057896 |
| Quinella dividends (duplicate source) | `API5/quinellaOddsInfo` | 15057090 |
| Entry sheet, field size | `API26_2/entrySheet_2` | 15058677 |
| Race result detail, finishing order | `API227/racedetailresult/getracedetailresult` | 15119524 |
| Race records | `API4_3/raceResult_3` | 15058305 |

Base URL `https://apis.data.go.kr/B551015`. Requests are parameterised by
racecourse (`meet`), race date or month, race number, and — for the two
multi-pool endpoints — pool code.

### Collection procedure

Requests are issued at racecourse × month granularity. `[TBD: exact worker
count, request interval, total wall-clock time]`

Every response is stored verbatim before parsing. Each stored response carries
the request URL, the retrieval timestamp, the HTTP status, a SHA-256 digest of
the response body, and the commit hash of the collector that produced it.
Normalised tables are derived from the stored responses and are reproducible
from them.

### Field-size determination

The number of runners $n$ enters every completeness check, so it must not be
derived from the dividend grid it is used to check. We obtain $n$ from the
entry-sheet endpoint (`dusu`) net of scratchings, independently of the
dividend endpoints.

The APIs enumerate combinations over **starters**, not entries. On 8 March
2025 at Seoul the quinella endpoint returned 520 cells for the day; the sum of
$\binom{n_{\text{starters}}}{2}$ over that day's races is 520, while the same
sum over entries is 550.

### Display cap

Dividends are capped at 9999.9 in the source. This is a property of the KRA
data itself and not of any one delivery channel: cells displayed as 9999.9 on
the KRA web dividend boards return 9999.9 through the API as well. The cap is
preserved in the dataset rather than imputed, and is flagged. Capped cells are
common in the deep pools — 477 of the 990 trifecta cells in one eleven-runner
race examined here.

### Non-race records

The APIs contain records for dates on which no betting took place. These
appear at the introduction of each new pool and are, on inspection, system
tests rather than racing.

Weekday cannot be used to identify them. Korean racing is normally held on
Friday, Saturday and Sunday, but the schedule is set administratively each
year and genuine meetings do fall outside that pattern, so a weekday filter
would discard real races.

We classify instead on evidence of settlement:

| Signal | Racing | Test record |
| --- | --- | --- |
| Pool turnover (`amt`) | positive, order 10⁸–10¹⁰ KRW | zero, or no row |
| Finishing order (`ord`) | present | absent |
| Entry sheet | present | absent |
| Pool completeness | all seven pools | subset only |

Seven candidate dates in 2016 were examined against two control dates. All
seven returned zero turnover, no finishing order and no entry sheet, and
carried trifecta records with no quinella records — a combination that cannot
arise in a settled race. The controls returned turnover of order 10¹⁰ KRW with
complete entry and result records.

Records so classified are retained in a separate table with the classification
and its evidence, not deleted.

### Scope boundary

Trifecta betting began at Jeju and Busan-Gyeongnam on 10 June 2016 (Friday)
and at Seoul on 11 June 2016 (Saturday). Trifecta records exist for three
dates in March 2016; these are test records under the classification above and
April and May 2016 are empty. The dataset therefore begins on 10 June 2016.

`[TBD: end date of the release]`

## Data Records

`[TBD — to be written against the final release. Structure:]`

- Repository, DOI, licence (CC BY 4.0)
- File inventory and formats
- Table schemas, one subsection per table:
  - races (race identity, date, racecourse, field size, distance, going)
  - dividends (race, pool, combination, dividend, capped flag)
  - pools (race, pool, turnover, winning combination, winning dividend,
    recovered ticket count)
  - runners (race, saddle number, horse, jockey, trainer, finishing position)
  - excluded_records (date, racecourse, classification, evidence)
  - manifest (endpoint, racecourse, month, totalCount, stored rows, checksum,
    retrieval time, collector commit)
- Row counts per table
- Identifier conventions and join keys

## Technical Validation

### Completeness against the source

Each API response reports a `totalCount` for the query. The number of rows
stored is compared against it for every racecourse × month × endpoint
combination and recorded in the manifest. Any mismatch marks the combination
incomplete and triggers re-collection.

In the pilot covering 2020–2021, all 288 combinations matched exactly.
`[TBD: result over the full range]`

This check is the dataset's principal guard against silent loss. It detects
truncated pagination, early termination, and duplicate storage, and it does so
without reference to any external source.

### Combinatorial completeness

For a race with $n$ starters the number of admissible combinations is fixed by
the pool:

| Pool | Cells |
| --- | --- |
| Win, place | $n$ each |
| Quinella, quinella place | $\binom{n}{2}$ each |
| Exacta | $n(n-1)$ |
| Trio | $\binom{n}{3}$ |
| Trifecta | $n(n-1)(n-2)$ |

The stored row count must equal this quantity, not merely be contained in it.
Verified instances:

| Race | $n$ | Pool | Rows | Expected |
| --- | ---: | --- | ---: | ---: |
| 2025-03-08 Seoul R1 | 11 | win + place | 22 | 22 |
| 2025-03-08 Seoul R1 | 11 | exacta + quinella + quinella place | 220 | 220 |
| 2025-03-08 Seoul R1 | 11 | trifecta | 990 | 990 |
| 2025-03-08 Seoul R1 | 11 | trio | 165 | 165 |
| 2016-09-25 Seoul R2 | 10 | trifecta | 720 | 720 |
| 2016-09-25 Seoul R2 | 10 | trio | 120 | 120 |
| 2021-05-15 Seoul R1 | 12 | trifecta | 1,320 | 1,320 |

Distinct combinations equal row counts in every case, so neither duplication
nor omission is present.

`[TBD: full-dataset pass rate]`

### Agreement with the published dividend boards

The APIs are one delivery channel for figures that KRA also publishes as
HTML dividend boards. We compared 804 quinella cells drawn from a
deterministic sample against the corresponding board values.

All 804 agreed to the displayed precision. No cell present on the board was
absent from the API, and no value differed. This establishes that the API
channel is not a degraded or differently rounded rendering of the same
underlying figures.

`[TBD: extend the comparison to the deeper pools]`

### Duplicate-source agreement

Quinella dividends are available from two independent endpoints
(`API5/quinellaOddsInfo` and `API29_1/doublePredictionRateInfo_1`). The two
are compared cell by cell.

`[TBD: result]`

### Pari-mutuel accounting consistency

For each pool the recovered ticket count
$n_c = tS/(100 O_c)$
is required to be integral, where $t$ is the statutory payback ratio (0.80 for
win and place, 0.73 otherwise). Worked instances, 2025-03-08 Seoul R1:

| Pool | Turnover $S$ (KRW) | Dividend $O$ | $t$ | Recovered $n_c$ |
| --- | ---: | ---: | ---: | ---: |
| Trifecta | 413,419,800 | 1,077.1 | 0.73 | 2,802 |
| Win | 21,591,100 | 12.2 | 0.80 | 14,158 |

Both are integers. This is a joint test of the turnover figures, the
dividends, and the assumed payback ratios; failure in any one would break it.

`[TBD: pass rate over the full dataset]`

### Overround

For each pool the sum of reciprocal dividends over uncapped cells is compared
against $1/t$. `[TBD]`

### Place cut-off

The number of place dividends actually paid is read directly from the turnover
endpoint, which lists each paid place dividend individually, rather than being
inferred from field size. `[TBD: distribution of observed cut-offs]`

## Usage Notes

**The display cap is a censoring mechanism, not missingness.** A cell recorded
as 9999.9 means the true dividend was at or above that value, which under
pari-mutuel accounting bounds the ticket count from above. Users fitting
models to the price vector should treat these cells as interval-censored.
`[TBD: share of cells at the cap, by pool]`

**Combinations are enumerated over starters.** Scratched entries do not appear
in the dividend grid. Field size for combinatorial purposes is the starter
count, supplied in the races table.

**2020 and 2021 are not representative.** Korean racing was suspended for
extended periods and otherwise run without spectators; turnover in those years
is far below trend while the price structure is unaffected. Both years carry a
flag. Users constructing turnover time series should treat them separately.

**Empty months are real.** Zero rows for a racecourse-month in 2020 reflects
suspension, not a collection failure. The manifest distinguishes the two.

**Excluded records are available.** Dates classified as non-racing are
retained with their evidence so that users may re-examine the classification.

`[TBD: suggested analyses and known limitations]`

## Code Availability

Collection and validation code: `[TBD: repository URL and archived DOI]`,
released under `[TBD]`. The code reproduces the dataset from the APIs given a
portal service key.

`[TBD: language, dependencies, runtime]`

## Data Availability

`[TBD: Zenodo DOI]`. Licensed CC BY 4.0.

---

## Drafting notes (remove before submission)

**Claim to defend.** Not "the first complete dividend grid" — combination-level
odds do circulate. The defensible claim is: the first such dataset that is
openly licensed, sourced from an official public API, technically validated,
and accompanied by pool turnover permitting exact recovery of bet quantities.

**Points still to verify before submission.**
- Whether the JRA combination-level data circulating commercially is a full
  grid or winning combinations only. Affects how the related-work paragraph
  is phrased.
- Whether any racing or betting Data Descriptor has appeared in this journal.
  None found so far.
- Extend the board-versus-API comparison beyond quinella.

**Journal requirements confirmed.**
- No subject-area restriction for Data Descriptors; not assessed on impact.
- No mandated repository for this data type; any repository meeting the
  policy is acceptable. Zenodo qualifies.
- Licence must be CC0 or CC BY; `-SA` and `-NC` are not permitted.
- Deposition required from the second round of review; informal anonymous
  sharing acceptable at first submission.
- APC up to USD 2,690. Discretionary waiver requests must be made at
  submission, not later.
- Figures: eight or fewer recommended.
