import unittest
import hashlib
import json
from pathlib import Path

import pandas as pd

from analyze import normalize_phone, phone_key


class PhoneTests(unittest.TestCase):
    def test_equivalent_sudan_formats(self):
        variants = ['0912345678', '912345678', '+249912345678', '00249912345678', '249912345678.0', '0 912-345-678']
        self.assertEqual({normalize_phone(value)[0] for value in variants}, {'+249912345678'})

    def test_missing_and_foreign_numbers_are_not_guessed(self):
        self.assertEqual(normalize_phone(None), (None, 'missing'))
        self.assertIsNone(normalize_phone('+254712345678')[0])
        self.assertIsNone(normalize_phone('91234')[0])
        self.assertIsNone(normalize_phone('912345678ext')[0])

    def test_malformed_exact_link_is_not_promoted_to_valid(self):
        master_key, master_quality = phone_key('91234567', 'master')
        call_key, call_quality = phone_key('24991234567', 'calls')
        self.assertEqual(master_key, call_key)
        self.assertTrue(master_key.startswith('invalid_exact:'))
        self.assertNotEqual(master_quality, 'normalized')
        self.assertNotEqual(call_quality, 'normalized')

    def test_foreign_prefix_is_not_removed(self):
        self.assertNotEqual(phone_key('+254712345678', 'calls')[0], phone_key('712345678', 'master')[0])


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent
        cls.output = cls.root / 'outputs'
        if not (cls.output / 'data_quality.json').exists():
            raise unittest.SkipTest('Run python analyze.py before model regression tests.')
        cls.quality = json.loads((cls.output / 'data_quality.json').read_text())
        cls.people = pd.read_csv(cls.output / 'persons.csv')
        cls.calls = pd.read_csv(cls.output / 'call_attempts.csv')
        cls.answers = pd.read_csv(cls.output / 'response_answers.csv')
        payload_text = (cls.root / 'dashboard' / 'data.js').read_text()
        cls.payload = json.loads(payload_text.removeprefix('const DATA = ').strip().removesuffix(';'))

    def test_actual_source_reconciliation(self):
        expected = {'master_rows': 3000, 'called': 3002, 'calls': 4118, 'reached': 804, 'answered_calls': 812,
                    'raw_completed': 116, 'log_completed': 133, 'call_rows_matched_master': 4086,
                    'called_keys_matched_master': 2991, 'response_rows_matched_master': 113,
                    'invalid_exact_call_rows_matched': 57, 'master_not_called': 9}
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(self.quality[key], value)

    def test_child_keys_and_grains(self):
        self.assertTrue(self.people.person_id.is_unique)
        self.assertTrue(self.calls.attempt_id.is_unique)
        self.assertFalse(self.answers.duplicated(['person_id', 'question']).any())
        self.assertTrue(self.calls.person_id.isin(self.people.person_id).all())
        self.assertTrue(self.answers.person_id.isin(self.people.person_id).all())
        joined = self.calls.merge(self.people, on='person_id', validate='many_to_one')
        self.assertEqual(len(joined), 4118)
        self.assertEqual(self.people.attempts.sum(), len(self.calls))
        self.assertEqual(self.people.answered_calls.sum(), self.calls.answered.sum())

    def test_funnel_and_denominators(self):
        completers = self.people.loc[self.people.response_complete]
        self.assertTrue(completers.reached.all())
        self.assertTrue(completers.started_proxy.all())
        self.assertEqual(len(completers), 116)
        self.assertEqual(self.calls.answered.sum() + (~self.calls.answered).sum(), len(self.calls))
        for value in self.quality['rates'].values():
            self.assertLessEqual(value['numerator'], value['denominator'])
            self.assertAlmostEqual(value['percent'], 100 * value['numerator'] / value['denominator'], places=2)
        incremental = self.quality['incremental_reach']
        self.assertEqual(sum(row['newly_reached'] for row in incremental), 804)

    def test_snapshot_and_report_conflicts_are_not_hidden(self):
        self.assertEqual(self.quality['log_flags_not_in_response_file'], 17)
        self.assertEqual(self.quality['income_q07_ineligible'], 35)
        self.assertEqual(self.quality['prelaunch_completed'], 3)
        self.assertEqual(self.quality['failed_suspect_number_contacts'], 317)
        self.assertEqual(self.quality['failed_suspect_number_contacts_ever_reached'], 16)
        self.assertEqual(self.quality['reconciliation'][5]['reported'], 117)
        self.assertEqual(self.quality['reconciliation'][5]['recomputed'], 116)

    def test_no_direct_identifiers_in_analytical_tables(self):
        forbidden = {'phone', 'phonenumber', 'subscriber phone', 'name', 'subscriber id', 'delivery id', 'link_key', 'original_phone', 'standardized_phone'}
        for path in self.output.glob('*.csv'):
            columns = set(pd.read_csv(path, nrows=0).columns.str.lower())
            self.assertFalse(columns & forbidden, str(path))
        public = (self.root / 'dashboard' / 'data.js').read_text()
        self.assertNotIn('+249', public)
        self.assertNotIn('invalid_exact:', public)

    def test_inputs_are_unchanged(self):
        for name, digest in self.quality['source_hashes'].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest)

    def test_small_survey_bases_withhold_percentages(self):
        results = pd.read_csv(self.output / 'survey_results.csv')
        self.assertTrue(results.loc[results.nonmissing_item_base.lt(10), 'percent'].isna().all())

    def test_question_presence_payload_excludes_answer_text(self):
        presence = pd.DataFrame(self.payload['question_presence'])
        self.assertEqual(set(presence.columns), {'person_id', 'question'})
        self.assertEqual(presence.person_id.nunique(), 220)
        expected = {'R1Q01': 220, 'R1Q02': 35, 'R1Q03': 191, 'R1Q04': 181, 'R1Q05': 168,
                    'R1Q06': 160, 'R1Q07': 62, 'R1Q08': 92, 'R1Q09': 146, 'R1Q10': 141,
                    'R1Q11': 138, 'R1Q12': 134, 'R1Q13': 133}
        observed = presence.groupby('question').person_id.nunique().to_dict()
        self.assertEqual(observed, expected)

    def test_unconditional_checkpoint_losses_are_reproducible(self):
        presence = pd.DataFrame(self.payload['question_presence'])
        recorded = set(zip(presence.person_id, presence.question))
        started = {person_id for person_id, question in recorded if question == 'R1Q01'}
        transitions = [('R1Q03', 'R1Q04'), ('R1Q04', 'R1Q05'), ('R1Q05', 'R1Q06'),
                       ('R1Q09', 'R1Q10'), ('R1Q10', 'R1Q11'), ('R1Q11', 'R1Q12'), ('R1Q12', 'R1Q13')]
        lost = {f'{first}->{second}': sum((person_id, first) in recorded and (person_id, second) not in recorded for person_id in started)
                for first, second in transitions}
        self.assertEqual(lost, {'R1Q03->R1Q04': 10, 'R1Q04->R1Q05': 13, 'R1Q05->R1Q06': 8,
                                'R1Q09->R1Q10': 5, 'R1Q10->R1Q11': 3, 'R1Q11->R1Q12': 4, 'R1Q12->R1Q13': 1})


if __name__ == '__main__':
    unittest.main()