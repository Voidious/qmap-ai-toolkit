import sys
t=open(sys.argv[1]).read(); out=[]; i=0; depth=0; start=0
# split top-level entities by brace depth
ents=[]; cur=[]
for line in t.split('\n'):
    if line=='{' and depth==0: cur=[line]; depth=1; continue
    if depth>0:
        cur.append(line)
        if line=='{': depth+=1
        elif line=='}':
            depth-=1
            if depth==0: ents.append('\n'.join(cur))
keep=[e for e in ents if '"func_detail_illusionary"' not in e.split('\n{')[0]]
open(sys.argv[2],'w').write('\n'.join(keep)+'\n')
print(len(ents),'entities,',len(ents)-len(keep),'illusionary removed')
