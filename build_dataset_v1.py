import json,os,re,subprocess,random,hashlib,collections,sys
sys.path.insert(0,'validator'); from validate import validate_dir, validate_files
random.seed(1337)
CAP=64000
SYS=("You are an Omarchy plugin expert. You write complete, valid Omarchy (Quattro / omarchy-shell, Quickshell QML) plugins. "
"Manifests use schemaVersion 1, a namespaced id that never uses the reserved omarchy.* namespace, name, version, kinds "
"(bar-widget|panel|overlay|menu|service|bar) with a matching safe relative entryPoints path for every kind, and no symlinks. "
"Return every file in full as '### path' followed by a fenced code block.")
EXT=('.qml','.json','.js','.mjs','.py','.sh')
SKIP=re.compile(r'(^|/)(vendor|node_modules|third_party|fonts|assets|icons|tests?|\.github|docs?|screenshots|packaging|webui|sdk|integrations)(/|$)|package-lock\.json$|(^|/)\.|\.min\.js$',re.I)
def lang(p): return {'.qml':'qml','.json':'json','.js':'javascript','.mjs':'javascript','.py':'python','.sh':'bash'}[os.path.splitext(p)[1]]
def tracked(d):
    r=subprocess.run(['git','-C',d,'ls-files'],capture_output=True,text=True).stdout.split()
    return r if r else [os.path.relpath(os.path.join(a,f),d) for a,_,fs in os.walk(d) for f in fs]
def bundle(pdir):
    top=subprocess.run(['git','-C',pdir,'rev-parse','--show-toplevel'],capture_output=True,text=True).stdout.strip()
    files={}
    for f in subprocess.run(['git','-C',pdir,'ls-files','.'],capture_output=True,text=True).stdout.split():
        if not f.endswith(EXT) or SKIP.search(f): continue
        if f!='manifest.json' and f.endswith('manifest.json'): continue
        fp=os.path.join(pdir,f)
        if os.path.islink(fp) or not os.path.isfile(fp): continue
        try: files[f]=open(fp,encoding='utf-8').read()
        except UnicodeDecodeError: continue
    return files
def render(files): return "\n\n".join(f"### {p}\n```{lang(p)}\n{c.rstrip()}\n```" for p,c in sorted(files.items(),key=lambda x:(x[0]!='manifest.json',x[0])))
def parse(text):
    return {m.group(1):m.group(3)+"\n" for m in re.finditer(r"### (\S+)\n```(\w*)\n(.*?)\n```",text,re.S)}
def kinds_of(m): return m.get('kinds',[])
def complexity(files):
    n=sum(len(c) for c in files.values()); return 'small' if n<12000 else 'medium' if n<32000 else 'large'
def describe(m):
    bw=m.get('barWidget') or {}
    desc=m.get('description') or bw.get('description') or m['name']
    return desc.rstrip('.')
EX=[]
def add(**k): EX.append(k)
INSTR=["Write a complete Omarchy plugin `{id}` called \"{name}\" ({kinds}). {desc}.",
       "I want an Omarchy {kinds} plugin named {name} (id `{id}`): {desc}. Give me every file.",
       "Create the full Omarchy plugin for this idea: {desc}. Use id `{id}`, display name \"{name}\", kinds {kinds}."]
# ---- sources
srcs=[]
OM='/tmp/omarchy-src'; OMSHA=subprocess.run(['git','-C',OM,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
for m in subprocess.run(['git','-C',OM,'ls-files','shell/plugins'],capture_output=True,text=True).stdout.split():
    if m.endswith('/manifest.json'): srcs.append(dict(origin='first-party',pdir=os.path.join(OM,os.path.dirname(m)),repo='https://github.com/basecamp/omarchy',commit=OMSHA,license='MIT',rep=2,author='basecamp'))
for r in ['rocketlauncher','compliantish','enricherino','encyclopedic','scriptural','sparklekeys']:
    d=f'/workspace/omarchy-{r}'; sha=subprocess.run(['git','-C',d,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    srcs.append(dict(origin='house',pdir=d,repo=f'https://github.com/kenhara/omarchy-{r}',commit=sha,license='MIT',rep=3,author='kenhara'))
S=json.load(open('sources/sources.json')); per_author=collections.Counter()
for s in sorted([s for s in S if s['bucket']=='train'],key=lambda s:-(s['stars'] or 0)-5*min(s['authorPlugins'],5)-50*s['core']):
    for mrel,v in zip(s['manifests'],s['validator']):
        if v=='pass': srcs.append(dict(origin='community',pdir=os.path.join('sources/repos',s['id'],os.path.dirname(mrel)),repo=s['repo'],commit=s['commit'],license=s['licenseVerified'],rep=1,author=s['author'],sid=s['id'])); break
used=[]
comm_taken=0
for s in srcs:
    files=bundle(s['pdir'])
    if 'manifest.json' not in files: continue
    m=json.loads(files['manifest.json']); size=sum(map(len,files.values()))
    s['size']=size; s['mid']=m.get('id')
    if size>CAP: s['skip']='too large for 32k ctx'; continue
    if s['origin']=='community':
        if per_author[s['author']]>=2 or comm_taken>=28: s['skip']='author/community cap'; continue
        per_author[s['author']]+=1; comm_taken+=1
    rid=m['id']
    if rid.startswith('omarchy.'):
        rid='acme.'+rid.split('.',1)[1]; m['id']=rid
        files['manifest.json']=json.dumps(m,indent=2)+"\n"
    s['used']=True; used.append(s)
    kinds=", ".join(m['kinds']); grp=hashlib.md5((s['repo']+s['pdir']).encode()).hexdigest()[:8]
    meta=dict(origin=s['origin'],repo=s['repo'],commit=s['commit'],license=s['license'],plugin_path=os.path.relpath(s['pdir'],OM) if s['origin']=='first-party' else s['pdir'].split('repos/')[-1],kinds=m['kinds'],complexity=complexity(files),group=grp)
    for i in range(s['rep']):
        u=INSTR[i%3].format(id=rid,name=m['name'],kinds=kinds,desc=describe(m))
        if s['origin']=='first-party' and i==0: u+=" (It's a third-party plugin, so don't use the reserved omarchy.* namespace.)"
        add(task='build_from_spec',user=u,files=files,meta=meta)
    # add-a-panel task
    if 'bar-widget' in m['kinds'] and any(re.search(r'Panel\.qml$',p) for p in files):
        man_only=dict(m); 
        u=("Here is my Omarchy bar-widget manifest:\n```json\n"+json.dumps(man_only,indent=2)+"\n```\nAdd a nested panel that opens when the bar chip is left-clicked "
           "(keep it a bar-widget; the panel loads via a Loader from the widget, not as a separate `panel` kind). Return the complete plugin.")
        add(task='add_panel',user=u,files=files,meta=meta)
# ---- fix-the-manifest tasks (validated in the context of the real plugin tree)
MUT=[('reserved_id',lambda m:m.update(id='omarchy.'+m['id'].split('.')[-1])),
     ('bad_path_dotdot',lambda m:m['entryPoints'].update({k:'../'+v for k,v in list(m['entryPoints'].items())[:1]})),
     ('bad_path_absolute',lambda m:m['entryPoints'].update({k:'/home/user/'+v for k,v in list(m['entryPoints'].items())[:1]})),
     ('missing_entry',lambda m:m['entryPoints'].pop(list(m['entryPoints'])[0])),
     ('schema_string',lambda m:m.update(schemaVersion="1")),
     ('missing_entry_file',lambda m:m['entryPoints'].update({k:v.replace('.qml','Main.qml') for k,v in list(m['entryPoints'].items())[:1]})),
     ('bad_default_section',lambda m:m.setdefault('barWidget',{}).update(defaultSection='top')),
     ('symlink',None)]
import copy,tempfile,shutil
pool=[u for u in used]; random.shuffle(pool); fi=0
for s in pool:
    if fi>=24: break
    name,f=MUT[fi%len(MUT)]
    files=bundle(s['pdir']); good=json.loads(files['manifest.json'])
    if good['id'].startswith('omarchy.'): good['id']='acme.'+good['id'].split('.',1)[1]
    if name=='bad_default_section' and 'bar-widget' not in good['kinds']: continue
    bad=copy.deepcopy(good)
    with tempfile.TemporaryDirectory() as t:
        for p,c in files.items():
            fp=os.path.join(t,p); os.makedirs(os.path.dirname(fp),exist_ok=True); open(fp,'w').write(c)
        if name=='symlink':
            ep=list(good['entryPoints'].values())[0]; os.remove(os.path.join(t,ep)); os.symlink('/home/user/dev/'+os.path.basename(ep),os.path.join(t,ep))
        else: f(bad)
        open(os.path.join(t,'manifest.json'),'w').write(json.dumps(bad,indent=2))
        err=validate_dir(t)
        if not err: continue
        if name=='symlink':
            u=(f"`omarchy plugin validate` fails on my plugin:\n```\nomarchy-plugin-validate: {err.replace(t+'/','./')}\n```\nI symlinked `{ep}` to my dev checkout. Here is the manifest and the real file contents:\n```json\n{json.dumps(good,indent=2)}\n```\n### {ep} (symlink target)\n```qml\n{files[ep].rstrip()}\n```\nFix it.")
            out={'manifest.json':json.dumps(good,indent=2)+"\n",ep:files[ep]}; note=f"Symlinks are refused anywhere in a plugin folder. Replace the link with a regular file (`rm {ep}` then write it as below); the manifest itself is fine."
        else:
            u=f"Fix this invalid Omarchy plugin manifest. `omarchy plugin validate` says:\n```\nomarchy-plugin-validate: {err.replace(t+'/','./')}\n```\n```json\n{json.dumps(bad,indent=2)}\n```\nOther files in the folder: {', '.join(sorted(p for p in files if p!='manifest.json'))}"
            out={'manifest.json':json.dumps(good,indent=2)+"\n"}; note="Corrected manifest:"
    meta=dict(origin=s['origin'],repo=s['repo'],commit=s['commit'],license=s['license'],kinds=good['kinds'],complexity='small',group=hashlib.md5((s['repo']+s['pdir']).encode()).hexdigest()[:8],mutation=name,validate_context=s['pdir'])
    add(task='fix_manifest:'+name,user=u,files=out,meta=meta,note=note); fi+=1
# ---- validate every assistant output
rows=[]
for e in EX:
    asst=(e.get('note','')+"\n\n" if e.get('note') else "")+render(e['files'])
    got=parse(asst)
    assert set(got)==set(e['files']),(e['task'],set(e['files'])^set(got))
    if e['task'].startswith('fix_manifest'):
        files=bundle(e['meta']['validate_context']); files.update(got); err=validate_files(files)
    else: err=validate_files(got)
    e['meta']['validator']='pass' if not err else 'fail: '+err
    rows.append(dict(messages=[{"role":"system","content":SYS},{"role":"user","content":e['user']},{"role":"assistant","content":asst}],task=e['task'],meta=e['meta']))
# ---- stratified 20% holdout by group, stratum=(primary kind, complexity)
groups=collections.defaultdict(list)
for i,r in enumerate(rows): groups[r['meta']['group']].append(i)
strata=collections.defaultdict(list)
for g,ix in groups.items():
    r=rows[ix[0]]; strata[(r['meta']['kinds'][0],r['meta']['complexity'])].append(g)
hold=set()
for k,gs in sorted(strata.items()):
    random.shuffle(gs); n=round(len(gs)*0.2)
    hold.update(gs[:n])
os.makedirs('data',exist_ok=True)
with open('data/train.jsonl','w') as a, open('data/holdout.jsonl','w') as b:
    for r in rows:
        r['meta']['split']='holdout' if r['meta']['group'] in hold else 'train'
        (b if r['meta']['split']=='holdout' else a).write(json.dumps(r,ensure_ascii=False)+"\n")
json.dump([{k:v for k,v in s.items()} for s in srcs],open('data/source_usage.json','w'),indent=1)
c=collections.Counter
print('total',len(rows),c(r['meta']['split'] for r in rows))
print('validator',c(r['meta']['validator'][:4] for r in rows))
for r in rows:
    if r['meta']['validator']!='pass': print('FAIL',r['task'],r['meta']['validator'])
print('task',c(r['task'].split(':')[0] for r in rows)); print('fix',c(r['task'] for r in rows if ':' in r['task']))
print('origin',c(r['meta']['origin'] for r in rows)); print('kind',c(k for r in rows for k in r['meta']['kinds']))
print('cplx',c(r['meta']['complexity'] for r in rows))
print('holdout kind',c(k for r in rows if r['meta']['split']=='holdout' for k in r['meta']['kinds']))
print('skipped',c(s.get('skip','used' if s.get('used') else '-') +'/'+s['origin'] for s in srcs))
