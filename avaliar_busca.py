"""
Avalia a recuperação com perguntas de referência (golden set).
Para cada pergunta, verifica se o trecho esperado aparece entre os top-K de cada método.
Rode depois de mudar chunking, modelo de embedding, pesos ou a busca.

    python avaliar_busca.py            # K=5
    python avaliar_busca.py --k 3

Colunas:
  vetorial     só embeddings
  bm25         só palavras-chave
  hibrido      como era antes: limit=K em cada lado, antes da fusão
  hibrido_p20  POOL candidatos de cada lado, fusão, corte em K
  hibrido_p20r igual ao anterior + reescrita da consulta (busca.reescrever_consulta)
  pipeline     o que o main.py realmente usa: busca.recuperar() (TOP_K do config.py)

Para ampliar: adicione itens em PERGUNTAS. Um acerto = algum resultado do top-K cujo
'ato' contém `ato` E cujo conteúdo contém `contem` (ambos sem diferenciar maiúsculas).
"""
import argparse

import lancedb

from busca import POOL, busca_hibrida, recuperar
from config import DB_PATH, NOME_TABELA, TOP_K
from embeddings import codificar_consulta

PERGUNTAS = [
    # (pergunta, trecho do nome do ato, texto que deve aparecer no chunk)
    ("Qual o intervalo mínimo de descanso a cada 24 horas de plantão extraordinário presencial?",
     "Lei nº 4.627/2025", "11 (onze) horas"),
    ("Quais plantões não são considerados para o pagamento da GRIN?",
     "Lei nº 2.644/2012", "sobreaviso"),
    ("Qual o vencimento do padrão III referência C do nível superior da saúde?",
     "Lei nº 2.670/2012", "6.679,19"),
    ("Qual o prazo de validade da ata de registro de preços do pregão 065/2018?",
     "065/2018", "12 (doze) meses"),
    ("Quais gratificações foram instituídas pela Lei 2.692 de 2012?",
     "Lei nº 2.692/2012", "GUEM"),
    ("Chamamento de médicos radioterapeutas para o hospital de Araguaína",
     "462/2019", "Radioterapeutas"),
    ("Como funciona a indenização por insalubridade dos profissionais da saúde?",
     "Lei nº 2.670/2012", "insalubridade"),
    ("Quem compõe a equipe de trabalho coordenada pela SGPES para o controle de jornada?",
     "", "Equipe de Trabalho"),
    ("O que a Lei 3.490 de 2019 mudou na gratificação do interior?",
     "Lei nº 3.490/2019", "GRIN"),
    ("Regras de acumulação de cargos dos servidores da Secretaria da Saúde",
     "479/2019", "acumula"),
    ("O que diz o art. 6º da Lei 4.627/2025?",
     "Lei nº 4.627/2025", "intervalo mínimo de 11"),
    ("Quais regras existem para plantão extraordinário?",
     "Lei nº 4.627/2025", "não se aplica"),          # art. 4º: não vinha no top-6
    ("Qual a carga horária do médico?",
     "Lei nº 2.670/2012", "quarenta horas semanais"),  # art. 23: jornada de trabalho
    ("Qual a carga horária do médico?",
     "Lei nº 3.490/2019", "Médicos"),                 # Anexo I: regime de plantão dos médicos
    ("Quais leis tratam de gratificações para servidores da saúde?",
     "Lei nº 2.644/2012", "Gratificação"),
    ("Quais leis tratam de gratificações para servidores da saúde?",
     "Lei nº 2.692/2012", "Gratificação"),
    ("O que diz o art. 14 da Lei 4.627/2025?",
     "Lei nº 4.627/2025", "Art. 14"),
]


def acertou(resultados, ato, contem):
    for pos, r in enumerate(resultados, 1):
        if ato.lower() in r["ato"].lower() and contem.lower() in r["content"].lower():
            return pos
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    k = ap.parse_args().k

    tabela = lancedb.connect(DB_PATH).open_table(NOME_TABELA)
    metodos = {
        "vetorial": lambda q, v: tabela.search(v).limit(k).to_list(),
        "bm25": lambda q, v: tabela.search(q, query_type="fts").limit(k).to_list(),
        "hibrido": lambda q, v: tabela.search(query_type="hybrid").vector(v).text(q).limit(k).to_list(),
        "hibrido_p20": lambda q, v: busca_hibrida(q, k, pool=POOL, reescrever=False, vetor=v),
        "hibrido_p20r": lambda q, v: busca_hibrida(q, k, pool=POOL, reescrever=True),
        # pipeline completo do main.py (busca direta por artigo, diversidade, partes vizinhas);
        # usa seu próprio TOP_K (config.py), por isso costuma achar mais que as colunas acima
        "pipeline": lambda q, v: recuperar(q, TOP_K)[0],
    }
    total = {m: 0 for m in metodos}
    print(f"{'pergunta':50s} " + " ".join(f"{m:>12s}" for m in metodos))
    for pergunta, ato, contem in PERGUNTAS:
        v = codificar_consulta(pergunta)
        linha = []
        for nome, fn in metodos.items():
            try:
                pos = acertou(fn(pergunta, v), ato, contem)
            except Exception as e:  # noqa: BLE001
                pos = -1
                print(f"   [erro em {nome}: {e}]")
            total[nome] += pos > 0
            linha.append("-" if pos == 0 else ("erro" if pos < 0 else f"#{pos}"))
        print(f"{pergunta[:49]:50s} " + " ".join(f"{x:>12s}" for x in linha))
    n = len(PERGUNTAS)
    print(f"\nAcertos no top-{k}: " + " | ".join(f"{m}: {total[m]}/{n}" for m in metodos))


if __name__ == "__main__":
    main()