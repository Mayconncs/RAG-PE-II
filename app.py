"""Interface local: python -m streamlit run app.py."""
import logging
import time

import lancedb
import streamlit as st

from config import DB_PATH, NOME_TABELA, PASTA_PDFS
from busca import catalogo, recuperar, formatar_contexto
from main import API_KEY, MODELOS, montar_pergunta, responder

st.set_page_config(page_title="Consulta Saúde · TO", page_icon="📚", layout="wide")
st.markdown("""
<style>
.stApp {background: #f7f9fc;}
.block-container {max-width: 1100px; padding-top: 2.5rem;}
[data-testid="stSidebar"] {background: #eaf0f6;}
[data-testid="stChatMessage"] {background: white; border: 1px solid #e2e8f0;
 border-radius: 16px; margin-bottom: 12px;}
.eyebrow {color:#137c80; font-size:.8rem; font-weight:700; letter-spacing:.14em;}
h1 {letter-spacing:-.04em;}
</style>
""", unsafe_allow_html=True)

st.session_state.setdefault("mensagens", [])
st.session_state.setdefault("trocas", [])


def mostrar_mensagem(item):
    with st.chat_message(item["role"], avatar="📚" if item["role"] == "assistant" else "👤"):
        st.markdown(item["content"])
        if item.get("aviso"):
            st.warning(item["aviso"])
        if item.get("modelo"):
            st.caption(f"Rota: {item['modelo']} · {item['segundos']:.1f} s")
        if item.get("fontes"):
            with st.expander(f"Fontes consultadas · {len(item['fontes'])} trechos"):
                st.caption("Trechos enviados ao modelo; confira quais sustentam cada afirmação da resposta.")
                for fonte in item["fontes"]:
                    st.markdown(f"**{fonte['ato']} · {fonte['artigos']}**")
                    st.caption(f"{fonte['fonte']} · página(s) {fonte['paginas']}")
                    st.text(fonte["content"])
                    st.divider()
        if item.get("notas"):
            with st.expander("Observações da busca"):
                for nota in item["notas"]:
                    st.info(nota)


erro_base = None
quantidade = 0
try:
    tabela = lancedb.connect(DB_PATH).open_table(NOME_TABELA)
    quantidade = tabela.count_rows()
    if not quantidade:
        erro_base = "A base está vazia. Processe os documentos antes de conversar."
except Exception:
    erro_base = "A base de documentos ainda não está disponível."

with st.sidebar:
    st.markdown("### 📚 Consulta Saúde")
    st.caption("LEGISLAÇÃO · TOCANTINS")
    if st.button("＋ Nova conversa", use_container_width=True):
        st.session_state.mensagens = []
        st.session_state.trocas = []
        st.rerun()
    st.divider()
    st.markdown("**Sua base de consulta**")
    st.caption(f"{len(list(PASTA_PDFS.glob('*.pdf')))} PDFs na pasta de entrada · {quantidade} trechos indexados")
    st.caption("Base disponível" if not erro_base else "Base pendente")
    st.caption("Chave configurada" if API_KEY else "Chave do OpenRouter pendente")
    with st.expander("Atos disponíveis", expanded=False):
        if not erro_base:
            try:
                st.markdown(catalogo() or "Nenhum ato identificado.")
            except Exception:
                st.warning("Não foi possível carregar o catálogo. Recrie a base com os scripts de preparação.")
        else:
            st.caption("Prepare a base para visualizar o catálogo.")
    with st.expander("Como funciona"):
        st.write("Sua pergunta busca trechos nos documentos locais. Esses trechos são enviados ao OpenRouter para elaborar a resposta com referências.")
        st.caption(f"Rota configurada: {', '.join(MODELOS)}")
        st.caption("A primeira busca pode demorar enquanto o modelo local é carregado ou baixado.")
    if st.session_state.mensagens:
        conversa = "\n\n".join(
            f"{'Você' if m['role'] == 'user' else 'Assistente'}:\n{m['content']}"
            for m in st.session_state.mensagens
        )
        st.download_button("Baixar conversa", conversa, "conversa.txt", "text/plain", use_container_width=True)
    st.divider()
    st.caption("Histórico mantido nesta sessão. Nova conversa apaga o histórico da tela.")

st.markdown('<div class="eyebrow">ASSISTENTE DE PESQUISA DOCUMENTAL</div>', unsafe_allow_html=True)
st.title("Sua pergunta. As fontes por perto.")
st.markdown("Consulte leis, portarias e atos da saúde do Tocantins em linguagem simples.")
st.caption("As respostas dependem dos documentos indexados e podem conter erros. Confira as fontes; a base pode não incluir alterações posteriores.")

if erro_base:
    st.warning(erro_base)
    st.write("Na pasta do projeto, execute os comandos abaixo em ordem e depois recarregue esta página:")
    st.code("python extrair_pdfs.py\npython fazer_chunks.py\npython criar_indice_bm25.py", language="powershell")
if not API_KEY:
    st.warning("Adicione OPENROUTER_API_KEY=sua_chave no arquivo .env e reinicie o Streamlit.")

pergunta_exemplo = None
if not st.session_state.mensagens:
    st.markdown("#### Por onde começar?")
    exemplos = ["Quais documentos estão disponíveis na base?", "Quais regras tratam do plantão extraordinário?", "O que a base diz sobre jornada de trabalho?"]
    for coluna, exemplo in zip(st.columns(3), exemplos):
        if coluna.button(exemplo, use_container_width=True, disabled=bool(erro_base) or not API_KEY):
            pergunta_exemplo = exemplo

for mensagem in st.session_state.mensagens:
    mostrar_mensagem(mensagem)

pergunta = st.chat_input("Pergunte sobre os documentos…", disabled=bool(erro_base) or not API_KEY, max_chars=4000)
pergunta = pergunta or pergunta_exemplo
if pergunta and pergunta.strip():
    pergunta = pergunta.strip()
    item_usuario = {"role": "user", "content": pergunta}
    st.session_state.mensagens.append(item_usuario)
    mostrar_mensagem(item_usuario)
    inicio = time.monotonic()
    try:
        with st.status("Buscando nos documentos…", expanded=True) as status:
            historico = st.session_state.trocas
            consulta = f"{historico[-1][0]} {pergunta}" if historico and len(pergunta.split()) <= 4 else pergunta
            fontes, notas, cat = recuperar(consulta)
            contexto = formatar_contexto(fontes, notas, cat)
            st.write(f"{len(fontes)} trechos recuperados.")
            status.update(label="Preparando a resposta com o OpenRouter…")
            texto, modelo, aviso = responder(montar_pergunta(pergunta, historico, contexto))
            status.update(label="Resposta pronta" if texto else "Não foi possível responder", state="complete" if texto else "error", expanded=False)
        item = {"role": "assistant", "content": texto or "Não consegui responder agora. Tente novamente em alguns instantes.",
                "modelo": modelo, "aviso": aviso, "fontes": fontes, "notas": notas,
                "segundos": time.monotonic() - inicio}
        if texto:
            st.session_state.trocas.append((pergunta, texto))
    except Exception:
        logging.exception("Falha ao processar pergunta na interface")
        item = {"role": "assistant", "content": "Não foi possível concluir a consulta.",
                "aviso": "Confira a conexão e a base local. Se o problema persistir, veja o erro no terminal. Para preparar a base, execute extrair_pdfs.py, fazer_chunks.py e criar_indice_bm25.py em ordem."}
    st.session_state.mensagens.append(item)
    st.rerun()
