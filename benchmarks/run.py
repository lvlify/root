#!/usr/bin/env python3
"""Paired Codex benchmark. Python stdlib only; signed-in Codex CLI required."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL, EFFORT = 'gpt-6-luna', 'max'
CONDITIONS = ('baseline', 'root')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def body():
    text = (ROOT / 'skills/root/SKILL.md').read_text(encoding='utf-8')
    return text.split('\n---\n', 1)[1].strip() + '\n'


def code_cases(name):
    """Published, deterministic oracle: edges plus 100 seeded cases per function."""
    rng = random.Random(20261002)
    cases = []
    def add(args, expected=None, raises=False):
        cases.append({'args': args, 'expected': expected, 'raises': raises})
    if name == 'merge_busy':
        for x in [[], [[1,2],[2,3]], [[5,9],[1,7],[3,4]], [[1,1]], [[4,2]]]:
            invalid = any(a >= b for a,b in x)
            out = []
            for a,b in sorted(x):
                if out and a < out[-1][1]: out[-1][1] = max(b,out[-1][1])
                else: out.append([a,b])
            add([x],out,invalid)
        for _ in range(100):
            x = [[rng.randrange(-20,20),rng.randrange(1,10)] for _ in range(rng.randrange(20))]
            x = [[a,a+b] for a,b in x]
            out=[]
            for a,b in sorted(x):
                if out and a < out[-1][1]:out[-1][1]=max(b,out[-1][1])
                else:out.append([a,b])
            add([x],out)
    elif name == 'apportion':
        for total,weights in [(0,[]),(3,[]),(-1,[1]),(1,[0]),(1,[-1]),(2,[1,1,1]),(10**18+1,[7,11,13])]+[(rng.randrange(1000),[rng.randrange(1,100) for _ in range(rng.randrange(1,20))]) for _ in range(100)]:
            invalid=total<0 or any(w<=0 for w in weights) or (not weights and total!=0)
            out=[]
            if weights and not invalid:
                s=sum(weights);out=[total*w//s for w in weights]
                order=sorted(range(len(weights)),key=lambda i:(-(total*weights[i]%s),i))
                for i in order[:total-sum(out)]:out[i]+=1
            add([total,weights],out,invalid)
    elif name == 'resolve_alias':
        for mapping,key,expected,raises in [({},'x','x',False),({'a':'a'},'a',None,True),({'a':'b','b':'a'},'a',None,True),({'z':'z','a':'b'},'a','b',False)]:
            add([mapping,key],expected,raises)
        for _ in range(100):
            n=rng.randrange(1,30);mapping={str(i):str(i+1) for i in range(n)}
            cycle=rng.choice([True,False])
            if cycle:mapping[str(n)]=str(rng.randrange(n+1))
            add([mapping,'0'],str(n),cycle)
    elif name == 'window_counts':
        for events,width in [([],1),([2,2,1,3],1),([0,5,10],5),([1],0),([],-1)]+[([rng.randrange(-20,20) for _ in range(rng.randrange(30))],rng.randrange(1,20)) for _ in range(100)]:
            add([events,width],[sum(t-width<x<=t for x in events) for t in events],width<=0)
    else:raise ValueError('Unknown code check: '+name)
    return cases


def code_child(request):
    """Restricted Python evaluation, not a general-purpose security sandbox."""
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(3,3))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    code=request['code'];name=request['name'];tree=ast.parse(code)
    banned=(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal,ast.ClassDef)
    for n in ast.walk(tree):
        if isinstance(n,banned):raise ValueError('Unsupported code construct')
        if isinstance(n,ast.Name) and n.id.startswith('__'):raise ValueError('Private names disabled')
        if isinstance(n,ast.Attribute) and n.attr not in {'append','extend','sort','get','items','keys','values','copy','add','remove','pop'}:
            raise ValueError('Unsupported attribute: '+n.attr)
    import builtins
    names='abs all any ascii bin bool bytearray bytes callable chr complex dict divmod enumerate filter float frozenset hash hex int isinstance issubclass iter len list map max min next oct ord pow range repr reversed round set slice sorted str sum tuple zip ValueError TypeError StopIteration'.split()
    safe={k:getattr(builtins,k) for k in names}
    safe['type']=lambda value:type(value)  # Introspection only; class creation is disabled.
    scope={'__builtins__':safe};exec(compile(tree,'<answer>','exec'),scope)
    fn=scope[name];failed=[];cases=code_cases(name)
    for index,c in enumerate(cases):
        args=deepcopy(c['args']);before=deepcopy(args)
        try:
            actual=fn(*args)
            ok=not c['raises'] and actual==c['expected']
        except ValueError:ok=c['raises']
        except Exception:ok=False
        if args!=before:ok=False
        if not ok:failed.append(index)
    return {'passed':len(cases)-len(failed),'total':len(cases),'failed_case_indices':failed}


def grade(task,row):
    if row.get('error'):return {'pass':False,'fraction':0,'reason':'run error'}
    try:
        answers=[json.loads(t['answer']) for t in row['turns']]
        if len(answers)>1 and answers[0]!={'ack':True}:raise ValueError('session acknowledgement failed')
        answer=answers[-1]
        if not isinstance(answer,dict):raise ValueError('Expected JSON object')
        if 'code_check' in task:
            code=answer['code']
            if not isinstance(code,str) or len(code.encode())>32768:raise ValueError('Invalid code')
            child=subprocess.run([sys.executable,'-I','-S',str(Path(__file__).resolve()),'--code-child'],input=json.dumps({'name':task['code_check'],'code':code}),capture_output=True,text=True,timeout=5)
            if child.returncode:raise ValueError('Code evaluation failed: '+child.stderr[-500:])
            result=json.loads(child.stdout)
            return {'pass':result['passed']==result['total'],'fraction':result['passed']/result['total'],'code_cases':result}
        checks={}
        for key,expected in task['expected'].items():
            actual=answer.get(key)
            if isinstance(expected,(int,float)):
                ok=isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isclose(actual,expected,rel_tol=1e-3,abs_tol=1e-6)
            else:ok=type(actual)==type(expected) and actual==expected
            checks[key]=ok
        if task['category']=='direct' and set(answer)!=set(task['expected']):checks['exact_fields']=False
        return {'pass':all(checks.values()),'fraction':sum(checks.values())/len(checks),'checks':checks}
    except (ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as e:
        return {'pass':False,'fraction':0,'reason':str(e)}


def command(work):
    cmd=['codex','exec','--json','--ignore-user-config','--ignore-rules','--sandbox','read-only','--skip-git-repo-check','-C',str(work),'-m',MODEL,'-c','model_reasoning_effort="max"','-c','web_search="disabled"','-c','skills.include_instructions=false','-c','skills.bundled.enabled=false']
    for value in ['skip_host_skill_discovery=true','plugins=false','apps=false','shell_tool=false','unified_exec=false','multi_agent=false','memories=false']:
        cmd+=['-c','features.'+value]
    return cmd


def inspect_context(home,skill,condition,expected_turns):
    contexts=[];messages=[];base_hashes=[]
    for f in home.glob('sessions/**/*.jsonl'):
        for line in f.read_text(encoding='utf-8').splitlines():
            event=json.loads(line);p=event['payload']
            if event['type']=='session_meta':base_hashes.append(sha(json.dumps(p.get('base_instructions'),sort_keys=True).encode()))
            if event['type']=='turn_context':contexts.append({'model':p.get('model'),'effort':p.get('effort')})
            if event['type']=='response_item' and p.get('role') in ('user','developer'):
                messages.append('\n'.join(c.get('text','') for c in p.get('content',[])))
    # Native AGENTS.md adds the full body as one session instruction message.
    copies=sum(text.count(skill.strip()) for text in messages)
    expected=1 if condition=='root' else 0
    if copies!=expected:raise ValueError(f'Context copies {copies}, expected {expected}')
    if len(contexts)!=expected_turns or any(c!={'model':MODEL,'effort':EFFORT} for c in contexts):
        raise ValueError('Model/effort/turn count mismatch: '+repr(contexts))
    forbidden=['PONYTAIL MODE ACTIVE','CAVEMAN MODE ACTIVE','ADHD MODE ACTIVE','Available skills']
    if any(s in t for s in forbidden for t in messages):raise ValueError('Other skill or global instructions leaked')
    developer=[t for t in messages if '<permissions instructions>' in t or '<multi_agent_' in t]
    return {'model_contexts':contexts,'root_body_copies':copies,'base_instructions_sha256':sorted(set(base_hashes)),'common_developer_sha256':sha('\n'.join(developer).encode())}


def run_one(index,task,trial,condition,skill,auth,timeout):
    row={'type':'response','schedule_position':index,'task_id':task['id'],'category':task['category'],'trial':trial,'condition':condition,'turns':[]}
    started=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='root-benchmark-') as d:
            p=Path(d);home=p/'codex';home.mkdir();work=p/'work';work.mkdir()
            (home/'auth.json').symlink_to(auth)
            if condition=='root':(work/'AGENTS.md').write_text(skill,encoding='utf-8')
            env={**os.environ,'CODEX_HOME':str(home)};thread=None;previous_usage={}
            for prompt in task['turns']:
                cmd=command(work)
                if thread:cmd+=['resume',thread]
                cmd+=['-']
                t=time.perf_counter()
                r=subprocess.run(cmd,input=prompt,capture_output=True,text=True,env=env,timeout=timeout)
                events=[];answer=None;usage={}
                for line in r.stdout.splitlines():
                    event=json.loads(line);events.append(event)
                    if event.get('type')=='thread.started':thread=event['thread_id']
                    if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='agent_message':answer=event['item']['text']
                    if event.get('type')=='turn.completed':usage=event.get('usage',{})
                elapsed=round((time.perf_counter()-t)*1000)
                cumulative_usage=usage
                usage={k:v-previous_usage.get(k,0) for k,v in cumulative_usage.items()}
                if any(v<0 for v in usage.values()):raise ValueError('Nonmonotonic cumulative usage')
                previous_usage=cumulative_usage
                # Publish CLI events; omit host-local temp paths and session identifiers.
                for event in events:
                    if 'thread_id' in event:event['thread_id']='<isolated-session>'
                    if 'item' in event and 'message' in event['item']:event['item']['message']=event['item']['message'].replace(str(p),'<temporary>')
                row['turns'].append({'answer':answer,'usage':usage,'cumulative_usage':cumulative_usage,'latency_ms':elapsed,'events':events,'exit_code':r.returncode})
                tool_events=[e for e in events if e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','web_search','file_change')]
                if tool_events:raise ValueError('Unexpected tool use')
                if r.returncode or answer is None:raise ValueError('Codex failure: '+r.stderr.replace(str(p),'<temporary>')[-2000:])
            row['context_check']=inspect_context(home,skill,condition,len(task['turns']))
    except Exception as e:row['error']=str(e)
    row['latency_ms']=round((time.perf_counter()-started)*1000)
    row['grade']=grade(task,row)
    return row


def summarize(rows,metadata):
    # Regrade both conditions from immutable answers. Keep original grades in JSONL.
    tasks={t['id']:t for t in json.loads((ROOT/'benchmarks/tasks.json').read_text())}
    if sha((ROOT/'benchmarks/tasks.json').read_bytes())!=metadata['tasks_sha256']:
        raise ValueError('Task set changed since collection')
    if sha((ROOT/'skills/root/SKILL.md').read_bytes())!=metadata['skill_sha256']:
        raise ValueError('Skill changed since collection')
    expected=metadata['task_count']*metadata['trials_per_condition']*2
    if len(rows)!=expected:raise ValueError('Incomplete run')
    seen=set();changes=[]
    for row in rows:
        key=(row['task_id'],row['trial'],row['condition'])
        if key in seen:raise ValueError('Duplicate response')
        seen.add(key)
        planned=metadata['schedule'][row['schedule_position']-1]
        if planned!={'task_id':key[0],'trial':key[1],'condition':key[2]}:
            raise ValueError('Schedule mismatch')
        if not row.get('error'):
            check=row['context_check'];turns=row['turns']
            if len(turns)!=len(tasks[row['task_id']]['turns']):raise ValueError('Turn count mismatch')
            if check['root_body_copies']!=(1 if row['condition']=='root' else 0):raise ValueError('Root context mismatch')
            if check['model_contexts']!=[{'model':MODEL,'effort':EFFORT}]*len(turns):raise ValueError('Actual model/effort mismatch')
            for token in turns[-1]['cumulative_usage']:
                if sum(t['usage'][token] for t in turns)!=turns[-1]['cumulative_usage'][token]:raise ValueError('Usage counted twice')
            for turn in turns:
                for event in turn['events']:
                    if 'item' in event and event['item']['type'] not in ('agent_message','error'):raise ValueError('Unexpected tool/event')
        corrected=grade(tasks[row['task_id']],row)
        if corrected!=row['grade']:
            changes.append({'task_id':key[0],'trial':key[1],'condition':key[2],'original':row['grade'],'corrected':corrected})
        row['grade']=corrected
    required={(task,trial,condition) for task in tasks for trial in range(1,metadata['trials_per_condition']+1) for condition in CONDITIONS}
    if seen!=required:raise ValueError('Wrong task/trial/condition coverage')
    results={}
    for condition in CONDITIONS:
        selected=[r for r in rows if r['condition']==condition]
        successes=[r for r in selected if not r.get('error')]
        usage={k:statistics.mean(sum(t['usage'].get(k,0) for t in r['turns']) for r in successes) if successes else None for k in ['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens']}
        results[condition]={'sessions':len(selected),'errors':sum(bool(r.get('error')) for r in selected),'passed':sum(r['grade']['pass'] for r in selected),'pass_rate':statistics.mean(r['grade']['pass'] for r in selected),'median_latency_seconds':statistics.median(r['latency_ms'] for r in selected)/1000,'mean_session_tokens':usage,'categories':{c:{'passed':sum(r['grade']['pass'] for r in selected if r['category']==c),'sessions':sum(r['category']==c for r in selected)} for c in sorted({r['category'] for r in selected})}}
    pairs={}
    for r in rows:pairs.setdefault((r['task_id'],r['trial']),{})[r['condition']]=r
    wins=losses=ties=0;by_task={}
    for (task,_),p in pairs.items():
        if len(p)!=2:raise ValueError('Incomplete paired data')
        diff=int(p['root']['grade']['pass'])-int(p['baseline']['grade']['pass'])
        wins+=diff>0;losses+=diff<0;ties+=diff==0
        by_task.setdefault(task,[]).append(diff)
    values=[statistics.mean(x) for x in by_task.values()];rng=random.Random(20261002)
    draws=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(10000))
    bases={h for r in rows for h in r.get('context_check',{}).get('base_instructions_sha256',[])}
    return {'metadata':metadata,'conditions':results,'paired_sessions':{'root_wins':wins,'root_losses':losses,'ties':ties},'pass_rate_difference_root_minus_baseline':statistics.mean(values),'task_cluster_bootstrap_95_percent_interval':[draws[249],draws[9749]],'base_instructions_consistent':len(bases)==1,'common_developer_instructions_consistent':len({r.get('context_check',{}).get('common_developer_sha256') for r in rows if not r.get('error')})==1,'base_instructions_sha256':sorted(bases),'scoring_runner_sha256':sha(Path(__file__).read_bytes()),'grading_rules':{'numeric_relative_tolerance':1e-3,'numeric_absolute_tolerance':1e-6,'allowed_divmod_and_type':True},'changed_grades':changes,'response_grades':[{'task_id':r['task_id'],'trial':r['trial'],'condition':r['condition'],'grade':r['grade']} for r in sorted(rows,key=lambda r:r['schedule_position'])]}


def self_check():
    tasks=json.loads((ROOT/'benchmarks/tasks.json').read_text())
    assert len(tasks)==24 and len({t['id'] for t in tasks})==24
    for t in tasks:
        if 'expected' in t:
            answer=json.dumps(t['expected']);turns=[{'answer':'{"ack":true}'}] if len(t['turns'])>1 else []
            row={'turns':turns+[{'answer':answer}]}
            assert grade(t,row)['pass'],t['id']
            row['turns'][-1]['answer']='{}';assert not grade(t,row)['pass']
        else:
            # Deliberately wrong constant implementation must fail the oracle.
            r=grade(t,{'turns':[{'answer':json.dumps({'code':f'def {t["code_check"]}(*args): return []'})}]})
            assert not r['pass']
    assert math.isclose(.001*.99**2/(.001*.99**2+.999*.02**2),tasks[4]['expected']['posterior'],rel_tol=1e-6)
    references={
        'merge_busy': 'def merge_busy(intervals):\n out=[]\n for a,b in sorted(intervals):\n  if a>=b:raise ValueError()\n  if out and a<out[-1][1]:out[-1][1]=max(out[-1][1],b)\n  else:out.append([a,b])\n return out',
        'apportion': 'def apportion(total,weights):\n if type(total) is not int:raise ValueError()\n if total<0 or any(w<=0 for w in weights) or (not weights and total):raise ValueError()\n if not weights:return []\n s=sum(weights)\n qr=[divmod(total*w,s) for w in weights]\n out=[q for q,r in qr]\n for i in sorted(range(len(weights)),key=lambda i:(-qr[i][1],i))[:total-sum(out)]:out[i]+=1\n return out',
        'resolve_alias': 'def resolve_alias(mapping,key):\n seen=set()\n while key in mapping:\n  if key in seen:raise ValueError()\n  seen.add(key)\n  key=mapping[key]\n return key',
        'window_counts': 'def window_counts(events,width):\n if width<=0:raise ValueError()\n return [sum(t-width<x<=t for x in events) for t in events]'
    }
    for t in tasks:
        if 'code_check' in t:
            r=grade(t,{'turns':[{'answer':json.dumps({'code':references[t['code_check']]})}]})
            assert r['pass'],(t['id'],r)
    numeric=next(t for t in tasks if t['id']=='queue-tail')
    assert grade(numeric,{'turns':[{'answer':'{"choice":"Y","p95_seconds":0.1498}'}]})['pass']
    assert not grade(numeric,{'turns':[{'answer':'{"choice":"Y","p95_seconds":0.2}'}]})['pass']
    print('PASS benchmark task/grade checks; correct code passes, wrong code fails')


def loading_check(output):
    """Run only this checkout's reviewed plugin in isolated Codex sessions."""
    import platform
    auth=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'auth.json'
    if output.exists():raise ValueError('Choose a new loading-check output')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'model':MODEL,'reasoning_effort':EFFORT,'codex_cli':subprocess.check_output(['codex','--version'],text=True).strip(),'platform':platform.system(),'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip(),'skill_sha256':sha((ROOT/'skills/root/SKILL.md').read_bytes()),'trust_mode':'hook-trust bypass for reviewed local plugin in isolated automation','sessions':[]}
    with tempfile.TemporaryDirectory(prefix='root-plugin-benchmark-') as d:
        base=Path(d);home=base/'codex';home.mkdir();(home/'auth.json').symlink_to(auth)
        env={**os.environ,'CODEX_HOME':str(home)}
        for cmd in [['codex','plugin','marketplace','add',str(ROOT),'--json'],['codex','plugin','add','root@root','--json']]:
            result=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=60)
            if result.returncode:raise ValueError(result.stderr.replace(str(base),'<temporary>'))
        for index in range(3):
            work=base/('work-'+str(index));work.mkdir();cmd=command(work)
            cmd.remove('--ignore-user-config')
            j=cmd.index('features.plugins=false');del cmd[j-1:j+1]
            cmd+=['-c','features.plugins=true','--dangerously-bypass-hook-trust','-']
            started=time.perf_counter()
            result=subprocess.run(cmd,input='Return only {"answer":323} for 17*19. Do not use tools.',capture_output=True,text=True,env=env,timeout=300)
            records=[]
            for path in home.glob('sessions/**/*.jsonl'):
                items=[json.loads(line) for line in path.read_text().splitlines()]
                if items[0]['payload'].get('cwd')==str(work):records=items
            # Count the body only before any model output, not from a self-report.
            copies=0;contexts=[]
            for event in records:
                data=event['payload']
                if event['type']=='turn_context':contexts.append({'model':data.get('model'),'effort':data.get('effort')})
                if event['type']=='response_item':
                    if data.get('type')=='reasoning' or data.get('role')=='assistant':break
                    if data.get('role') in ('user','developer'):
                        copies+=sum(part.get('text','').count(body().strip()) for part in data.get('content',[]))
            answers=[]
            for line in result.stdout.splitlines():
                event=json.loads(line)
                if event.get('item',{}).get('type')=='agent_message':answers.append(event['item']['text'])
            row={'fresh_session':index+1,'root_body_copies_before_model_output':copies,'model_contexts':contexts,'exit_code':result.returncode,'answer':answers[-1] if answers else None,'latency_ms':round((time.perf_counter()-started)*1000),'stderr':result.stderr.replace(str(base),'<temporary>')}
            row['pass']=result.returncode==0 and copies==1 and contexts==[{'model':MODEL,'effort':EFFORT}] and json.loads(row['answer'] or '{}')=={'answer':323}
            report['sessions'].append(row)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    if not all(row['pass'] for row in report['sessions']):raise ValueError('Plugin loading failed; see '+str(output))
    print('PASS three fresh plugin sessions: one body before model output')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--trials',type=int,default=3)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--seed',type=int,default=20261002)
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--loading-check',type=Path,help='Reviewed local plugin only; bypasses hook trust in isolated sessions')
    parser.add_argument('--summarize',type=Path)
    parser.add_argument('--code-child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.code_child:
        print(json.dumps(code_child(json.load(sys.stdin))));return
    if args.self_check:self_check();return
    if args.loading_check:loading_check(args.loading_check);return
    if args.summarize:
        data=[json.loads(l) for l in args.summarize.read_text().splitlines()]
        summary=summarize(data[1:],data[0]);summary['raw_responses_sha256']=sha(args.summarize.read_bytes());out=args.summarize.with_suffix('.summary.json');out.write_text(json.dumps(summary,indent=2)+'\n');print(out);return
    if not args.output or min(args.trials,args.workers,args.timeout)<1:parser.error('Need new --output and positive trials/workers/timeout')
    if args.output.exists():parser.error('Output exists; choose a new path')
    self_check();tasks_path=ROOT/'benchmarks/tasks.json';tasks=json.loads(tasks_path.read_text());skill=body()
    auth=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'auth.json'
    if not auth.is_file():parser.error('Sign in with codex login first')
    schedule=[(t,i,c) for t in tasks for i in range(1,args.trials+1) for c in CONDITIONS]
    random.Random(args.seed).shuffle(schedule)
    metadata={'type':'metadata','started_at':datetime.now(timezone.utc).isoformat(),'model':MODEL,'reasoning_effort':EFFORT,'codex_cli':subprocess.check_output(['codex','--version'],text=True).strip(),'root_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'task_count':len(tasks),'trials_per_condition':args.trials,'max_concurrent_calls':args.workers,'timeout_seconds_per_turn':args.timeout,'schedule_seed':args.seed,'tasks_sha256':sha(tasks_path.read_bytes()),'runner_sha256':sha(Path(__file__).read_bytes()),'skill_sha256':sha((ROOT/'skills/root/SKILL.md').read_bytes()),'body_sha256':sha(skill.encode()),'body_bytes':len(skill.encode()),'loading_path':'native project AGENTS.md; fresh isolated CODEX_HOME for each session','tool_access':'web disabled; shell disabled; no skills catalog, plugins, apps or memories','retries':0,'primary_metric':'all required fields/code cases correct; errors count as failures','schedule':[{'task_id':t['id'],'trial':i,'condition':c} for t,i,c in schedule]}
    args.output.parent.mkdir(parents=True,exist_ok=True);rows=[]
    with args.output.open('x',encoding='utf-8') as f:
        f.write(json.dumps(metadata)+'\n');f.flush()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(run_one,n,t,i,c,skill,auth,args.timeout) for n,(t,i,c) in enumerate(schedule,1)]
            for future in as_completed(futures):
                r=future.result();rows.append(r);f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush()
                print(f'{len(rows)}/{len(schedule)} {r["task_id"]} {r["condition"]} trial {r["trial"]}: {"ERROR "+r["error"] if r.get("error") else "PASS" if r["grade"]["pass"] else "FAIL"}',flush=True)
    summary=summarize(rows,metadata);summary['raw_responses_sha256']=sha(args.output.read_bytes());args.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['conditions','paired_sessions','pass_rate_difference_root_minus_baseline','task_cluster_bootstrap_95_percent_interval','base_instructions_consistent']},indent=2))
    if any(r.get('error') for r in rows):raise SystemExit(1)

if __name__=='__main__':main()
