"""Configuração central do RAG. Mude aqui, não nos scripts."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

PASTA_PDFS = RAIZ / "documentos_originais"
PASTA_TEXTO = RAIZ / "data_texto"          # saída de extrair_pdfs.py
DB_PATH = str(RAIZ / ".lancedb_local")
NOME_TABELA = "documentos_hibrido"

# --- Embeddings ---------------------------------------------------------------
# multilingual-e5-base: bom em português e aceita até 512 tokens por trecho.
# O modelo antigo (paraphrase-multilingual-MiniLM-L12-v2) só lê 128 tokens
# (~450 caracteres): o resto de cada chunk era ignorado no embedding.
# Se voltar ao MiniLM, reduza CHUNK_MAX para ~450.
MODELO_EMBEDDING = "intfloat/multilingual-e5-base"

# --- Chunking -----------------------------------------------------------------
CHUNK_MAX = 1000        # caracteres por chunk (≈250-300 tokens em português jurídico)
LINHA_MAX = 900         # linha única maior que isso é quebrada por sentenças
SOBREPOSICAO = 150      # sobreposição ao quebrar uma linha muito longa

# --- Busca --------------------------------------------------------------------
TOP_K = 10                  # trechos "âncora" da busca híbrida (antes: 6)
MAX_POR_ATO = 6             # no máximo N âncoras do mesmo ato (evita uma lei engolir tudo)
MAX_PARTES_EXPANDIR = 6     # artigo dividido em até N partes: traz TODAS as partes
                            # (acima disso, como nos anexos gigantes: só a parte vizinha)
MAX_CHARS_CONTEXTO = 16000  # teto do contexto enviado ao modelo (~4 mil tokens)

# --- Modelo (OpenRouter, planos gratuitos) -------------------------------------
# A lista de modelos :free muda a cada poucos dias. Para ver o que está no ar HOJE:
#     python listar_modelos_gratis.py --testar
# e cole o resultado em OPENROUTER_MODELS no .env (separado por vírgula).
# O main.py tenta os modelos na ordem; se um falhar (429, vazio, cortado), usa o próximo.
# Evite "openrouter/free" como 1ª opção: ele sorteia um modelo diferente a cada pergunta
# (inclusive modelos de raciocínio que estouram o limite de tokens e cortam a resposta).
MODELOS_GRATIS = [
    "openrouter/free",          # último recurso
]
MAX_TOKENS_RESPOSTA = 3000
USAR_FERRAMENTAS = False    # a recuperação já é automática; modelos grátis erram tool calling