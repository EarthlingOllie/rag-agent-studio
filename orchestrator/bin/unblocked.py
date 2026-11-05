import re,glob,sys,os
root=sys.argv[1]
st={};title={};deps={};path={}
for f in glob.glob(root+'/docs/tickets/*/*.md'):
    t=open(f).read()
    m=re.search(r'\*\*Ticket:\*\*\s*`([0-9]{2}-[0-9]{2})`',t)
    if not m: continue
    i=m.group(1)
    s=re.search(r'\*\*Status:\*\*\s*([\w-]+)',t); st[i]=s.group(1) if s else '?'
    h=re.search(r'^#\s+(.*)$',t,re.M); title[i]=h.group(1) if h else ''
    b=re.search(r'\*\*Blocked by:\*\*(.*?)(?:\n\s*\n|\*\*Status)',t,re.S)
    deps[i]=re.findall(r'\b(\d{2}-\d{2})\b',b.group(1)) if b else []
    path[i]=f.split('/docs/tickets/')[1].split('/')[0]
for i in sorted(st):
    if st[i] in('done','in-progress'): continue
    if all(st.get(d)=='done' for d in deps[i]): print(f"{path[i]}/{i} {title[i]}  [{st[i]}; deps {deps[i]}]")
print('DONE:',sorted(k for k in st if st[k]=='done'),file=sys.stderr)
print('INPROG:',sorted(k for k in st if st[k]=='in-progress'),file=sys.stderr)
