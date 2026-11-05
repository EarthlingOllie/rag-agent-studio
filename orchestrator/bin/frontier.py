import re,subprocess,sys
ref=sys.argv[1]; repo=sys.argv[2]
def show(p): return subprocess.run(['git','-C',repo,'show',f'{ref}:{p}'],capture_output=True,text=True).stdout
idx=show('docs/tickets/README.md')
rows=re.findall(r'^\| `(\d\d-\d\d)` \| \[([^\]]+)\]\(\./([^)]+)\) \| ([^|]+) \|',idx,re.M)
st={}
for tid,title,path,deps in rows:
    m=re.search(r'\*\*Status:\*\*\s*([\w-]+)',show('docs/tickets/'+path)); st[tid]=m.group(1) if m else '?'
spec={}
for tid,title,path,deps in rows:
    d=[x.strip() for x in deps.split(',') if x.strip()!='none']
    if st[tid] in('done','in-progress'): continue
    if all(st.get(x)=='done' for x in d):
        print(f"{path.split('/')[0]}/{tid} {title}")
