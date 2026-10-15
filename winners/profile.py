import os,json,re,sys
CODE=('.qml','.js','.mjs','.sh','.py','.lua','.cpp','.hpp','.h','.bash')
PAT={
 'Process':r'\bProcess\s*\{','StdioCollector':r'StdioCollector','SplitParser':r'SplitParser','FileView':r'\bFileView\b',
 'Timer':r'\bTimer\s*\{','XHR':r'XMLHttpRequest','Hyprland':r'\bHyprland\b|hyprctl','IpcHandler':r'IpcHandler','Mpris':r'Mpris',
 'qs.Commons':r'import qs\.Commons','qs.Ui':r'import qs\.Ui','Loader':r'\bLoader\s*\{','execDetached':r'execDetached',
 'onExited':r'onExited','exitCode':r'exitCode','try/catch':r'\btry\s*\{|\bcatch\s*\(','sh set -e/pipefail':r'set -[a-z]*e|pipefail',
 'trap':r'\btrap\b','command -v':r'command -v|which ','timeout':r'--max-time|timeout\b|-m \d+|connect-timeout',
 'JSON.parse':r'JSON\.parse','settings/defaults':r'\bsettings\.|bar\.settings|pluginSettings','Quickshell.env':r'Quickshell\.env|XDG_',
 'mktemp':r'mktemp','flock':r'\bflock\b','notify-send':r'notify-send',
}
def prof(d):
    r={'files':0,'code_files':0,'loc':{}, 'bytes':0,'api':{k:0 for k in PAT}}
    names=set(); allrel=[]
    for root,ds,fs in os.walk(d):
        ds[:]=[x for x in ds if x not in('.git','node_modules','__pycache__')]
        for f in fs:
            p=os.path.join(root,f); rel=os.path.relpath(p,d); allrel.append(rel); r['files']+=1
            try: r['bytes']+=os.path.getsize(p)
            except: pass
            istest=bool(re.search(r'(^|/)(tests?|spec)(/|$)|\.test\.|_test\.|test_',rel))
            ext=os.path.splitext(f)[1].lower()
            sh=False
            if ext in CODE or (not ext and os.path.getsize(p)<400000):
                try: c=open(p,encoding='utf-8').read()
                except: continue
                if not ext and not c.startswith('#!'): continue
                e=ext or ('.script')
                n=c.count('\n')+1
                key=e+('(test)' if istest else '')
                r['loc'][key]=r['loc'].get(key,0)+n
                if not istest:
                    r['code_files']+=1
                    for k,pt in PAT.items(): r['api'][k]+=len(re.findall(pt,c))
    low=[x.lower() for x in allrel]
    top=[x for x in low if '/' not in x]
    r['has_license']=any(x.startswith(('license','licence','copying')) for x in top)
    r['has_readme']=any(x.startswith('readme') for x in top)
    r['has_changelog']=any(x.startswith(('changelog','changes','history','release')) for x in top)
    r['has_tests']=any(re.search(r'(^|/)(tests?|spec)/',x) for x in low)
    r['has_ci']=any(x.startswith('.github/workflows/') for x in low)
    r['has_agent_files']=any(os.path.basename(x) in('agents.md','claude.md','gemini.md') or x.startswith('.claude/') or x.startswith('.cursor') for x in low)
    r['has_docs_dir']=any(x.startswith('docs/') for x in low)
    r['has_security_md']=any(x.startswith('security') for x in top)
    r['has_contributing']=any(x.startswith('contributing') for x in top)
    r['has_pkgbuild']=any('pkgbuild' in x for x in low)
    r['scripts_exec']=sum(1 for x in allrel if os.access(os.path.join(d,x),os.X_OK) and os.path.isfile(os.path.join(d,x)) and not x.startswith('.git'))
    r['prod_loc']=sum(v for k,v in r['loc'].items() if '(test)' not in k)
    r['test_loc']=sum(v for k,v in r['loc'].items() if '(test)' in k)
    try:
        m=json.load(open(os.path.join(d,'manifest.json')))
        b=m.get('barWidget',{}) if isinstance(m.get('barWidget'),dict) else {}
        r['manifest']={'version':'version' in m,'license':'license' in m,'license_val':m.get('license'),'repository':'repository' in m or 'homepage' in m,'keywords':'keywords' in m,
          'author':'author' in m,'activation':m.get('activation'),'keepLoaded':m.get('keepLoaded'),'schema':'schema' in b,'defaults':'defaults' in b,'category':b.get('category'),
          'kinds':m.get('kinds'),'entryPoints':sorted((m.get('entryPoints') or {}).keys()),'version_val':m.get('version'),'n_schema':len(b.get('schema',[])) if isinstance(b.get('schema'),list) else 0}
    except Exception as e: r['manifest']=None
    return r
if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='winners':
        W={'akshar.radio-atlas':'aksharp5__omarchy-radio-atlas','slcode777.omagotchi':'slcode777__omagotchi','io.github.thisisgm.omapods':'thisisgm__omarchy-pods','robzolkos.github':'robzolkos__omarchy-github'}
        out={k:prof('/workspace/sweep_repos/'+v) for k,v in W.items()}
        json.dump(out,open('winners_profile.json','w'),indent=1)
    else:
        out=[]
        for l in open('/workspace/wt-retrain-v2/dell/sweep/corpus.jsonl'):
            c=json.loads(l)
            if not c.get('is_plugin') or not os.path.isdir(c['local_dir']): continue
            try: p=prof(c['local_dir'])
            except Exception as e: continue
            p['key']=c['key'];p['plugin_id']=c['plugin_id'];out.append(p)
        json.dump(out,open('corpus_profile.json','w'))
        print(len(out))
