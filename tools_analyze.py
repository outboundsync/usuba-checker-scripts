import json,os,re,subprocess,glob,collections
S='sources'; cands={p['id']:p for p in json.load(open(f'{S}/candidates.json'))}
cc=dict(l.strip().split('\t') for l in open(f'{S}/commit_counts.tsv'))
def lic_text(t):
    s=re.sub(r'\s+',' ',t).lower(); h=s[:400]
    if 'gnu affero' in h: return 'AGPL-3.0'
    if 'gnu lesser' in h: return 'LGPL'
    if 'gnu general public license' in h: return 'GPL-3.0' if 'version 3' in s else 'GPL-2.0' if 'version 2' in s else 'GPL'
    if 'mozilla public license' in h: return 'MPL-2.0'
    if 'apache license' in s and 'version 2.0' in s: return 'Apache-2.0'
    if 'polyform' in s or 'noncommercial' in s: return 'NONCOMMERCIAL'
    if 'permission is hereby granted, free of charge' in s and 'the above copyright notice and this permission notice shall be included' in s: return 'MIT'
    if 'permission to use, copy, modify, and/or distribute' in s or ('permission to use, copy, modify, and distribute' in s and 'isc' in s): return 'ISC'
    if 'redistribution and use in source and binary forms' in s: return 'BSD-3-Clause' if 'neither the name' in s or 'endorse or promote' in s else 'BSD-2-Clause'
    if 'unlicense' in s or 'released into the public domain' in s: return 'Unlicense'
    return 'UNKNOWN'
PERM={'MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause','ISC','MPL-2.0'}
rows=[]
for d in sorted(glob.glob(f'{S}/repos/*')):
    pid=os.path.basename(d); p=cands[pid]
    sha=subprocess.run(['git','-C',d,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    lf=[f for f in os.listdir(d) if re.match(r'(LICEN[SC]E|COPYING)(\.|$)',f,re.I)]
    lt=open(os.path.join(d,lf[0]),errors='ignore').read() if lf else ''
    lic=lic_text(lt) if lf else 'NONE'
    cr=[l.strip() for l in lt.splitlines() if re.match(r'\s*(copyright|\(c\))',l,re.I) and not re.search(r'copyright (notice|holder|owner)',l,re.I)][:2]
    mans=[m for m in glob.glob(d+'/**/manifest.json',recursive=True) if '/.git/' not in m and '/node_modules/' not in m]
    mans=[m for m in mans if 'schemaVersion' in open(m,errors='ignore').read()]
    mlic=[];vres=[]
    for m in mans:
        try: mlic.append(json.load(open(m)).get('license'))
        except: mlic.append('BADJSON')
        r=subprocess.run(['bash','validator/omarchy-plugin-validate',os.path.dirname(m)],capture_output=True,text=True)
        vres.append('pass' if r.returncode==0 else r.stderr.strip().split(': ',1)[-1][:80])
    pj=os.path.join(d,'package.json'); plic=json.load(open(pj)).get('license') if os.path.exists(pj) else None
    vend=[]
    for root,ds,fs in os.walk(d):
        if '.git' in ds: ds.remove('.git')
        rel=os.path.relpath(root,d)
        for x in ds:
            if x.lower() in ('vendor','third_party','third-party','node_modules','external','lib3p','fonts'): vend.append(os.path.join(rel,x))
        for f in fs:
            if rel!='.' and re.match(r'(LICEN[SC]E|COPYING|NOTICE)',f,re.I): vend.append(os.path.join(rel,f))
            if f.endswith(('.min.js','.ttf','.otf','.woff2')): vend.append(os.path.join(rel,f))
    mism=[x for x in set(mlic+[plic]) if x and lic in PERM|{'NONE'} and x not in (lic,) and not (lic=='MIT' and x=='MIT')]
    if lic in PERM and not cr: bucket='exclude-unclear (no copyright line)'
    elif lic in PERM and mism: bucket='exclude-unclear (license field mismatch)' if any(x and x!=lic for x in mism) else 'train'
    elif lic in PERM: bucket='train'
    elif lic=='NONE': bucket='reference-only (no license)'
    elif lic in('GPL-3.0','GPL-2.0','GPL','AGPL-3.0','LGPL'): bucket='reference-only (copyleft)'
    else: bucket='exclude (custom/unclear)'
    FORKS={'mscurtescu.island-bar','voyagen.oma-gradient-topbar','grantabell.three-state-bar','io.github.adamritter.surface-studio','io.github.rk4500.adaptive-bar','evindor.keystroke'}
    if pid in FORKS: bucket='reference-only (fork: LICENSE names only DHH, no fork-author copyright)'
    if bucket=='train' and not any(v=='pass' for v in vres): bucket='exclude (no valid plugin manifest)'
    rows.append(dict(id=pid,repo=p['repo'],commit=sha,stars=p.get('stars'),commits=int(cc.get(pid,1)),author=p['_owner'],core=p['_core'],coreCommits=p['_coreCommits'],authorPlugins=p['_authorPlugins'],kind=p['kind'],catalogLicense=p['license'],licenseFile=lf[0] if lf else None,licenseVerified=lic,manifestLicense=mlic,packageLicense=plic,copyright=cr,manifests=[os.path.relpath(m,d) for m in mans],validator=vres,vendored=vend[:8],bucket=bucket,updated=p.get('repositoryUpdatedAt')))
json.dump(rows,open(f'{S}/sources.json','w'),indent=1)
print(collections.Counter(r['bucket'] for r in rows))
for r in rows:
    if r['bucket']!='train': print(r['id'],r['licenseVerified'],r['catalogLicense'],r['manifestLicense'],r['validator'][:2],r['bucket'])
