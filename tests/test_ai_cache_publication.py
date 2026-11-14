import json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ai_content_research import merge_cache
class CacheRecovery(unittest.TestCase):
 def test_success_survives_failure_and_missing_keys_merge(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);a=p/'a.json';b=p/'b.json'
   a.write_text(json.dumps({'model':'model','items':{'x':{'status':'complete','result':1},'y':{'status':'error'}}}))
   b.write_text(json.dumps({'items':{'x':{'status':'error'},'y':{'status':'complete','result':2},'z':{'status':'error'}}}))
   merge_cache(a,b);v=json.loads(a.read_text())['items'];self.assertEqual(v['x']['result'],1);self.assertEqual(v['y']['result'],2);self.assertIn('z',v)
 def test_missing_backup_does_not_touch_account(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);a=p/'a.json';a.write_text('{"items":{}}');before=a.read_bytes();merge_cache(a,p/'missing');self.assertEqual(a.read_bytes(),before)
 def test_concurrent_report_update_recomputes_without_replacing_remote_history(self):
  import textwrap
  workflow=Path(__file__).resolve().parents[1]/'.github/workflows/ai-portfolio.yml'
  text=workflow.read_text();start=text.index('          set -euo pipefail',text.index('      - name: Commit AI account'));end=text.find('      - name:',start);script=textwrap.dedent(text[start:end if end>=0 else None])
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);remote=p/'remote.git';client=p/'client';writer=p/'writer'
   def git(cwd,*args):return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
   def write(folder,path,value):
    file=folder/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps(value))
   git(p,'init','--bare',str(remote));git(p,'clone',str(remote),str(client));git(client,'config','user.name','fixture');git(client,'config','user.email','fixture@example.com');git(client,'checkout','-b','main')
   write(client,'data/ai_portfolio.json',{'history':['original'],'decisions':['original']});write(client,'data/reports.json',{'source':'old'});write(client,'data/ai_reference_manifest.json',{'files':{'data/reports.json':{}}})
   updater=client/'scripts/update_ai_portfolio.py';updater.parent.mkdir();updater.write_text('''import json
from pathlib import Path
p=Path('data/ai_portfolio.json');d=json.loads(p.read_text());assert d['decisions']==['original'];assert json.loads(Path('data/reports.json').read_text())['source']=='new';d['decisions'].append('fresh');p.write_text(json.dumps(d))
''')
   git(client,'add','.');git(client,'commit','-m','base');git(client,'push','-u','origin','main');git(p,'clone','-b','main',str(remote),str(writer));git(writer,'config','user.name','fixture');git(writer,'config','user.email','fixture@example.com')
   write(writer,'data/reports.json',{'source':'new'});git(writer,'add','.');git(writer,'commit','-m','concurrent report');git(writer,'push')
   write(client,'data/ai_portfolio.json',{'history':['original'],'decisions':['original','unpublished-stale']});write(client,'data/ai_research_content.json',{'items':{'cached':{'status':'complete'}}})
   (client/'.ai-content-cache').mkdir()
   result=subprocess.run(['bash','-c',script],cwd=client,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr+result.stdout)
   self.assertEqual(json.loads((client/'data/ai_portfolio.json').read_text())['decisions'],['original','fresh']);self.assertEqual(git(client,'rev-parse','HEAD'),git(client,'ls-remote','origin','refs/heads/main').split()[0]);self.assertIn('cached',json.loads((client/'data/ai_research_content.json').read_text())['items'])
if __name__=='__main__':unittest.main()
