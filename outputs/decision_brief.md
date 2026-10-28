# Sudan farmers IVR survey: decision brief

Analysis date: 4 October 2026. Source export: 2 October. All supplied log rows included; scheduled dates 2-29 September, with nine rows preceding the reported 8 September launch.

## Executive findings

- 4,118 observed call-log rows cover 3,002 phone keys. 804 ever answered (26.78% of called keys); 812 answered rows (19.72% of log rows). These are contact keys, not proven unique individuals.
- 116 completed response records imply 3.86% of called keys and 14.43% of reached keys. 688 reached contacts have no completed response record; 2198 called contacts never answered. 9 master contacts have no call row.
- Completion-source discrepancy: 133 log snapshot flags, 116 raw records, 117 reported. The 17 flagged-only contacts are listed in completion_discrepancies.csv. Completion timestamps are unavailable.
- Linkage: 4,086/4,118 call rows (99.22%), 2,991/3,002 called keys (99.63%), and 113/116 response records (97.41%) match the master. 57 matched call rows use flagged exact malformed-number matches, NOT validated Sudan phone numbers.

## Geographic and demographic selection

Comparisons below use only master-linked respondents (n=113); the three unmatched raw completers are excluded from master representativeness, not from overall survey answers.

| State | Master phone keys | Called | Reached | Completed | Master share | Respondent share | Difference (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|
| River Nile | 794 | 792 | 475 | 66 | 26.47% | 58.41% | +31.94 |
| Gedaref | 1621 | 1620 | 181 | 20 | 54.03% | 17.7% | -36.33 |
| Kassala | 413 | 409 | 78 | 15 | 13.77% | 13.27% | -0.49 |
| White Nile | 86 | 86 | 49 | 6 | 2.87% | 5.31% | +2.44 |
| Al Jazeera | 22 | 22 | 10 | 2 | 0.73% | 1.77% | +1.04 |
| Red Sea | 43 | 41 | 3 | 2 | 1.43% | 1.77% | +0.34 |
| Sennar | 21 | 21 | 4 | 2 | 0.7% | 1.77% | +1.07 |

River Nile is overrepresented and Gedaref underrepresented in the observed completed sample relative to this programme roster. This roster is not a population census of Sudanese farmers. Unweighted answers must not be generalized to all farmers.

- Female: 1207 master keys; 1201 called, 223 reached, 38 completed; contact 18.57% of called, completion 3.16% of called. Master share 40.23%, respondent share 33.63%.
- Male: 1788 master keys; 1785 called, 576 reached, 75 completed; contact 32.27% of called, completion 4.2% of called. Master share 59.6%, respondent share 66.37%.
- Unknown: 5 master keys; 5 called, 1 reached, 0 completed; contact 20.0% of called, completion 0.0% of called. Master share 0.17%, respondent share 0.0%.

Gender interpretation: the aggregate female contact gap is not uniform across states. In Gedaref, female reach is 97/758 (12.8%) versus male reach 83/857 (9.7%); female completion is 14/758 (1.85%) versus 6/857 (0.70%). In River Nile, female reach is 79/138 (57.2%) versus male reach 396/654 (60.6%), while female completion is 14/138 (10.1%) versus 52/654 (8.0%). Geographic composition can contribute to the aggregate gender gap; no adjusted causal gender effect is established. See gender_within_state.csv.


The representativeness.csv table extends these comparisons to locality, community, support type, project and age bands. Differences are descriptive; neither gender nor state effects are causal. Missing/invalid ages remain a separate category.

## Substantive survey signals

- Income decreased: 70/116 (60.34%). Unweighted self-report, unknown recall period.
- Spending categories: Food 57/116; Repaying Debt 40/116. The exact wording/multiple-choice constraints were not supplied.
- Q07 has 35 answers from respondents who did not report increased income. All 34 unchanged-income respondents answered Q07, as did one decreased-income respondent. Do not publish Q07 as an eligible-population indicator until Viamo verifies routing.
- The paired question-text columns agree after case normalization. This is duplicate storage, not a second response. Q02/Q07/Q08 are potentially branched; missing values are not automatically refusals or dropouts.
- Exact questionnaire/audio and routing rules are absent. Several yes/no and access items cannot be given a reliable substantive title; these remain labelled with their question ID and neutral answer description.

## Calling operations and retries

- Mean observed rows per called phone: 1.372; repeat-call rate 31.08% of called phones. The platform Call Attempts field sums to 28,946, but its event/retry semantics are not documented. Do not sum it as physical dial attempts.
- Scheduled hours, not actual failed-call dial times, drive time comparisons. Calls cluster at 09:00, 13:00 and 19:00; this is compatible with batch scheduling, not evidence that these times are optimal. Received times exist for answered calls and some errors, not failed no-answer calls.
- Nine pre-launch rows cover four contacts; three are raw completed respondents. The report launch date and export scope therefore differ. Excluding pre-launch rows must not remove these facts from the audit.
- Final-attempt cohorts suffer selection: unsuccessful phones are preferentially retried. Use incremental first-reach yield among previously unreached phones; completion is undated and cannot be attributed to a retry or calling hour.

| Observed sequence | Previously unreached at this attempt | Newly reached | Conditional pickup |
|---|---:|---:|---:|
| 1 | 3002 | 736 | 24.52% |
| 2 | 923 | 67 | 7.26% |
| 3 | 84 | 1 | 1.19% |
| 4 | 83 | 0 | 0.0% |
| 5 | 8 | 0 | 0.0% |
| 6 | 8 | 0 | 0.0% |

The 350 failed rows with disconnected/unallocated/malformed-number causes correspond to 317 distinct contacts, of whom 16 were reached on another logged row. A network cause is an operational flag, not proof that a phone is permanently dead. The narrative recommendation confuses attempts with numbers. Verify contacts before deletion.

## Priority actions

1. Ask Viamo to reconcile 116 raw completions, 133 snapshot flags and 117 reported; obtain one versioned export with questionnaire, routing, event timestamps, retry semantics and test-contact markers.
2. Field-verify the 46 malformed master phone values, 11 unmatched called keys and nine uncalled master keys. Retain an audit; do not invent missing digits or remove contacts solely on one carrier cause.
3. Concentrate sensitization and alternate-contact verification on underrepresented Gedaref and female beneficiaries. Establish state/gender completion quotas informed by the master roster and contact costs.
4. Randomize comparable unreached contacts across allowable time windows and attempt limits; stratify by state/gender. Measure incremental reach, verified completion, cost and complaints per allocated contact.
5. Obtain the exact intro, consent audio and question routing. Repair Q06/Q07 before interpreting apparent financial-question attrition. Pilot a shorter intro and question-order changes, then compare with randomized controls.
6. Clarify whether Round 2 targets verified completers, all reached contacts, or a fresh representative sample. Fix the panel definition before scheduling follow-up.
7. Share aggregated dashboard tables only; keep the source files, detailed model and private linkage audit in access-controlled storage. If exporting publicly, apply additional disclosure review to small geographic cells.

## Definitions and limitations

- Targeted: 3,002 observed called keys is a proxy; no independent target-allocation list exists. Master roster contains 3,000 rows/keys, not 3,002.
- Reached: at least one Finished (complete) or Finished (incomplete) row. Finished (complete) means natural call end, not survey completion.
- Started: any Q01 subscriber snapshot, a proxy because all r1_started_survey fields are empty. Intro is another undated subscriber flag.
- Completed: unique phone in the supplied completed-response file. Abandoned: started proxy without a completed record; distinguish from answered-without-completion and report both.
- Never reached in the master includes uncalled contacts and called-never-answered contacts; in the called funnel it means only called-never-answered.
- Invalid phones can match only through exact digits after documented source prefix removal. They remain invalid; no missing-digit inference or fuzzy matching is used.
- One phone may represent more than one beneficiary. Current normalized/flagged-exact master keys have no duplicates; the model nevertheless separates master records from contact keys and flags ambiguous attributes.
- Labels use master values preferentially. Only one-to-one code mappings backfill unmatched contacts. A globally conflicting locality code is withheld rather than guessed; a gender code with an unknown label is not de-anonymized.
- No causal claims, population weighting or national farmer inference. IVR selection, mobile access, language, consent and completion barriers are not independently measured.
- Date/outcome filters select calling exposure cohorts. Completion and answers are lifetime-in-export snapshots within that cohort, NOT completions occurring in the selected window. Date/outcome filters restrict the master comparison to exposed contacts; full-roster comparison requires unrestricted exposure filters.
- Small bases (<10) retain counts but suppress displayed rates for subgroup survey results. Counts may still be sensitive; local internal use only.
- Maps use geoBoundaries open administrative boundaries, not an official UN boundary endorsement. Labels are mapped only with explicit spelling aliases. Unknown states remain in tables.

## Reproducibility and data model

Run `python analyze.py`, then `python -m unittest test_analysis -v`. Original inputs are never edited. SHA-256 source hashes are recorded in data_quality.json.
persons: one contact key; master_records: one original beneficiary row; call_attempts: one unique Delivery ID row; response_answers: one respondent/question; subscriber_answer_snapshots: one contact/question, not timestamped events. All child joins use person_id; master-to-contact is many-to-one. No join expands call or response rows.
Private phone linkage (private/phone_linkage_audit_DO_NOT_SHARE.csv) is necessary for corrections and explicitly must not be distributed. All analytical tables omit phone numbers, names, subscriber IDs and delivery IDs. Pseudonymous detailed records are still sensitive and should remain local.
The SQLite model is reproducible and the CSVs support further analysis. source_profile.json records source-level distributions; report_reconciliation.csv preserves every compared report figure.

Source roles: the September activity DOCX supplies programme context, launch and status rubric; master supplies beneficiary labels; call logs supply exposures/statuses; raw completed responses supply primary completions/answers; the September XLSX supplies reference funnel and question counts. Neither report overrides source facts.
