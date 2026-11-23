Object.assign(P,{x:'<path d="M18 6 6 18M6 6l12 12"/>',up:'<path d="M12 19V5M5 12l7-7 7 7"/>'});
const TK=document.querySelector('meta[name=tk]').content;
const $=(s,e=document)=>e.querySelector(s),$$=(s,e=document)=>[...e.querySelectorAll(s)];
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function ic(r=document){$$('[data-i]',r).forEach(e=>{if(e.dataset.d!=1||e.dataset.k!==e.dataset.i){e.innerHTML='<svg class="i" viewBox="0 0 24 24">'+(P[e.dataset.i]||'')+'</svg>';e.dataset.d=1;e.dataset.k=e.dataset.i}})}
async function api(p,body,method){const o={method:method||(body?'POST':'GET'),headers:{'X-Token':TK}};if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  const r=await fetch(p,o),d=(r.headers.get('content-type')||'').includes('json')?await r.json():await r.text();if(!r.ok)throw new Error((d&&d.error)||r.status);return d}
const B=document.body,WORKSPACE_MODE='Acesso ao workspace',MD=['Pedir aprovação',WORKSPACE_MODE,'Somente plano'];
const S={tasks:[],cur:null,run:false,ask:0,mode:MD.includes(localStorage.mode)?localStorage.mode:'Pedir aprovação',prov:localStorage.prov&&localStorage.prov.startsWith('openai_compat@omniroute')?'auto':(localStorage.prov||'openai_codex'),provs:[],def:'',codexAccounts:[],codexUsage:{},codexUsagePromise:null,codexUsageTimer:null,codexAccount:localStorage.codex_account||'primary',atts:[],chg:[],meta:{},attf:false,ws:'',wsn:'',branch:'',pct:0,art:'',ctl:null,rec:null,term:[],cwd:'',hist:[],hi:0,tpl:null};
let RS={};
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('o');clearTimeout(toast.h);toast.h=setTimeout(()=>t.classList.remove('o'),3200)};
const fail=e=>toast(e.message||String(e));
function md(s){const ps=[];s=s.replace(/```\w*\n?([\s\S]*?)(```|$)/g,(m,c)=>{ps.push('<pre class="cdb">'+esc(c.replace(/\n$/,''))+'</pre>');return '\u0000'+(ps.length-1)+'\u0000'});
  return esc(s).replace(/`([^`\n]+)`/g,'<code class="chip">$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>').replace(/\u0000(\d+)\u0000/g,(m,i)=>ps[i])}
function diffHtml(d){return '<div class="df">'+d.map(l=>l[0]==='h'?'<div class="l h">'+esc(l[2])+'</div>':'<div class="l '+(l[0]==='+'?'a':l[0]==='-'?'m':'')+'"><i>'+l[1]+'</i>'+(l[0]===' '?' ':l[0])+' '+esc(l[2])+'</div>').join('')+'</div>'}
function add(h,c,par){const d=document.createElement('div');d.className=c||'';d.innerHTML=h;(par||$('#col')).insertBefore(d,par?null:$('#think'));ic(d);if(!par)$('#feed').scrollTop=1e9;return d}
function popup(btn,items,up){const m=$('#menu'),r=btn.getBoundingClientRect();m.classList.remove('model-menu');m.style.width='';m.style.right='';m.innerHTML=items.map((x,i)=>x.sep?'<div class="sp"></div>':'<button data-n="'+i+'"'+(x.d?' class="dg"':'')+'>'+(x.i?'<span class="mi">'+x.i+'</span>':'')+esc(x.t)+(x.k?'<span class="k">'+esc(x.k)+'</span>':'')+'</button>').join('');
  m.style.left=Math.min(r.left,innerWidth-240)+'px';m.style.top=up?'auto':(r.bottom+4)+'px';m.style.bottom=up?(innerHeight-r.top+6)+'px':'auto';m.classList.add('o');
  if(!up){const h=m.offsetHeight;if(r.bottom+4+h>innerHeight-8)m.style.top=Math.max(8,innerHeight-h-8)+'px'}
  $$('button',m).forEach(b=>b.onclick=e=>{e.stopPropagation();m.classList.remove('o');items[b.dataset.n].f()})}
const hideMenu=()=>$('#menu').classList.remove('o');
const TH=['green','claude','codex','jarvis'];
function theme(c){B.dataset.ac=c;localStorage.ac=c;$$('.dots i').forEach(x=>x.classList.toggle('on',x.dataset.c===c))}
function setMode(m){
  if(m===WORKSPACE_MODE&&S.prov!=='openai_codex'){S.mode='Pedir aprovação';localStorage.mode=S.mode;$('#apt').textContent=S.mode;$('#sbm').textContent=S.mode.toLowerCase();toast('Acesso ao workspace sem prompts está disponível somente com OpenAI Codex.');return}
  S.mode=m;localStorage.mode=m;$('#apt').textContent=m;$('#sbm').textContent=m.toLowerCase();
  $('#ap').title=m===WORKSPACE_MODE?'Codex sem confirmações dentro da pasta atual; sem rede ou acesso fora dela':'Modo de execução: '+m;
}
function setProv(id){
  S.prov=id;localStorage.prov=id;
  if(S.mode===WORKSPACE_MODE&&id!=='openai_codex'){S.mode='Pedir aprovação';localStorage.mode=S.mode;$('#apt').textContent=S.mode;$('#sbm').textContent=S.mode.toLowerCase();toast('Voltando a Pedir aprovação: o modo sem prompts é exclusivo do Codex.')}
  paintProv();
}
function modelDisplayText(value){return String(value||'').replace(/autom.tico/gi,'automático').replace(/\s*\?\s*/g,' · ')}
function paintProv(){const p=S.provs.find(x=>x.id===(S.prov==='auto'?S.def:S.prov))||{label:'Automático',model:''};$('#mdt').textContent=S.prov==='auto'?'Auto':p.label;$('#crt').textContent=S.prov==='auto'?'Automático':p.label;const details=[modelDisplayText(p.model||(S.prov==='auto'?'Padrão da configuração':'')),S.prov==='openai_codex'?(S.codexAccounts.find(a=>a.id===S.codexAccount)?.label||'Conta principal'):''].filter(Boolean);$('#crs').textContent=details.join(' · ')}
function timeStr(t){const d=t?new Date(t*1000):new Date(),z=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+z(d.getMonth()+1)+'-'+z(d.getDate())+' '+z(d.getHours())+':'+z(d.getMinutes())}
// ---------------------------------------------------------------- tarefas
const TI={r:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',d:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/></svg>'};
async function renameId(id){const t=S.tasks.find(x=>x.id===id);const n=await askIn('Renomear tarefa','Novo nome da tarefa',t?t.title:'');if(!n||!n.trim())return;try{await api('/api/rename',{id:id,title:n.trim()});if(id===S.cur)$('#ttl').textContent=n.trim().slice(0,80);await refresh()}catch(e){fail(e)}}
async function delId(id){const t=S.tasks.find(x=>x.id===id);if(t&&t.running)return toast('Pare a tarefa antes de excluir');if(!await askOk('Excluir permanentemente','A tarefa "'+(t?t.title:'')+'" e o hist\u00f3rico dela ser\u00e3o apagados. Isso n\u00e3o pode ser desfeito.','Excluir permanentemente',true))return;try{await api('/api/delete',{id:id});if(id===S.cur){S.cur=null;await refresh();if(S.tasks.length)openTask(S.tasks[0].id);else{clearFeed();$('#ttl').textContent='Nova tarefa';S.meta={};S.run=false;state()}}else await refresh()}catch(e){fail(e)}}
const PI='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 3h6l-1 7 3 3v2H7v-2l3-3z"/></svg>',AI='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10h14V9"/><path d="M10 13h4"/></svg>',DI='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/></svg>';
const LS=k=>{try{return JSON.parse(localStorage[k]||'[]')}catch(e){return[]}};
function togL(k,id){const a=LS(k),i=a.indexOf(id);i<0?a.push(id):a.splice(i,1);localStorage[k]=JSON.stringify(a)}
function taskMenu(el){const bt=el.closest('.tk'),id=bt.dataset.id,pin=LS('pins').includes(id),arc=LS('arcs').includes(id);popup(bt,[{t:'Renomear',i:TI.r,f:()=>renameId(id)},{t:pin?'Desafixar':'Fixar no topo',i:PI,f:()=>{togL('pins',id);paintTasks()}},{sep:1},{t:arc?'Desarquivar':'Arquivar',i:AI,d:1,f:()=>{togL('arcs',id);paintTasks()}},{t:'Excluir permanentemente',i:TI.d,d:1,f:()=>delId(id)}])}
function paintTasks(){const pins=LS('pins'),arcs=LS('arcs');let ts=S.attf?S.tasks.filter(t=>t.awaiting):S.tasks.slice();const na=ts.filter(t=>arcs.includes(t.id)).length;if(!S.showArc)ts=ts.filter(t=>!arcs.includes(t.id));ts.sort((x,y)=>pins.includes(y.id)-pins.includes(x.id));
  $('#tks').innerHTML=ts.map(t=>'<button class="tk'+(t.id===S.cur?' on':'')+(arcs.includes(t.id)?' ar':'')+'" data-id="'+t.id+'">'+(pins.includes(t.id)?'<span class="pn2">'+PI+'</span>':'')+'<span>'+esc(t.title)+'</span><em class="'+(t.awaiting?'w':'')+'">'+(t.awaiting?'●':t.running?'⠿':'')+'</em><span class="ta" data-a="m" title="Mais ações">'+DI+'</span></button>').join('')||'<div class="mt">Nenhuma tarefa</div>';if(na){$('#tks').insertAdjacentHTML('beforeend','<div class="mt arq" id="arqt">'+(S.showArc?'Ocultar':'Mostrar')+' arquivadas ('+na+')</div>');$('#arqt').onclick=()=>{S.showArc=!S.showArc;paintTasks()}}
  $$('#tks .tk').forEach(b=>{b.onclick=e=>{const x=e.target.closest('.ta');if(x){e.stopPropagation();taskMenu(x);return}openTask(b.dataset.id)};b.oncontextmenu=e=>{e.preventDefault();taskMenu(b)}});$('#attn').textContent=S.tasks.filter(t=>t.awaiting).length||'';$('#att').classList.toggle('on',S.attf)}
async function refresh(){try{const d=await api('/api/state');S.tasks=d.tasks;S.provs=d.providers;S.def=d.default;S.codexAccounts=d.codex_accounts||[{id:'primary',label:'Conta principal',primary:true,authenticated:false}];if(!S.codexAccounts.some(a=>a.id===S.codexAccount)){S.codexAccount='primary';localStorage.codex_account='primary'}if(S.provs.some(p=>p.id==='openai_codex')&&localStorage.getItem('jarvis_codex_default_migrated')!=='v1'){S.prov='openai_codex';localStorage.prov=S.prov;localStorage.jarvis_codex_default_migrated='v1'}if(S.prov.startsWith('openai_compat@omniroute')&&!String(S.def).toLowerCase().includes('omniroute')){S.prov='auto';localStorage.prov='auto'}S.ws=d.ws;S.wsn=d.name;S.branch=d.branch;
  $('#wsn').textContent=d.ws;$('#ftw').textContent='Local · '+d.name;$('#ftb').textContent=d.branch;paintProv();paintTasks()}catch(e){}}
function clearFeed(){$$('#col>*:not(#think):not(#emp)').forEach(x=>x.remove());RS={steps:{},ask:{}};$('#emp').style.display='';S.chg=[];S.art='';paintChg()}
async function newTask(){if(S.cur&&!$$('#col>:not(#think):not(#emp)').length){$('#in').focus();return}
  const t=await api('/api/task/new',{});S.cur=t.id;$('#ttl').textContent=t.title;clearFeed();S.run=false;S.meta={};state();await refresh();$('#in').focus()}
async function openTask(id){if(S.ctl)S.ctl.abort();S.cur=id;clearFeed();const t=await api('/api/task?id='+id);$('#ttl').textContent=t.title;S.meta=t;S.pct=t.pct;
  const last=t.events.map(e=>e.t).lastIndexOf('done');S.rep=true;t.events.forEach((e,i)=>onEv(e,false,i===last));S.rep=false;
  S.run=t.running;if(!t.running){$$('.s.run').forEach(s=>{s.className='s bad';s.firstChild.dataset.i='bad';ic(s)});$$('.ask').forEach(a=>a.remove())}
  $$('.gr.live').forEach(g=>{if(!t.running)endGroup(g)});S.ask=$$('.ask').length;state();paintTasks();refreshChanges();paintPanel();
  if(t.running)stream(id,t.n);$('#feed').scrollTop=1e9}
// ---------------------------------------------------------------- eventos
function ensureGroup(){if(RS.grp)return;RS.grp=add('<div class="gh"><span class="bx" data-i="chev"></span><span class="tm">Executando</span></div><div class="stp"></div>','gr live');
  $('.gh',RS.grp).onclick=function(){this.parentNode.classList.toggle('c')};RS.stp=$('.stp',RS.grp);RS.gn=0}
function step(cls,icon,label,chip,detail){ensureGroup();RS.gn++;return add('<span data-i="'+icon+'"></span><b>'+esc(label)+'</b>'+(chip?'<span class="chip">'+esc(chip)+'</span>':'')+(detail?'<span class="d">· '+esc(detail)+'</span>':''),'s '+cls,RS.stp)}
function endGroup(g){g.classList.remove('live');const n=$$('.s',g).length;$('.tm',g).textContent='Executou · '+n+' etapa'+(n===1?'':'s')}
function expand(el,html){const dt=document.createElement('div');dt.className='dt';dt.innerHTML=html;el.after(dt);el.classList.add('ex');el.onclick=()=>dt.classList.toggle('o')}
function onEv(e,live,lastDone){const T=e.t;
  if(T==='user'){$('#emp').style.display='none';RS.grp=RS.tx=RS.thk=null;RS.t0=Date.now();add(esc(e.text)+((e.atts||[]).length?'<div class="ua">📎 '+e.atts.map(esc).join(', ')+'</div>':''),'um')}
  else if(T==='text'){if(!RS.tx){RS.tx=add('','tx');RS.txt='';RS.grp=null;RS.thk=null}RS.txt+=e.d;RS.tx.innerHTML=md(RS.txt);if(live)$('#feed').scrollTop=1e9}
  else if(T==='think'){RS.tx=null;if(!RS.thk){RS.thk=step('ok','ok','Pensamento','','');RS.thkt=''}RS.thkt+=e.d;let d=$('.d',RS.thk);if(!d){d=document.createElement('span');d.className='d';RS.thk.append(d)}d.textContent='· '+RS.thkt.replace(/\s+/g,' ').slice(-4000)}
  else if(T==='tool'){RS.tx=null;RS.thk=null;const el=step('run','spin',e.label,e.chip,e.detail);RS.steps[e.id]=el;if(live)$('#feed').scrollTop=1e9}
  else if(T==='result'){const el=RS.steps[e.id];if(!el)return;{const pg=$('.pg',el);if(pg)pg.remove()}el.className='s '+(e.ok?'ok':'bad');el.firstChild.dataset.i=e.ok?'ok':'bad';ic(el);
    if(e.label)$('b',el).textContent=e.label;if(e.path)S.art=e.path;let d=$('.d',el);if(!d&&(e.detail||e.err)){d=document.createElement('span');d.className='d';el.append(d)}
    if(d)d.textContent='· '+(e.err&&!e.ok&&e.name!=='run_command'?e.err:(d.textContent.replace(/^· /,'')?d.textContent.replace(/^· /,'')+' · ':'')+(e.detail||'')).replace(/ · $/,'').slice(0,1500);
    if(e.diff&&e.diff.length)expand(el,'<div class="sb2">'+(e.add||0)+' adições, '+(e.del||0)+' remoções</div>'+diffHtml(e.diff));else if(e.out)expand(el,'<pre class="tr">'+esc(e.out)+'</pre>')}
  else if(T==='prog'){const el=RS.steps[e.id];if(!el)return;let p=$('.pg',el);if(!p){p=document.createElement('span');p.className='pg';p.innerHTML='<span class="pgb"><i></i></span><span class="pgt"></span>';el.append(p)}$('.pgt',p).textContent=e.d;$('.pgb i',p).style.width=(e.pct||0)+'%';$('#feed').scrollTop=1e9}
  else if(T==='todos'){S.meta.todos=e.items;paintTodos()}
  else if(T==='ask'){RS.tx=null;const o='Aprovar somente esta ação';
    const a=add('<div class="q">'+e.title+'<small>'+(e.danger?'comando potencialmente perigoso · ':'')+'aguardando aprovação</small></div>'+(e.cmd?'<code class="cmd">'+esc(e.cmd)+'</code>':'')+(e.diff?diffHtml(e.diff):'')+
      '<button class="op f" data-k="1"><b>1</b>'+o+'</button>'+(e.always?'<button class="op" data-k="2"><b>2</b>Aprovar sempre ('+esc(e.always)+')</button>':'')+'<button class="op" data-k="3"><b>'+(e.always?3:2)+'</b>Não, e dizer ao Jarvis o que fazer diferente</button>','ask');
    a.dataset.id=e.id;a.dataset.kind=e.kind;RS.ask[e.id]=a;S.ask++;state();$$('.op',a).forEach(b=>b.onclick=()=>answer(e.id,+b.dataset.k))}
  else if(T==='asked'){const a=RS.ask[e.id];if(a){const bad=e.choice===3,cmd=a.dataset.kind==='cmd',q=$('.q',a),chip=cmd?$('.cmd',a).textContent.slice(0,90):(($('code',q)||{}).textContent||'');
    a.outerHTML='<div class="s '+(bad?'bad':'ok')+'"><span data-i="'+(bad?'bad':'ok')+'"></span><b>'+esc(cmd?'Executar comando':q.textContent.split(' ')[0]+' arquivo')+'</b>'+(cmd?'':'<span class="chip">'+esc(chip)+'</span>')+'<span class="d">· '+(cmd?esc(chip)+' · ':'')+['', 'aprovado uma vez', e.scope==='session'?'aprovado nesta sess?o':'aprovado sempre', 'recusado'][e.choice]+'</span></div>';ic();S.ask=Math.max(0,S.ask-1);delete RS.ask[e.id];state()}}
  else if(T==='compact'){add('<span data-i="cmp"></span>Contexto comprimido','cc')}
  else if(T==='error'){step('bad','bad','Erro','',e.msg)}
  else if(T==='usage'){setPct(e.pct)}
  else if(T==='changes'){if(live)refreshChanges()}
  else if(T==='done'){setPct(e.pct);$$('.gr.live').forEach(endGroup);RS.grp=RS.tx=RS.thk=null;if(live){S.run=false;state();loadMeta();refresh()}
    add('Trabalhou por '+e.secs+'s','wk');if(live||lastDone)addFc()}}
function setPct(p){S.pct=p;$('#pct').textContent=p+'%';$('#barf').style.setProperty('--p',p+'%')}
function paintTodos(){const it=S.meta.todos||[];let el=$('.td');if(!it.length){if(el)el.remove();return}
  const h='<h4>Tarefas</h4>'+it.map(x=>'<div class="'+(x.status==='done'?'d2':x.status==='in_progress'?'n':'')+'"><span class="bx2">'+(x.status==='done'?'✓':'')+'</span>'+esc(x.text)+'</div>').join('');
  if(!el){el=document.createElement('div');el.className='td';$('#col').insertBefore(el,$('#think'))}el.innerHTML=h;paintPill()}
async function answer(id,k){let note='';if(k===3)note=(await askIn('Ajustar','O que o Jarvis deve fazer diferente?',''))||'';try{await api('/api/approve',{ask:id,choice:k,note})}catch(e){fail(e)}}
async function stream(id,from){if(S.ctl)S.ctl.abort();const ctl=S.ctl=new AbortController();
  try{const r=await fetch('/api/stream?id='+id+'&from='+from,{headers:{'X-Token':TK},signal:ctl.signal}),rd=r.body.getReader(),dc=new TextDecoder();let buf='';
    for(;;){const {done,value}=await rd.read();if(done)break;buf+=dc.decode(value,{stream:true});let i;
      while((i=buf.indexOf('\n\n'))>=0){const c=buf.slice(0,i);buf=buf.slice(i+2);if(c.startsWith('data: ')){const e=JSON.parse(c.slice(6));if(e.t==='end'){if(S.cur===id){S.run=false;state()}return}if(S.cur===id)onEv(e,true)}}}}
  catch(e){if(e.name!=='AbortError')toast('conexão com o servidor perdida')}}
// ---------------------------------------------------------------- estado / painéis
S.tab='pa';
function state(){$('#sd').innerHTML='<svg class="i" viewBox="0 0 24 24">'+(S.run?'<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>':P.up)+'</svg>';
  $('#sd').classList.toggle('idle',!S.run&&!$('#in').value.trim());$('#think').style.display=S.run&&!S.ask?'':'none';paintPill()}
function paintPill(){const p=$('#pill'),n=S.chg.length,td=(S.meta&&S.meta.todos)||[];if(!S.run&&!n){$('#pw').classList.add('h');return}$('#pw').classList.remove('h');
  const a=S.chg.reduce((s,f)=>s+f.add,0),d=S.chg.reduce((s,f)=>s+f.del,0),dn=td.filter(x=>x.status==='done').length;p.className='pill'+(S.run?'':' idle');
  p.innerHTML='<span data-i="'+(S.run?'spin':'ok')+'"></span>'+(td.length?'Etapa '+Math.min(dn+(S.run?1:0),td.length)+' / '+td.length+'<span class="x">·</span>':'')+(n?n+' arquivo'+(n>1?'s':'')+' alterado'+(n>1?'s':'')+' <span class="a">+'+a+'</span><span class="m">-'+d+'</span>':'trabalhando…');ic(p)}
async function refreshChanges(){if(!S.cur){S.chg=[];paintChg();return}try{S.chg=(await api('/api/changes?id='+S.cur)).files}catch(e){S.chg=[]}paintChg()}
function paintChg(){$('#chgn').textContent=S.chg.length;paintPill();if(S.tab==='pb')renderPB();if(S.tab==='pa')renderPA()}
async function addFc(){await refreshChanges();$$('.fc').forEach(x=>x.remove());const n=S.chg.length;if(!n)return;
  const el=add('<div class="r hh">'+n+' arquivo'+(n>1?'s':'')+' alterado'+(n>1?'s':'')+'<button>Revisar</button></div>'+S.chg.map(f=>'<div class="r"><span>'+esc(f.path)+'</span><em>+'+f.add+'</em></div>').join(''),'fc');$('button',el).onclick=()=>tab('pb')}
async function loadMeta(){if(!S.cur)return;try{S.meta=await api('/api/task?id='+S.cur)}catch(e){}if(S.tab==='pa')renderPA()}
function tab(p){B.classList.remove('norp');$('#trp').classList.add('on');S.tab=p;$$('.tab').forEach(t=>t.classList.toggle('on',t.dataset.p===p));$$('.rp .pn').forEach(x=>x.classList.toggle('on',x.id===p));paintPanel();const ta=$('.tab.on');if(ta&&ta.scrollIntoView)ta.scrollIntoView({block:'nearest',inline:'nearest'})}
function paintPanel(){({pa:renderPA,pb:renderPB,pc:renderPC,pd:termPaint}[S.tab])()}
async function renderPA(){const m=S.meta||{},procs=(m.procs||[]).slice().reverse();let env={add:0,del:0};try{env=await api('/api/env')}catch(e){}if(S.tab!=='pa')return;
  $('#pa').innerHTML='<div class="cd"><span data-i="leaf"></span><small>Atualizado em '+timeStr(m.updated)+'</small><p>'+esc((m.last||'Nenhum resumo ainda — envie uma tarefa ao Jarvis.').slice(0,420))+'</p></div>'+
  '<div class="ht">Ambiente</div><div class="it" title="Diferença do repositório contra o último commit"><span class="ib" data-i="br"></span><span class="mono"><span class="pa">+'+env.add+'</span> <span class="pb">-'+env.del+'</span></span></div>'+
  '<div class="it"><span class="ib" data-i="mon"></span><span>'+esc(S.wsn)+'</span></div><div class="it"><span class="ib" data-i="br"></span><span>'+esc(S.branch)+'</span></div>'+
  '<div class="it cl" id="rcm"><span class="ib" data-i="cm"></span><span>Commit ou push</span></div>'+
  '<div class="ht">Processos em segundo plano</div>'+(procs.map(p=>'<div class="it"><span class="ib" data-i="term"></span><span class="mono" title="'+esc(p.cmd)+'">'+esc(p.cmd)+'</span><span class="'+(p.ok?'pa':'fail')+'" style="margin-left:auto;flex:none;font-size:11.5px">'+(p.ok?'OK':'Falhou')+'</span></div>').join('')||'<div class="mt">Nenhum processo</div>')+
  '<div class="ht">Artefato</div>'+(S.art?'<div class="it cl" id="rart"><span class="ib" data-i="file"></span><span>'+esc(S.art.split('/').pop())+'</span></div>':'<div class="mt">Nenhum arquivo ainda</div>')+
  '<div class="ht">Fonte<button id="rsrc" data-i="plus" title="Anexar arquivo"></button></div><div class="it"><span class="ib" style="color:var(--bl)" data-i="folder"></span><span>'+esc(S.wsn)+'</span></div>'+
  S.atts.map(a=>'<div class="it"><span class="ib" style="color:var(--ok)" data-i="file"></span><span>'+esc(a.name)+'</span></div>').join('');
  ic($('#pa'));$('#rcm').onclick=commitFlow;$('#rsrc').onclick=()=>$('#fin').click();if($('#rart'))$('#rart').onclick=()=>openFile(S.art)}
async function openSkills(){const m=$('#skm');m.classList.add('o');$('#skq').value='';$('#skl').innerHTML='<div class="mt">Carregando...</div>';$('#skq').focus();
try{S.sk=await api('/api/skills')}catch(e){$('#skl').innerHTML='<div class="mt">Falha ao ler as skills.</div>';return}
paintSK()}
function paintSK(){const d=S.sk||{agents:[],skills:[]},q=($('#skq').value||'').toLowerCase().trim(),L={instaladas:'Instaladas',superpowers:'Superpowers',opencode:'OpenCode'};
const hit=(...a)=>!q||a.join(' ').toLowerCase().includes(q);
const row=(ico,name,chip,det)=>'<div class="it cl"><span class="ib" data-i="'+ico+'"></span><span>'+esc(name)+'</span>'+(chip?'<span class="chip" style="margin-left:auto;flex:none">'+esc(chip)+'</span>':'')+'</div><div class="skd">'+det+'</div>';
const ag=d.agents.filter(a=>hit(a.name,a.desc,a.model,a.uses.join(' '))),grp={};
d.skills.filter(s=>hit(s.name,s.desc,s.source)).forEach(s=>(grp[s.origin]=grp[s.origin]||[]).push(s));
let h='<div class="ht">Agentes<span class="chip" style="margin-left:8px">'+ag.length+'</span></div>'+(ag.map(a=>row('spark',a.name,a.mode,esc(a.desc)+(a.model?'<br><span class="mono">'+esc(a.model)+'</span>':'')+(a.uses.length?'<br>Skills citadas no prompt: '+esc(a.uses.join(', ')):''))).join('')||'<div class="mt">Nenhum agente</div>');
const ks=Object.keys(grp);
ks.forEach(k=>{h+='<div class="ht">Skills \u00b7 '+(L[k]||esc(k))+'<span class="chip" style="margin-left:8px">'+grp[k].length+'</span></div>'+grp[k].map(s=>row('file',s.name,'',esc(s.desc)+'<br><span class="mono">'+esc(s.path)+'</span><br>'+(s.source?'Origem: '+esc(s.source)+(s.installed?' \u00b7 instalada em '+esc(s.installed):'')+' \u00b7 ':'')+s.files+' arquivo(s)')).join('')});
if(!ks.length)h+='<div class="mt">'+(q?'Nenhuma skill encontrada.':'Nenhuma skill instalada.')+'</div>';
h+='<div class="mt" style="padding-top:12px">Skills nao sao aplicadas automaticamente: selecione com $ ou digite [$nome] para carrega-las nesta tarefa.</div>';
$('#skl').innerHTML=h;ic($('#skl'));$$('#skl .it.cl').forEach(i=>i.onclick=()=>{const label=i.querySelector('span:nth-child(2)')?.textContent||'';if(S.skillInsert){const sk=(S.sk.skills||[]).find(x=>x.name===label);if(!sk){toast('Escolha uma skill da lista, não um agente');return}const folder=sk?.path?.split(String.fromCharCode(92)).join('/').split('/').slice(-2,-1)[0]||label.toLowerCase().replace(/[^a-z0-9_.-]+/g,'-');ta.value+=(ta.value?' ':'')+'[$'+folder+'] ';ta.focus();ta.oninput();S.skillInsert=false;$('#skm').classList.remove('o')}else i.nextElementSibling.classList.toggle('on')})}
function renderPB(){const el=$('#pb'),f=S.chg;if(!f.length){el.innerHTML='<div class="mt">Nenhuma alteração não revisada.</div>';return}
  const a=f.reduce((s,x)=>s+x.add,0),d=f.reduce((s,x)=>s+x.del,0);
  el.innerHTML='<div style="font-size:12.5px;color:var(--dim);display:flex;gap:10px"><b style="color:var(--fg)">Não revisadas</b><span class="pa mono">+'+a+'</span><span class="pb mono">-'+d+'</span><span style="margin-left:auto">'+f.length+' arquivo'+(f.length>1?'s':'')+'</span></div>'+
    f.map((x,i)=>'<div><div class="fh">▾ '+esc(x.path)+'<em>+'+x.add+(x.del?' -'+x.del:'')+'</em><button class="rv" data-k="'+i+'">reverter</button></div>'+diffHtml(x.diff)+'</div>').join('')+
    '<div class="rft"><button id="rva">Reverter tudo</button><button class="p" id="cmt">Fazer commit</button></div>';
  $$('.fh',el).forEach(h=>h.onclick=()=>{const df=h.nextElementSibling;df.style.display=df.style.display==='none'?'':'none'});
  $$('.rv',el).forEach(b=>b.onclick=e=>{e.stopPropagation();revert(S.chg[b.dataset.k].key)});$('#rva').onclick=()=>revert();$('#cmt').onclick=commitFlow}
async function revert(key){if(S.run)return toast('Pare a tarefa antes de reverter');if(!await askOk('Reverter',key?'Reverter este arquivo?':'Reverter todas as altera\u00e7\u00f5es desta tarefa?','Reverter',true))return;
  try{await api('/api/revert',{id:S.cur,key});toast('Revertido');refreshChanges();$$('.fc').forEach(x=>x.remove())}catch(e){fail(e)}}
async function commitFlow(){if(!S.chg.length)return toast('Nenhuma alteração desta tarefa para commitar');const m=await askIn('Commit','Mensagem do commit:','Jarvis: '+$('#ttl').textContent);if(m===null)return;
  try{await api('/api/commit',{id:S.cur,message:m});toast('Commit feito');$$('.fc').forEach(x=>x.remove());refreshChanges();refresh()}catch(e){fail(e)}}
async function renderPC(){if(S.view)return;$('#pc').innerHTML='<div class="tree" id="tr0"></div>';await loadDir('.',$('#tr0'))}
async function loadDir(p,box){try{const d=await api('/api/tree?path='+encodeURIComponent(p));
  box.innerHTML=d.items.map(i=>'<div class="tn" data-p="'+esc(i.path)+'" data-d="'+(i.dir?1:0)+'"><span class="ar">'+(i.dir?'▸':'·')+'</span>'+esc(i.name)+(i.st?'<em>'+i.st+'</em>':'')+'</div>').join('')||'<div class="mt">vazia</div>';
  $$('.tn',box).forEach(n=>{if(n.parentNode!==box)return;n.onclick=async e=>{e.stopPropagation();if(n.dataset.d!=='1')return openFile(n.dataset.p);const nx=n.nextElementSibling;
    if(nx&&nx.classList.contains('kids')){nx.remove();$('.ar',n).textContent='▸'}else{const k=document.createElement('div');k.className='kids';n.after(k);$('.ar',n).textContent='▾';await loadDir(n.dataset.p,k)}}})}catch(e){fail(e)}}
async function openFile(p){S.view=p;tab('pc');try{const f=await api('/api/file?path='+encodeURIComponent(p)),ls=f.text.split('\n').slice(0,600);
  $('#pc').innerHTML='<div class="vb"><button id="vbk">← voltar</button><span>'+esc(f.path)+'</span></div><div class="df">'+ls.map((l,i)=>'<div class="l"><i>'+(i+1)+'</i>  '+esc(l)+'</div>').join('')+(f.lines>600?'<div class="l h">… mostrando 600 de '+f.lines+' linhas</div>':'')+'</div>';
  $('#vbk').onclick=()=>{S.view=null;renderPC()}}catch(e){S.view=null;fail(e);renderPC()}}
function termPaint(){const h=$('#trh');h.innerHTML=S.term.map(x=>'<span class="p">'+esc(x.p)+'</span> '+esc(x.cmd)+'\n'+esc(x.out||'')).join('\n');h.scrollTop=1e9;$('#tpr').textContent='PS '+S.cwd+'>'}
$('#tci').onkeydown=async e=>{if(e.key==='Enter'){const c=e.target.value.trim();if(!c)return;e.target.value='';S.hist.push(c);S.hi=S.hist.length;const it={p:'PS '+S.cwd+'>',cmd:c,out:'executando…'};S.term.push(it);termPaint();
    try{const r=await runTerm(c);it.out=r.out;S.cwd=r.cwd}catch(x){it.out=x.message}termPaint()}
  else if(e.key==='ArrowUp'){e.preventDefault();S.hi=Math.max(0,S.hi-1);e.target.value=S.hist[S.hi]||''}else if(e.key==='ArrowDown'){e.preventDefault();S.hi=Math.min(S.hist.length,S.hi+1);e.target.value=S.hist[S.hi]||''}};
// ---------------------------------------------------------------- composer
const ta=$('#in'),SL=[['/plan','modo somente plano'],['/clear','limpar conversa'],['/compact','comprimir contexto'],['/model','trocar modelo'],['/commit','commitar alterações'],['/voz','ditar por voz']];
function pmenu(it){const m=$('#menu'),r=ta.getBoundingClientRect();if(!it.length){hideMenu();return}m.innerHTML=it.map(x=>'<button data-v="'+esc(x[0])+'">'+esc(x[0])+'<span class="k">'+esc(x[1])+'</span></button>').join('');
  m.style.left=r.left+'px';m.style.top='auto';m.style.bottom=(innerHeight-r.top+8)+'px';m.classList.add('o');$$('button',m).forEach(b=>b.onclick=e=>{e.stopPropagation();pick(b.dataset.v)})}
function pick(v){ta.value=v[0]==='/'&&!ta.value.includes(' ')?v+' ':ta.value.replace(/@\S*$/,'@'+v+' ');hideMenu();ta.focus();ta.oninput()}
let ft;ta.oninput=()=>{ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,200)+'px';const v=ta.value,at=v.match(/@(\S*)$/);
  const sm=v.match(/\[\$([\w.-]*)$/);if(sm){clearTimeout(ft);ft=setTimeout(async()=>{try{if(!S.sk)S.sk=await api('/api/skills');const list=(S.sk.skills||[]).filter(x=>x.name.toLowerCase().includes(sm[1].toLowerCase())).slice(0,8);popup($('#skillpick'),list.map(x=>({t:'[$'+x.name+']',k:x.origin,f:()=>{const folder=x.path.replace(/\\/g,'/').split('/').slice(-2,-1)[0]||x.name.toLowerCase();ta.value=ta.value.replace(/\[\$[\w.-]*$/,'[$'+folder+'] ');hideMenu();ta.focus();ta.oninput()}})),true)}catch(e){}},80)}else if(v[0]==='/'&&!v.includes(' '))pmenu(SL.filter(x=>x[0].startsWith(v)));else if(at){clearTimeout(ft);ft=setTimeout(async()=>{try{const d=await api('/api/find?q='+encodeURIComponent(at[1]));if(ta.value.match(/@(\S*)$/))pmenu(d.files.slice(0,8).map(f=>[f,'arquivo']))}catch(e){}},150)}else hideMenu();
  $('#sd').classList.toggle('idle',!S.run&&!v.trim())};
ta.onkeydown=e=>{const o=$('#menu').classList.contains('o')&&$('#menu [data-v]');if(o&&(e.key==='Tab'||e.key==='Enter')){e.preventDefault();pick(o.dataset.v);return}
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();S.run?toast('Aguarde ou pare a tarefa (■)'):send()}};
async function send(){const v=ta.value.trim();if((!v&&!S.atts.length)||S.run)return;if(v[0]==='/'&&await slash(v))return;if(!S.cur)await newTask();
  const atts=S.atts;S.atts=[];renderAtts();ta.value='';ta.oninput();
  try{const r=await api('/api/send',{id:S.cur,text:v||'Analise os anexos enviados e me diga o que encontrou.',mode:S.mode,provider:S.prov,codex_account:S.codexAccount,atts});S.run=true;state();stream(S.cur,r.n-1);refresh()}catch(e){S.atts=atts;renderAtts();ta.value=v;fail(e)}}
async function stopRun(){try{await api('/api/stop',{id:S.cur})}catch(e){fail(e)}}
$('#sd').onclick=()=>S.run?stopRun():send();
async function slash(v){const c=v.split(/\s+/)[0];if(c==='/plan'){setMode('Somente plano');toast('Modo: Somente plano')}else if(c==='/clear')await clearTask();else if(c==='/compact')await compactCtx();
  else if(c==='/model')modelPicker($('#md2'));else if(c==='/commit')await commitFlow();else if(c==='/voz')mic();else return false;ta.value='';ta.oninput();return true}
async function clearTask(){if(!S.cur)return;if(S.run)return toast('Pare a tarefa antes');if(!await askOk('Limpar conversa','Toda a conversa desta tarefa ser\u00e1 apagada.','Limpar',true))return;try{await api('/api/clear',{id:S.cur});clearFeed();S.meta={};setPct(0)}catch(e){fail(e)}}
async function compactCtx(){if(!S.cur||S.run)return toast('Nada para comprimir agora');toast('Comprimindo contexto…');try{const r=await api('/api/compact',{id:S.cur,provider:S.prov});if(r.managed){toast('O Codex gerencia a compacta??o do contexto automaticamente');setPct(r.pct)}else{add('<span data-i="cmp"></span>Contexto comprimido','cc');setPct(r.pct);toast('Contexto comprimido')}}catch(e){fail(e)}}
function codexUsageResetLabel(ts){
  if(!ts)return '';
  const d=new Date(ts*1000);
  if(Number.isNaN(d.getTime()))return '';
  return 'renova '+d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' às '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
}
function codexUsageMarkup(id){
  const u=S.codexUsage[id];
  if(!u||u.status==='loading')return '<span class="pm-usage-note">Consultando consumo da conta…</span>';
  if(u.status==='not_connected')return '<span class="pm-usage-note">Entre nessa conta para consultar o uso</span>';
  if(u.status==='unsupported')return '<span class="pm-usage-note">Uso não disponível para este tipo de login</span>';
  if(u.status==='unavailable')return '<span class="pm-usage-note">Não foi possível consultar · tente atualizar</span>';
  if(u.status==='no_limits')return '<span class="pm-usage-note">O Codex não informou uma janela de limite</span>';
  if(u.status==='unlimited')return '<span class="pm-usage-note">Sem limite de uso informado</span>';
  if(u.status!=='ready'||!u.windows?.length)return '<span class="pm-usage-note">Uso indisponível</span>';
  return u.windows.map(w=>{
    const pct=Math.max(0,Math.min(100,Number(w.used_percent)||0)),remaining=Math.max(0,100-pct),level=pct>=90?'high':pct>=75?'medium':'normal';
    return '<span class="pm-usage-window"><span class="pm-usage-caption"><b>'+esc(w.label)+' · '+esc(w.period)+'</b><strong class="'+level+'">'+pct+'% usado</strong></span><span class="pm-usage-meter '+level+'"><i style="width:'+pct+'%"></i></span><span class="pm-usage-foot">'+remaining+'% disponível'+(w.resets_at?' · '+esc(codexUsageResetLabel(w.resets_at)):'')+'</span></span>';
  }).join('')+(u.refreshing?'<span class="pm-usage-note">Atualizando dados…</span>':'');
}
function positionModelMenu(anchor){
  const m=$('#menu');
  if(!m.classList.contains('model-menu')||!m.classList.contains('o'))return;
  anchor=anchor&&anchor.isConnected?anchor:$('#crd');
  const r=anchor.getBoundingClientRect(),h=m.offsetHeight,maxTop=Math.max(8,innerHeight-h-8),above=r.top-h-8;
  const top=above>=8?above:Math.min(r.bottom+8,maxTop);
  m.style.bottom='auto';
  m.style.top=Math.max(8,Math.min(top,maxTop))+'px';
}
function paintCodexUsage(){
  const m=$('#menu');
  if(!m.classList.contains('model-menu'))return;
  $$('[data-usage-account]',m).forEach(el=>{el.innerHTML=codexUsageMarkup(el.dataset.usageAccount)});
  positionModelMenu(S.codexUsageAnchor);
}
async function loadCodexUsage(force=false,attempt=0){
  if(S.codexUsagePromise)return S.codexUsagePromise;
  S.codexUsagePromise=(async()=>{
    try{
      const d=await api('/api/codex/usage'+(force?'?refresh=1':''));
      S.codexUsage=d.accounts||{};
      paintCodexUsage();
      const pending=Object.values(S.codexUsage).some(x=>x.status==='loading'||x.refreshing);
      if(pending&&attempt<18){
        clearTimeout(S.codexUsageTimer);
        S.codexUsageTimer=setTimeout(()=>loadCodexUsage(false,attempt+1),1400);
      }
    }catch(e){
      if(attempt===0)toast('Não foi possível consultar o uso do Codex');
    }
  })();
  try{return await S.codexUsagePromise}finally{S.codexUsagePromise=null}
}
function modelPicker(anchor){
  S.codexUsageAnchor=anchor;
  const m=$('#menu'),r=anchor.getBoundingClientRect(),providers=S.provs.map((p,i)=>({id:p.id,index:i,label:(String(p.label||p.id).toLowerCase()==='gemini'?'Gemini':(p.label||p.id)),model:p.model||'',kind:/gemini/i.test((p.label||'')+' '+p.id)?'gemini':/nvidia|nemotron|glm/i.test((p.label||'')+' '+p.id)?'nvidia':/codex|openai/i.test((p.label||'')+' '+p.id)?'openai':'default'}));
  const autoSelected=S.prov==='auto';
  const providerRows=providers.map(p=>'<button type="button" class="pm-item'+(S.prov===p.id?' selected':'')+'" data-provider="'+p.index+'" aria-pressed="'+(S.prov===p.id)+'"><span class="pm-logo '+p.kind+'">'+(p.kind==='openai'?'C':p.kind==='gemini'?'G':p.kind==='nvidia'?'N':'AI')+'</span><span class="pm-copy"><strong>'+esc(p.label)+'</strong><small>'+esc(modelDisplayText(p.model||p.id))+'</small></span><span class="pm-check" aria-hidden="true">✓</span></button>').join('');
  const accountSection=S.prov==='openai_codex'?'<section class="pm-section"><div class="pm-section-head"><span>CONTAS OPENAI</span><div class="pm-usage-tools"><small>'+S.codexAccounts.length+' '+(S.codexAccounts.length===1?'conta':'contas')+'</small><button type="button" data-action="refresh-usage" title="Atualizar uso das contas">↻ Atualizar</button></div></div>'+S.codexAccounts.map((a,i)=>'<button type="button" class="pm-account'+(a.id===S.codexAccount?' selected':'')+'" data-account="'+i+'" aria-pressed="'+(a.id===S.codexAccount)+'"><span class="pm-account-mark">'+(a.id===S.codexAccount?'✓':'○')+'</span><span class="pm-copy"><strong>'+esc(a.label)+'</strong><small>'+(a.primary?'Conta principal':'Conta adicional')+'</small><span class="pm-usage" data-usage-account="'+esc(a.id)+'">'+codexUsageMarkup(a.id)+'</span></span><span class="pm-status '+(a.authenticated?'connected':'pending')+'">'+(a.authenticated?'Conectada':'Login pendente')+'</span></button>').join('')+'<div class="pm-actions"><button type="button" class="pm-action" data-action="add"><span class="pm-action-icon">＋</span><span><strong>Adicionar outra conta</strong><small>Conectar outro ChatGPT / Codex</small></span></button>'+(S.codexAccounts.find(a=>a.id===S.codexAccount&&!a.primary)?'<button type="button" class="pm-action compact" data-action="rename"><span class="pm-action-icon">✎</span><span><strong>Renomear conta</strong></span></button>':'')+'</div></section>':'';
  m.classList.add('model-menu');
  m.innerHTML='<div class="pm-heading"><div><strong>Provedor e modelo</strong><small>Escolha quem vai executar suas tarefas</small></div><span class="pm-live">JARVIS</span></div><div class="pm-section"><div class="pm-section-head"><span>PROVEDORES</span><small>'+providers.length+' disponíveis</small></div><button type="button" class="pm-item'+(autoSelected?' selected':'')+'" data-auto="1" aria-pressed="'+autoSelected+'"><span class="pm-logo auto">✦</span><span class="pm-copy"><strong>Automático</strong><small>Usar o padrão definido na configuração</small></span><span class="pm-check" aria-hidden="true">✓</span></button>'+providerRows+'</div>'+accountSection+'<div class="pm-bottom"><button type="button" class="pm-nvidia" data-action="nvidia"><span class="pm-nvidia-mark">N</span><span><strong>Configurar NVIDIA</strong><small>Chave de API e teste dos modelos</small></span><span class="pm-arrow">›</span></button></div>';
  const width=Math.min(360,innerWidth-16);
  m.style.width=width+'px';
  m.style.left=Math.max(8,Math.min(r.left,innerWidth-width-8))+'px';
  m.style.right='auto';m.style.top='auto';m.style.bottom=(innerHeight-r.top+8)+'px';
  m.classList.add('o');
  positionModelMenu(anchor);
  $$('[data-auto]',m).forEach(b=>b.onclick=e=>{e.stopPropagation();hideMenu();setProv('auto')});
  $$('[data-provider]',m).forEach(b=>b.onclick=e=>{e.stopPropagation();const p=S.provs[Number(b.dataset.provider)];if(p){hideMenu();setProv(p.id)}});
  $$('[data-account]',m).forEach(b=>b.onclick=e=>{e.stopPropagation();const a=S.codexAccounts[Number(b.dataset.account)];if(!a)return;S.codexAccount=a.id;localStorage.codex_account=a.id;paintProv();hideMenu();toast('Conta Codex: '+a.label)});
  $$('[data-action]',m).forEach(b=>b.onclick=e=>{e.stopPropagation();const action=b.dataset.action;if(action==='refresh-usage'){loadCodexUsage(true);return}hideMenu();if(action==='add')addCodexAccount();else if(action==='rename')renameCodexAccount();else if(action==='nvidia')openNvidia()});
  if(S.prov==='openai_codex')loadCodexUsage(false);
}
async function addCodexAccount(){const label=await askIn('Adicionar conta Codex','Nome para identificar essa conta (ex.: conta reserva)','Conta '+(S.codexAccounts.length+1));if(label===null)return;try{const r=await api('/api/codex/accounts/add',{label:label.trim()||'Conta Codex'});S.codexAccount=r.account.id;localStorage.codex_account=S.codexAccount;await refresh();paintProv();toast('Login aberto em uma janela do PowerShell. Conclua o login e aguarde a conta aparecer como conectada.')}catch(e){fail(e)}}
async function renameCodexAccount(){const a=S.codexAccounts.find(x=>x.id===S.codexAccount);if(!a||a.primary)return toast('A conta principal n?o pode ser renomeada aqui');const label=await askIn('Renomear conta Codex','Nome exibido no seletor',a.label);if(label===null||!label.trim())return;try{await api('/api/codex/accounts/rename',{id:a.id,label:label.trim()});await refresh();paintProv();toast('Conta renomeada')}catch(e){fail(e)}}
function openNvidia(){$('#nvstatus').textContent='';$('#nvstatus').className='';$('#nvkey').value='';$('#nvtest').disabled=!S.provs.some(p=>p.id==='openai_compat@nvidia');$('#nvm').classList.add('o');setTimeout(()=>$('#nvkey').focus(),0)}
function closeNvidia(){$('#nvm').classList.remove('o');$('#nvkey').value='';$('#nvfileinput').value='';$('#nvstatus').textContent='';$('#nvstatus').className=''}
async function saveNvidia(){const key=$('#nvkey').value.trim(),status=$('#nvstatus'),btn=$('#nvsave');if(!/^nvapi-[A-Za-z0-9_-]{20,}$/.test(key)){status.className='err';status.textContent='Informe uma chave NVIDIA válida (nvapi-…).';return}btn.disabled=true;status.className='';status.textContent='Validando a chave no catálogo NVIDIA…';try{await api('/api/nvidia/configure',{api_key:key});await refresh();setProv('auto');$('#nvtest').disabled=false;$('#nvkey').value='';status.className='ok';status.textContent='Chave validada e salva localmente. Agora teste o Nemotron para ativar o modelo de programação; o Gemini continuará como alternativa.'}catch(e){status.className='err';status.textContent=e.message||'Não foi possível conectar à NVIDIA.'}finally{btn.disabled=false}}
async function importNvidiaDownloads(){const btn=$('#nvdl'),status=$('#nvstatus');btn.disabled=true;status.className='';status.textContent='Lendo o arquivo local e validando no catálogo NVIDIA…';try{await api('/api/nvidia/import-downloads',{});await refresh();setProv('auto');$('#nvtest').disabled=false;status.className='ok';status.textContent='Chave validada e salva localmente. Agora teste o Nemotron para ativar o modelo de programação; o Gemini continuará como alternativa.'}catch(e){status.className='err';status.textContent=e.message||'Não foi possível importar a chave de Downloads.'}finally{btn.disabled=false}}
async function testNvidiaNemotron(){const btn=$('#nvtest'),status=$('#nvstatus');btn.disabled=true;status.className='';status.textContent='Testando geração e ciclo completo de ferramenta no Nemotron…';try{await api('/api/nvidia/test-nemotron',{});await refresh();setProv('auto');closeNvidia();toast('Nemotron testado e ativado como padrão de programação. Gemini permanece como fallback.')}catch(e){status.className='err';status.textContent=e.message||'O Nemotron não passou no teste. O Gemini continua como padrão.'}finally{btn.disabled=false}}
$('#nvdl').onclick=importNvidiaDownloads;$('#nvfile').onclick=()=>$('#nvfileinput').click();
$('#nvfileinput').onchange=async e=>{const f=e.target.files&&e.target.files[0];if(!f)return;const status=$('#nvstatus');try{const content=await f.text(),m=content.match(/Bearer\s+(nvapi-[A-Za-z0-9_-]{20,})/i)||content.match(/(nvapi-[A-Za-z0-9_-]{20,})/i);if(!m)throw new Error('Não encontrei uma chave NVIDIA nesse arquivo.');$('#nvkey').value=m[1];status.className='ok';status.textContent='Chave identificada e ocultada. Clique em “Validar e salvar chave”.'}catch(x){status.className='err';status.textContent=x.message||'Não foi possível ler o arquivo.'}finally{e.target.value=''}};
$('#nvsave').onclick=saveNvidia;$('#nvtest').onclick=testNvidiaNemotron;$('#nvcancel').onclick=closeNvidia;$('#nvx').onclick=closeNvidia;$('#nvm').onclick=e=>{if(e.target.id==='nvm')closeNvidia()};$('#nvkey').onkeydown=e=>{if(e.key==='Enter')saveNvidia()};
function renderAtts(){$('#atl').innerHTML=S.atts.map((a,i)=>'<span class="chip" data-n="'+i+'" title="remover">'+(a.kind==='image'?'<img class="att-thumb" src="'+esc(a.data)+'" alt="">':a.kind==='pdf'?'📄':'📎')+' '+esc(a.name)+' ✕</span>').join('');$$('#atl .chip').forEach(c=>c.onclick=()=>{S.atts.splice(+c.dataset.n,1);renderAtts()});if(S.tab==='pa')renderPA()}
$('#clp').onclick=()=>$('#fin').click();
async function addFiles(files){for(const f of [...files].slice(0,Math.max(0,8-S.atts.length))){if(f.type==='application/pdf'||f.name.toLowerCase().endsWith('.pdf')){if(f.size>20*1024*1024){toast(f.name+': PDF acima de 20 MB');continue}const data=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=no;r.readAsDataURL(f)});S.atts.push({name:f.name,kind:'pdf',data});continue}if(/^image\/(png|jpeg|webp|gif)$/i.test(f.type)){if(f.size>5*1024*1024){toast(f.name+': imagem acima de 5 MB');continue}const data=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=no;r.readAsDataURL(f)});S.atts.push({name:f.name,kind:'image',data});continue}if(f.size>400000){toast(f.name+': maior que 400 KB');continue}const t=await f.text();if(t.includes('\u0000')||t.includes('\ufffd')){toast(f.name+': só arquivos de texto');continue}S.atts.push({name:f.name,text:t})}renderAtts()}
$('#fin').onchange=async e=>{await addFiles(e.target.files);e.target.value=''};
ta.addEventListener('paste',e=>{const fs=[...(e.clipboardData?.items||[])].filter(x=>x.kind==='file'&&x.type.startsWith('image/')).map(x=>x.getAsFile()).filter(Boolean);if(fs.length){e.preventDefault();addFiles(fs);toast('Imagem da área de transferência anexada')}});
const composer=$('.cw');composer.addEventListener('dragover',e=>{e.preventDefault();composer.classList.add('drop')});composer.addEventListener('dragleave',e=>{if(!composer.contains(e.relatedTarget))composer.classList.remove('drop')});composer.addEventListener('drop',e=>{e.preventDefault();composer.classList.remove('drop');if(e.dataTransfer?.files?.length)addFiles(e.dataTransfer.files)});
$('#pls').onclick=e=>{e.stopPropagation();popup($('#pls'),SL.map(x=>({t:x[0],k:x[1],f:()=>{ta.value=x[0]+' ';ta.focus();ta.oninput()}})),true)};
$('#ap').onclick=e=>{e.stopPropagation();popup($('#ap'),MD.map(m=>({t:m,k:m===S.mode?'✓':'',f:()=>setMode(m)})),true)};
$('#md2').onclick=e=>{e.stopPropagation();modelPicker($('#md2'))};$('#crd').onclick=e=>{e.stopPropagation();modelPicker($('#crd'))};
function mic(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return toast('Ditado de voz não é suportado neste navegador');if(S.rec){S.rec.stop();return}
  const r=new SR(),base=ta.value;r.lang='pt-BR';r.interimResults=true;r.continuous=true;r.onresult=ev=>{let s='';for(const x of ev.results)s+=x[0].transcript;ta.value=(base?base+' ':'')+s;ta.oninput()};
  r.onerror=ev=>toast('Ditado: '+ev.error);r.onend=()=>{S.rec=null;$('#mic').classList.remove('on')};r.start();S.rec=r;$('#mic').classList.add('on');toast('Ouvindo… clique no microfone para parar')}
$('#mic').onclick=mic;
// ---------------------------------------------------------------- barra, menus, atalhos
const togRp=()=>{B.classList.toggle('norp');$('#trp').classList.toggle('on')};
const nextTheme=()=>theme(TH[(TH.indexOf(B.dataset.ac)+1)%TH.length]);
async function chWs(){const p=await askIn('Pasta de trabalho','Caminho completo da nova pasta',S.ws);if(!p||p===S.ws)return;try{await api('/api/ws',{path:p});S.view=null;await refresh();S.cwd=S.ws;toast('Pasta: '+S.wsn);if(S.tab==='pc')renderPC();renderPA()}catch(e){fail(e)}}
async function renameT(){if(!S.cur)return;const t=await askIn('Renomear tarefa','Novo nome da tarefa',$('#ttl').textContent);if(!t)return;try{await api('/api/rename',{id:S.cur,title:t});$('#ttl').textContent=t;refresh()}catch(e){fail(e)}}
async function delTask(){if(!S.cur)return;if(!await askOk('Excluir permanentemente','Esta tarefa e o hist\u00f3rico dela ser\u00e3o apagados. Isso n\u00e3o pode ser desfeito.','Excluir permanentemente',true))return;try{await api('/api/delete',{id:S.cur});S.cur=null;await refresh();if(S.tasks.length)openTask(S.tasks[0].id);else{clearFeed();$('#ttl').textContent='Nova tarefa';S.meta={};S.run=false;state()}}catch(e){fail(e)}}
async function exportT(){if(!S.cur)return;try{const t=await api('/api/export?id='+S.cur),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'text/markdown'}));a.download=($('#ttl').textContent||'tarefa').replace(/[^\w-]+/g,'_')+'.md';a.click()}catch(e){fail(e)}}
function copyLast(){const x=$$('.tx').pop();if(!x)return toast('Nenhuma resposta ainda');navigator.clipboard.writeText(x.innerText).then(()=>toast('Resposta copiada'))}
function help(){$('#msi').style.display='none';$('#msr').innerHTML='<pre>Enter envia · Shift+Enter quebra linha · Shift+Tab troca o modo\nCtrl+N nova tarefa · Ctrl+K buscar · Ctrl+B barra lateral\n1 aprova esta ação · 2 recusa\n\n/plan   modo somente plano\n/clear  limpa a conversa\n/compact comprime o contexto\n/model  escolhe o provedor\n/commit commita as alterações da tarefa\n/voz    ditado por voz\n@arquivo anexa o conteúdo do arquivo ao pedido\n\nModos:\n· Pedir aprovação: confirma alterações/comandos conforme solicitado.\n· Acesso ao workspace: OpenAI Codex sem confirmações repetidas, limitado à pasta atual; rede e caminhos externos continuam bloqueados. Para sair desse limite, troque para Pedir aprovação.\n· Somente plano: leitura e planejamento, sem alterações.</pre>';$('#mod').classList.add('o')}
const closeMod=()=>$('#mod').classList.remove('o');
function openSearch(){$('#msi').style.display='';$('#msi').value='';$('#msr').innerHTML='<div class="mt">Digite para buscar em tarefas e arquivos</div>';$('#mod').classList.add('o');$('#msi').focus()}
let st;$('#msi').oninput=e=>{clearTimeout(st);st=setTimeout(async()=>{const q=e.target.value.trim();if(!q)return;try{const d=await api('/api/search?q='+encodeURIComponent(q));
  $('#msr').innerHTML=(d.tasks.length?'<div class="hd">Tarefas</div>'+d.tasks.map(t=>'<button class="rs" data-t="'+t.id+'">'+esc(t.title)+'</button>').join(''):'')+(d.files.length?'<div class="hd">Arquivos</div>'+d.files.map(f=>'<button class="rs" data-f="'+esc(f)+'">'+esc(f)+'</button>').join(''):'')||'<div class="mt">Nada encontrado</div>';
  $$('#msr .rs').forEach(b=>b.onclick=()=>{closeMod();b.dataset.t?openTask(b.dataset.t):openFile(b.dataset.f)})}catch(x){}},200)};
$('#mod').onclick=e=>{if(e.target.id==='mod')closeMod()};
const MB={arq:[{t:'Nova tarefa',k:'Ctrl+N',f:newTask},{t:'Trocar pasta de trabalho…',f:chWs},{t:'Exportar conversa (.md)',f:exportT},{t:'Excluir tarefa',f:delTask}],
  edt:[{t:'Copiar última resposta',f:copyLast},{t:'Renomear tarefa',f:renameT},{t:'Limpar conversa',f:clearTask}],
  exi:[{t:'Barra lateral',k:'Ctrl+B',f:()=>B.classList.toggle('nosb')},{t:'Painel direito',f:togRp},{t:'Terminal',k:'Ctrl+`',f:togBt},{t:'Próximo tema',f:nextTheme}],
  aju:[{t:'Atalhos e comandos',f:help}]};
$$('.tb .mn').forEach(b=>b.onclick=e=>{e.stopPropagation();popup(b,MB[b.dataset.m])});
$('#tsb').onclick=()=>B.classList.toggle('nosb');$('#trp').onclick=togRp;$('#tdb').onclick=function(){B.classList.toggle('notd');this.classList.toggle('on')};
$('#trm2').onclick=()=>{tab('pd');$('#tci').focus()};$('#zap').onclick=compactCtx;$('#nt').onclick=newTask;$('#sr').onclick=openSearch;
$('#att').onclick=()=>{S.attf=!S.attf;paintTasks()};$('#hudb').onclick=async()=>{try{const r=await api('/api/hud',{});if(r&&r.ok===false)toast(r.msg)}catch(e){fail(e)}};$('#ttl').ondblclick=renameT;$('#nsk').onclick=()=>{S.skillInsert=false;openSkills()};$('#skillpick').onclick=()=>{S.skillInsert=true;openSkills()};$('#skq').oninput=paintSK;$('#skm').onclick=e=>{if(e.target.id==='skm')$('#skm').classList.remove('o')};document.addEventListener('keydown',e=>{if(e.key==='Escape')$('#skm').classList.remove('o')});
$('#more').onclick=e=>{e.stopPropagation();popup($('#more'),[{t:'Renomear',f:renameT},{t:'Copiar última resposta',f:copyLast},{t:'Exportar (.md)',f:exportT},{t:'Excluir tarefa',f:delTask}])};
$('#fld').onclick=e=>{e.stopPropagation();popup($('#fld'),[{t:'Abrir no Explorer',f:()=>api('/api/open',{}).catch(fail)},{t:'Trocar pasta de trabalho…',f:chWs}])};
$('#gear').onclick=e=>{e.stopPropagation();popup($('#gear'),[{t:'Configurar NVIDIA · GLM-5.3-Flash',f:openNvidia},{sep:1},{t:'Trocar pasta de trabalho…',f:chWs},{t:'Próximo tema',f:nextTheme},{t:'Limpar conversa',f:clearTask}],true)};
$('#pill').onclick=()=>tab('pb');
$$('.tab').forEach(t=>t.onclick=()=>{if(t.dataset.p==='pc')S.view=null;tab(t.dataset.p)});
$$('.dots i').forEach(d=>d.onclick=()=>theme(d.dataset.c));
document.onclick=hideMenu;
document.addEventListener('keydown',e=>{if(e.key==='Escape'){hideMenu();closeMod();closeNvidia();return}
  if(e.ctrlKey&&e.key==='n'){e.preventDefault();newTask()}else if(e.ctrlKey&&e.key==='k'){e.preventDefault();openSearch()}else if(e.ctrlKey&&e.key==='b'){e.preventDefault();B.classList.toggle('nosb')}
  else if(e.key==='Tab'&&e.shiftKey){e.preventDefault();setMode(MD[(MD.indexOf(S.mode)+1)%MD.length])}
  else if(S.ask&&/^[123]$/.test(e.key)&&!['TEXTAREA','INPUT'].includes(document.activeElement.tagName)){const a=$('.ask');if(a)answer(a.dataset.id,+e.key)}});
setInterval(()=>{$$('.gr.live .tm').forEach(x=>x.textContent='Executando · '+Math.round((Date.now()-(RS.t0||Date.now()))/1000)+'s')},1000);
// ---------------------------------------------------------------- início
(async()=>{theme(TH.includes(localStorage.ac)?localStorage.ac:'green');setMode(S.mode);ic();state();await refresh();S.cwd=S.ws;
  try{const d=await api('/api/state');$('#usr').textContent=d.user||'usuário';$('#uin').textContent=(d.user||'?')[0].toUpperCase()}catch(e){}
  if(S.tasks.length)await openTask(S.tasks[0].id);else paintPanel();setInterval(refresh,3000)})();


function dlgBox(o){return new Promise(res=>{const m=document.createElement('div');m.className='dlg';m.innerHTML='<div class="dlb"><h3></h3><p></p>'+(o.input!=null?'<input type="text" spellcheck="false">':'')+'<div class="dla"><button class="dc">Cancelar</button><button class="dk'+(o.danger?' dg':'')+'"></button></div></div>';
m.querySelector('h3').textContent=o.title;m.querySelector('p').textContent=o.msg||'';m.querySelector('.dk').textContent=o.ok||'OK';
const inp=m.querySelector('input');if(inp)inp.value=o.input;document.body.appendChild(m);if(inp){inp.focus();inp.select()}else m.querySelector('.dc').focus();
const done=v=>{m.remove();document.removeEventListener('keydown',kd,true);res(v)};
const kd=e=>{if(e.key==='Escape'){e.preventDefault();done(null)}else if(e.key==='Enter'&&!o.danger&&e.target.tagName!=='BUTTON'){e.preventDefault();done(inp?inp.value:true)}};
document.addEventListener('keydown',kd,true);
m.querySelector('.dc').onclick=()=>done(null);m.querySelector('.dk').onclick=()=>done(inp?inp.value:true);m.onclick=e=>{if(e.target===m)done(null)}})}
const askIn=(t,msg,v)=>dlgBox({title:t,msg:msg,input:v});
const askOk=async(t,msg,ok,danger)=>(await dlgBox({title:t,msg:msg,ok:ok,danger:danger}))===true;
async function runTerm(c){let r=await api('/api/term',{cmd:c});if(r.approval_required){const ok=await askOk('Autorizar comando no PC','O Jarvis vai executar este comando no terminal:\n\n'+c+'\n\nA autorização vale somente para este comando.','Executar comando',true);if(!ok)return {out:'Comando recusado pelo usuário.',cwd:S.cwd};r=await api('/api/term',{cmd:c,approved:true})}return r;}
function btPaint(){const o=$('#bto');if(!o)return;o.textContent=S.term.map(x=>x.p.replace(/^PS /,'')+' '+x.cmd+'\n'+(x.out||'')).join('\n');o.scrollTop=1e9;$('#btp').textContent=S.cwd+'>'}
function togBt(){const m=$('#btm');m.classList.toggle('o');if(m.classList.contains('o')){btPaint();$('#btin').focus()}}
$('#btx').onclick=togBt;
$('#btin').onkeydown=async e=>{const i=e.target;if(e.key==='ArrowUp'&&S.hist.length){S.hi=Math.max(0,(S.hi===undefined?S.hist.length:S.hi)-1);i.value=S.hist[S.hi]||'';e.preventDefault();return}
if(e.key!=='Enter')return;const c=i.value.trim();if(!c)return;i.value='';S.hist.push(c);S.hi=S.hist.length;const it={p:'PS '+S.cwd+'>',cmd:c,out:'executando...'};S.term.push(it);btPaint();if(typeof termPaint==='function')termPaint();
try{const r=await runTerm(c);it.out=r.out;S.cwd=r.cwd}catch(x){it.out=String(x.message||x)}btPaint();if(typeof termPaint==='function')termPaint()};
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='`'){e.preventDefault();togBt()}});
