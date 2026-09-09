#!/usr/bin/env python3
import argparse,json,sqlite3
from pathlib import Path
from query import query
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',required=True); a=ap.parse_args(); c=sqlite3.connect(f"file:{Path(a.db).resolve()}?mode=ro",uri=True)
    try:
        r=query(c,'42','653'); assert r['status']=='EXACT',r; assert r['curve'][0]['fraction']=='1/1',r; assert r['north']=='42' and r['south']=='653',r
        count=c.execute('SELECT COUNT(*) FROM exact_rows').fetchone()[0]; assert count>0
        overlap=c.execute('SELECT COUNT(*) FROM exact_rows e JOIN deferred_rows d USING(state_id)').fetchone()[0]; assert overlap==0
    finally:c.close()
    print(json.dumps({'status':'GREEN','sample_status':r['status'],'exact_rows':count},sort_keys=True))
if __name__=='__main__':main()
