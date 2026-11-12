/* Report Speech v2 — browser speech only; no paid AI/TTS requests. */
(()=>{'use strict';if(window.ReportSpeech)return;
const supported='speechSynthesis' in window&&'SpeechSynthesisUtterance' in window;
const synth=supported?window.speechSynthesis:null;
const clean=value=>String(value??'').replace(/https?:\/\/[^\s<>]+/gi,'').replace(/\bwww\.[^\s<>]+/gi,'').replace(/[\u200B-\u200D\uFEFF]/g,'').replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n').trim();
function splitText(text,max=300){
 const parts=[];
 for(const sentence of clean(text).split(/(?<=[。！？；\n])/u)){
  let chars=Array.from(sentence.trim());while(chars.length){let n=Math.min(max,chars.length);if(n<chars.length){const sample=chars.slice(0,n).join('');const comma=Math.max(sample.lastIndexOf('，'),sample.lastIndexOf('、'),sample.lastIndexOf(' '));if(comma>max*.45)n=Array.from(sample.slice(0,comma+1)).length;}const piece=chars.splice(0,n).join('').trim();if(piece)parts.push(piece);}
 }
 const joined=[];for(const part of parts){if(joined.length&&Array.from(joined.at(-1)+' '+part).length<=max)joined[joined.length-1]+=' '+part;else joined.push(part);}return joined;
}
function textFromDOM(root){
 if(!root)return '';
 const copy=root.cloneNode(true);
 copy.querySelectorAll('script,style,button,summary,svg,canvas,.rs-button,.rs-controls,.report-source-link,.rm-source-details,.rm-table-scroll~small,.rm-ai-table-hint').forEach(e=>e.remove());
 copy.querySelectorAll('table').forEach(table=>{
  const headings=[...table.querySelectorAll('thead th')].map(e=>clean(e.textContent));
  const lines=[...table.querySelectorAll('tbody tr')].map(row=>[...row.querySelectorAll('th,td')].map((e,i)=>`${headings[i]?headings[i]+'：':''}${clean(e.textContent)}`).join('，'));
  const text=document.createElement('p');text.textContent=lines.join('。\n');table.replaceWith(text);
 });
 copy.querySelectorAll('a').forEach(a=>{if(/查看.*(?:原始|報告)|PDF|↗|→|檢視|閱讀全文/.test(a.textContent))a.remove();});
 copy.querySelectorAll('p,li,h1,h2,h3,h4,blockquote,figcaption,section,div').forEach(e=>e.appendChild(document.createTextNode('\n')));
 return clean(copy.textContent);
}
function textFromHTML(html){const div=document.createElement('div');div.innerHTML=html;return textFromDOM(div);}
let player,now=null,generation=0,rate=1,mode='full',activeUtterance=null,voiceURI='';
try{voiceURI=localStorage.getItem('report-speech-voice')||'';}catch{}
try{const stored=Number(localStorage.getItem('report-speech-rate'));if([.8,1,1.25,1.5,1.75,2].includes(stored))rate=stored;}catch{}
function css(){if(document.getElementById('rs-style'))return;const style=document.createElement('style');style.id='rs-style';style.textContent=`
.rs-meta-row{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:8px 0 12px}.rs-meta-row>.rm-sub,.rs-meta-row>.report-meta{flex:1 1 180px;min-width:0;margin:0!important}.rs-meta-row>.rs-button{flex:0 0 auto;margin:0 0 0 auto!important;white-space:nowrap}.rs-button{display:inline-flex!important;align-items:center;gap:5px;font:inherit;font-size:13px!important;line-height:1.4;padding:8px 12px!important;min-height:38px;border:1px solid #cbd9e9!important;border-radius:999px!important;background:#edf5ff!important;color:#205c91!important;cursor:pointer;margin:0 0 12px!important;position:relative;z-index:1;touch-action:manipulation}.rs-button:focus-visible,#rs-player button:focus-visible{outline:3px solid #80b8f2;outline-offset:2px}.rs-button[aria-pressed=true]{background:#234f79!important;color:#fff!important}.rs-button:disabled{opacity:.65;cursor:default}
#rs-player{position:fixed;z-index:2147483000;bottom:calc(78px + env(safe-area-inset-bottom,0px));left:50%;transform:translateX(-50%);width:min(680px,calc(100% - 24px));padding:13px 15px;border:1px solid #d7e3f0;border-radius:16px;background:#fff;color:#243a51;box-shadow:0 10px 38px #122a4b30;font-family:-apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;box-sizing:border-box}
#rs-player[hidden]{display:none!important}#rs-player .rs-title{font-weight:750;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-right:36px}#rs-player .rs-status{font-size:12px;color:#65768b;margin:5px 0 9px;line-height:1.5}#rs-player .rs-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}#rs-player button,#rs-player select{font:inherit;font-size:13px;border:1px solid #d5dfeb;border-radius:8px;background:#f5f8fc;color:#27486b;padding:7px 9px;min-height:36px;cursor:pointer}#rs-player button:disabled{opacity:.45;cursor:default}#rs-player .rs-close{position:absolute;right:9px;top:9px;border:0;background:transparent;font-size:20px;padding:0;width:30px;min-height:30px}#rs-player .rs-caption{font-size:11px;color:#8290a1;line-height:1.45;margin:9px 0 0}html[data-theme=dark] #rs-player{background:#222c37;color:#e5edf7;border-color:#46576b}html[data-theme=dark] #rs-player .rs-status{color:#bccbde}html[data-theme=dark] .rs-button{background:#263d53!important;color:#d7e9ff!important;border-color:#486783!important}
`;document.head.append(style);}
function ensurePlayer(){
 if(player)return;css();player=document.createElement('aside');player.id='rs-player';player.hidden=true;player.setAttribute('aria-label','報告朗讀播放器');
 player.innerHTML='<button type="button" class="rs-close" aria-label="停止並關閉播放器">×</button><div class="rs-title"></div><div class="rs-status" role="status" aria-live="polite"></div><div class="rs-controls"><button type="button" data-rs="toggle">暫停</button><button type="button" data-rs="prev">上一段</button><button type="button" data-rs="next">下一段</button><button type="button" data-rs="restart">重播</button><label>語速 <select aria-label="朗讀語速"><option value="0.8">0.8×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="1.75">1.75×</option><option value="2">2×</option></select></label><label>內容 <select aria-label="朗讀內容"><option value="full">全文</option><option value="summary">重點摘要</option></select></label><label>聲音 <select aria-label="朗讀聲音"><option value="">自動選擇中文語音</option></select></label></div><p class="rs-caption">瀏覽器即時朗讀；鎖屏或切換 App 可能中斷。暫停後繼續會重念本段。</p>';
 document.body.append(player);
 player.querySelector('.rs-close').onclick=stop;
 player.querySelector('[data-rs=toggle]').onclick=()=>{if(!now)return;if(now.state==='playing')pause();else if(now.state==='paused'||now.state==='error')speakCurrent();else if(now.state==='done'){now.index=0;speakCurrent();}};
 for(const [action,diff] of [['prev',-1],['next',1]])player.querySelector(`[data-rs=${action}]`).onclick=()=>{if(!now?.chunks?.length)return;now.index=Math.max(0,Math.min(now.chunks.length-1,now.index+diff));speakCurrent();};
 player.querySelector('[data-rs=restart]').onclick=()=>{if(now?.chunks?.length){now.index=0;speakCurrent();}};
 const selects=player.querySelectorAll('select');selects[0].value=String(rate);
 selects[0].onchange=()=>{rate=Number(selects[0].value);try{localStorage.setItem('report-speech-rate',String(rate));}catch{}if(now?.state==='playing')speakCurrent();};
 selects[1].onchange=()=>{mode=selects[1].value;if(now?.data){cancel();try{setChunks();speakCurrent();}catch(error){now.chunks=[];now.state='error';showStatus(error.message);}}};
 updateVoices();
 selects[2].onchange=()=>{voiceURI=selects[2].value;try{localStorage.setItem('report-speech-voice',voiceURI);}catch{}if(now?.state==='playing')speakCurrent();};
}
function buttons(){document.querySelectorAll('.rs-button').forEach(b=>{const current=now&&b.dataset.rsId===now.id;b.setAttribute('aria-pressed',String(!!current&&now.state==='playing'));b.textContent=current&&now.state==='loading'?'載入全文…':current&&now.state==='playing'?'⏸ 暫停朗讀':current&&now.state==='paused'?'▶ 繼續朗讀':'🔊 聆聽';});}
function showStatus(message){if(!player||!now)return;player.hidden=false;player.querySelector('.rs-title').textContent=now.title;player.querySelector('.rs-status').textContent=message;
 const ready=!!now.chunks?.length;for(const b of player.querySelectorAll('[data-rs]'))b.disabled=!ready;
 const toggle=player.querySelector('[data-rs=toggle]');toggle.textContent=now.state==='playing'?'暫停':now.state==='done'?'重播':now.state==='loading'?'載入中':'繼續';
 player.querySelector('[data-rs=prev]').disabled=!ready||now.index<=0;
 player.querySelector('[data-rs=next]').disabled=!ready||now.index>=now.chunks.length-1;buttons();}
function cancel(){generation++;if(synth){synth.cancel();if(synth.paused)synth.resume();}activeUtterance=null;}
function stop(){cancel();now=null;if(player)player.hidden=true;buttons();}
function pause(){if(!now)return;cancel();now.state='paused';showStatus(`已暫停 · 第 ${now.index+1}／${now.chunks.length} 段`);}
function setChunks(){const text=clean(now.data[mode]);if(!text)throw Error(mode==='summary'?'這篇尚無可朗讀的重點摘要':'這篇尚無可朗讀的解析正文');now.chunks=splitText([now.data.intro,text].filter(Boolean).join('。\n'));now.index=0;}
function voiceScore(v){return (/^zh[-_]TW$/i.test(v.lang)?100:0)+(/premium|enhanced|natural|neural|增強|高品質/i.test(v.name)?30:0)+(v.localService?1:0);}
function voices(){return synth.getVoices().filter(v=>/^zh(?:[-_]|$)/i.test(v.lang)).sort((a,b)=>voiceScore(b)-voiceScore(a)||a.name.localeCompare(b.name));}
function voice(){const list=voices();return list.find(v=>v.voiceURI===voiceURI)||list[0];}
function updateVoices(){if(!player)return;const select=player.querySelector('[aria-label="朗讀聲音"]');const options=voices();
 select.replaceChildren();const auto=document.createElement('option');auto.value='';auto.textContent=options.length?'自動選擇中文語音':'裝置預設（未提供中文清單）';select.append(auto);
 const used=new Set();for(const v of options){if(used.has(v.voiceURI))continue;used.add(v.voiceURI);const option=document.createElement('option');option.value=v.voiceURI;option.textContent=v.name+' · '+v.lang;select.append(option);}
 select.value=options.some(v=>v.voiceURI===voiceURI)?voiceURI:'';
}
function speakCurrent(){
 if(!now?.chunks?.length)return;cancel();const token=generation,id=now.id;now.state='playing';const utterance=new SpeechSynthesisUtterance(now.chunks[now.index]);activeUtterance=utterance;utterance.lang='zh-TW';utterance.rate=rate;const v=voice();if(v)utterance.voice=v;
 const valid=()=>now?.id===id&&token===generation;
 utterance.onstart=()=>{if(valid())showStatus(`朗讀中 · 第 ${now.index+1}／${now.chunks.length} 段`);};
 utterance.onend=()=>{if(!valid())return;activeUtterance=null;if(now.index+1<now.chunks.length){now.index++;speakCurrent();}else{now.state='done';showStatus('本篇朗讀完成');}};
 utterance.onerror=e=>{if(!valid())return;now.state='error';showStatus(e.error==='not-allowed'?'瀏覽器未允許播放，請再點「繼續」。':'朗讀中斷，請點「繼續」重試或檢查裝置語音設定。');};
 showStatus(`準備朗讀 · 第 ${now.index+1}／${now.chunks.length} 段`);try{synth.speak(utterance);}catch{if(valid()){now.state='error';showStatus('裝置無法開始朗讀，請點「繼續」重試。');}}
}
async function start(item){
 ensurePlayer();cancel();const token=generation;now={id:item.id,title:item.title||'研究報告',state:'loading',index:0,chunks:[]};showStatus('正在載入本篇解析內容…');
 // Invoke speech in the click gesture before an optional asynchronous shard request.
 // This empty utterance is not research audio and never auto-plays another article.
 try{synth.speak(new SpeechSynthesisUtterance(''));}catch{}
 try{const data=await item.load();if(!now||now.id!==item.id||token!==generation)return;now.data=data;setChunks();speakCurrent();}
 catch(error){if(!now||now.id!==item.id||token!==generation)return;now.state='error';showStatus(clean(error.message||'內容載入失敗，請稍後重試。'));}
}
function attach(card,item){if(!card||!item||card.querySelector('.rs-button'))return;css();
 const b=document.createElement('button');b.type='button';b.className='rs-button';b.dataset.rsId=item.id;b.textContent='🔊 聆聽';b.setAttribute('aria-label',`朗讀：${item.title||'本篇報告'}`);b.setAttribute('aria-pressed','false');
 if(!supported){b.disabled=true;b.textContent='裝置不支援朗讀';}
 else b.onclick=e=>{e.preventDefault();e.stopPropagation();if(now?.id===item.id&&now.state==='loading')return;if(now?.id===item.id&&now.state==='playing')pause();else if(now?.id===item.id&&now.state==='paused')speakCurrent();else start(item);};
 const meta=card.querySelector('.rm-sub,.report-meta');
 const row=document.createElement('div');row.className='rs-meta-row';
 if(meta){meta.replaceWith(row);row.append(meta,b);}
 else{row.append(b);const title=card.querySelector('.report-v2-top,.report-title,.rm-title');if(title)title.insertAdjacentElement('afterend',row);else card.prepend(row);}
 buttons();
}
// An explicit page/category switch stops reading; normal scrolling does not.
document.addEventListener('click',e=>{if(e.target.closest('.nav,[data-category],[data-report-mode],.report-filter,.mobile-page-nav-item'))stop();});
window.addEventListener('pagehide',stop);
if(supported)synth.addEventListener?.('voiceschanged',updateVoices);
window.ReportSpeech={attach,textFromDOM,textFromHTML,clean,splitText,stop};
})();

