"""Bounded artificial network-construction experiment. No modulus selection."""
from pathlib import Path
import json, re, time, resource, hashlib, subprocess, traceback, sys, os
import numpy as np
B=Path(__file__).resolve().parent
P=B/'batch_crosslinks_01_02'
G=os.environ.get('GMX_BINARY','/Users/selp/miniconda3/envs/md-intro-tutorial/bin/gmx')
MASS=32*28118.35848/6.02214076e23*1e24
CAP_WALL=3000; CAP_BYTES=1100000000

def gro(f):
 l=f.read_text().splitlines();n=int(l[1]);box=np.array(list(map(float,l[-1].split())))
 assert n==135958 and len(box)==3 and np.all(np.isfinite(box)) and np.all(box>10)
 x=np.array([[float(z[j:j+8]) for j in (20,28,36)] for z in l[2:2+n]])
 return x,box,l

def distances(x,box,pairs):
 v=np.array([x[j-1]-x[i-1] for i,j in pairs]);v-=np.rint(v/box)*box
 return np.linalg.norm(v,axis=1)

def choose(f,old):
 x,box,l=gro(f);used={i for e in old for i in e};oldpairs={tuple(sorted(((i-1)//579,(j-1)//579))) for i,j in old}
 ids=[i for i in range(1,18529) if l[i+1][5:10].strip()=='TYR' and l[i+1][10:15].strip()=='SC1' and i not in used]
 allpairs=[]
 for n,i in enumerate(ids):
  for j in ids[n+1:]:
   ci,cj=(i-1)//579,(j-1)//579
   if ci==cj or tuple(sorted((ci,cj))) in oldpairs:continue
   d=float(distances(x,box,[(i,j)])[0])
   if d<=2.5:allpairs.append((d,i,j,ci,cj))
 result=[];chains=set()
 for d,i,j,ci,cj in sorted(allpairs):
  if ci in chains or cj in chains:continue
  result.append({'atoms':[i,j],'chains':[ci+1,cj+1],'initial_distance_nm':d});chains.update([ci,cj])
  if len(result)==3:break
 return result

def xvg(f):
 return np.array([[float(v) for v in l.split()] for l in f.read_text().splitlines() if l and not l.startswith(('#','@'))])

def cpinfo(f):
 c=subprocess.run([G,'dump','-cp',str(f)],capture_output=True,text=True,timeout=15);assert c.returncode==0
 t=c.stdout+c.stderr
 return int(re.search(r'^step\s*=\s*(\d+)',t,re.M)[1]),float(re.search(r'^t\s*=\s*([\d.eE+-]+)',t,re.M)[1])

def write_index(f,pairs):
 groups=[('System',range(1,135959)),('Protein',range(1,18529)),('non-Protein',range(18529,135959))]
 for k,(i,j) in enumerate(pairs,1):groups.extend([(f'A{k}',[i]),(f'B{k}',[j])])
 out=''
 for name,ids in groups:
  ids=list(ids);out+=f'[ {name} ]\n'+'\n'.join(' '.join(map(str,ids[j:j+15])) for j in range(0,len(ids),15))+'\n'
 assert max(map(len,out.splitlines()))<120;f.write_text(out)

def graph(f,links):
 # Include intrachain image offsets: a boundary crossing alone is not percolation.
 x,box,_=gro(f);sec='';edges=[]
 for line in (B/'2KY5_clean_precursor/solvated/molecule_0.itp').read_text().splitlines():
  z=line.split(';')[0].strip()
  if z.startswith('['):sec=z.strip('[] ').strip()
  elif z and not z.startswith('#') and sec in ('bonds','constraints'):
   a=z.split();edges.append((int(a[0])-1,int(a[1])-1))
 adj=[[] for _ in range(579)]
 for i,j in edges:adj[i].append(j);adj[j].append(i)
 image=np.zeros((18528,3),dtype=int)
 for c in range(32):
  offset=579*c;seen={0};todo=[0]
  while todo:
   i=todo.pop()
   for j in adj[i]:
    v=-np.rint((x[offset+j]-x[offset+i])/box).astype(int)
    if j not in seen:image[offset+j]=image[offset+i]+v;seen.add(j);todo.append(j)
  assert len(seen)==579
  for i,j in edges:assert np.array_equal(image[offset+j]-image[offset+i],-np.rint((x[offset+j]-x[offset+i])/box).astype(int))
 cadj=[[] for _ in range(32)]
 for a,b in links:
  i,j=a-1,b-1;ci,cj=i//579,j//579
  v=-np.rint((x[j]-x[i])/box).astype(int)+image[i]-image[j]
  cadj[ci].append((cj,v));cadj[cj].append((ci,-v))
 seen=set();components=[];cycles=[]
 for c in range(32):
  if c in seen:continue
  seen.add(c);pos={c:np.zeros(3,dtype=int)};todo=[c];component=[]
  while todo:
   i=todo.pop();component.append(i+1)
   for j,v in cadj[i]:
    if j not in seen:seen.add(j);pos[j]=pos[i]+v;todo.append(j)
    else:
     loop=pos[i]+v-pos[j]
     if np.any(loop):cycles.append(loop.tolist())
  components.append(sorted(component))
 return {'components':components,'component_count':len(components),'largest_component_chains':max(map(len,components)),'periodic_cycle_vectors':cycles,'periodic_winding_rank':int(np.linalg.matrix_rank(np.array(cycles))) if cycles else 0,'Z_periodic_percolation':any(v[2]!=0 for v in cycles)}

def main():
 global rec,start,coords,cpt,step,old,cfg,base_top
 P.mkdir(exist_ok=False);start=time.monotonic()
 src=B/'guided_single_link_retry1/relax';prior=json.loads((B/'guided_single_link_retry1/progress.json').read_text())
 assert prior['state']=='completed';assert hashlib.sha256((src/'md.cpt').read_bytes()).hexdigest()==prior['final_checkpoint_sha256']
 coords=src/'md.gro';cpt=src/'md.cpt';step,t=cpinfo(cpt);assert step==167510 and abs(t-335.02)<1e-6
 old=[[10605,16395]];base_top=(B/'concentration_adjustment/system.top').read_text();cfg={}
 for l in (B/'concentration_adjustment/npt100ps/stage.mdp').read_text().splitlines():
  if '=' in l:k,v=l.split('=',1);cfg[k.strip()]=v.strip()
 rec={'state':'running','authorization':'user approved batch artificial linking','method':'artificial construction, not reaction kinetics','source_checkpoint_sha256':prior['final_checkpoint_sha256'],'initial_step':step,'initial_time_ps':t,'CPU_core_seconds_cap':12000,'wall_seconds_cap':CAP_WALL,'storage_cap_bytes':CAP_BYTES,'GPU_seconds':0,'maximum_batches':2,'maximum_new_links_per_batch':3,'selection':'nearest cross-chain unused Tyr SC1; distinct chains within batch; no duplicate chain pair; initial distance <=2.5 nm; no modulus selection','guide_schedule':[200]*5+[500,1000],'guide_stage_ps':20,'capture_gate_nm':0.7,'permanent_stages':[[100,20],[1000,20],[4000,20],[4000,50]],'stages':[],'batches':[],'committed_links':old.copy(),'PBS_explicit':False,'gel_modulus_available':False}
 save();update_ledger(False)
 try:
  for bn in (1,2):
   selected=choose(coords,old)
   if not selected:rec['stop_reason']='No eligible pair within 2.5 nm';break
   pairs=[s['atoms'] for s in selected];batch={'batch':bn,'selected':selected,'source_gro_sha256':hashlib.sha256(coords.read_bytes()).hexdigest(),'state':'guiding'};rec['batches'].append(batch);save()
   for j,k in enumerate(rec['guide_schedule'],1):
    s=stage(f'b{bn}_guide{j}',20,pairs,guide_k=k)
    passed=[a<=.7 and b<=.7 for a,b in zip(s['candidate_endpoint_nm'],s['candidate_last5ps_mean_nm'])]
    if all(passed):break
   accepted=[e for e,ok in zip(pairs,passed) if ok];batch['capture_passed']=passed;batch['accepted_links']=accepted;batch['state']='forming' if accepted else 'no_capture';save()
   # Drop temporary guides for failed as well as accepted pairs.
   if accepted:
    for name,k,dur in [('soft',100,20),('medium',1000,20),('full',4000,20),('relax',4000,50)]:stage(f'b{bn}_{name}',dur,accepted,bond_k=k)
    old+=accepted;rec['committed_links']=old.copy()
   else:stage(f'b{bn}_release',20,[])
   audit=graph(coords,old);batch.update(state='completed' if accepted else 'no_capture',graph=audit,final_stage=rec['stages'][-1]['name']);save()
   if not accepted:rec['stop_reason']='No pair captured; batch series stopped';break
  rec.update(state='completed',final_step=step,final_time_ps=step*.002,final_gro=str(coords.relative_to(B)),final_checkpoint_sha256=hashlib.sha256(cpt.read_bytes()).hexdigest(),temporary_guide_removed=True,graph=graph(coords,old))
 except Exception as e:
  rec.update(state='stopped',error=repr(e),traceback=traceback.format_exc());print(rec['traceback'],flush=True)
 finally:save();update_ledger(True);print(json.dumps(rec,indent=2),flush=True)

def save():
 u=resource.getrusage(resource.RUSAGE_CHILDREN);rec.update(CPU_seconds=u.ru_utime+u.ru_stime,wall_seconds=time.monotonic()-start)
 q=P/'progress.tmp';q.write_text(json.dumps(rec,indent=2)+'\n');q.replace(P/'progress.json')

def update_ledger(terminal):
 f=B/'resource_ledger.json';l=json.loads(f.read_text());l['scope']='100 mg/mL precursor preparation and bounded CPU artificial crosslink pilots; separate from historical Slurm campaigns'
 l['extensions']['batch_crosslinks_01_02']={'CPU_seconds':rec['CPU_seconds'],'GPU_seconds':0,'state':rec['state'],'CPU_core_seconds_cap':12000,'MD_ps':sum(s['duration_ps'] for s in rec['stages'] if s['state']=='completed')}
 l['all_local_simulations_terminal']=terminal
 if not terminal:l['active_work']={'directory':str(P),'CPU_core_seconds_cap':12000,'GPU_seconds':0,'storage_cap_bytes':CAP_BYTES}
 else:l.pop('active_work',None)
 l['metered_CPU_seconds_including_extensions']=l['metered_CPU_seconds']+sum(e['CPU_seconds'] for e in l['extensions'].values())
 l['local_new_bytes_snapshot']=sum(f.stat().st_size for f in B.rglob('*') if f.is_file());l['combined_new_bytes_snapshot']=l['local_new_bytes_snapshot']+l['remote_new_bytes_snapshot'];f.write_text(json.dumps(l,indent=2)+'\n')

def run(args,d,name,guard=False):
 with (d/name).open('w') as out:
  proc=subprocess.Popen(args,cwd=d,stdout=out,stderr=subprocess.STDOUT);lastdisk=0
  try:
   while proc.poll() is None:
    now=time.monotonic();txt=''.join(f.read_text(errors='replace') for f in (d/name,d/'md.log') if f.exists())
    if re.search(r'LINCS WARNING|constraint warning|Fatal error',txt,re.I):raise RuntimeError('Numerical warning; stopped')
    if now-start>CAP_WALL-15:raise RuntimeError('Wall/core resource guard')
    if now-lastdisk>10:
     if sum(f.stat().st_size for f in P.rglob('*') if f.is_file())>CAP_BYTES:raise RuntimeError('Disk guard')
     lastdisk=now
    time.sleep(1)
   assert proc.returncode==0,(name,proc.returncode)
  except BaseException:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
   raise

def stage(name,duration,pairs,guide_k=None,bond_k=None):
 global coords,cpt,step
 actual,t=cpinfo(cpt);assert actual==step and abs(t-step*.002)<1e-6
 d=P/name;d.mkdir();write_index(d/'index.ndx',pairs);c=cfg.copy()
 c.update({'init-step':str(step),'nsteps':str(round(duration/.002)),'gen_vel':'no','continuation':'yes','nstxout-compressed':'1000','compressed-x-grps':'Protein','nstlog':'500','pull':'yes' if guide_k else 'no'})
 if guide_k:
  c.update({'pull-ngroups':str(2*len(pairs)),'pull-ncoords':str(len(pairs)),'pull-nstxout':'50','pull-nstfout':'50'})
  for a in range(1,len(pairs)+1):
   c[f'pull-group{2*a-1}-name']=f'A{a}';c[f'pull-group{2*a}-name']=f'B{a}'
   for key,v in {'type':'flat-bottom','geometry':'distance','groups':f'{2*a-1} {2*a}','dim':'Y Y Y','start':'no','init':'.45','rate':'0','k':str(guide_k)}.items():c[f'pull-coord{a}-{key}']=v
 links=[(i,j,4000) for i,j in old]+([(i,j,bond_k) for i,j in pairs] if bond_k else [])
 top=base_top+'\n[ intermolecular_interactions ]\n[ bonds ]\n'+''.join(f'{i} {j} 6 0.35 {k}\n' for i,j,k in links)
 (d/'system.top').write_text(top);(d/'stage.mdp').write_text('\n'.join(f'{k} = {v}' for k,v in c.items())+'\n')
 s={'name':name,'duration_ps':duration,'initial_step':step,'temporary_guide':guide_k,'new_bond_k':bond_k,'candidate_pairs':pairs,'active_permanent_links':links,'state':'preparing'};rec['stages'].append(s);save()
 run([G,'grompp','-f','stage.mdp','-c',str(coords),'-t',str(cpt),'-p','system.top','-n','index.ndx','-o','md.tpr','-po','actual.mdp'],d,'grompp.out')
 s['state']='running';save();run([G,'mdrun','-deffnm','md','-ntmpi','1','-ntomp','4','-nb','cpu','-bonded','cpu','-pin','off'],d,'mdrun.out',True)
 ns=step+round(duration/.002);act,tt=cpinfo(d/'md.cpt');assert act==ns and abs(tt-ns*.002)<1e-6
 x,box,_=gro(d/'md.gro');allpairs=[list(z[:2]) for z in links]+([e for e in pairs if e not in [list(z[:2]) for z in links]])
 selection='; '.join(f'atomnr {i} plus atomnr {j}' for i,j in allpairs)
 run([G,'distance','-s','md.tpr','-f','md.xtc','-select',selection,'-oall','distances.xvg'],d,'distance.out')
 a=xvg(d/'distances.xvg');assert a.shape[1]==len(allpairs)+1 and np.all(np.isfinite(a)) and 0<=tt-a[-1,0]<2.001
 # Use dense pull output for guide capture and sparse protein trajectory for permanent links.
 if guide_k:
  ar=xvg(d/'md_pullx.xvg');assert ar.shape[1]==len(pairs)+1;last=ar[ar[:,0]>=tt-5,1:]
 elif pairs:last=a[a[:,0]>=tt-5,1:][:,[allpairs.index(e) for e in pairs]]
 else:last=np.zeros((1,0))
 if links:assert np.min(a[:,1:len(links)+1])>.15 and np.max(a[:,1:len(links)+1])<1.0
 cp=subprocess.run([G,'energy','-f',str(d/'md.edr'),'-o',str(d/'thermo.xvg')],input='Temperature\nPressure\nVolume\n0\n',capture_output=True,text=True,timeout=20);(d/'energy.out').write_text(cp.stdout+cp.stderr);assert cp.returncode==0
 h=xvg(d/'thermo.xvg');assert np.all(np.isfinite(h));tail=h[h[:,0]>=tt-duration/2];T=float(tail[:,1].mean());conc=float(np.mean(MASS/tail[:,3]));assert 300<T<320 and 99<conc<101
 s.update(state='completed',final_step=ns,final_time_ps=tt,candidate_endpoint_nm=distances(x,box,pairs).tolist() if pairs else [],candidate_last5ps_mean_nm=last.mean(0).tolist(),mean_T_K=T,mean_concentration_mg_ml=conc,checkpoint_sha256=hashlib.sha256((d/'md.cpt').read_bytes()).hexdigest())
 coords=d/'md.gro';cpt=d/'md.cpt';step=ns;save();print(json.dumps({'stage':name,'endpoints':s['candidate_endpoint_nm'],'T':T,'concentration':conc}),flush=True);return s

if __name__=='__main__':main()
