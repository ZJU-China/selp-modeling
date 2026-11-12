import numpy as np
from scipy.spatial import cKDTree
def stable_operators(s):
 raw,xu,box,nc,nb,cov=[s[q] for q in ['raw','xu','box','nc','nb','cov']];centers=xu.reshape(nc,nb,3).mean(1);D=[]
 for i in range(3):h=np.zeros((3,3));h[i,i]=1;D.append(h)
 for i,j in [(1,2),(0,2),(0,1)]:h=np.zeros((3,3));h[i,j]=h[j,i]=.5;D.append(h)
 def row(i,j):
  ci,cj=i//nb,j//nb;d=raw[j]-raw[i];d-=np.rint(d/box)*box;u=d/np.linalg.norm(d);ri=xu[i]-centers[ci];rj=xu[j]-centers[cj];b=np.zeros(6*nc);b[3*ci:3*ci+3]-=u;b[3*cj:3*cj+3]+=u;b[3*nc+3*ci:3*nc+3*ci+3]-=np.cross(ri,u);b[3*nc+3*cj:3*nc+3*cj+3]+=np.cross(rj,u);return b,np.array([u@h@(d-rj+ri) for h in D])
 pairs=cKDTree(np.mod(raw,box),boxsize=box).query_pairs(.7,output_type='ndarray');pairs=pairs[pairs[:,0]//nb!=pairs[:,1]//nb];dv=raw[pairs[:,1]]-raw[pairs[:,0]];dv-=np.rint(dv/box)*box;dist=np.linalg.norm(dv,axis=1);groups={};covset=set(cov)
 for i,j in pairs[dist<=.6]:
  pair=(int(i),int(j))
  if pair not in covset:groups.setdefault((int(i)//nb,int(j)//nb),[]).append(pair)
 selected=list(cov);rows=[row(i,j) for i,j in cov];weights=[1.]*len(rows);count=0
 for key,pairs in sorted(groups.items()):
  pairs=sorted(pairs)
  if len(pairs)<3:continue
  count+=1;mids=[]
  for i,j in pairs:d=raw[j]-raw[i];d-=np.rint(d/box)*box;mids.append(xu[i]+d/2)
  mids=np.array(mids);take=[int(np.argmax(np.sum((mids-mids.mean(axis=0))**2,axis=1)))];d2=np.sum((mids-mids[take[0]])**2,axis=1)
  for _ in range(min(24,len(pairs))-1):d2[take]=-1;idx=int(np.argmax(d2));take.append(idx);d2=np.minimum(d2,np.sum((mids-mids[idx])**2,axis=1))
  selected.extend(pairs[idx] for idx in take);rows.extend(row(*pairs[idx]) for idx in take);weights.extend([1/np.sqrt(len(take))]*len(take))
 w=np.array(weights)[:,None];return np.array([r[0] for r in rows])*w,np.array([r[1] for r in rows])*w,count,selected,groups
