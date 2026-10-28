# Sudan farmer IVR monitoring

Open [dashboard/index.html](dashboard/index.html) in a browser. It runs locally without a server or internet connection; charts, icons, fonts, data and state boundaries are bundled. Six pages share state, gender, calling period, outcome, observed-attempt, completion-status and support-type filters. Navigation, map state selection, question/group selectors, aggregate CSV download and print are available.

## Outputs

- [Decision brief](outputs/decision_brief.md): findings, nonresponse risks, discrepancies and October recommendations.
- [Data quality summary](outputs/data_quality.json): profiles, phone quality, match counts/rates, hashes and report reconciliation.
- [SQLite analytical model](outputs/analytical_model.sqlite): contact dimension and relational fact tables.
- [Source profiles](outputs/source_profile.json): column missingness, cardinality, distributions and duplicate checks.
- [Report reconciliation](outputs/report_reconciliation.csv): reference funnel and per-question figures compared without forcing agreement.
- [Representativeness](outputs/representativeness.csv), [gender within state](outputs/gender_within_state.csv), [survey results](outputs/survey_results.csv) and [retry yield](outputs/incremental_retry_reach.csv): denominator-aware analytical tables.
- [Unmatched contacts](outputs/unmatched_contacts.csv) and [completion discrepancies](outputs/completion_discrepancies.csv): pseudonymous exception lists.

The detailed phone correction audit is at `private/phone_linkage_audit_DO_NOT_SHARE.csv`. It is deliberately excluded from dashboard assets and analytical tables. It contains original and standardized numbers for necessary internal correction, not dissemination. Neither it nor the original spreadsheets should be served from a web root.

## Reproduce

```powershell
python -m pip install -r requirements.txt
python analyze.py
python -m unittest test_analysis -v
node --check dashboard/app.js
```

Python 3.12 with pandas/openpyxl was used. Node is needed only for the optional JavaScript syntax check, not to run the dashboard. Existing inputs are read-only. A first build downloads open state boundaries; subsequent builds reuse the local asset. If that download fails, tables and all other analyses still work and the map explicitly indicates unavailability.

Tests pin totals for these supplied exports. Replacing source exports requires reviewing and updating the expected regression totals, not changing data to satisfy tests.

## Data Model

| Table | Grain | Relationship |
|---|---|---|
| `persons` | One normalized or flagged-exact contact key | Unique `person_id`; no phone columns |
| `master_records` | One original beneficiary row | Many rows may link to one contact |
| `call_attempts` | One unique Delivery ID log row | Many-to-one contact; row-based attempts only |
| `response_answers` | One completed respondent/question | Unique contact/question |
| `subscriber_answer_snapshots` | One subscriber/question snapshot | Undated; not attempt events |
| `label_mapping` | One attribute/code | Ambiguous/unknown mappings flagged |

Current inputs contain no duplicate master or completed-response phone keys, but the model preserves the distinction between contact and beneficiary grains. Master values override IVR codes; only reliable one-to-one mappings backfill external contacts. Malformed values are never made valid by an exact textual match. Invalid exact matches require the known export's `249` prefix and otherwise identical master digits; no fuzzy matching or inferred digits.

Age bands retain 15–100 as an analytical plausibility screen, not a beneficiary eligibility rule. Whitespace is trimmed/collapsed in labels; category names and project synonyms are not guessed. Paired response columns are duplicate representations; one canonical `R1Qxx` field is used after case-insensitive agreement checks. Missing conditional responses are retained as missing/not applicable, not automatically dropped/refused.

## Interpretation

Primary completed surveys = 116 records in the raw completed-response file. The 133 platform completion flags and 117 reported completions remain separate. Three raw completers are unmatched/pre-launch contacts; 113 match the roster. No completion timestamp exists.

Date and outcome filters select calling-exposure cohorts and matching call-log rows. Contact reach, final attempt counts and response answers remain full-export snapshots for those contacts. Consequently, a completed contact can appear under a failed-call exposure filter because it answered on another call. The dashboard never labels this as completion at the selected hour/date. Representativeness with date/outcome restrictions is against the exposed master cohort, not the full roster.

Called = observed target proxy, not independently confirmed planned targeting. Answered = `Finished (complete)` or `Finished (incomplete)` call status. Started = Q01-present proxy because started flags are empty. Call end is not survey completion. Log rows are not confirmed physical carrier retry events; the undocumented `Call Attempts` field is not summed. Percentages always name their denominator; item bases below 10 have withheld percentages.

The programme roster is not a national farmer sampling frame. All estimates are unweighted and descriptive. State/gender selection, phone access and IVR consent/engagement may bias outcomes. Exact questionnaire wording, routing rules, consent/audio, timestamps, retry definitions, test-contact markers and a target-allocation file are missing. Neutral labels are retained when a substantive question mapping cannot be verified.

## Privacy

Dashboard visuals and aggregate CSV downloads contain no phones, names, subscriber IDs or delivery IDs. The bundled dashboard data and detailed analytical tables retain pseudonymous contact-level attributes; they are **internal analytical products, not anonymized public-release microdata**. Keep them local/access controlled. For a public deployment, publish disclosure-reviewed aggregates rather than the bundled contact facts. Small-cell counts can still disclose information even when percentages are withheld.

## Geographic Detail

The Geographic Performance page includes:

- Six state-map measures: calling coverage/master, reach/called, completion/called, completion/reached, completion/master, and completed counts. Map bins rescale with the cohort; tooltips and the scale note state the measure and denominator.
- A state funnel including the Q01 start proxy, coverage, selected attempt counts, contact rates and separate completion denominators.
- Mutually exclusive nonresponse groups: uncalled, called-never-answered, reached-without-completion and completed. These sum to the master-linked state cohort.
- Master versus completer composition, percentage-point differences and representation indices. The proportional completion benchmark fixes the observed total completed count; it is not a quota, estimated missing count, population weight or causal effect.
- Locality and community detail, with search and coverage-gap filters. Parent-safe groups use state + locality, or state + locality + community. Identical names in different parents are not merged. These controls affect only the detail table; shared dashboard filters affect every measure.
- Aggregate CSV exports for all three geographic levels in the shared-filter cohort, regardless of the detail-table search/gap filter. Each row includes counts, nonresponse decomposition, rate denominators, representation measures and small-base flags.
- A next-call focus panel with three distinct decision modes: highest observed retry rate, largest illustrative pickup volume or geographic coverage gaps. It uses campaign calls on/after 8 September, excludes pre-launch rows from attempt sequence, flags low retry denominators, and reports eligible valid-format contacts and state-filter links. Illustrative retry pickup is a historical-rate scenario, not a forecast; less-reached contacts may be harder to reach than prior retry cohorts.

In the unrestricted post-launch cohort, 1,321 valid-format contacts remain unreached after one call. White Nile had the highest observed second-call pickup (21/31, 67.7%; limited base), while River Nile had a lower rate but a larger retry evidence base (40/118, 33.9%) and eligible pool (234). Applying those observed rates illustratively suggests about 18 and 79 pickups respectively; these are not forecasts. Gedaref has the largest coverage gap (1,421 valid-format never-reached contacts), but its observed second-call pickup was 5/586 (0.9%). Use the high-rate view for a capped pickup test, River Nile for potential pickup volume, and a separate timing/sensitization experiment for Gedaref rather than mass-redialing it unchanged. Shared date/outcome filters select contacts; pickup benchmarks remain full post-launch history for those contacts.

## Question Progression

Survey Results includes answer-presence snapshots from 220 contacts with a Q01 record. The progression chart uses checkpoints Q01, Q03–Q06 and Q09–Q13; Q02, Q07 and Q08 are shown separately because their eligibility/routing is conditional or unverified. The clearest directly adjacent loss is Q04→Q05: 13/181 prior answerers (7.2%). The Q06→Q09 gap is 14/160 (8.8%) but spans Q07/Q08, so it cannot be attributed to either item. Q01→Q03 has 29 fewer records across Q02, whose eligibility is also unverified. Q13 appears for 133 snapshot contacts (60.5% of the Q01 base), but this matches the 133 log completion flags, not the 116 completed-response records; treat it as answer presence, not a verified survey-exit event.

Completed-file question availability is shown separately with its denominator of 116 records. All 116 completed records include the non-branch checkpoints; Q02 has 20, Q07 has 47, and Q08 has 70 recorded answers. Q07 includes 35 answers from respondents not reporting increased income. Do not infer response burden or drop-off from those branch fields without Viamo's routing/eligibility map. Filters restrict the contact cohort, but answer fields remain undated lifetime snapshots. The dashboard payload adds only `person_id` + question-presence flags for incomplete callers, not their answer text.

With unrestricted filters, the supplied data covers 7 states, 25 state-locality units and 119 state-locality-community units. All three levels reconcile to 3,000 master contact keys, 2,991 called keys, 4,086 selected master-linked call rows, 800 reached contacts and 113 linked completers. Six localities and 82 communities have no completed-response records. These are sample coverage gaps, not evidence that the places are permanently unreachable. No locality/community coordinates are supplied, so only state boundaries are mapped.

State names in the conversion table and map select the shared state filter. Small completed bases are marked; percentages with denominators below 10 are withheld. Unmatched-only cohorts show an explicit exclusion message rather than a fabricated geographic baseline. Existing geographic attribute comparisons in the analytical CSVs remain by attribute label; the dashboard geographic export additionally preserves parent hierarchy.

## Assets

- Design reference: [color-palette-dashboard.html](color-palette-dashboard.html). Its light-theme tokens define dashboard surfaces, text, borders, alerts, categorical colors and the five-step positive map scale. Called = `#006EB5`, reached = `#5DD4F0`, completed = `#02A38A`, not reached = `#E78625`; gender swatches use the supplied male/female colors. Layout and analytical definitions are unchanged.
- Inter: SIL Open Font License 1.1, bundled locally to match the reference typography, https://github.com/google/fonts/tree/main/ofl/inter
- Chart.js 4.4.8: MIT, https://www.chartjs.org/
- D3 7.9.0: ISC, https://d3js.org/
- Lucide 0.468.0: ISC, https://lucide.dev/
- Source Sans 3: SIL Open Font License 1.1, https://github.com/adobe-fonts/source-sans
- geoBoundaries SDN ADM1: CC BY 3.0 IGO, 2020 boundaries, https://www.geoboundaries.org/api/current/gbOpen/SDN/ADM1/

The map uses the explicit Gezira → Al Jazeera spelling alias and a rendering-only ring-orientation adaptation for D3. Original downloaded geometry is retained unchanged. Boundaries and place names do not imply an official UN endorsement; the dashboard does not adjudicate the status of Abyei. White regions are outside the supplied roster or lack a usable denominator, following the reference's graph-no-data token.

## Verification

Browser checks covered all six pages, combined state/gender filters, post-launch and outcome exposure filters, uncalled contacts, invalid date ranges, Q07 alerts, small-base suppression, state-map clicks and generated aggregate CSV content. Desktop (1440 px) and mobile (390 px) screenshots were reviewed; chart pixels were nonblank and horizontal overflow was absent. The integrated browser did not expose a download event, so CSV blob content/filename were verified directly; OS-level file saving was not independently confirmed.