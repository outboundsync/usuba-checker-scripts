#!/usr/bin/env python3
"""Sealed-set overlap by IDENTIFIER ONLY. Reads only the 'id' field of the Dell key (never labels) and plugin URLs/repos of the HANCORE holdout."""
import json,sys
W={'akshar.radio-atlas':'aksharp5/omarchy-radio-atlas','slcode777.omagotchi':'slcode777/omagotchi','io.github.thisisgm.omapods':'thisisgm/omarchy-pods','robzolkos.github':'robzolkos/omarchy-github'}
R='/workspace/wt-retrain-v2/'
dell=[json.loads(l)['id'] for l in open(R+'functest/dell_ground_truth.jsonl')]
ho=[json.loads(l)['repo'].lower() for l in open(R+'eval/hancore_holdout/manifest.jsonl')]
for pid,repo in W.items():
    author=pid.split('.')[2] if pid.startswith('io.github.') else pid.split('.')[0]
    print(pid,'| dell exact:',pid in dell,'| dell same-author/tail:',[i for i in dell if i!=pid and author in i.split('.')[:3]],'| holdout repo:',repo in ho)
print('sibling thisisgm ids in dell key:',[i for i in dell if 'thisisgm' in i])
