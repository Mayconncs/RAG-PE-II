"""API local do chatbot. Execute: python -m uvicorn api:app --reload."""
import logging
import threading
import time
from pathlib import Path

import lancedb
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import DB_PATH, NOME_TABELA, PASTA_PDFS
from busca import catalogo, recuperar, formatar_contexto
from main import API_KEY, MODELOS, montar_pergunta, responder

app = FastAPI(title="Consulta Saúde - TO")
_consulta_lock = threading.Lock()


class Troca(BaseModel):
    pergunta: str = Field(max_length=4000)
    resposta: str = Field(max_length=30000)


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1, max_length=4000)
    historico: list[Troca] = Field(default_factory=list, max_length=2)


@app.get('/api/status')
def status():
    try:
        tabela = lancedb.connect(DB_PATH).open_table(NOME_TABELA)
        quantidade = tabela.count_rows()
        return dict(base_pronta=quantidade > 0, trechos=quantidade, chave_configurada=bool(API_KEY), modelos=MODELOS)
    except Exception:
        return dict(base_pronta=False, trechos=0, chave_configurada=bool(API_KEY), modelos=MODELOS)


@app.get('/api/documentos')
def documentos():
    try:
        return {'catalogo': catalogo()}
    except Exception:
        raise HTTPException(503, 'Prepare a base com extrair_pdfs.py, fazer_chunks.py e criar_indice_bm25.py.')


@app.post('/api/chat')
def chat(dados: Pergunta):
    pergunta = dados.pergunta.strip()
    if not pergunta:
        raise HTTPException(422, 'Digite uma pergunta.')
    if not API_KEY:
        raise HTTPException(503, 'Configure OPENROUTER_API_KEY no .env e reinicie o servidor.')
    if not _consulta_lock.acquire(blocking=False):
        raise HTTPException(429, 'Há uma consulta em andamento. Aguarde e tente novamente.')
    try:
        inicio = time.monotonic()
        historico = [(t.pergunta, t.resposta) for t in dados.historico]
        consulta = f'{historico[-1][0]} {pergunta}' if historico and len(pergunta.split()) <= 4 else pergunta
        fontes, notas, cat = recuperar(consulta)
        contexto = formatar_contexto(fontes, notas, cat)
        texto, modelo, aviso = responder(montar_pergunta(pergunta, historico, contexto))
        if not texto:
            raise HTTPException(502, aviso or 'O provedor não retornou uma resposta. Tente novamente.')
        campos = ('ato', 'artigos', 'fonte', 'paginas', 'content')
        return dict(resposta=texto, modelo=modelo, aviso=aviso, notas=notas,
                    fontes=[{k: f[k] for k in campos} for f in fontes], segundos=round(time.monotonic()-inicio, 1))
    except HTTPException:
        raise
    except Exception:
        logging.exception('Falha na consulta RAG')
        raise HTTPException(503, 'Não foi possível consultar a base. Confira o terminal e a preparação dos documentos.')
    finally:
        _consulta_lock.release()


@app.get('/api/fontes/{arquivo}')
def abrir_fonte(arquivo: str):
    # Apenas PDFs diretamente na pasta de entrada; nunca caminhos fornecidos pelo cliente.
    if '/' in arquivo or '\\' in arquivo or not arquivo.lower().endswith('.pdf'):
        raise HTTPException(404, 'Documento não encontrado.')
    caminho = (PASTA_PDFS / arquivo).resolve()
    if caminho.parent != PASTA_PDFS.resolve() or not caminho.is_file():
        raise HTTPException(404, 'Documento não encontrado.')
    return FileResponse(caminho, media_type='application/pdf', filename=caminho.name, content_disposition_type='inline')


dist = Path(__file__).parent / 'frontend' / 'dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
