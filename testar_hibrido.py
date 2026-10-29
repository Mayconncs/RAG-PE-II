"""
Compara, lado a lado, os 3 métodos de busca no LanceDB para qualquer pergunta:
  1) Vetorial pura (semântica)
  2) BM25 pura (palavra-chave / FTS)
  3) Híbrida (vetorial + BM25, combinadas pelo reranker RRF padrão do LanceDB)

    python testar_hibrido.py "qual o intervalo de descanso no plantão extraordinário?"
"""
import sys

import lancedb

from config import DB_PATH, NOME_TABELA
from embeddings import codificar_consulta

TOP_K = 5


def mostrar_resultados(titulo, resultados):
    print(f"\n=== {titulo} ===")
    if not resultados:
        print("  (nenhum resultado retornado)")
        return
    for i, r in enumerate(resultados, 1):
        trecho = r["content"].split("\n", 1)[-1][:110].replace("\n", " ")
        print(f"  [{i}] {r['ato'][:34]} | {r['artigos'][:34]} | pág {r['paginas']}\n      {trecho}...")


def main():
    pergunta = " ".join(sys.argv[1:]) or input("\nDigite a pergunta para testar o RAG híbrido: ").strip()
    if not pergunta:
        pergunta = "Para que serve este documento?"

    print("Conectando ao banco local...")
    db = lancedb.connect(DB_PATH)
    try:
        tabela = db.open_table(NOME_TABELA)
    except Exception as e:  # noqa: BLE001
        print(f"[ERRO] Tabela '{NOME_TABELA}' não encontrada ({e}). Rode 'python fazer_chunks.py' primeiro.")
        return

    print(f"-> Pergunta-teste: \"{pergunta}\"")
    vetor = codificar_consulta(pergunta)

    buscas = {
        "1) Busca VETORIAL pura": lambda: tabela.search(vetor).limit(TOP_K).to_list(),
        "2) Busca BM25 pura (palavra-chave)": lambda: tabela.search(pergunta, query_type="fts").limit(TOP_K).to_list(),
        "3) Busca HÍBRIDA (vetorial + BM25)": lambda: tabela.search(query_type="hybrid").vector(vetor).text(pergunta).limit(TOP_K).to_list(),
    }
    resultados = {}
    for titulo, fn in buscas.items():
        try:
            resultados[titulo] = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[ERRO em '{titulo}'] {e}  (rode 'criar_indice_bm25.py' antes?)")
            resultados[titulo] = []
        mostrar_resultados(titulo, resultados[titulo])

    vet = [r["content"][:60] for r in resultados["1) Busca VETORIAL pura"]]
    hib = [r["content"][:60] for r in resultados["3) Busca HÍBRIDA (vetorial + BM25)"]]
    print("\n--- Diagnóstico ---")
    if vet and vet == hib:
        print("ATENÇÃO: híbrido idêntico ao vetorial. O índice BM25 foi criado (criar_indice_bm25.py)?")
    else:
        print("OK: o ranking híbrido difere do vetorial, ou seja, o BM25 está influenciando.")


if __name__ == "__main__":
    main()
