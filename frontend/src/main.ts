import './style.css';
import { createIcons, Plus, MessagesSquare, Files, ChevronRight, Download, ShieldCheck, Sparkles, Clock3, Landmark, ArrowUpRight, ArrowUp, Menu, LoaderCircle, X, Copy, Check, BookOpen, ChevronDown, Trash2, Info, Lightbulb, FileText, ExternalLink, TriangleAlert, CircleAlert } from 'lucide';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import {loadHistory, saveHistory, type Conversation} from './history';

type Fonte = {ato:string; artigos:string; fonte:string; paginas:string; content:string};
type Resposta = {resposta:string; modelo:string; aviso:string|null; notas:string[]; fontes:Fonte[]; segundos:number};
type Mensagem = {role:'user'|'assistant'; content:string; dados?:Resposta; erro?:boolean};
let mensagens:Mensagem[] = [];
let ocupado = false;
let pronto = false;
let conversas:Conversation<Mensagem>[]=[];
let conversaId:string=crypto.randomUUID();
let avisoHistorico='';
let historicoLegivel=true;
const $ = <T extends HTMLElement = HTMLElement>(selector:string) => document.querySelector<T>(selector)!;
const esc = (s:string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const icon = (name:string) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const markdown = (text:string) => DOMPurify.sanitize(marked.parse(text, {async:false}));
// Abaixo de 1024px a barra lateral vira um menu deslizante.
const drawerMQ = matchMedia('(max-width: 1023.98px)');

$('#app').innerHTML = `
<div class="shell">
 <button id="overlay" class="overlay" aria-label="Fechar menu" tabindex="-1"></button>
 <aside id="sidebar" class="sidebar" aria-label="Menu principal">
  <div class="sidebar-top">
   <a class="brand" href="/" aria-label="Tuca, assistente de legislação da saúde do Tocantins"><img class="brand-logo" src="/tuca-logo.svg" alt="Tuca"><small>Legislação da Saúde · TO</small></a>
   <button id="close-menu" class="icon-button drawer-only" aria-label="Fechar menu">${icon('x')}</button>
  </div>
  <button id="new-chat" class="button-new">${icon('plus')}<span>Nova consulta</span></button>
  <nav class="nav-group" aria-labelledby="nav-title">
   <p id="nav-title" class="nav-label">Consultar</p>
   <button id="chat-nav" class="nav-item active" aria-current="page">${icon('messages-square')}<span>Consulta documental</span></button>
   <button id="documents" class="nav-item">${icon('files')}<span>Documentos disponíveis</span>${icon('chevron-right')}</button>
  </nav>
  <section class="history" aria-labelledby="history-title">
   <div class="history-heading"><p id="history-title" class="nav-label">Conversas salvas <span id="history-count"></span></p><button id="delete-chat" class="icon-button icon-button-sm danger" title="Excluir conversa atual" aria-label="Excluir conversa atual">${icon('trash-2')}</button></div>
   <div id="history-list" aria-label="Conversas salvas"></div>
  </section>
  <div id="sidebar-note" class="sidebar-note">${icon('info')}<div><strong>Sobre esta consulta</strong><p>As respostas são elaboradas a partir dos documentos disponíveis. Abra as referências de cada resposta para conferir o texto original.</p></div><button id="close-note" class="icon-button icon-button-sm" title="Fechar aviso" aria-label="Fechar aviso Sobre esta consulta">${icon('x')}</button></div>
  <div class="sidebar-bottom">
   <button id="export" class="nav-item" disabled>${icon('download')}<span>Exportar conversa</span></button>
   <div class="workspace">${icon('shield-check')} Ambiente local <span>v1.0</span></div>
  </div>
 </aside>
 <main class="main">
  <header class="topbar">
   <button id="menu" class="icon-button drawer-only" aria-label="Abrir menu" aria-controls="sidebar" aria-expanded="false">${icon('menu')}</button>
   <a class="topbar-brand" href="/" aria-label="Tuca, início"><img src="/tuca-logo.svg" alt="Tuca"></a>
   <div class="breadcrumb">Legislação ${icon('chevron-right')} <strong>Consulta documental</strong></div>
   <button id="header-documents" class="button-ghost" aria-label="Ver documentos">${icon('book-open')}<span>Ver documentos</span></button>
  </header>
  <div id="scroll-area" class="scroll-area">
   <section id="welcome" class="column welcome">
    <div class="welcome-hero">
     <img class="hero-mascot" src="/tuca-icon.svg" alt="" width="132" height="100">
     <div>
      <p class="hero-kicker">${icon('sparkles')} Assistente inteligente de normas e documentos</p>
      <h1>Oi, eu sou o Tuca!</h1>
      <p class="intro">Pergunte sobre leis, portarias e atos da saúde do Tocantins. Eu respondo com base nos documentos e mostro de onde veio cada informação, para você conferir.</p>
     </div>
    </div>
    <h2 class="section-label">Por onde começar?</h2>
    <div class="suggestions">
     <button data-question="Quais documentos estão disponíveis na base?" class="suggestion"><span class="tile-icon">${icon('files')}</span><span class="suggestion-text"><strong>Documentos disponíveis</strong><span>Quais normas estão na base?</span></span>${icon('arrow-up-right')}</button>
     <button data-question="Quais regras tratam do plantão extraordinário?" class="suggestion"><span class="tile-icon">${icon('clock-3')}</span><span class="suggestion-text"><strong>Plantões e jornadas</strong><span>Quais regras se aplicam ao plantão extraordinário?</span></span>${icon('arrow-up-right')}</button>
     <button data-question="O que a base diz sobre vencimentos e gratificações?" class="suggestion"><span class="tile-icon">${icon('landmark')}</span><span class="suggestion-text"><strong>Vencimentos e gratificações</strong><span>O que os documentos estabelecem?</span></span>${icon('arrow-up-right')}</button>
    </div>
    <div class="tip">${icon('lightbulb')}<p><strong>Dica:</strong> para uma busca mais precisa, informe a norma, o artigo ou o cargo.</p></div>
   </section>
   <section id="messages" class="column messages" aria-label="Conversa" aria-live="polite"></section>
  </div>
  <div class="composer-area"><div class="column">
   <div id="notice" role="status" hidden>${icon('circle-alert')}<span id="notice-text"></span><button id="refresh" class="button-link" hidden>Tentar novamente</button></div>
   <div id="progress" hidden>${icon('loader-circle')}<span>O Tuca está buscando nos documentos e preparando sua resposta…</span></div>
   <form id="form" class="composer-form"><label class="sr-only" for="question">Sua pergunta</label><textarea id="question" rows="1" maxlength="4000" placeholder="Pergunte ao Tuca sobre a legislação…" enterkeyhint="send" disabled></textarea><span class="hint"><kbd>Enter</kbd> envia · <kbd>Shift</kbd> + <kbd>Enter</kbd> quebra a linha</span><button id="send" class="button-send" type="submit" aria-label="Enviar pergunta" disabled><span>Enviar</span>${icon('arrow-up')}</button></form>
   <p class="disclaimer">A IA pode cometer erros. Confira as fontes e possíveis alterações posteriores nas normas.</p>
  </div></div>
 </main>
</div>
<dialog id="catalog-dialog" aria-labelledby="catalog-title"><div class="dialog-heading"><div><small>Biblioteca local</small><h2 id="catalog-title">Documentos disponíveis</h2></div><button id="close-dialog" class="icon-button" aria-label="Fechar documentos">${icon('x')}</button></div><div id="catalog-content"></div></dialog>`;

function drawIcons(){ createIcons({icons: {Plus, MessagesSquare, Files, ChevronRight, Download, ShieldCheck, Sparkles, Clock3, Landmark, ArrowUpRight, ArrowUp, Menu, LoaderCircle, X, Copy, Check, BookOpen, ChevronDown, Trash2, Info, Lightbulb, FileText, ExternalLink, TriangleAlert, CircleAlert}}); }
function notice(text:string){ const aviso=text||avisoHistorico; $('#notice-text').textContent=aviso; $('#notice').hidden=!aviso; }

// ---------- menu lateral (tablet e celular) ----------
function syncDrawer(){
 const aberto=document.body.classList.contains('menu-open');
 $('#sidebar').toggleAttribute('inert', drawerMQ.matches && !aberto);
 $('#menu').setAttribute('aria-expanded', String(aberto));
}
function setMenu(open:boolean){
 document.body.classList.toggle('menu-open', open && drawerMQ.matches);
 syncDrawer();
 if(open && drawerMQ.matches) $('#close-menu').focus();
}
function closeMenu(){ setMenu(false); }
drawerMQ.addEventListener('change', ()=>setMenu(false));

// Mantém a altura útil correta quando o teclado virtual abre (iOS/Safari).
const vv=window.visualViewport;
function fitViewport(){
 if(!vv || vv.scale>1.01)return;
 document.documentElement.style.setProperty('--app-height', `${Math.round(vv.height)}px`);
 if(window.scrollY)window.scrollTo(0,0);
}
vv?.addEventListener('resize', fitViewport); fitViewport();

function formatDate(iso:string){
 const d=new Date(iso); if(Number.isNaN(d.getTime()))return '';
 const hoje=new Date(); const hora=d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
 return d.toDateString()===hoje.toDateString()?`Hoje, ${hora}`:d.toLocaleDateString('pt-BR',{day:'2-digit',month:'short',year:d.getFullYear()===hoje.getFullYear()?undefined:'numeric'});
}

// Destaca citações normativas (Lei nº 1.234/2012, Art. 5º...) no texto das respostas.
const REFERENCIA=/\b(?:Lei(?:\s+Complementar)?|Decreto(?:-Lei)?|Portaria|Resolução|Emenda\s+Constitucional|Medida\s+Provisória|Instrução\s+Normativa)(?:\s+n\.?\s*[º°o]\.?\s*|\s+)\d(?:[\d.]*\d)?(?:\s*\/\s*\d{2,4})?|\bArts?\.\s*\d+(?:[º°o]|-[A-Z])?(?:\s*(?:,|e|a)\s*\d+(?:[º°o])?)*/gi;
function highlightRefs(root:HTMLElement){
 const walker=document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode:n=>n.parentElement?.closest('a,code,pre,mark')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
 const nodes:Text[]=[]; while(walker.nextNode())nodes.push(walker.currentNode as Text);
 for(const node of nodes){
  const text=node.data; REFERENCIA.lastIndex=0; if(!REFERENCIA.test(text))continue;
  REFERENCIA.lastIndex=0; const frag=document.createDocumentFragment(); let pos=0;
  for(const m of text.matchAll(REFERENCIA)){
   frag.append(text.slice(pos,m.index));
   const mark=document.createElement('mark'); mark.className='lex-ref'; mark.textContent=m[0]; frag.append(mark);
   pos=m.index!+m[0].length;
  }
  frag.append(text.slice(pos)); node.replaceWith(frag);
 }
}

function persist(){
 if(mensagens.length){
  const item:Conversation<Mensagem>={id:conversaId,title:mensagens.find(m=>m.role==='user')?.content.slice(0,65)||'Consulta',messages:mensagens,updated:new Date().toISOString()};
  conversas=[item,...conversas.filter(c=>c.id!==conversaId)];
 }
 try{if(historicoLegivel)saveHistory(localStorage,conversas);}catch{avisoHistorico='Não foi possível salvar no navegador. Exporte a conversa para não perdê-la.';notice('');}
 renderHistory();
}
function renderHistory(){
 $('#history-list').innerHTML=conversas.map(c=>`<button class="history-item ${c.id===conversaId?'selected':''}" data-conversation="${esc(c.id)}" ${ocupado?'disabled':''} title="${esc(c.title)}" ${c.id===conversaId?'aria-current="true"':''}><span class="history-title">${esc(c.title)}</span><time datetime="${esc(c.updated)}">${esc(formatDate(c.updated))}</time></button>`).join('')||'<p>Nenhuma conversa salva.</p>';
 $('#history-count').textContent=conversas.length?String(conversas.length):'';
 $<HTMLButtonElement>('#delete-chat').disabled=ocupado||!conversas.some(c=>c.id===conversaId);
}
function updateControls(){
 $('#send').toggleAttribute('disabled', ocupado || !pronto || !$<HTMLTextAreaElement>('#question').value.trim());
 $<HTMLTextAreaElement>('#question').disabled=!pronto || ocupado;
 $<HTMLButtonElement>('#new-chat').disabled=ocupado;
 $('#progress').hidden=!ocupado;
 $<HTMLButtonElement>('#export').disabled=!mensagens.length;
}
function pdfHref(f:Fonte){ return `/api/fontes/${encodeURIComponent(f.fonte.toLowerCase().endsWith('.pdf')?f.fonte:f.fonte+'.pdf')}#page=${Math.max(1,parseInt(String(f.paginas),10)||1)}`; }
function renderSources(fontes:Fonte[]){
 return `<details class="sources"><summary><span class="sources-icon">${icon('book-open')}</span><span class="sources-title"><strong>${fontes.length} trechos consultados</strong><small>Confira quais trechos sustentam cada afirmação da resposta.</small></span>${icon('chevron-down')}</summary>
 <ol class="source-list">${fontes.map((f,i)=>`<li><details class="source"><summary><span class="source-index">${i+1}</span><span class="source-title"><strong>${esc(f.ato)}</strong><span class="source-meta">${f.artigos?`<span class="chip">${esc(f.artigos)}</span>`:''}<span class="chip">p. ${esc(String(f.paginas))}</span></span></span>${icon('chevron-down')}</summary>
 <div class="source-body"><div class="source-file"><span class="file-name">${icon('file-text')}<span>${esc(f.fonte)}</span></span><a class="pdf-link" target="_blank" rel="noopener noreferrer" href="${pdfHref(f)}">Abrir PDF na página ${esc(String(f.paginas).split('-')[0])} ${icon('external-link')}</a></div><blockquote class="excerpt">${esc(f.content)}</blockquote></div></details></li>`).join('')}</ol></details>`;
}
function renderMessage(m:Mensagem, index:number){
 if(m.role==='user')return `<article class="message user"><div class="bubble"><span class="sr-only">Você: </span><p>${esc(m.content)}</p></div></article>`;
 const d=m.dados;
 return `<article class="message assistant${m.erro?' is-error':''}">
  <div class="message-head"><span class="msg-avatar"><img src="/tuca-icon.svg" alt=""></span><strong>Tuca</strong><span class="tag">Assistente</span></div>
  <div class="answer-card">
   ${m.erro?`<div class="error-text">${icon('circle-alert')}<p>${esc(m.content)}</p></div>`:`<div class="md">${markdown(m.content)}</div>`}
   ${d?`${[d.aviso,...d.notas].filter(Boolean).map(n=>`<p class="note-warning">${icon('triangle-alert')}<span>${esc(n!)}</span></p>`).join('')}
   <div class="answer-actions"><button class="action" data-copy="${index}">${icon('copy')}<span>Copiar resposta</span></button><span class="answer-meta">${icon('clock-3')}${d.segundos}s · ${esc(d.modelo)}</span></div>
   ${d.fontes.length?renderSources(d.fontes):''}`:''}
  </div></article>`;
}
function render(focoNaResposta=false){
 renderHistory();
 $('#welcome').hidden=mensagens.length>0;
 const pendente=ocupado?`<article class="message assistant pending" aria-hidden="true"><div class="message-head"><span class="msg-avatar"><img src="/tuca-icon.svg" alt=""></span><strong>Tuca</strong><span class="typing"><i></i><i></i><i></i></span></div><div class="answer-card"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton short"></span></div></article>`:'';
 $('#messages').innerHTML=mensagens.map(renderMessage).join('')+pendente;
 document.querySelectorAll<HTMLElement>('.message.assistant:not(.is-error) .md').forEach(highlightRefs);
 drawIcons(); updateControls();
 const area=$('#scroll-area');
 const perguntas=document.querySelectorAll<HTMLElement>('.message.user');
 const ultima=perguntas[perguntas.length-1];
 // Com uma resposta nova, rola até a pergunta para a leitura começar do início da resposta.
 if(!mensagens.length)area.scrollTo({top:0});
 else if(focoNaResposta && ultima)area.scrollTo({top:ultima.offsetTop-16,behavior:'smooth'});
 else area.scrollTo({top:area.scrollHeight,behavior:'smooth'});
}
async function request<T>(url:string,init?:RequestInit):Promise<T>{
 const r=await fetch(url,init); const data=await r.json();
 if(!r.ok) throw new Error(typeof data.detail==='string'?data.detail:`Não foi possível concluir a solicitação (${r.status}).`);
 return data;
}
async function checkStatus(){
 $<HTMLButtonElement>('#refresh').disabled=true;
 try {
  const s=await request<{base_pronta:boolean; chave_configurada:boolean}>('/api/status');
  pronto=s.base_pronta && s.chave_configurada;
  notice(pronto?'':'A consulta está indisponível no momento. Entre em contato com o responsável pelo sistema para verificar '+(!s.base_pronta?'a preparação dos documentos.':'a configuração do serviço.'));
 }catch { pronto=false; notice('Não foi possível acessar o serviço. Verifique sua conexão e tente novamente. Se o problema continuar, entre em contato com o responsável pelo sistema.'); }
 finally { $<HTMLButtonElement>('#refresh').disabled=false; $('#refresh').hidden=pronto; }
 updateControls();
}
function autoGrow(){
 const t=$<HTMLTextAreaElement>('#question'); const max=parseFloat(getComputedStyle(t).maxHeight)||200;
 t.style.height='auto'; t.style.height=`${Math.min(t.scrollHeight,max)}px`; t.style.overflowY=t.scrollHeight>max?'auto':'hidden';
}
async function send(question:string){
 if(ocupado || !pronto || !question.trim())return;
 question=question.trim();
 const historico: {pergunta:string;resposta:string}[]=[];
 for(let i=0;i<mensagens.length-1;i++)if(mensagens[i].role==='user' && mensagens[i+1].dados)historico.push({pergunta:mensagens[i].content,resposta:mensagens[i+1].content});
 mensagens.push({role:'user',content:question}); ocupado=true; notice(''); persist();
 $<HTMLTextAreaElement>('#question').value=''; autoGrow(); render();
 try {const dados=await request<Resposta>('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pergunta:question,historico:historico.slice(-2)})}); mensagens.push({role:'assistant',content:dados.resposta,dados});}
 catch(e){mensagens.push({role:'assistant',content:e instanceof Error?e.message:'Falha na conexão. Tente novamente.',erro:true});}
 finally{
  ocupado=false; persist(); render(true);
  // No celular, focar o campo abriria o teclado por cima da resposta.
  if(matchMedia('(pointer: fine)').matches)$<HTMLTextAreaElement>('#question').focus();
 }
}
$('#form').addEventListener('submit',e=>{e.preventDefault();void send($<HTMLTextAreaElement>('#question').value);});
$('#question').addEventListener('keydown',e=>{const key=e as KeyboardEvent;if(key.key==='Enter'&&!key.shiftKey&&!key.isComposing){e.preventDefault();void send($<HTMLTextAreaElement>('#question').value);}});
$('#question').addEventListener('input',()=>{autoGrow();updateControls();});
document.querySelectorAll<HTMLButtonElement>('[data-question]').forEach(b=>b.onclick=()=>{void send(b.dataset.question!);});
$('#new-chat').onclick=()=>{if(ocupado)return;mensagens=[];conversaId=crypto.randomUUID();notice('');render();closeMenu();};
$('#refresh').onclick=()=>{void checkStatus();};
$('#menu').onclick=()=>setMenu(!document.body.classList.contains('menu-open'));
$('#close-menu').onclick=()=>{closeMenu();$('#menu').focus();};
$('#overlay').onclick=closeMenu;
$('#chat-nav').onclick=closeMenu;
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('menu-open')){closeMenu();$('#menu').focus();}});
$('#messages').addEventListener('click',async e=>{
 const button=(e.target as HTMLElement).closest<HTMLButtonElement>('[data-copy]');if(!button)return;
 try{
  await navigator.clipboard.writeText(mensagens[Number(button.dataset.copy)].content);
  const original=button.innerHTML; button.innerHTML=`${icon('check')}<span>Copiado!</span>`; button.classList.add('done'); drawIcons();
  setTimeout(()=>{button.innerHTML=original;button.classList.remove('done');},2000);
 }catch{notice('Não foi possível copiar automaticamente. Selecione o texto da resposta.');}
});
$('#export').onclick=()=>{const text=mensagens.map(m=>`${m.role==='user'?'Você':'Tuca'}\n${m.content}${m.dados?'\n\nFontes:\n'+m.dados.fontes.map(f=>`${f.ato} | ${f.artigos} | ${f.fonte} | p. ${f.paginas}`).join('\n'):''}`).join('\n\n---\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='consulta-saude.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
// Catálogo: separa o nome do arquivo e a ementa de cada ato para leitura mais clara.
function decorateCatalog(root:HTMLElement){
 root.querySelectorAll('li').forEach(li=>{li.innerHTML=li.innerHTML.replace(/^([^:(<]+?)\s*\(arquivo ([^)<]+)\)(?::\s*)?/,(_,ato:string,arquivo:string)=>`<span class="cat-head"><strong>${ato}</strong><span class="cat-file">${arquivo}</span></span>`);});
}
$('#documents').onclick=async()=>{closeMenu();$<HTMLDialogElement>('#catalog-dialog').showModal();$('#catalog-content').innerHTML='<p class="catalog-loading">Carregando documentos…</p>';try{const d=await request<{catalogo:string}>('/api/documentos');$('#catalog-content').innerHTML=markdown(d.catalogo||'Nenhum ato disponível.');decorateCatalog($('#catalog-content'));}catch(e){$('#catalog-content').textContent=e instanceof Error?e.message:'Falha ao carregar documentos.';}};
$('#close-dialog').onclick=()=>$<HTMLDialogElement>('#catalog-dialog').close();
// Feche apenas quando o clique começar e terminar fora do painel.
const catalogDialog=$<HTMLDialogElement>('#catalog-dialog');
function outsideDialog(event:MouseEvent){
 const rect=catalogDialog.getBoundingClientRect();
 return event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom;
}
let startedOutside=false;
catalogDialog.addEventListener('pointerdown',event=>{startedOutside=outsideDialog(event);});
catalogDialog.addEventListener('click',event=>{if(startedOutside && outsideDialog(event))catalogDialog.close();startedOutside=false;});
$('#header-documents').onclick=()=>$('#documents').click();
$('#history-list').onclick=e=>{const b=(e.target as HTMLElement).closest<HTMLButtonElement>('[data-conversation]');if(!b||ocupado)return;const c=conversas.find(c=>c.id===b.dataset.conversation);if(c){conversaId=c.id;mensagens=c.messages;render();closeMenu();}};
$('#delete-chat').onclick=()=>{if(ocupado||!confirm('Excluir esta conversa salva neste navegador?'))return;conversas=conversas.filter(c=>c.id!==conversaId);mensagens=[];conversaId=crypto.randomUUID();persist();render();};
try{conversas=loadHistory<Mensagem>(localStorage);if(conversas.length){conversaId=conversas[0].id;mensagens=conversas[0].messages;}}catch{historicoLegivel=false;avisoHistorico='Não foi possível ler o histórico salvo. Os dados foram preservados; novas conversas não serão salvas. Use a exportação.';notice('');}
// O aviso "Sobre esta consulta" continua fechado depois que o usuário o dispensa.
const AVISO_FECHADO='tuca.aviso-sobre-fechado';
try{$('#sidebar-note').hidden=localStorage.getItem(AVISO_FECHADO)==='1';}catch{}
$('#close-note').onclick=()=>{$('#sidebar-note').hidden=true;try{localStorage.setItem(AVISO_FECHADO,'1');}catch{}};
syncDrawer(); render(); void checkStatus();
