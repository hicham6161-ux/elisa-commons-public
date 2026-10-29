import unittest
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_index as main

class TestCloseMomentum(unittest.TestCase):
    def test_long_net_under_gross(self):
        self.assertLess(main.pnl(100,100.2,1,10),main.pnl(100,100.2,1,0))
    def test_short_direction(self):
        self.assertGreater(main.pnl(100,99,-1,0),0)
        self.assertLess(main.pnl(100,101,-1,0),0)
    def test_cost_effect_same_price(self):
        self.assertAlmostEqual(main.pnl(100,100,1,10),-0.02)
        self.assertAlmostEqual(main.pnl(100,100,-1,10),-0.02)
    def test_stress_cost(self):
        self.assertLess(main.pnl(100,100.2,1,15),main.pnl(100,100.2,1,10))
    def test_no_free_sign_change(self):
        self.assertGreater(main.pnl(100,101,1,10),main.pnl(100,101,-1,10))
    def build_session(self,day,close_cutoff,entry=101.0,exit=101.3):
        # Synthetic session made exclusively from fixed prior values.
        start=dt.datetime.combine(day,dt.time(9,30),tzinfo=main.EASTERN)
        d={}
        for j in range(78):
            t=start+dt.timedelta(minutes=5*j)
            local=t.strftime('%H:%M')
            op=101.0 if local!='15:35' else entry
            cl=101.0 if local!='15:25' and local!='15:55' else (close_cutoff if local=='15:25' else exit)
            d[local]={'open':op,'close':cl,'high':max(op,cl),'low':min(op,cl),'source_utc':t.astimezone(main.UTC).isoformat()}
        return d
    def test_signal_uses_previous_session(self):
        p=self.build_session(dt.date(2026,9,30),100.0,exit=100.0)
        c=self.build_session(dt.date(2026,10,1),102.0)
        rows, _=main.build_ledger('SPY',{'2026-09-30':p,'2026-10-01':c})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['decision'],'LONG')
        self.assertEqual(rows[0]['entry_et'],'15:35')
    def test_close_signal_not_future(self):
        p=self.build_session(dt.date(2026,9,30),100.0,exit=100.0)
        c=self.build_session(dt.date(2026,10,1),102.0,exit=98.0)
        rows,_=main.build_ledger('QQQ',{'2026-09-30':p,'2026-10-01':c})
        self.assertEqual(rows[0]['decision'],'LONG')
        self.assertLess(rows[0]['gross_usd'],0)
    def test_even_same_flat(self):
        p=self.build_session(dt.date(2026,9,30),100.0,exit=101.0)
        c=self.build_session(dt.date(2026,10,1),101.0,exit=99.0)
        rows,_=main.build_ledger('SPY',{'2026-09-30':p,'2026-10-01':c})
        self.assertEqual(rows[0]['decision'],'WAIT')
        self.assertIsNone(rows[0]['net_usd'])

if __name__=='__main__': unittest.main()
