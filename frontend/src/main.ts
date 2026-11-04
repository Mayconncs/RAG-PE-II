import './style.css';
import { createIcons, Library, Plus, MessagesSquare, Files, ChevronRight, Quote, Download, ShieldCheck, RefreshCw, Sparkles, Clock3, Landmark, ArrowUpRight, ScanText, Paperclip, ArrowUp, Menu, LoaderCircle, X, UserRound, Copy, BookOpen, ChevronDown } from 'lucide';
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

$('#app').innerHTML = `
<div class="shell">
 <button id="overlay" class="overlay" aria-label="Fechar menu"></button>
 <aside id="sidebar">
  <a class="brand" href="/"> <span class="brand-icon">${icon('library')}</span><span>Legislação Saúde<small>TOCANTINS</small></span></a>
  <button id="new-chat" class="btn btn-primary new-chat">${icon('plus')} Nova consulta</button>
  <p class="nav-label">CONSULTAR</p>
  <button id="chat-nav" class="nav-item active">${icon('messages-square')} Consulta documental</button>
  <button id="documents" class="nav-item">${icon('files')} Documentos da base ${icon('chevron-right')}</button>
  <div class="history-heading">CONVERSAS SALVAS <button id="delete-chat" title="Excluir conversa atual" aria-label="Excluir conversa atual">Excluir atual</button></div>
  <div id="history-list" aria-label="Conversas salvas"></div>
  <div class="sidebar-note"><strong>Sobre esta consulta</strong><p>As respostas usam os documentos indexados na base local.</p><small>Abra as referências de cada resposta para conferir o texto original.</small></div>
  <div class="sidebar-bottom"><div class="base-card"><div><span id="status-dot" class="dot"></span><strong id="base-status">Conectando à base</strong></div><p id="base-detail">Verificando documentos…</p><button id="refresh">${icon('refresh-cw')} Atualizar conexão</button></div>
  <button id="export" class="nav-item" disabled>${icon('download')} Exportar conversa</button><div class="workspace">${icon('shield-check')} Ambiente local <span>v1.0</span></div></div>
 </aside>
 <main><header><button id="menu" class="icon-button mobile-only" aria-label="Abrir menu">${icon('menu')}</button><div class="breadcrumb">Legislação ${icon('chevron-right')} <strong>Consulta documental</strong></div><button id="header-documents" class="btn btn-sm btn-ghost">${icon('book-open')} Ver documentos</button></header>
 <div id="scroll-area"><section id="welcome">
  <div class="welcome-icon">${icon('messages-square')}</div>
  <h1>Consulta à legislação da saúde</h1>
  <p class="intro">Faça uma pergunta sobre leis, portarias e atos do Tocantins.<br>As respostas incluem referências para você conferir nos documentos.</p>
  <div class="section-label"><span>Exemplos de consulta</span></div>
  <div class="suggestions">
   <button data-question="Quais documentos estão disponíveis na base?" class="card suggestion"><span class="tile-icon">${icon('files')}</span><strong>Documentos disponíveis</strong><p>Quais normas estão na base?</p>${icon('chevron-right')}</button>
   <button data-question="Quais regras tratam do plantão extraordinário?" class="card suggestion"><span class="tile-icon">${icon('clock-3')}</span><strong>Plantões e jornadas</strong><p>Quais regras se aplicam ao plantão extraordinário?</p>${icon('chevron-right')}</button>
   <button data-question="O que a base diz sobre vencimentos e gratificações?" class="card suggestion"><span class="tile-icon">${icon('landmark')}</span><strong>Vencimentos e gratificações</strong><p>O que os documentos estabelecem?</p>${icon('chevron-right')}</button>
  </div>
  <div class="source-promise">${icon('book-open')} Para uma busca mais precisa, informe a norma, o artigo ou o cargo.</div>
 </section><section id="messages" aria-label="Conversa" aria-live="polite"></section></div>
 <div class="composer-area"><div id="notice" role="status" hidden></div><div id="progress" hidden>${icon('loader-circle')} Buscando nos documentos e preparando sua resposta…</div>
 <form id="form"><label class="sr-only" for="question">Sua pergunta</label><textarea id="question" rows="1" maxlength="4000" placeholder="Escreva sua pergunta sobre a legislação…" disabled></textarea><div class="composer-bottom"><span>Enter envia · Shift + Enter quebra a linha</span><div><button id="send" class="btn btn-primary btn-sm" type="submit" aria-label="Enviar pergunta" disabled>Enviar ${icon('arrow-up')}</button></div></div></form>
 <p class="disclaimer">A IA pode cometer erros. Confira as fontes e possíveis alterações posteriores nas normas.</p></div>
 </main>
</div>
<dialog id="catalog-dialog"><div class="dialog-heading"><div><small>BIBLIOTECA LOCAL</small><h2>Documentos da base</h2></div><button id="close-dialog" class="icon-button" aria-label="Fechar documentos">${icon('x')}</button></div><div id="catalog-content"></div></dialog>`;

function drawIcons(){ createIcons({icons: {Library, Plus, MessagesSquare, Files, ChevronRight, Quote, Download, ShieldCheck, RefreshCw, Sparkles, Clock3, Landmark, ArrowUpRight, ScanText, Paperclip, ArrowUp, Menu, LoaderCircle, X, UserRound, Copy, BookOpen, ChevronDown}}); }
function notice(text:string){ const aviso=text||avisoHistorico; $('#notice').textContent=aviso; $('#notice').hidden=!aviso; }
function closeMenu(){ document.body.classList.remove('menu-open'); }
function persist(){
 if(mensagens.length){
  const item:Conversation<Mensagem>={id:conversaId,title:mensagens.find(m=>m.role==='user')?.content.slice(0,65)||'Consulta',messages:mensagens,updated:new Date().toISOString()};
  conversas=[item,...conversas.filter(c=>c.id!==conversaId)];
 }
 try{if(historicoLegivel)saveHistory(localStorage,conversas);}catch{avisoHistorico='Não foi possível salvar no navegador. Exporte a conversa para não perdê-la.';notice('');}
 renderHistory();
}
function renderHistory(){
 $('#history-list').innerHTML=conversas.map(c=>`<button class="history-item ${c.id===conversaId?'selected':''}" data-conversation="${esc(c.id)}" ${ocupado?'disabled':''} title="${esc(c.title)}">${esc(c.title)}</button>`).join('')||'<p>Nenhuma conversa salva.</p>';
 $<HTMLButtonElement>('#delete-chat').disabled=ocupado||!conversas.some(c=>c.id===conversaId);
}
function updateControls(){
 $('#send').toggleAttribute('disabled', ocupado || !pronto || !$<HTMLTextAreaElement>('#question').value.trim());
 $<HTMLTextAreaElement>('#question').disabled=!pronto || ocupado;
 $<HTMLButtonElement>('#new-chat').disabled=ocupado;
 $('#progress').hidden=!ocupado;
 $<HTMLButtonElement>('#export').disabled=!mensagens.length;
}
function render(){
 renderHistory();
 $('#welcome').hidden=mensagens.length>0;
 $('#messages').innerHTML=mensagens.map((m,index)=>`<article class="message ${m.role}"><div class="avatar">${icon(m.role==='user'?'user-round':'library')}</div><div class="message-body"><div class="message-label">${m.role==='user'?'Você':'Consulta'}${m.role==='assistant'?'<span>ASSISTENTE</span>':''}</div><div class="prose ${m.erro?'error-text':''}">${m.role==='user'?`<p>${esc(m.content)}</p>`:markdown(m.content)}</div>${m.dados?`${m.dados.aviso?`<p class="warning">${esc(m.dados.aviso)}</p>`:''}${m.dados.notas.map(n=>`<p class="warning">${esc(n)}</p>`).join('')}<div class="answer-meta"><button class="copy" data-copy="${index}">${icon('copy')} Copiar resposta</button><span>${m.dados.segundos}s · ${esc(m.dados.modelo)}</span></div>${m.dados.fontes.length?`<details class="sources"><summary>${icon('book-open')} ${m.dados.fontes.length} trechos consultados ${icon('chevron-down')}</summary><p class="sources-hint">Confira quais trechos sustentam cada afirmação da resposta.</p>${m.dados.fontes.map(f=>`<details class="source"><summary><strong>${esc(f.ato)}</strong><span>${esc(f.artigos)} · p. ${esc(String(f.paginas))}</span></summary><small>${esc(f.fonte)}</small><a class="pdf-link" target="_blank" rel="noopener noreferrer" href="/api/fontes/${encodeURIComponent(f.fonte.toLowerCase().endsWith('.pdf')?f.fonte:f.fonte+'.pdf')}#page=${Math.max(1,parseInt(String(f.paginas),10)||1)}">Abrir PDF na p?gina ${esc(String(f.paginas).split('-')[0])} ?</a><pre>${esc(f.content)}</pre></details>`).join('')}</details>`:''}`:''}</div></article>`).join('');
 drawIcons(); updateControls();
 $('#scroll-area').scrollTo({top:$('#scroll-area').scrollHeight,behavior:'smooth'});
}
async function request<T>(url:string,init?:RequestInit):Promise<T>{
 const r=await fetch(url,init); const data=await r.json();
 if(!r.ok) throw new Error(typeof data.detail==='string'?data.detail:`Não foi possível concluir a solicitação (${r.status}).`);
 return data;
}
async function checkStatus(){
 try {
  const s=await request<{base_pronta:boolean; trechos:number; chave_configurada:boolean}>('/api/status');
  pronto=s.base_pronta && s.chave_configurada;
  $('#status-dot').classList.toggle('connected',pronto);
  $('#base-status').textContent=s.base_pronta?'Base conectada':'Base pendente';
  $('#base-detail').textContent=`${s.trechos.toLocaleString('pt-BR')} trechos indexados`;
  notice(!s.base_pronta?'Prepare a base: execute extrair_pdfs.py, fazer_chunks.py e criar_indice_bm25.py em ordem.':!s.chave_configurada?'Configure OPENROUTER_API_KEY no .env e reinicie o backend.':'');
 }catch { pronto=false; $('#base-status').textContent='Servidor indisponível'; $('#base-detail').textContent='Confira se o FastAPI está rodando.'; notice('Não foi possível conectar ao servidor. Execute python -m uvicorn api:app --reload e atualize a conexão.'); }
 updateControls();
}
async function send(question:string){
 if(ocupado || !pronto || !question.trim())return;
 question=question.trim();
 const historico: {pergunta:string;resposta:string}[]=[];
 for(let i=0;i<mensagens.length-1;i++)if(mensagens[i].role==='user' && mensagens[i+1].dados)historico.push({pergunta:mensagens[i].content,resposta:mensagens[i+1].content});
 mensagens.push({role:'user',content:question}); ocupado=true; notice(''); persist();
 $<HTMLTextAreaElement>('#question').value=''; $<HTMLTextAreaElement>('#question').style.height='auto'; render();
 try {const dados=await request<Resposta>('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pergunta:question,historico:historico.slice(-2)})}); mensagens.push({role:'assistant',content:dados.resposta,dados});}
 catch(e){mensagens.push({role:'assistant',content:e instanceof Error?e.message:'Falha na conexão. Tente novamente.',erro:true});}
 finally{ocupado=false; persist(); render(); $<HTMLTextAreaElement>('#question').focus();}
}
$('#form').addEventListener('submit',e=>{e.preventDefault();void send($<HTMLTextAreaElement>('#question').value);});
$('#question').addEventListener('keydown',e=>{const key=e as KeyboardEvent;if(key.key==='Enter'&&!key.shiftKey&&!key.isComposing){e.preventDefault();void send($<HTMLTextAreaElement>('#question').value);}});
$('#question').addEventListener('input',()=>{const t=$<HTMLTextAreaElement>('#question');t.style.height='auto';t.style.height=`${Math.min(t.scrollHeight,160)}px`;updateControls();});
document.querySelectorAll<HTMLButtonElement>('[data-question]').forEach(b=>b.onclick=()=>{void send(b.dataset.question!);});
$('#new-chat').onclick=()=>{if(ocupado)return;mensagens=[];conversaId=crypto.randomUUID();notice('');render();closeMenu();};
$('#refresh').onclick=()=>{void checkStatus();};
$('#menu').onclick=()=>document.body.classList.toggle('menu-open');
$('#overlay').onclick=closeMenu;
$('#chat-nav').onclick=closeMenu;
$('#messages').addEventListener('click',async e=>{const button=(e.target as HTMLElement).closest<HTMLButtonElement>('[data-copy]');if(!button)return;try{await navigator.clipboard.writeText(mensagens[Number(button.dataset.copy)].content);button.textContent='Copiado!';}catch{notice('Não foi possível copiar automaticamente. Selecione o texto da resposta.');}});
$('#export').onclick=()=>{const text=mensagens.map(m=>`${m.role==='user'?'Você':'Consulta'}\n${m.content}${m.dados?'\n\nFontes:\n'+m.dados.fontes.map(f=>`${f.ato} | ${f.artigos} | ${f.fonte} | p. ${f.paginas}`).join('\n'):''}`).join('\n\n---\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='consulta-saude.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('#documents').onclick=async()=>{closeMenu();$<HTMLDialogElement>('#catalog-dialog').showModal();$('#catalog-content').textContent='Carregando documentos…';try{const d=await request<{catalogo:string}>('/api/documentos');$('#catalog-content').innerHTML=markdown(d.catalogo||'Nenhum ato disponível.');}catch(e){$('#catalog-content').textContent=e instanceof Error?e.message:'Falha ao carregar documentos.';}};
$('#close-dialog').onclick=()=>$<HTMLDialogElement>('#catalog-dialog').close();
$('#header-documents').onclick=()=>$('#documents').click();
$('#history-list').onclick=e=>{const b=(e.target as HTMLElement).closest<HTMLButtonElement>('[data-conversation]');if(!b||ocupado)return;const c=conversas.find(c=>c.id===b.dataset.conversation);if(c){conversaId=c.id;mensagens=c.messages;render();closeMenu();}};
$('#delete-chat').onclick=()=>{if(ocupado||!confirm('Excluir esta conversa salva neste navegador?'))return;conversas=conversas.filter(c=>c.id!==conversaId);mensagens=[];conversaId=crypto.randomUUID();persist();render();};
try{conversas=loadHistory<Mensagem>(localStorage);if(conversas.length){conversaId=conversas[0].id;mensagens=conversas[0].messages;}}catch{historicoLegivel=false;avisoHistorico='Não foi possível ler o histórico salvo. Os dados foram preservados; novas conversas não serão salvas. Use a exportação.';notice('');}
render();void checkStatus();

