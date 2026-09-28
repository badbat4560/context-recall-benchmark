import unittest
import benchmark as b

class ProtocolTests(unittest.TestCase):
    def test_exact_reconstruction(self):
        data=b.dataset();db,_=b.prepare(data)
        self.assertEqual([r[0] for r in db.execute('SELECT exact FROM segments ORDER BY ordinal')],[m['content'] for m in data['messages']])
    def test_correction_evidence_points_to_new_revision(self):
        data=b.dataset();case=next(c for c in data['questions'] if c['id']=='update')
        self.assertIn('now 7',data['messages'][case['evidence_ordinal']]['content'])
    def test_scorer_rejects_partial_hash_and_old_value(self):
        self.assertFalse(b.correct('b794a823','b794a823'*8))
        self.assertFalse(b.correct('3','7'))
        self.assertFalse(b.correct('The answer is 7','7'))
        self.assertTrue(b.correct(' NO. ','no'))
    def test_cosine_rejects_bad_dimensions(self):
        with self.assertRaises(ValueError):b.cosine([1],[1,2])
        with self.assertRaises(ValueError):b.cosine([0],[1])
        self.assertAlmostEqual(b.cosine([1,0],[1,0]),1)
    def test_missing_usage_is_not_zero(self):
        case={'expected':'x','evidence_at_5':True,**{a:{'answer':'x'} for a in ('full','handoff_only','recall')}}
        self.assertIsNone(b.summarize({'cases':[case]})['prompt_token_reduction_pct'])

if __name__=='__main__':unittest.main()
