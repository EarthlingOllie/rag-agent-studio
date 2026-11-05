# usage: resolve.py FILE choice[,choice...]  choice per hunk: o=ours t=theirs ot=ours+theirs to=theirs+ours
import re,sys
f,choices=sys.argv[1],sys.argv[2].split(",")
s=open(f).read()
pat=re.compile(r"<<<<<<< [^\n]*\n(.*?)(?:\|\|\|\|\|\|\| [^\n]*\n.*?)?=======\n(.*?)>>>>>>> [^\n]*\n",re.S)
hs=pat.findall(s); assert len(hs)==len(choices),(len(hs),len(choices))
it=iter(choices)
def rep(m):
    c=next(it);o,t=m.group(1),m.group(2)
    return {"o":o,"t":t,"ot":o+t,"to":t+o}[c]
open(f,"w").write(pat.sub(rep,s))
