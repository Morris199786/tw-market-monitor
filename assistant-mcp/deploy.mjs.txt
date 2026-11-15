// Manual deployment helper. Credentials are read from GitHub Actions secrets.
import {readFile,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
const account=process.env.CLOUDFLARE_ACCOUNT_ID?.trim();
const token=process.env.CLOUDFLARE_API_TOKEN?.trim();
const password=process.env.MARKET_ASSISTANT_PASSWORD;
if(!account || !token || !password || password.length<20)throw new Error('請設定CLOUDFLARE_ACCOUNT_ID、CLOUDFLARE_API_TOKEN，以及至少20字元的MARKET_ASSISTANT_PASSWORD。請勿將密碼寫入程式。');
if(!/^[a-f0-9]{32}$/i.test(account))throw new Error('CLOUDFLARE_ACCOUNT_ID格式錯誤：必須是32字元的帳戶ID，不是Email、Zone ID或Token。');
const redact=s=>String(s || '').split(password).join('[REDACTED]').split(token).join('[REDACTED]');
const api=async(path,options={})=>{
 const r=await fetch(`https://api.cloudflare.com/client/v4/accounts/${account}/${path}`,{...options,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...options.headers}});
 let d;try{d=await r.json();}catch{throw new Error(`Cloudflare回應不是JSON：HTTP ${r.status}，步驟 ${path.split('?')[0]}`);}
 if(!r.ok||!d.success){
  const details=(d.errors || []).map(e=>`${e.code ?? 'unknown'}: ${e.message ?? '未提供說明'}`).join('; ');
  throw new Error(redact(`Cloudflare API失敗：HTTP ${r.status}；步驟 ${path.split('?')[0]}；${details || '未提供錯誤碼'}。請依實際錯誤檢查GitHub所存Token、帳戶ID與Token帳戶範圍是否相符。`));
 }return d;
};
let page=1,namespace;
do{const d=await api(`storage/kv/namespaces?per_page=100&page=${page}`);namespace=d.result.find(x=>x.title==='tw-market-research-oauth');if(namespace || d.result.length<100)break;page++;}while(page<20);
if(!namespace)namespace=(await api('storage/kv/namespaces',{method:'POST',body:JSON.stringify({title:'tw-market-research-oauth'})})).result;
const config=JSON.parse(await readFile(new URL('./wrangler.deploy.jsonc',import.meta.url),'utf8'));
config.kv_namespaces=[{binding:'OAUTH_KV',id:namespace.id}];
await writeFile(new URL('./wrangler.deploy.jsonc',import.meta.url),JSON.stringify(config,null,2)+'\n');
function wrangler(args,input){const r=spawnSync('npx',['--yes','wrangler@4.162.0',...args,'--config','wrangler.deploy.jsonc'],{cwd:new URL('.',import.meta.url),env:{...process.env,CI:'true'},input,encoding:'utf8',maxBuffer:4*1024*1024});
 const redact=s=>String(s || '').split(password).join('[REDACTED]').split(token).join('[REDACTED]');process.stdout.write(redact(r.stdout));process.stderr.write(redact(r.stderr));if(r.status!==0)throw new Error('部署未完成，請查看上方Cloudflare錯誤。');}
// Deploy fails closed until the owner secret is configured.
wrangler(['deploy']);wrangler(['secret','put','OWNER_PASSWORD'],password);
const subdomain=(await api('workers/subdomain')).result.subdomain;
if(!subdomain)throw new Error('請先在Cloudflare帳號開通workers.dev網域。');
const url=`https://${config.name}.${subdomain}.workers.dev`;
let ready=false;for(let i=0;i<4;i++){try{const r=await fetch(url+'/health');ready=r.ok&&(await r.json()).ready;if(ready)break;}catch{}await new Promise(r=>setTimeout(r,1500));}
if(!ready)throw new Error('Worker已部署，但健康檢查尚未通過，請檢查KV綁定及OWNER_PASSWORD。');
const unauthorized=await fetch(url+'/mcp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list',params:{}})});
if(unauthorized.status!==401)throw new Error('未授權請求保護檢查未通過。');
console.log(`\n研究資料服務已部署。ChatGPT MCP連線網址：${url}/mcp\n授權方式：OAuth；登入時使用你設定的研究資料連線密碼。`);
if(process.env.GITHUB_STEP_SUMMARY)await writeFile(process.env.GITHUB_STEP_SUMMARY,`## 台股研究唯讀連線\n\nMCP網址：${url}/mcp\n\n請在ChatGPT新增自訂MCP連線，選擇OAuth，並以研究資料連線密碼授權。\n\n健康檢查與未授權401檢查已通過。尚需實際在ChatGPT授權並測試工具。\n`);
