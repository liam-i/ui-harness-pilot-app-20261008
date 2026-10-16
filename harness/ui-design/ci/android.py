"""Thin native Android result contract; shared current UI checking remains upstream."""
import argparse,hashlib,json,math,os,platform,re,signal,subprocess,sys,time,zipfile
from pathlib import Path

def require(condition,message):
    if not condition:raise ValueError(message)

def duration(row,limit):
    start,end=row.get('started_at'),row.get('finished_at')
    require(all(type(v) in [int,float] and math.isfinite(v) for v in [start,end]),'Missing/invalid actual completion times')
    require(0<=end-start<=limit,'Reviewed timeout exceeded')

def verify_native(build,runtime,expected,head):
    try:
        ids=[x['id'] for x in expected['cases']];keys=list(expected['devices'])
        require(ids==[f'A{i:02}' for i in range(1,17)] and keys==['small','regular'],'Independent case/device denominator differs')
        require(expected['cases_per_device']==16 and expected['total_device_cases']==32,'Independent denominator differs')
        require(build['passed'] is True and build['source_head']==head and build['source_dirty']=='','Actual build/source failed')
        require(len(build['steps'])==1,'Missing/duplicate build step')
        step=build['steps'][0]
        require(step['exit']==0 and step['timeout_seconds']==900 and not step.get('timed_out') and not step.get('interrupted'),'Build failed/interrupted')
        duration(step,900);duration(build,1020)
        require(runtime['passed'] is True and runtime['selected_passed'] is True and runtime['mode']=='full','No complete native matrix')
        require(runtime['source_head']==runtime['test_head']==head and runtime['test_dirty']=='','Source/test identity differs')
        require(runtime['expected_cases']==32 and runtime['apk']==build['apk'],'APK/runtime identity differs')
        require(runtime['cleanup_errors']==[] and not runtime.get('interrupted'),'Cleanup failed or run interrupted')
        duration(runtime,4320)
        require(runtime['started_at']>=build['finished_at'],'Stale runtime')
        require([d['key'] for d in runtime['devices']]==keys,'Missing/wrong/duplicate device')
        for index,d in enumerate(runtime['devices']):
            e=expected['devices'][d['key']]
            require(d['serial']=='emulator-'+str(5580+index*2),'Device serial differs')
            require(d['name']=='Harness_UI_'+d['key'].title()+'_20261009','AVD name differs')
            require(d['identity']=={'fingerprint':e['fingerprint'],'api':str(e['api']),'abi':e['abi'],'page_size':str(e['page_size_bytes']),
                'size':f"Physical size: {e['pixels'][0]}x{e['pixels'][1]}",'density':f"Physical density: {e['density_dpi']}"},'Device identity differs')
            require(0<=d['boot_completed_at']-d['boot_started_at']<=240,'Device boot timeout')
            require(d['restored_settings']==d['original_settings'] and set(d['original_settings'])=={'font_scale','accelerometer_rotation','user_rotation'},'Device settings not restored')
            require([c['id'] for c in d['cases']]==ids,'Missing/duplicate/unexpected cases')
            last=d['boot_completed_at']
            for case in d['cases']:
                require(case['status']=='passed' and case['started_at']>=last,'Case not actually completed')
                limit=240 if case['id'] in ['A12','A14','A15','A16'] else 90
                require(case['timeout_seconds']==limit,'Case timeout changed');duration(case,limit)
                require(bool(case['assertions']) and all(a['passed'] is True for a in case['assertions']),'Missing/failed assertions')
                last=case['finished_at']
            require(last-d['cases'][0]['started_at']<=1800 and last<=runtime['finished_at'],'Suite incomplete or timed out')
        return {'passed':True,'device_count':2,'case_count':32}
    except (KeyError,TypeError,IndexError) as error:raise ValueError('Incomplete native result: '+str(error)) from error

def fingerprint(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inside(root,name):
    path=(root/name).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(),'File outside reviewed root')
    return path

def run_command(command,root,output,name,timeout):
    row={'command':command,'started_at':time.time(),'timeout_seconds':timeout,'interrupted':False}
    try:
        with (output/(name+'.stdout')).open('wb') as so,(output/(name+'.stderr')).open('wb') as se:
            child=subprocess.Popen(command,cwd=root,stdout=so,stderr=se,start_new_session=True)
            try:child.wait(timeout=timeout)
            except BaseException:
                row['interrupted']=True;os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=120)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                raise
            finally:row['exit']=child.returncode
    finally:
        row['finished_at']=time.time();(output/(name+'.command.json')).write_text(json.dumps(row,indent=2)+'\n')
    require(row['exit']==0 and not row['interrupted'],name+' failed; raw output retained')
    return row

def verify_artifacts(root,output,build,runtime,expected):
    apk=Path(build['apk']['path']).resolve(strict=True)
    require(apk.is_relative_to(output/'build') and apk.stat().st_size==build['apk']['bytes'] and fingerprint(apk)==build['apk']['sha256'],'Retained APK differs')
    package=root/'design-inputs/packages/UI-FIGMA-ANDROID-MENU/U001'
    with zipfile.ZipFile(apk) as z:
        require(z.read('classes.dex')[:3]==b'dex','Real native classes required')
        for name,path in [('asset-arrow.png','assets/asset-arrow.png'),('asset-reset.png','assets/asset-reset.png'),('tokens.json','tokens.json')]:
            require(hashlib.sha256(z.read('assets/ui/'+name)).hexdigest()==fingerprint(package/path),'Actual APK asset differs from D')
    labels={'default','reset-empty-128','zero-empty','reset-empty-0','session','zero-resumable','reset-resumable-0','resumable','reset-resumable-128'}
    for device in runtime['devices']:
        folder=(output/'runtime'/device['serial']).resolve(strict=True);require(folder.is_relative_to(output/'runtime'),'Invalid evidence path')
        detail=json.loads(inside(folder,'suite.json').read_text());require(detail['cases']==device['cases'],'Case details differ')
        for case in ['A14','A15']:
            shots=[x for x in detail['screenshots'] if x['case']==case]
            require({Path(x['path']).stem for x in shots}=={case+'-'+n for n in labels} and len(shots)==9,'Required visual variant screenshots missing/duplicated')
            for shot in shots:
                png=inside(folder,shot['path']);require(fingerprint(png)==shot['sha256'] and png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Screenshot changed/missing')
                inside(folder,png.with_suffix('.xml').name);obs=json.loads(inside(folder,png.with_suffix('.json').name).read_text())
                require(obs['package']=='io.harness.menu' and obs['state']==shot['state'] and obs['frame']>0,'Screenshot observation mismatched')
        for name in ['commands.json','logcat.txt']:inside(folder,name)
        visual=list(folder.glob('visual-*.json'));require(len(visual)>=21,'Per-state visual evidence incomplete')
        require(all(json.loads(p.read_text())['failures']==[] for p in visual),'Visual evidence reports failure')

def execute(root,config_path,host_path,head,output):
    root=root.resolve(strict=True);output=output.resolve()
    require(not output.exists() and output.parent.is_dir() and not output.is_relative_to(root),'New evidence folder outside source required');output.mkdir()
    record={'passed':False,'head':head,'started_at':time.time(),'adapter_sha256':fingerprint(Path(__file__))}
    def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True,timeout=20).strip()
    def clean():require(git('rev-parse','HEAD')==head and not git('status','--porcelain'),'Actual checked SHA/clean source differs')
    def files():return {name:fingerprint(inside(root,name)) for name in git('ls-files','-z').split('\0') if name}
    try:
        require(re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',head),'Exact independent host SHA required');clean()
        require(platform.system()=='Darwin' and platform.machine()=='arm64','Reviewed Mac ARM64 host required')
        config=json.loads(inside(root,config_path).read_text());host=json.loads(host_path.read_text())
        require(set(config)=={'expected_path','expected_sha256','build_script','test_script','toolchain_files'},'Unexpected CI configuration')
        require(not host_path.resolve(strict=True).is_relative_to(root),'Keep host paths outside repository')
        expected_path=inside(root,config['expected_path']);require(fingerprint(expected_path)==config['expected_sha256'],'Independent expectations changed')
        expected=json.loads(expected_path.read_text());require(bool(config['toolchain_files']),'Tool identities required')
        for tool in config['toolchain_files']:
            path=Path(host[tool['base']])/tool['relative'] if tool['relative'] else Path(host[tool['base']])
            require(fingerprint(path.resolve(strict=True))==tool['sha256'],'Tool identity differs: '+tool['base']+'/'+tool['relative'])
        record.update(config=config,source_files=files())
        record['build_command']=run_command([sys.executable,'-B',str(inside(root,config['build_script'])),'--config',str(host_path),'--output',str(output/'build')],root,output,'build',1020)
        record['runtime_command']=run_command([sys.executable,'-B',str(inside(root,config['test_script'])),'--config',str(host_path),'--build',str(output/'build/result.json'),'--output',str(output/'runtime')],root,output,'runtime',4320)
        build=json.loads((output/'build/result.json').read_text());runtime=json.loads((output/'runtime/result.json').read_text())
        record['verified']=verify_native(build,runtime,expected,head);verify_artifacts(root,output,build,runtime,expected)
        clean();require(record['source_files']==files(),'Tracked source changed during execution');record.update(passed=True,apk=build['apk'])
    except Exception as error:record['error']=str(error)
    finally:record['finished_at']=time.time();(output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--config',required=True)
    p.add_argument('--host-config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    def stop(n,f):
        signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN);raise InterruptedError('CI signal '+str(n))
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        record=execute(a.root,a.config,a.host_config,a.head,a.output)
        print(json.dumps({'passed':record['passed'],'error':record.get('error'),'output':str(a.output)}));return 0 if record['passed'] else 1
    except Exception as error:print(str(error),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
