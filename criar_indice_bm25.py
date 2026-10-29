import lancedb

from config import DB_PATH, NOME_TABELA

print("Conectando ao banco local...")
db = lancedb.connect(DB_PATH)

try:
    tabela = db.open_table(NOME_TABELA)
except Exception as e:
    print(f"[ERRO] Não foi possível abrir a tabela '{NOME_TABELA}': {e}")
    print("Rode 'python fazer_chunks.py' antes.")
    raise SystemExit(1)

print("Criando índice BM25 (palavras-chave) na coluna 'content'...")
tabela.create_fts_index(
    "content",
    replace=True,
    language="Portuguese",
    stem=True,            # "gratificações" ~ "gratificação"
    ascii_folding=True,   # "saude" ~ "saúde"
    remove_stop_words=True,
)
print(f"[SUCESSO] Índice BM25 criado ({tabela.count_rows()} chunks).")
