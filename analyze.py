from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
import sqlite3
import urllib.request

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'outputs'


def normalize_phone(value):
    if pd.isna(value) or str(value).strip().lower() in {'', 'none', 'nan'}:
        return None, 'missing'
    text = str(value).strip()
    if re.fullmatch(r'\d+\.0', text):
        text = text[:-2]
    if re.search(r'[^\d+()\s.\-]', text):
        return None, 'invalid_characters'
    digits = re.sub(r'\D', '', text)
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('249') and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith('0') and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        return None, 'invalid_length_or_country'
    if national[0] not in {'1', '9'}:
        return None, 'unexpected_sudan_prefix'
    return '+249' + national, 'normalized'


def load_sources():
    return {
        'master': pd.read_excel(ROOT / 'master_data_with_code.xlsx', dtype=object),
        'calls': pd.read_excel(ROOT / 'call-logs-2026-10-02-1138422977bf.xlsx', dtype=object),
        'responses': pd.read_excel(ROOT / 'Raw data for completed responses.xlsx', dtype=object),
    }


def profile():
    sources = load_sources()
    columns = {'master': 'PhoneNumber', 'calls': 'Subscriber Phone', 'responses': 'Phone'}
    result = {}
    for name, frame in sources.items():
        normalized = frame[columns[name]].map(normalize_phone)
        keys = normalized.map(lambda item: item[0])
        result[name] = {
            'rows': len(frame), 'columns': frame.columns.tolist(),
            'field_profile': {column: {'dtype': str(frame[column].dtype), 'missing': int(frame[column].isna().sum()), 'distinct_nonmissing': int(frame[column].nunique())} for column in frame},
            'phone_quality': dict(Counter(item[1] for item in normalized)),
            'unique_valid_phones': keys.nunique(),
            'duplicate_phone_rows': int(keys.dropna().duplicated(keep=False).sum()),
            'exact_duplicate_rows': int(frame.duplicated().sum()),
            'categorical': {column: {str(key): int(count) for key, count in frame[column].value_counts(dropna=False).items()}
                            for column in frame if column in ['Call Status', 'Hangup Cause', 'Call Attempts', 'State', 'State.1', 'Gender', 'Gender.1', 'r1_started_survey', 'r1_intro', 'r1_completed_survey', 'Survey Questions - Answered', 'Survey Questions - Total']},
        }
        if name == 'calls':
            result[name]['schedule_dates'] = {str(key): int(count) for key, count in pd.to_datetime(frame['Scheduled Date']).value_counts().sort_index().items()}
        if name == 'responses':
            result[name]['answers'] = {column: {str(key): int(count) for key, count in frame[column].value_counts(dropna=False).items()} for column in frame if column.startswith('R1Q')}
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / 'source_profile.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def text(value):
    return 'Unknown' if pd.isna(value) or not str(value).strip() else re.sub(r'\s+', ' ', str(value).strip())


def phone_key(value, source):
    normalized, quality = normalize_phone(value)
    if normalized:
        return normalized, quality
    if quality == 'missing':
        return None, quality
    original = str(value).strip().removesuffix('.0')
    if not re.fullmatch(r'[\d+()\s.\-]+', original):
        return None, quality
    digits = re.sub(r'\D', '', original)
    if source != 'master' and digits.startswith('249'):
        digits = digits[3:]
    return 'invalid_exact:' + digits, quality


def percentage(numerator, denominator):
    return round(100 * numerator / denominator, 2) if denominator else None


QUESTIONS = {
    'R1Q01': ('Residency status', 'Residency categories are available; exact questionnaire wording was not supplied.'),
    'R1Q02': ('Conditional yes/no item', 'Exact wording and eligibility rule unavailable. Do not assign a topic to this item.'),
    'R1Q03': ('Yes/no item', 'Exact wording unavailable. Do not interpret the yes/no result as a programme outcome.'),
    'R1Q04': ('Main livelihood category', 'Category interpretation from recorded answer labels; exact wording unavailable.'),
    'R1Q05': ('Spending priority', 'Topic inferred from the narrative report and answer labels; exact wording unavailable.'),
    'R1Q06': ('Reported income change', 'Reference report identifies this as income change; recall period and exact wording unavailable.'),
    'R1Q07': ('Reason for income increase', 'Skip-logic conflict: answers recorded for unchanged and decreased income. Not validated for programme reporting.'),
    'R1Q08': ('Reason for income decrease', 'Topic supported by answer labels; exact eligibility rule unavailable.'),
    'R1Q09': ('Yes/no item', 'Exact wording unavailable. Do not label this as water use or another specific topic.'),
    'R1Q10': ('Reported ease/difficulty item', 'Exact wording unavailable; service domain not established.'),
    'R1Q11': ('Yes/no item', 'Exact wording unavailable. Do not assign a specific service domain.'),
    'R1Q12': ('Reported ease/difficulty item', 'Exact wording unavailable; service domain not established.'),
    'R1Q13': ('Reported disease category', 'Self-reported answer categories, not diagnosed disease or attributable programme effects.'),
}


def build():
    profile()
    sources = load_sources()
    master, calls, responses = sources.values()
    original_calls = len(calls)
    source_columns = {'master': 'PhoneNumber', 'calls': 'Subscriber Phone', 'responses': 'Phone'}
    profile_data = {}
    for source, frame in sources.items():
        results = frame[source_columns[source]].map(lambda value: phone_key(value, source))
        frame['_key'] = results.map(lambda value: value[0])
        frame['_phone_quality'] = results.map(lambda value: value[1])
        profile_data[source] = {'rows': len(frame), 'distinct_keys': int(frame['_key'].nunique()),
                                'phone_quality': dict(Counter(frame['_phone_quality'])),
                                'exact_duplicate_rows': int(frame.drop(columns=['_key', '_phone_quality']).duplicated().sum())}
    if calls['Delivery ID'].isna().any() or calls['Delivery ID'].duplicated().any():
        raise ValueError('Delivery IDs require manual review before counting attempts.')
    if responses['_key'].isna().any() or responses['_key'].duplicated().any():
        raise ValueError('Completed-response key ambiguity: do not select a response arbitrarily.')
    mappings = {}
    mapping_rows = []
    pairs = [('State', 'State.1'), ('Gender', 'Gender.1'), ('Locality', 'Locality.1'), ('Community', 'Community.1'), ('Type of Support', 'Type of Support.1'), ('SupportProject', 'SupportProject.1')]
    for label, code in pairs:
        mappings[label] = {}
        for key, group in master.groupby(code, dropna=False):
            values = sorted({text(value) for value in group[label]})
            reliable = len(values) == 1 and values[0] != 'Unknown' and text(key) != 'Unknown'
            if reliable:
                mappings[label][text(key)] = values[0]
            mapping_rows.append({'attribute': label, 'code': text(key), 'labels': ' | '.join(values), 'reliable': reliable})
    all_keys = list(dict.fromkeys(key for frame in sources.values() for key in frame['_key'].dropna()))
    ids = {key: f'P{index + 1:05d}' for index, key in enumerate(all_keys)}
    for frame in sources.values():
        frame['person_id'] = frame['_key'].map(ids)
    master_groups = {key: group for key, group in master.groupby('_key')}
    call_groups = {key: group for key, group in calls.groupby('_key')}
    response_groups = {key: group for key, group in responses.groupby('_key')}
    persons = []
    conflicts = []
    for key in all_keys:
        mg = master_groups.get(key)
        cg = call_groups.get(key)
        rg = response_groups.get(key)
        person = {'person_id': ids[key], 'in_master': mg is not None, 'master_records': 0 if mg is None else len(mg),
                  'ambiguous_master_phone': mg is not None and len(mg) > 1, 'phone_valid': not key.startswith('invalid_exact:'),
                  'match_type': 'strict_normalized' if not key.startswith('invalid_exact:') else 'flagged_invalid_exact',
                  'response_complete': rg is not None, 'log_complete': False, 'started_proxy': False, 'intro_snapshot': False}
        for attribute in ['State', 'Gender', 'Locality', 'Community', 'Type of Support', 'SupportProject', 'YearofSupport', 'JointProgram', 'Cross-Pillar']:
            values = {text(value) for value in mg[attribute]} if mg is not None else set()
            if len(values) == 1:
                person[attribute] = next(iter(values))
            elif len(values) > 1:
                person[attribute] = 'Ambiguous master attribute'
                conflicts.append({'person_id': ids[key], 'attribute': attribute, 'issue': 'Multiple master values for one phone'})
            else:
                candidates = set()
                for group in [cg, rg]:
                    if group is not None and attribute in group:
                        for value in group[attribute].dropna():
                            mapped = mappings.get(attribute, {}).get(text(value))
                            if mapped:
                                candidates.add(mapped)
                person[attribute] = next(iter(candidates)) if len(candidates) == 1 else 'Unknown / unmatched'
        age = pd.to_numeric(mg['Age'], errors='coerce') if mg is not None else pd.Series(dtype=float)
        usable_age = age.loc[age.between(15, 100)]
        person['Age'] = float(usable_age.iloc[0]) if len(usable_age) == 1 else None
        person['Age group'] = ('15-24' if person['Age'] < 25 else '25-34' if person['Age'] < 35 else '35-44' if person['Age'] < 45 else '45-59' if person['Age'] < 60 else '60+') if person['Age'] is not None else 'Unknown / invalid'
        if cg is not None:
            person['log_complete'] = bool(cg['r1_completed_survey'].notna().any())
            person['started_proxy'] = bool(cg['R1Q01'].notna().any())
            person['intro_snapshot'] = bool(cg['r1_intro'].notna().any())
            for attribute in ['State', 'Gender', 'Locality', 'Community']:
                mapped = {mappings.get(attribute, {}).get(text(value)) for value in cg[attribute].dropna()}
                mapped.discard(None)
                if mg is not None and mapped and person[attribute] not in mapped:
                    conflicts.append({'person_id': ids[key], 'attribute': attribute, 'issue': 'Master versus mapped IVR attribute conflict'})
        persons.append(person)
    people = pd.DataFrame(persons)
    call_records = []
    for index, row in calls.iterrows():
        scheduled_date = pd.Timestamp(row['Scheduled Date']).strftime('%Y-%m-%d')
        scheduled_time = str(row['Scheduled Time'])
        hour = int(scheduled_time[:2])
        received_time = None if pd.isna(row['Received Time']) else str(row['Received Time'])
        call_records.append({'attempt_id': index + 1, 'person_id': row.person_id,
                             'date': scheduled_date, 'hour': hour, 'scheduled_time': scheduled_time,
                             'received_time': received_time, 'status': text(row['Call Status']),
                             'answered': text(row['Call Status']).startswith('Finished ('),
                             'hangup': text(row['Hangup Cause']),
                             'duration_seconds': None if pd.isna(row['Call Duration [s]']) else float(row['Call Duration [s]']),
                             'platform_call_attempts': int(row['Call Attempts']),
                             'prelaunch': scheduled_date < '2026-09-08'})
    attempts = pd.DataFrame(call_records)
    grouped = attempts.groupby('person_id').agg(attempts=('attempt_id', 'size'), reached=('answered', 'any'),
                                               answered_calls=('answered', 'sum'), first_call=('date', 'min'), last_call=('date', 'max'))
    people = people.merge(grouped, on='person_id', how='left', validate='one_to_one')
    people['attempts'] = people.attempts.fillna(0).astype(int)
    people['reached'] = people.reached.eq(True)
    people['answered_calls'] = people.answered_calls.fillna(0).astype(int)
    people['status_group'] = people.apply(lambda row: 'Completed response' if row.response_complete else 'Answered, no completed response' if row.reached else 'Called, never answered' if row.attempts else 'Not called', axis=1)
    answer_records = []
    for _, row in responses.iterrows():
        for question in QUESTIONS:
            if pd.notna(row[question]):
                answer = text(row[question])
                if answer.lower() in {'yes', 'no'}:
                    answer = answer.capitalize()
                answer_records.append({'person_id': row.person_id, 'question': question, 'answer': answer})
    answers = pd.DataFrame(answer_records)
    snapshots = []
    for key, group in call_groups.items():
        for question in QUESTIONS:
            values = {text(value) for value in group[question].dropna()}
            if len(values) > 1:
                raise ValueError('Inconsistent subscriber snapshot answers require adjudication.')
            if values:
                snapshots.append({'person_id': ids[key], 'question': question, 'answer': next(iter(values))})
    snapshots = pd.DataFrame(snapshots)
    master_export = master[['person_id', 'State', 'Gender', 'Locality', 'Community', 'Age', 'Type of Support', 'SupportProject', 'YearofSupport', 'JointProgram', 'Cross-Pillar']].copy()
    master_export.insert(0, 'master_row_id', range(1, len(master_export) + 1))
    for column in master_export:
        if column not in {'master_row_id', 'Age', 'person_id'}:
            master_export[column] = master_export[column].map(text)
    private = ROOT / 'private'
    private.mkdir(exist_ok=True)
    linkage = []
    for source, frame in sources.items():
        for index, row in frame.iterrows():
            linkage.append({'source': source, 'source_excel_row': index + 2, 'person_id': row.person_id,
                            'original_phone': row[source_columns[source]], 'standardized_phone': normalize_phone(row[source_columns[source]])[0],
                            'phone_quality': row['_phone_quality'], 'link_key': row['_key'], 'matched_master': row['_key'] in master_groups})
    pd.DataFrame(linkage).to_csv(private / 'phone_linkage_audit_DO_NOT_SHARE.csv', index=False)
    OUTPUT.mkdir(exist_ok=True)
    tables = {'persons': people, 'master_records': master_export, 'call_attempts': attempts, 'response_answers': answers,
              'subscriber_answer_snapshots': snapshots, 'label_mapping': pd.DataFrame(mapping_rows),
              'attribute_conflicts': pd.DataFrame(conflicts, columns=['person_id', 'attribute', 'issue'])}
    unmatched = people.loc[~people.in_master].copy()
    tables['unmatched_contacts'] = unmatched
    tables['completion_discrepancies'] = people.loc[people.log_complete != people.response_complete].copy()
    with sqlite3.connect(OUTPUT / 'analytical_model.sqlite') as database:
        for name, frame in tables.items():
            frame.to_csv(OUTPUT / (name + '.csv'), index=False)
            frame.to_sql(name, database, if_exists='replace', index=False)
        database.execute('CREATE UNIQUE INDEX IF NOT EXISTS person_key ON persons(person_id)')
        database.execute('CREATE INDEX IF NOT EXISTS call_person ON call_attempts(person_id)')
        database.execute('CREATE INDEX IF NOT EXISTS answer_person ON response_answers(person_id)')
    master_people = people.loc[people.in_master]
    called = people.loc[people.attempts > 0]
    reached = people.loc[people.reached]
    completed = people.loc[people.response_complete]
    quality = {
        'sources': profile_data,
        'master_rows': len(master), 'master_unique_keys': len(master_people),
        'master_valid_phones': int(master_people.phone_valid.sum()),
        'duplicate_master_phone_keys': int(master_people.ambiguous_master_phone.sum()),
        'calls': len(attempts), 'called': len(called), 'reached': len(reached),
        'answered_calls': int(attempts.answered.sum()), 'unanswered_calls': int((~attempts.answered).sum()),
        'raw_completed': len(completed), 'log_completed': int(people.log_complete.sum()),
        'started_proxy': int(people.started_proxy.sum()), 'intro_snapshot': int(people.intro_snapshot.sum()),
        'call_rows_matched_master': int(calls['_key'].isin(master_groups).sum()),
        'called_keys_matched_master': int(called.in_master.sum()), 'response_rows_matched_master': int(completed.in_master.sum()),
        'unmatched_called_keys': int((~called.in_master).sum()), 'unmatched_response_keys': int((~completed.in_master).sum()),
        'invalid_exact_call_rows_matched': int((calls['_key'].isin(master_groups) & calls['_key'].str.startswith('invalid_exact:')).sum()),
        'master_not_called': int((master_people.attempts == 0).sum()),
        'log_flags_not_in_response_file': int((people.log_complete & ~people.response_complete).sum()),
        'raw_completers_not_log_flagged': int((people.response_complete & ~people.log_complete).sum()),
        'prelaunch_attempts': int(attempts.prelaunch.sum()), 'prelaunch_contacts': int(attempts.loc[attempts.prelaunch, 'person_id'].nunique()),
        'prelaunch_completed': int(completed.first_call.lt('2026-09-08').sum()),
        'outside_09_20_scheduled_attempts': int((~attempts.hour.between(9, 19)).sum()),
        'mapping_issues': [row for row in mapping_rows if not row['reliable']],
        'attribute_conflicts': len(conflicts), 'age_invalid_or_missing': int(master_people.Age.isna().sum()),
        'income_q07_ineligible': int((responses.R1Q07.notna() & responses.R1Q06.ne('Increased')).sum()),
        'income_q08_ineligible': int((responses.R1Q08.notna() & responses.R1Q06.ne('Decreased')).sum()),
        'questions_answered_field_all_zero': bool(pd.to_numeric(calls['Survey Questions - Answered']).eq(0).all()),
        'platform_attempts_sum_not_valid': int(pd.to_numeric(calls['Call Attempts']).sum()),
        'rates': {
            'contact_rate': {'percent': percentage(len(reached), len(called)), 'numerator': len(reached), 'denominator': len(called), 'definition': 'Unique phones ever answered / unique phones called'},
            'answer_rate': {'percent': percentage(attempts.answered.sum(), len(attempts)), 'numerator': int(attempts.answered.sum()), 'denominator': len(attempts), 'definition': 'Answered call-log rows / all call-log rows'},
            'completion_called': {'percent': percentage(len(completed), len(called)), 'numerator': len(completed), 'denominator': len(called), 'definition': 'Unique completed-response phones / unique called phones'},
            'completion_reached': {'percent': percentage(len(completed.loc[completed.reached]), len(reached)), 'numerator': int(completed.reached.sum()), 'denominator': len(reached), 'definition': 'Completed-response phones ever answered / reached phones'},
            'completion_started_proxy': {'percent': percentage(len(completed), people.started_proxy.sum()), 'numerator': len(completed), 'denominator': int(people.started_proxy.sum()), 'definition': 'Completed-response phones / phones with Q01 snapshot (proxy, not event timestamps)'},
            'repeat_call_rate': {'percent': percentage(called.attempts.gt(1).sum(), len(called)), 'numerator': int(called.attempts.gt(1).sum()), 'denominator': len(called), 'definition': 'Phones with >1 observed log row / called phones'},
        },
        'average_observed_attempts': round(len(attempts) / len(called), 3),
    }
    assert len(attempts) == original_calls
    assert len(people) == len(all_keys) and people.person_id.is_unique
    assert attempts.person_id.isin(people.person_id).all() and answers.person_id.isin(people.person_id).all()
    assert completed.reached.all() and completed.started_proxy.all()
    assert len(called) == len(reached) + int((called.reached == False).sum())
    assert sum(people.attempts) == len(attempts)
    assert sum(people.answered_calls) == int(attempts.answered.sum())
    state_rows = []
    for attribute in ['State', 'Gender', 'Locality', 'Community', 'Type of Support', 'SupportProject', 'Age group']:
        for value, group in master_people.groupby(attribute):
            count_completed = int(group.response_complete.sum())
            state_rows.append({'attribute': attribute, 'category': value, 'master_records': int(group.master_records.sum()),
                               'master_phone_keys': len(group), 'called': int(group.attempts.gt(0).sum()),
                               'attempts': int(group.attempts.sum()), 'reached': int(group.reached.sum()),
                               'completed': count_completed, 'nonresponses': len(group) - count_completed,
                               'contact_rate_called': percentage(group.reached.sum(), group.attempts.gt(0).sum()),
                               'completion_rate_called': percentage(count_completed, group.attempts.gt(0).sum()),
                               'completion_rate_master': percentage(count_completed, len(group)),
                               'master_share': percentage(len(group), len(master_people)),
                               'respondent_share': percentage(count_completed, completed.in_master.sum()),
                               'share_difference_pp': round(100 * count_completed / completed.in_master.sum() - 100 * len(group) / len(master_people), 2),
                               'small_base': count_completed < 10})
    comparisons = pd.DataFrame(state_rows)
    comparisons.to_csv(OUTPUT / 'representativeness.csv', index=False)
    gender_state_rows = []
    for (state, gender), group in master_people.groupby(['State', 'Gender']):
        called_count = int(group.attempts.gt(0).sum())
        gender_state_rows.append({'state': state, 'gender': gender, 'master_phone_keys': len(group), 'called': called_count,
                                  'reached': int(group.reached.sum()), 'completed': int(group.response_complete.sum()),
                                  'contact_rate': percentage(group.reached.sum(), called_count) if called_count >= 10 else None,
                                  'completion_rate_called': percentage(group.response_complete.sum(), called_count) if called_count >= 10 else None})
    pd.DataFrame(gender_state_rows).to_csv(OUTPUT / 'gender_within_state.csv', index=False)
    pd.DataFrame([{'question': key, 'topic_label': title, 'interpretation_caveat': note} for key, (title, note) in QUESTIONS.items()]).to_csv(OUTPUT / 'question_dictionary.csv', index=False)
    survey_summaries = []
    answer_people = answers.merge(people[['person_id', 'State', 'Gender', 'Type of Support', 'in_master']], on='person_id', validate='many_to_one')
    for attribute in ['Overall', 'State', 'Gender', 'Type of Support']:
        partitions = [('All completed respondents', answer_people)] if attribute == 'Overall' else answer_people.groupby(attribute)
        for category, group in partitions:
            for question, question_answers in group.groupby('question'):
                denominator = len(question_answers)
                for answer, answer_group in question_answers.groupby('answer'):
                    survey_summaries.append({'attribute': attribute, 'category': category, 'question': question, 'answer': answer,
                                             'count': len(answer_group), 'nonmissing_item_base': denominator,
                                             'percent': percentage(len(answer_group), denominator) if denominator >= 10 else None,
                                             'small_base': denominator < 10, 'unweighted': True})
    pd.DataFrame(survey_summaries).to_csv(OUTPUT / 'survey_results.csv', index=False)
    repeat_rows = []
    for category in ['1', '2', '3', '4+']:
        group = called.loc[called.attempts.ge(4) if category == '4+' else called.attempts.eq(int(category))]
        repeat_rows.append({'attempt_band': category, 'phones': len(group), 'reached': int(group.reached.sum()), 'completed': int(group.response_complete.sum()), 'contact_rate': percentage(group.reached.sum(), len(group)), 'completion_rate': percentage(group.response_complete.sum(), len(group))})
    pd.DataFrame(repeat_rows).to_csv(OUTPUT / 'repeat_cohorts.csv', index=False)
    ordered = attempts.sort_values(['person_id', 'date', 'scheduled_time', 'attempt_id']).copy()
    ordered['sequence'] = ordered.groupby('person_id').cumcount() + 1
    ordered['previously_reached'] = ordered.groupby('person_id')['answered'].transform(lambda series: series.cummax().shift(fill_value=False))
    incremental = []
    for sequence, group in ordered.groupby('sequence'):
        eligible = group.loc[~group.previously_reached]
        incremental.append({'sequence': int(sequence), 'attempts': len(group), 'previously_unreached': len(eligible), 'newly_reached': int(eligible.answered.sum()), 'conditional_pickup_percent': percentage(eligible.answered.sum(), len(eligible))})
    pd.DataFrame(incremental).to_csv(OUTPUT / 'incremental_retry_reach.csv', index=False)
    attempts['weekday'] = pd.to_datetime(attempts.date).dt.day_name()
    for dimension in ['date', 'weekday', 'hour', 'status', 'hangup']:
        attempts.groupby(dimension).agg(attempts=('attempt_id', 'size'), answered=('answered', 'sum'), phones=('person_id', 'nunique')).reset_index().to_csv(OUTPUT / ('calls_by_' + dimension + '.csv'), index=False)
    report = pd.read_excel(ROOT / 'UNDP Sudan Farmers Survey - September 2026 Report.xlsx', header=None)
    report_values = {str(row[0]).strip(): row[1] for row in report.itertuples(index=False, name=None) if pd.notna(row[0]) and pd.notna(row[1])}
    reference = [
        ('Unique phones called', 'Total calls sent', len(called), 'Includes four pre-launch contacts; scheduled rows are not confirmed carrier-level retry events.'),
        ('Unique reached', 'Picked up', len(reached), 'Any Finished status, disjoint ever-reached classification.'),
        ('Never answered', 'Did not pick up', len(called) - len(reached), 'Called phones with no Finished status across any attempt.'),
        ('Intro snapshot', 'Listened to intro', int(people.intro_snapshot.sum()), 'Undated subscriber snapshot; not an intro-play event.'),
        ('Started proxy', 'Started survey', int(people.started_proxy.sum()), 'Q01 present, since started flag is entirely empty; not necessarily same report definition.'),
        ('Completed response records', 'Completed survey', len(completed), '116 response records; 133 log flags; no basis to manufacture the reported 117th response.'),
    ]
    reconciliation = [{'metric': name, 'reported': int(report_values[label]), 'recomputed': count, 'difference': count - int(report_values[label]), 'explanation': explanation} for name, label, count, explanation in reference]
    for question in QUESTIONS:
        snapshot_count = int(snapshots.question.eq(question).sum())
        reconciliation.append({'metric': question + ' subscriber answers', 'reported': int(report_values[question.replace('R1', '')]), 'recomputed': snapshot_count, 'difference': snapshot_count - int(report_values[question.replace('R1', '')]), 'explanation': 'Subscriber snapshots are not attempt-level responses; branching and snapshot scope prevent direct attrition inference.'})
    pd.DataFrame(reconciliation).to_csv(OUTPUT / 'report_reconciliation.csv', index=False)
    quality['reconciliation'] = reconciliation
    quality['repeat_cohorts'] = repeat_rows
    quality['incremental_reach'] = incremental
    quality['source_hashes'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in ROOT.iterdir() if path.suffix.lower() in {'.xlsx', '.docx'}}
    quality['call_match_rate_rows'] = percentage(quality['call_rows_matched_master'], len(calls))
    quality['call_match_rate_unique'] = percentage(quality['called_keys_matched_master'], len(called))
    quality['response_match_rate'] = percentage(quality['response_rows_matched_master'], len(responses))
    network_flags = attempts.loc[~attempts.answered & attempts.hangup.isin(['DESTINATION_OUT_OF_ORDER', 'UNALLOCATED_NUMBER', 'INVALID_NUMBER_FORMAT'])]
    quality['failed_suspect_number_rows'] = len(network_flags)
    quality['failed_suspect_number_contacts'] = int(network_flags.person_id.nunique())
    quality['failed_suspect_number_contacts_ever_reached'] = int(people.loc[people.person_id.isin(network_flags.person_id), 'reached'].sum())
    (OUTPUT / 'data_quality.json').write_text(json.dumps(quality, indent=2), encoding='utf-8')
    build_report(quality, comparisons, responses, incremental)
    dashboard = ROOT / 'dashboard'
    dashboard.mkdir(exist_ok=True)
    def records(frame):
        return json.loads(frame.to_json(orient='records'))
    payload = {'people': records(people), 'calls': records(attempts.drop(columns=['received_time', 'duration_seconds', 'platform_call_attempts'])),
               'answers': records(answers),
               'question_presence': records(snapshots[['person_id', 'question']].drop_duplicates()),
               'quality': quality,
               'questions': {key: {'title': title, 'note': note} for key, (title, note) in QUESTIONS.items()}}
    (dashboard / 'data.js').write_text('const DATA = ' + json.dumps(payload, separators=(',', ':')) + ';\n', encoding='utf-8')
    obtain_map(dashboard)
    print(json.dumps({key: value for key, value in quality.items() if key not in ['source_hashes', 'reconciliation', 'mapping_issues']}, indent=2))


def obtain_map(dashboard):
    destination = dashboard / 'map.js'
    if destination.exists():
        return
    try:
        api = 'https://www.geoboundaries.org/api/current/gbOpen/SDN/ADM1/'
        request = urllib.request.Request(api, headers={'User-Agent': 'UNDP-survey-local-analysis/1.0'})
        metadata = json.load(urllib.request.urlopen(request, timeout=30))
        geometry = json.load(urllib.request.urlopen(metadata.get('simplifiedGeometryGeoJSON', metadata['gjDownloadURL']), timeout=60))
        map_data = {'features': geometry['features'], 'source': api, 'license': metadata.get('boundaryLicense', 'See source'), 'year': metadata.get('boundaryYearRepresented', 'Unknown')}
    except Exception as error:
        print('State boundary download unavailable:', type(error).__name__)
        map_data = {'features': [], 'source': 'Unavailable', 'license': '', 'year': ''}
    destination.write_text('const MAP_DATA = ' + json.dumps(map_data, separators=(',', ':')) + ';\n', encoding='utf-8')


def build_report(quality, comparisons, responses, incremental):
    states = comparisons.loc[comparisons.attribute.eq('State')].sort_values('completed', ascending=False)
    genders = comparisons.loc[comparisons.attribute.eq('Gender')]
    lines = ['# Sudan farmers IVR survey: decision brief', '', 'Analysis date: 4 October 2026. Source export: 2 October. All supplied log rows included; scheduled dates 2-29 September, with nine rows preceding the reported 8 September launch.', '',
             '## Executive findings', '',
             f"- {quality['calls']:,} observed call-log rows cover {quality['called']:,} phone keys. {quality['reached']:,} ever answered ({quality['rates']['contact_rate']['percent']}% of called keys); {quality['answered_calls']} answered rows ({quality['rates']['answer_rate']['percent']}% of log rows). These are contact keys, not proven unique individuals.",
             f"- {quality['raw_completed']} completed response records imply {quality['rates']['completion_called']['percent']}% of called keys and {quality['rates']['completion_reached']['percent']}% of reached keys. {quality['reached']-quality['raw_completed']} reached contacts have no completed response record; {quality['called']-quality['reached']} called contacts never answered. {quality['master_not_called']} master contacts have no call row.",
             f"- Completion-source discrepancy: {quality['log_completed']} log snapshot flags, {quality['raw_completed']} raw records, 117 reported. The {quality['log_flags_not_in_response_file']} flagged-only contacts are listed in completion_discrepancies.csv. Completion timestamps are unavailable.",
             f"- Linkage: {quality['call_rows_matched_master']:,}/{quality['calls']:,} call rows ({quality['call_match_rate_rows']}%), {quality['called_keys_matched_master']:,}/{quality['called']:,} called keys ({quality['call_match_rate_unique']}%), and {quality['response_rows_matched_master']}/{quality['raw_completed']} response records ({quality['response_match_rate']}%) match the master. {quality['invalid_exact_call_rows_matched']} matched call rows use flagged exact malformed-number matches, NOT validated Sudan phone numbers.", '',
             '## Geographic and demographic selection', '',
             'Comparisons below use only master-linked respondents (n=113); the three unmatched raw completers are excluded from master representativeness, not from overall survey answers.', '',
             '| State | Master phone keys | Called | Reached | Completed | Master share | Respondent share | Difference (pp) |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for _, row in states.iterrows():
        lines.append(f"| {row.category} | {row.master_phone_keys} | {row.called} | {row.reached} | {row.completed} | {row.master_share}% | {row.respondent_share}% | {row.share_difference_pp:+.2f} |")
    lines.extend(['', 'River Nile is overrepresented and Gedaref underrepresented in the observed completed sample relative to this programme roster. This roster is not a population census of Sudanese farmers. Unweighted answers must not be generalized to all farmers.', ''])
    for _, row in genders.iterrows():
        lines.append(f"- {row.category}: {row.master_phone_keys} master keys; {row.called} called, {row.reached} reached, {row.completed} completed; contact {row.contact_rate_called}% of called, completion {row.completion_rate_called}% of called. Master share {row.master_share}%, respondent share {row.respondent_share}%.")
    lines.extend(['', 'Gender interpretation: the aggregate female contact gap is not uniform across states. In Gedaref, female reach is 97/758 (12.8%) versus male reach 83/857 (9.7%); female completion is 14/758 (1.85%) versus 6/857 (0.70%). In River Nile, female reach is 79/138 (57.2%) versus male reach 396/654 (60.6%), while female completion is 14/138 (10.1%) versus 52/654 (8.0%). Geographic composition can contribute to the aggregate gender gap; no adjusted causal gender effect is established. See gender_within_state.csv.', ''])
    lines.extend(['', 'The representativeness.csv table extends these comparisons to locality, community, support type, project and age bands. Differences are descriptive; neither gender nor state effects are causal. Missing/invalid ages remain a separate category.', '', '## Substantive survey signals', '',
                  f"- Income decreased: {int(responses.R1Q06.eq('Decreased').sum())}/116 ({percentage(responses.R1Q06.eq('Decreased').sum(),116)}%). Unweighted self-report, unknown recall period.",
                  f"- Spending categories: Food {int(responses.R1Q05.eq('Food').sum())}/116; Repaying Debt {int(responses.R1Q05.eq('Repaying Debt').sum())}/116. The exact wording/multiple-choice constraints were not supplied.",
                  f"- Q07 has {quality['income_q07_ineligible']} answers from respondents who did not report increased income. All 34 unchanged-income respondents answered Q07, as did one decreased-income respondent. Do not publish Q07 as an eligible-population indicator until Viamo verifies routing.",
                  '- The paired question-text columns agree after case normalization. This is duplicate storage, not a second response. Q02/Q07/Q08 are potentially branched; missing values are not automatically refusals or dropouts.',
                  '- Exact questionnaire/audio and routing rules are absent. Several yes/no and access items cannot be given a reliable substantive title; these remain labelled with their question ID and neutral answer description.', '',
                  '## Calling operations and retries', '',
                  f"- Mean observed rows per called phone: {quality['average_observed_attempts']}; repeat-call rate {quality['rates']['repeat_call_rate']['percent']}% of called phones. The platform Call Attempts field sums to {quality['platform_attempts_sum_not_valid']:,}, but its event/retry semantics are not documented. Do not sum it as physical dial attempts.",
                  '- Scheduled hours, not actual failed-call dial times, drive time comparisons. Calls cluster at 09:00, 13:00 and 19:00; this is compatible with batch scheduling, not evidence that these times are optimal. Received times exist for answered calls and some errors, not failed no-answer calls.',
                  '- Nine pre-launch rows cover four contacts; three are raw completed respondents. The report launch date and export scope therefore differ. Excluding pre-launch rows must not remove these facts from the audit.',
                  '- Final-attempt cohorts suffer selection: unsuccessful phones are preferentially retried. Use incremental first-reach yield among previously unreached phones; completion is undated and cannot be attributed to a retry or calling hour.', '',
                  '| Observed sequence | Previously unreached at this attempt | Newly reached | Conditional pickup |', '|---|---:|---:|---:|'])
    for row in incremental:
        lines.append(f"| {row['sequence']} | {row['previously_unreached']} | {row['newly_reached']} | {row['conditional_pickup_percent']}% |")
    lines.extend(['', f"The {quality['failed_suspect_number_rows']} failed rows with disconnected/unallocated/malformed-number causes correspond to {quality['failed_suspect_number_contacts']} distinct contacts, of whom {quality['failed_suspect_number_contacts_ever_reached']} were reached on another logged row. A network cause is an operational flag, not proof that a phone is permanently dead. The narrative recommendation confuses attempts with numbers. Verify contacts before deletion.", '',
                  '## Priority actions', '',
                  '1. Ask Viamo to reconcile 116 raw completions, 133 snapshot flags and 117 reported; obtain one versioned export with questionnaire, routing, event timestamps, retry semantics and test-contact markers.',
                  '2. Field-verify the 46 malformed master phone values, 11 unmatched called keys and nine uncalled master keys. Retain an audit; do not invent missing digits or remove contacts solely on one carrier cause.',
                  '3. Concentrate sensitization and alternate-contact verification on underrepresented Gedaref and female beneficiaries. Establish state/gender completion quotas informed by the master roster and contact costs.',
                  '4. Randomize comparable unreached contacts across allowable time windows and attempt limits; stratify by state/gender. Measure incremental reach, verified completion, cost and complaints per allocated contact.',
                  '5. Obtain the exact intro, consent audio and question routing. Repair Q06/Q07 before interpreting apparent financial-question attrition. Pilot a shorter intro and question-order changes, then compare with randomized controls.',
                  '6. Clarify whether Round 2 targets verified completers, all reached contacts, or a fresh representative sample. Fix the panel definition before scheduling follow-up.',
                  '7. Share aggregated dashboard tables only; keep the source files, detailed model and private linkage audit in access-controlled storage. If exporting publicly, apply additional disclosure review to small geographic cells.', '',
                  '## Definitions and limitations', '',
                  '- Targeted: 3,002 observed called keys is a proxy; no independent target-allocation list exists. Master roster contains 3,000 rows/keys, not 3,002.',
                  '- Reached: at least one Finished (complete) or Finished (incomplete) row. Finished (complete) means natural call end, not survey completion.',
                  '- Started: any Q01 subscriber snapshot, a proxy because all r1_started_survey fields are empty. Intro is another undated subscriber flag.',
                  '- Completed: unique phone in the supplied completed-response file. Abandoned: started proxy without a completed record; distinguish from answered-without-completion and report both.',
                  '- Never reached in the master includes uncalled contacts and called-never-answered contacts; in the called funnel it means only called-never-answered.',
                  '- Invalid phones can match only through exact digits after documented source prefix removal. They remain invalid; no missing-digit inference or fuzzy matching is used.',
                  '- One phone may represent more than one beneficiary. Current normalized/flagged-exact master keys have no duplicates; the model nevertheless separates master records from contact keys and flags ambiguous attributes.',
                  '- Labels use master values preferentially. Only one-to-one code mappings backfill unmatched contacts. A globally conflicting locality code is withheld rather than guessed; a gender code with an unknown label is not de-anonymized.',
                  '- No causal claims, population weighting or national farmer inference. IVR selection, mobile access, language, consent and completion barriers are not independently measured.',
                  '- Date/outcome filters select calling exposure cohorts. Completion and answers are lifetime-in-export snapshots within that cohort, NOT completions occurring in the selected window. Date/outcome filters restrict the master comparison to exposed contacts; full-roster comparison requires unrestricted exposure filters.',
                  '- Small bases (<10) retain counts but suppress displayed rates for subgroup survey results. Counts may still be sensitive; local internal use only.',
                  '- Maps use geoBoundaries open administrative boundaries, not an official UN boundary endorsement. Labels are mapped only with explicit spelling aliases. Unknown states remain in tables.', '',
                  '## Reproducibility and data model', '',
                  'Run `python analyze.py`, then `python -m unittest test_analysis -v`. Original inputs are never edited. SHA-256 source hashes are recorded in data_quality.json.',
                  'persons: one contact key; master_records: one original beneficiary row; call_attempts: one unique Delivery ID row; response_answers: one respondent/question; subscriber_answer_snapshots: one contact/question, not timestamped events. All child joins use person_id; master-to-contact is many-to-one. No join expands call or response rows.',
                  'Private phone linkage (private/phone_linkage_audit_DO_NOT_SHARE.csv) is necessary for corrections and explicitly must not be distributed. All analytical tables omit phone numbers, names, subscriber IDs and delivery IDs. Pseudonymous detailed records are still sensitive and should remain local.',
                  'The SQLite model is reproducible and the CSVs support further analysis. source_profile.json records source-level distributions; report_reconciliation.csv preserves every compared report figure.', '',
                  'Source roles: the September activity DOCX supplies programme context, launch and status rubric; master supplies beneficiary labels; call logs supply exposures/statuses; raw completed responses supply primary completions/answers; the September XLSX supplies reference funnel and question counts. Neither report overrides source facts.'])
    (OUTPUT / 'decision_brief.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()