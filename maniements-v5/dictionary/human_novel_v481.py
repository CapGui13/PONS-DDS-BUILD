#!/usr/bin/env python3
from __future__ import annotations

import human_novel_v48 as v48

# Fast review pool: still completely absent from the reviewed corpus, but small
# enough to return a human-facing batch quickly. No human answer is supplied.
v48.POOL=[
 ('N12','AQT84','632',4),
 ('N13','AJ984','Q32',4),
 ('N14','KJT84','A32',4),
 ('N15','KQ984','J32',4),
 ('N16','AQJ84','632',4),
 ('N17','AK984','Q32',4),
 ('N21','A9854','K32',4),
 ('N22','K9854','A32',4),
 ('N23','QJ854','A32',4),
 ('N24','AJ854','K32',4),
 ('N25','AQ854','T32',4),
 ('N26','KQ854','J32',4),
]

if __name__=='__main__':
    v48.main()
