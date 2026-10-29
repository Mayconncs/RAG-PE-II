"""Recuperação de trechos: busca híbrida (vetorial + BM25) + regras para perguntas jurídicas.

Pipeline de `recuperar()`:
  1. Pergunta de CATÁLOGO ("quais leis tratam de...") -> lista dos atos da base + trechos
     de vários atos diferentes (no máx. 2 por ato).
  2. Pergunta com referência explícita ("art. 6º da Lei 4.627/2025", "Anexo III da Lei
     3.490") -> busca DIRETA pelo rótulo do chunk (não depende de embedding nem BM25).
  3. Demais perguntas -> busca híbrida, com diversidade entre atos.
  4. Em todos os casos, artigos que foram divididos em "parte 1/3, 2/3, 3/3" são trazidos
     inteiros (ou só as partes vizinhas, se o artigo for gigante, como os anexos).

Usado por main.py e avaliar_busca.py.
"""
import re
from collections import Counter, defaultdict

import lancedb

from config import (DB_PATH, MAX_CHARS_CONTEXTO, MAX_PARTES_EXPANDIR, MAX_POR_ATO,
                    NOME_TABELA, TOP_K)
from embeddings import codificar_consulta

POOL = 30           # candidatos de cada lado antes da fusão
REESCREVER = True   # False desliga a reescrita da consulta

_tabela = None
_chunks = None      # cache em memória dos chunks (sem o vetor): a base é pequena


# --------------------------------------------------------------------------- #
# Acesso à base
# --------------------------------------------------------------------------- #
def _abrir():
    global _tabela
    if _tabela is None:
        _tabela = lancedb.connect(DB_PATH).open_table(NOME_TABELA)
    return _tabela


def _carregar_chunks():
    """Todos os chunks, na ordem de gravação (= ordem do documento)."""
    global _chunks
    if _chunks is None:
        colunas = ["content", "fonte", "ato", "tipo_ato", "artigos", "paginas", "ementa"]
        linhas = _abrir().to_arrow().select(colunas).to_pylist()
        for i, r in enumerate(linhas):
            r["_i"] = i
        _chunks = linhas
    return _chunks


_ID_POR_CONTEUDO = {}


def _preparar_indices():
    if not _ID_POR_CONTEUDO:
        for r in _carregar_chunks():
            _ID_POR_CONTEUDO.setdefault(r["content"], r["_i"])


def _canonico(c):
    """Devolve o registro do cache (com `_i`) correspondente a um resultado da busca."""
    if "_i" in c:
        return c
    _preparar_indices()
    i = _ID_POR_CONTEUDO.get(c["content"])
    return _carregar_chunks()[i] if i is not None else c


# --------------------------------------------------------------------------- #
# Reescrita da consulta (só ACRESCENTA termos)
# --------------------------------------------------------------------------- #
def reescrever_consulta(pergunta: str) -> str:
    extra = []
    padrao = re.search(r"padr[ãa]o\s+([IVXL]{1,5})\b", pergunta, re.IGNORECASE)
    referencia = re.search(r"refer[êe]ncia\s+([A-L])\b", pergunta, re.IGNORECASE)
    if padrao or referencia:
        extra += ["tabela", "vencimento"]
        if padrao:
            extra.append(f"Padrão {padrao.group(1).upper()}")
        if referencia:
            extra.append(f"Referência {referencia.group(1).upper()}")
    # sinônimos do jargão do serviço público (a lei diz "jornada de trabalho"; o usuário, "carga horária")
    baixa = pergunta.lower()
    if re.search(r"carga hor[áa]ria", baixa) and "jornada" not in baixa:
        extra.append("jornada de trabalho")
    elif "jornada" in baixa and "carga hor" not in baixa:
        extra.append("carga horária")
    if (re.search(r"\b(sal[áa]rio|remunera[çc][ãa]o|quanto (ganha|recebe))\b", baixa)
            and "vencimento" not in baixa and "vencimento" not in extra):
        extra.append("vencimento")
    return f"{pergunta} {' '.join(extra)}" if extra else pergunta


def busca_hibrida(pergunta: str, k: int = 5, pool: int = POOL,
                  reescrever: bool = REESCREVER, vetor=None) -> list:
    """Top-k da busca híbrida, com `pool` candidatos de cada lado antes da fusão."""
    consulta = reescrever_consulta(pergunta) if reescrever else pergunta
    if vetor is None or consulta != pergunta:
        vetor = codificar_consulta(consulta)
    candidatos = (
        _abrir()
        .search(query_type="hybrid")
        .vector(vetor)
        .text(consulta)
        .limit(max(pool, k))
        .to_list()
    )
    return candidatos[:k]


# --------------------------------------------------------------------------- #
# Referências explícitas na pergunta: ato, artigos, anexo
# --------------------------------------------------------------------------- #
_RE_ATO_PERG = re.compile(
    r"\b(?P<tipo>lei complementar|lei|portaria|decreto)\b[^\d\n]{0,25}?"
    r"(?P<num>\d[\d.]*)"
    r"(?:\s*/\s*(?P<ano1>\d{4})|\s*,?\s+de\s+(?:\d{1,2}\s*[ºo°]?\s+de\s+\w+\s+de\s+)?(?P<ano2>\d{4}))?",
    re.IGNORECASE)
_RE_ATO_ROTULO = re.compile(
    r"^(?P<tipo>Lei Complementar|Lei|Portaria|Decreto)\b[^\n]*?\bnº\s*(?P<num>\d[\d.]*)/(?P<ano>\d{4})")
_RE_ART_PERG = re.compile(r"\bart(?:igos?|s?\.?)\s*((?:\d+\s*[ºo°]?\s*(?:,|e|ao|até|a|-|–)?\s*)+)", re.IGNORECASE)
_RE_ANEXO_PERG = re.compile(r"\banexo\s+(único|unico|[ivxl]+)\b", re.IGNORECASE)


def _num(texto):
    return int(texto.replace(".", "") or 0)


def identificar_atos(pergunta: str):
    """Atos citados na pergunta -> conjunto de rótulos de ato existentes na base."""
    alvos = []
    for m in _RE_ATO_PERG.finditer(pergunta):
        num = m.group("num").rstrip(".")
        if not num:
            continue
        ano = m.group("ano1") or m.group("ano2")
        alvos.append((m.group("tipo").lower(), _num(num), int(ano) if ano else None))
    if not alvos:
        return set()
    achados = set()
    for rotulo in {c["ato"] for c in _carregar_chunks()}:
        r = _RE_ATO_ROTULO.match(rotulo)
        if not r:
            continue
        for tipo, num, ano in alvos:
            if (r.group("tipo").lower() == tipo and _num(r.group("num")) == num
                    and (ano is None or int(r.group("ano")) == ano)):
                achados.add(rotulo)
    return achados


def identificar_artigos(pergunta: str):
    """'art. 6º', 'arts. 6 e 8', 'artigos 5 a 7' -> {6}, {6, 8}, {5, 6, 7}."""
    numeros = set()
    for m in _RE_ART_PERG.finditer(pergunta):
        itens = re.findall(r"\d+|\b(?:a|ao|até)\b|[-–]", m.group(1), re.IGNORECASE)
        anterior, intervalo = None, False
        for it in itens:
            if it.isdigit():
                n = int(it)
                if intervalo and anterior is not None and 0 < n - anterior <= 30:
                    numeros.update(range(anterior, n + 1))
                numeros.add(n)
                anterior, intervalo = n, False
            else:
                intervalo = True
    return numeros


def identificar_anexos(pergunta: str):
    out = set()
    for m in _RE_ANEXO_PERG.finditer(pergunta):
        id_ = m.group(1).upper()
        out.add("ÚNICO" if id_ in ("ÚNICO", "UNICO") else id_)
    return out


def _artigos_do_rotulo(rotulo: str):
    """'Art. 9º a Art. 10º' -> {9, 10}; 'Art. 14º (parte 2/5)' -> {14}."""
    nums = [int(n) for n in re.findall(r"Art\.\s*(\d+)", rotulo)]
    if not nums:
        return set()
    if re.search(r"Art\.\s*\d+\S*\s+a\s+Art\.", rotulo) and len(nums) >= 2:
        return set(range(nums[0], nums[-1] + 1))
    return set(nums)


def _anexo_do_rotulo(rotulo: str):
    m = re.match(r"Anexo\s+(Único|[IVXL]+)", rotulo)
    return m.group(1).upper() if m else None


# --------------------------------------------------------------------------- #
# Partes de um mesmo artigo ("Art. 14º (parte 2/5)")
# --------------------------------------------------------------------------- #
_RE_PARTE = re.compile(r"^(?P<base>.*?)\s*\(parte (?P<i>\d+)/(?P<n>\d+)\)$")


def _parte(rotulo: str):
    m = _RE_PARTE.match(rotulo)
    return (m.group("base"), int(m.group("i")), int(m.group("n"))) if m else (rotulo, 1, 1)


def expandir_partes(ancoras: list) -> list:
    """Para cada chunk 'parte i/n', inclui as demais partes do mesmo artigo.
    Se o artigo tem mais de MAX_PARTES_EXPANDIR partes, inclui só as vizinhas (i-1, i+1).
    Mantém a ordem de relevância das âncoras (partes novas vêm logo depois da âncora)."""
    grupos = defaultdict(list)
    for r in _carregar_chunks():
        base, i, _ = _parte(r["artigos"])
        grupos[(r["fonte"], r["ato"], base)].append((i, r))
    saida, vistos = [], set()
    for c in ancoras:
        c = _canonico(c)
        base, i, n = _parte(c["artigos"])
        membros = grupos.get((c["fonte"], c["ato"], base), [])
        if n <= MAX_PARTES_EXPANDIR:
            escolhidas = [r for _, r in membros]
        else:
            escolhidas = [r for j, r in membros if abs(j - i) <= 1]
        for r in escolhidas or [c]:
            if r["_i"] not in vistos:
                vistos.add(r["_i"])
                saida.append(r)
    return saida


# --------------------------------------------------------------------------- #
# Seleção com diversidade
# --------------------------------------------------------------------------- #
def selecionar_diverso(candidatos: list, k: int, max_por_ato: int) -> list:
    """Percorre os candidatos (já por relevância) respeitando o teto por ato."""
    escolhidos, cont = [], Counter()
    for c in candidatos:
        if cont[c["ato"]] >= max_por_ato:
            continue
        escolhidos.append(c)
        cont[c["ato"]] += 1
        if len(escolhidos) == k:
            break
    return escolhidos


def _eh_catalogo(pergunta: str) -> bool:
    p = pergunta.lower()
    return bool(
        re.search(r"\b(quais|que|quantas?)\s+(leis|portarias|normas|atos|decretos|documentos)\b", p)
        or re.search(r"\b(do que|sobre o que)\s+(trata|tratam|fala|falam)\s+(a|esta|essa)\s+base\b", p)
        or re.search(r"\bquais\s+(as\s+)?(leis|normas|portarias)\b", p)
    )


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #
def catalogo() -> str:
    """Lista os atos da base (arquivo + resumo). Ignora os trechos 'sem cabeçalho de ato'."""
    atos = {}
    for r in _carregar_chunks():
        if r["tipo_ato"] == "outros":
            continue
        atos.setdefault((r["ato"], r["fonte"]), r["ementa"])
    return "\n".join(
        f"- {ato} (arquivo {fonte})" + (f": {ementa}" if ementa else "")
        for (ato, fonte), ementa in sorted(atos.items())
    )


# --------------------------------------------------------------------------- #
# Recuperação completa
# --------------------------------------------------------------------------- #
def recuperar(pergunta: str, k: int = TOP_K):
    """Retorna (chunks, notas, catalogo_txt). `chunks` já vem expandido e limitado."""
    notas, cat_txt = [], ""
    atos = identificar_atos(pergunta)
    artigos = identificar_artigos(pergunta)
    anexos = identificar_anexos(pergunta)
    ancoras = []

    # 2) referência explícita a ato + artigo/anexo: busca direta pelo rótulo
    if atos and (artigos or anexos):
        todos = [c for c in _carregar_chunks() if c["ato"] in atos]
        achados_art, achados_anx = set(), set()
        for c in todos:
            a = _artigos_do_rotulo(c["artigos"]) & artigos
            x = {_anexo_do_rotulo(c["artigos"])} & anexos
            if a or x:
                ancoras.append(c)
                achados_art |= a
                achados_anx |= x
        faltam = sorted(artigos - achados_art) if not anexos else []
        if faltam:
            disp = sorted({n for c in todos for n in _artigos_do_rotulo(c["artigos"])})
            notas.append(
                f"O(s) art. {', '.join(map(str, faltam))} NÃO foi(ram) localizado(s) em "
                f"{'; '.join(sorted(atos))}. Artigos existentes na base: "
                f"{disp[0] if disp else '?'} a {disp[-1] if disp else '?'}. "
                "Não invente o conteúdo; avise o usuário.")
        for x in sorted(anexos - achados_anx):
            notas.append(f"Anexo {x.title()} NÃO foi localizado em {'; '.join(sorted(atos))}.")

    # 1) catálogo / 3) busca híbrida
    if not ancoras:
        catalogo_q = _eh_catalogo(pergunta)
        if catalogo_q:
            cat_txt = catalogo()
        candidatos = busca_hibrida(pergunta, k=POOL, pool=POOL)
        if atos:   # o usuário citou a lei, mas sem artigo: prefere trechos dessa lei
            da_lei = [c for c in candidatos if c["ato"] in atos]
            candidatos = da_lei if len(da_lei) >= 3 else da_lei + [c for c in candidatos if c["ato"] not in atos]
        teto = 2 if catalogo_q else MAX_POR_ATO
        ancoras = selecionar_diverso(candidatos, k=(8 if catalogo_q else k), max_por_ato=teto)

    # 4) partes vizinhas + teto de tamanho (corta pelo fim da lista de relevância)
    ordenados = expandir_partes(ancoras)
    escolhidos, total = [], 0
    for c in ordenados:
        if total + len(c["content"]) > MAX_CHARS_CONTEXTO and escolhidos:
            notas.append("Contexto limitado por tamanho: pode haver outros trechos relevantes "
                         "na base que não couberam aqui. Diga isso ao usuário se a resposta puder estar incompleta.")
            break
        escolhidos.append(c)
        total += len(c["content"])
    # ordem de leitura: agrupa por ato (na ordem de relevância) e segue a ordem do documento
    ordem_ato = {}
    for c in escolhidos:
        ordem_ato.setdefault(c["ato"], len(ordem_ato))
    escolhidos.sort(key=lambda c: (ordem_ato[c["ato"]], c["_i"]))
    return escolhidos, notas, cat_txt


def formatar_contexto(chunks: list, notas: list = (), cat_txt: str = "") -> str:
    partes = []
    if cat_txt:
        partes.append("ATOS DISPONÍVEIS NA BASE (catálogo completo):\n" + cat_txt)
    for n in notas:
        partes.append(f"[AVISO DO SISTEMA] {n}")
    vistos = set()
    for r in chunks:
        if r["content"] in vistos:
            continue
        vistos.add(r["content"])
        # o próprio conteúdo já começa com "[Ato | Artigo | Capítulo]"
        partes.append(f"(arquivo: {r['fonte']}, pág. {r['paginas']})\n{r['content']}")
    return "\n\n---\n\n".join(partes) if partes else "Nenhum trecho encontrado."


def recuperar_contexto(pergunta: str, k: int = TOP_K) -> str:
    return formatar_contexto(*recuperar(pergunta, k))