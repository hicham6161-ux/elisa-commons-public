import io, unittest, zipfile
from probe_g0 import parse_form, inspect_tick_csv, sha256, YEAR, MONTH

class DataGateTests(unittest.TestCase):
    def form(self, **kwargs):
        fields={'tk':'t'*16, 'date':str(YEAR), 'datemonth':f'{YEAR}{MONTH:02d}', 'platform':'ASCII','timeframe':'T','fxpair':'EURUSD'}
        fields.update(kwargs)
        return '<form id="file_down">'+''.join(f'<input name="{k}" id="{k}" value="{v}">' for k,v in fields.items())+'</form>'
    def test_valid_form(self):
        d=parse_form(self.form(),'EURUSD');self.assertEqual(d['timeframe'],'T')
    def test_wrong_symbol(self):
        with self.assertRaises(ValueError):parse_form(self.form(fxpair='GBPUSD'),'EURUSD')
    def test_absent_token(self):
        with self.assertRaises(ValueError):parse_form('<html>no login</html>','EURUSD')
    def test_utc_and_quotes(self):
        data=b'20260812 100001001,1.1000,1.1002,0\n20260812 100002002,1.1001,1.1003,0\n'
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('EURUSD.csv',data)
        b.seek(0)
        with zipfile.ZipFile(b) as z:res=inspect_tick_csv(z)
        self.assertEqual(res['ticks'],2);self.assertEqual(res['crossed_bidask_rows'],0)
        self.assertTrue(res['first_utc'].startswith('2026-08-12T15:00:01.001'))
        self.assertEqual(res['csv_sha256'],sha256(data))
    def test_crossed(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('EURUSD.csv',b'20260812 100001001,1.1002,1.1000,0\n')
        b.seek(0)
        with zipfile.ZipFile(b) as z:res=inspect_tick_csv(z)
        self.assertEqual(res['crossed_bidask_rows'],1)
if __name__=='__main__':unittest.main()