"""
Lê data_texto/*.json (gerado por extrair_pdfs.py), divide em chunks respeitando a
estrutura de normas jurídicas e grava no LanceDB.

Estratégia:
  1. Separa cada PDF em ATOS (Lei, Portaria, Ata...). Os PDFs do Diário Oficial
     misturam vários atos (e conteúdo de outras secretarias) na mesma página.
  2. Dentro do ato, quebra por ARTIGO / ANEXO / TABELA — nunca no meio de um
     artigo, a menos que ele seja maior que CHUNK_MAX.
  3. Cada chunk recebe um cabeçalho "[Lei nº 2.644/2012 | Art. 2º | Capítulo]".
     O cabeçalho entra no embedding e no BM25, então perguntas como
     "o que diz o art. 6º da lei 4.627?" encontram o trecho certo.
  4. Tabelas de vencimentos viram linhas autossuficientes
     ("Padrão III: Ref. A = R$ 6.058,22; ...") em vez de colunas soltas.
"""
import json
import re
from pathlib import Path

import lancedb

from config import (CHUNK_MAX, DB_PATH, LINHA_MAX, NOME_TABELA, PASTA_TEXTO,
                    SOBREPOSICAO)
from embeddings import codificar_passagens

# --------------------------------------------------------------------------- #
# Expressões regulares
# --------------------------------------------------------------------------- #
# Cabeçalho de ato numerado. O tipo é case-sensitive (MAIÚSCULAS) para não
# confundir com citações no corpo do texto ("a Lei nº 2.644, de ...").
RE_ATO = re.compile(
    r"^(?P<tipo>LEI COMPLEMENTAR|LEI|PORTARIA|DECRETO|RESOLUÇÃO|INSTRUÇÃO NORMATIVA)"
    r"(?P<orgao>[A-Za-zÀ-ÿ/ .\-]{0,40}?)[\s/]*N[ºo°.]\s*"
    r"(?P<num>\d[\d.]*(?:/[\w.\-/]+)?)"
    r"(?i:.{0,80}?\bde\s+(?P<data>\d{1,2}\s*[ºo°]?\s+de\s+\w+\s+de\s+(?P<ano>\d{4})))"
)
RE_ATA = re.compile(r"^ATA PARA REGISTRO DE PREÇOS(?:\s+PREGÃO[^\n]*?N[ºo°.]\s*(?P<num>\d+/\d{4}))?")
# Início de conteúdo de OUTRO órgão/seção dentro do Diário Oficial
RE_OUTRO_DOE = re.compile(
    r"^(SECRETARIA|EXTRATOS?|AVISO|ERRATA|EDITAL|COMISSÃO|PROCURADORIA|CONTROLADORIA|"
    r"TRIBUNAL|AGÊNCIA|INSTITUTO|FUNDAÇÃO|PREGÃO)\b"
)
RE_ART = re.compile(r"^\*?\s*Art\.?\s*(?P<n>\d+)\s*[ºo°]?(?P<suf>\s*-\s*[A-Z])?")
RE_ANEXO = re.compile(r"^\*?\s*ANEXO\s+(?P<id>ÚNICO|UNICO|[IVXL]+)\b")
RE_CAP = re.compile(r"^(CAP[ÍI]TULO|T[ÍI]TULO|SE[ÇC][ÃA]O)\s+[IVXLC]+\b[^\n]*", re.I)
RE_TABELA = re.compile(r"^TABELA\s+(?P<id>[IVXL]+)\s*[-–—]")
# Linhas de cabeçalho de página do Diário Oficial (ruído): "20 DIÁRIO OFICIAL No 3.817 Ano XXV - ..."
# ou "5.429 DIÁRIO OFICIAL No 22" ou "Ano XXXI - Estado do Tocantins, quarta-feira, ..."
RE_CABEC_DOE = re.compile(
    r"^(?:\d[\d.]*\s+)?DI[ÁA]RIO OFICIAL\s+N[ºo°]\s*\d[\d.]*(?:\s+Ano\b.*)?$|"
    r"^Ano\s+[IVXL]+\s*-\s*Estado do Tocantins", re.I)
RE_EDICAO = re.compile(r"(\d[\d.]*)\s+DI[ÁA]RIO OFICIAL\s+N[ºo°]\s*(\d[\d.]*)|"
                       r"DI[ÁA]RIO OFICIAL\s+N[ºo°]\s*(\d[\d.]*)", re.I)
RE_PUBLICADA = re.compile(r"Publicad[ao] no Di[áa]rio Oficial n[ºo°]\s*(\d[\d.]*)", re.I)
RE_DINHEIRO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
RE_EMENTA = re.compile(
    r"\b(Institui|Dispõe|Disciplina|Estabelece|Regulamenta|Altera|Dá nova|Cria|Torna|Autoriza)\b[^\n]{15,350}?\.(?=\s|$)",
)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def rotular_ato(m):
    tipo = m["tipo"].title()
    orgao = "/".join(t for t in re.split(r"[\s/]+", m["orgao"].strip()) if t)
    num = m["num"].rstrip(".")
    if "/" not in num:
        num = f"{num}/{m['ano']}"
    return f"{tipo}{' ' + orgao if orgao else ''} nº {num}", tipo.lower()


def edicao_doe(texto_pagina):
    """Número da edição do Diário Oficial a partir do cabeçalho da página."""
    for ln in texto_pagina.split("\n")[:4]:
        m = RE_EDICAO.search(ln)
        if m:
            numeros = [g for g in m.groups() if g]
            candidatos = [int(n.replace(".", "")) for n in numeros]
            return f"{max(candidatos):,}".replace(",", ".")
    return None


def quebrar_linha_longa(texto):
    """Quebra uma linha > LINHA_MAX em sentenças, com sobreposição."""
    if len(texto) <= LINHA_MAX:
        return [texto]
    partes, atual = [], ""
    for sent in re.split(r"(?<=[.;:])\s+", texto):
        while len(sent) > LINHA_MAX:  # sentença gigante (ex.: lista sem pontuação)
            corte = sent.rfind(" ", 0, LINHA_MAX)
            corte = corte if corte > LINHA_MAX // 2 else LINHA_MAX
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(sent[:corte])
            sent = sent[max(0, corte - SOBREPOSICAO):] if corte > SOBREPOSICAO else sent[corte:]
        if len(atual) + len(sent) + 1 > LINHA_MAX and atual:
            partes.append(atual)
            atual = atual[-SOBREPOSICAO:] + " " + sent if SOBREPOSICAO else sent
        else:
            atual = f"{atual} {sent}".strip()
    if atual:
        partes.append(atual)
    return partes


# --------------------------------------------------------------------------- #
# 1) Leitura e segmentação por ato
# --------------------------------------------------------------------------- #
def ler_documento(caminho):
    """Retorna (fonte, eh_doe, edicao, [(pagina, linha), ...])."""
    paginas = json.loads(Path(caminho).read_text(encoding="utf-8"))
    fonte = Path(caminho).stem
    eh_doe, edicao, linhas = False, None, []
    for p in paginas:
        for i, ln in enumerate(p["texto"].split("\n")):
            if RE_CABEC_DOE.search(ln.strip()) and len(ln) < 200:
                eh_doe = True
                edicao = edicao or edicao_doe(ln)
                continue  # cabeçalho de página = ruído
            if not edicao:
                pub = RE_PUBLICADA.search(ln)
                if pub:
                    edicao = pub.group(1)
            linhas.append((p["pagina"], ln.strip()))
    return fonte, eh_doe, edicao, linhas


def segmentar_atos(fonte, eh_doe, edicao, linhas):
    """Divide as linhas em atos. Retorna lista de dicts {rotulo, tipo, linhas}."""
    generico = (f"DOE nº {edicao} - trecho sem cabeçalho de ato (continuação ou outro órgão)" if edicao
                else f"Conteúdo sem cabeçalho de ato ({fonte})")
    atos = [{"rotulo": generico, "tipo": "outros", "linhas": []}]

    for pag, ln in linhas:
        if not ln:
            continue
        m = RE_ATO.match(ln) if len(ln) < 300 else None
        if m:
            rotulo, tipo = rotular_ato(m)
            atos.append({"rotulo": rotulo, "tipo": tipo, "linhas": [(pag, ln)]})
            continue
        m = RE_ATA.match(ln)
        if m and (not atos[-1]["rotulo"].startswith("Ata")):
            num = m.group("num")
            rotulo = f"Ata de Registro de Preços {('nº ' + num) if num else ''}".strip()
            atos.append({"rotulo": rotulo, "tipo": "ata", "linhas": [(pag, ln)]})
            continue
        if (eh_doe and RE_OUTRO_DOE.match(ln) and atos[-1]["tipo"] not in ("outros",)
                and not RE_ART.match(ln) and not RE_ANEXO.match(ln)):
            # outro órgão/seção do DOE começa aqui: não pertence ao ato anterior
            atos.append({"rotulo": generico, "tipo": "outros", "linhas": [(pag, ln)]})
            continue
        atos[-1]["linhas"].append((pag, ln))

    return [a for a in atos if sum(len(t) for _, t in a["linhas"]) > 0]


# --------------------------------------------------------------------------- #
# 2) Tabelas de vencimento -> linhas autossuficientes
# --------------------------------------------------------------------------- #
def converter_tabela(titulo, bloco):
    """Converte a matriz PADRÃO x REFERÊNCIA em linhas autossuficientes:
    'Padrão III — vencimento — Referência A: R$ 6.058,22; Referência B: ...'.
    Lê token a token (o PDF às vezes cola o rótulo do padrão no fim da linha
    anterior). Se a estrutura não bater, devolve None e o texto bruto é mantido."""
    refs, linhas_row, notas, atual = None, [], [], None
    for pag, ln in bloco:
        if refs is None:
            if re.fullmatch(r"(?:[A-Z]\s+){2,}[A-Z]", ln):
                refs = ln.split()
            continue  # "REFERÊNCIA", "PADRÃO" etc. antes da matriz
        tokens, k = ln.split(), 0
        # consome rótulos de padrão (I, II...) e valores; o que sobrar é nota de rodapé
        while k < len(tokens) and re.fullmatch(r"[IVXL]+|" + RE_DINHEIRO.pattern, tokens[k]):
            t = tokens[k]
            if re.fullmatch(r"[IVXL]+", t):
                atual = {"padrao": t, "valores": [], "pag": pag}
                linhas_row.append(atual)
            elif atual is not None:
                atual["valores"].append(t)
            k += 1
        if k < len(tokens):
            notas.append((pag, " ".join(tokens[k:])))
    if not refs or not linhas_row:
        return None
    if any(len(r["valores"]) != len(refs) for r in linhas_row):
        return None  # estrutura inesperada: mantém o texto bruto
    rotulo = "valor-hora" if re.search(r"VALOR\s+HORA", titulo, re.IGNORECASE) else "vencimento mensal"
    saida = [(linhas_row[0]["pag"], titulo)]
    for r in linhas_row:
        pares = "; ".join(f"Referência {a}: R$ {v}" for a, v in zip(refs, r["valores"]))
        saida.append((r["pag"], f"Padrão {r['padrao']} — {rotulo} — {pares}"))
    saida.extend(notas)
    return saida


def normalizar_tabelas(linhas):
    out, i = [], 0
    while i < len(linhas):
        pag, ln = linhas[i]
        if RE_TABELA.match(ln):
            j, bloco = i + 1, []
            while j < len(linhas) and not RE_TABELA.match(linhas[j][1]) \
                    and not RE_ANEXO.match(linhas[j][1]):
                bloco.append(linhas[j])
                j += 1
            conv = converter_tabela(ln, bloco)
            if conv:
                out.extend(conv)
                i = j
                continue
        out.append(linhas[i])
        i += 1
    return out


# --------------------------------------------------------------------------- #
# 3) Unidades (artigo / anexo / tabela / preâmbulo) e empacotamento
# --------------------------------------------------------------------------- #
def montar_unidades(linhas):
    unidades = [{"tipo": "preambulo", "rotulo": "Ementa/preâmbulo", "secao": "", "linhas": []}]
    secao, anterior, anexo_atual = "", "", ""
    for pag, ln in linhas:
        m_art, m_anexo, m_tab = RE_ART.match(ln), RE_ANEXO.match(ln), RE_TABELA.match(ln)
        m_cap = RE_CAP.match(ln)
        fim_ok = (not anterior) or anterior[-1] in ".:;!?)”\"" or RE_CAP.match(anterior) \
            or unidades[-1]["tipo"] in ("preambulo",)
        if m_cap:
            secao = ln[:120]
        if m_art and fim_ok:
            rot = f"Art. {m_art.group('n')}º" + (m_art.group("suf") or "").replace(" ", "")
            unidades.append({"tipo": "artigo", "rotulo": rot, "secao": secao, "linhas": [(pag, ln)]})
        elif m_anexo and (fim_ok or re.match(r"^\*?\s*ANEXO\s+[IVXL]+\s+À", ln)):
            id_anexo = m_anexo.group("id")
            anexo_atual = "Anexo Único" if id_anexo in ("ÚNICO", "UNICO") else f"Anexo {id_anexo}"
            unidades.append({"tipo": "anexo", "rotulo": anexo_atual, "secao": "", "linhas": [(pag, ln)]})
        elif m_tab:
            rot = (f"{anexo_atual} — " if anexo_atual else "") + ln[:110]
            unidades.append({"tipo": "tabela", "rotulo": rot, "secao": "", "linhas": [(pag, ln)]})
        else:
            unidades[-1]["linhas"].append((pag, ln))
        anterior = ln
    return [u for u in unidades if u["linhas"]]


def dividir_unidade(u):
    """Divide unidade maior que CHUNK_MAX em partes por linha (inciso/parágrafo)."""
    partes, atual, tam = [], [], 0
    for pag, ln in u["linhas"]:
        for pedaco in quebrar_linha_longa(ln):
            if tam + len(pedaco) + 1 > CHUNK_MAX and atual:
                partes.append(atual)
                ultima = atual[-1]
                atual, tam = ([ultima] if len(ultima[1]) < 250 else []), 0
                tam = sum(len(t) + 1 for _, t in atual)
            atual.append((pag, pedaco))
            tam += len(pedaco) + 1
    if atual:
        partes.append(atual)
    return partes


def empacotar(unidades):
    """Junta artigos pequenos vizinhos; divide os grandes. Retorna chunks brutos."""
    chunks, grupo = [], None

    def fechar():
        nonlocal grupo
        if grupo:
            nums = [x["rotulo"] for x in grupo["unidades"]]
            rot = nums[0] if len(nums) == 1 else f"{nums[0]} a {nums[-1]}"
            chunks.append({"rotulo": rot, "secao": grupo["secao"], "linhas": grupo["linhas"]})
        grupo = None

    for u in unidades:
        tam = sum(len(t) + 1 for _, t in u["linhas"])
        if tam > CHUNK_MAX:
            fechar()
            partes = dividir_unidade(u)
            for i, parte in enumerate(partes, 1):
                rot = u["rotulo"] + (f" (parte {i}/{len(partes)})" if len(partes) > 1 else "")
                chunks.append({"rotulo": rot, "secao": u["secao"], "linhas": parte})
            continue
        mesclavel = u["tipo"] in ("artigo", "preambulo")
        cabe = grupo is not None and grupo["tam"] + tam <= CHUNK_MAX
        mesma_secao = grupo is not None and (grupo["secao"] == u["secao"] or grupo["tipo"] == "preambulo")
        if cabe and mesclavel and mesma_secao:
            grupo["unidades"].append(u)
            grupo["linhas"].extend(u["linhas"])
            grupo["tam"] += tam
            grupo["tipo"] = u["tipo"]
        else:
            fechar()
            grupo = {"unidades": [u], "linhas": list(u["linhas"]), "secao": u["secao"],
                     "tam": tam, "tipo": u["tipo"]}
            if not mesclavel:
                fechar()
    fechar()
    return chunks


# --------------------------------------------------------------------------- #
# 4) Pipeline
# --------------------------------------------------------------------------- #
def processar_arquivos():
    todos = []
    arquivos = sorted(PASTA_TEXTO.glob("*.json"))
    if not arquivos:
        print(f"[ERRO] Nenhum JSON em {PASTA_TEXTO}. Rode extrair_pdfs.py primeiro.")
        return todos

    for caminho in arquivos:
        fonte, eh_doe, edicao, linhas = ler_documento(caminho)
        atos = segmentar_atos(fonte, eh_doe, edicao, linhas)
        print(f"\n{fonte}: {len(atos)} ato(s)" + (f" [DOE nº {edicao}]" if edicao else ""))
        for ato in atos:
            lin = normalizar_tabelas(ato["linhas"])
            unidades = montar_unidades(lin)
            brutos = empacotar(unidades)
            texto_ato = " ".join(t for _, t in ato["linhas"])
            ementa = RE_EMENTA.search(texto_ato[:900])
            print(f"   - {ato['rotulo'][:60]:60s} {len(brutos):3d} chunks")
            for b in brutos:
                corpo = "\n".join(t for _, t in b["linhas"]).strip()
                so_titulo = len(corpo) < 70 and (corpo.isupper() or (RE_ATO.match(corpo) and "\n" not in corpo))
                if len(corpo) < 25 or so_titulo:
                    continue
                cab = f"[{ato['rotulo']} | {b['rotulo']}" + (f" | {b['secao']}" if b["secao"] else "") + "]"
                pags = sorted({p for p, _ in b["linhas"]})
                todos.append({
                    "content": f"{cab}\n{corpo}",
                    "fonte": fonte,
                    "ato": ato["rotulo"],
                    "tipo_ato": ato["tipo"],
                    "artigos": b["rotulo"],
                    "secao": b["secao"],
                    "pagina": str(pags[0]),
                    "paginas": f"{pags[0]}-{pags[-1]}" if len(pags) > 1 else str(pags[0]),
                    "edicao_doe": edicao or "",
                    "ementa": ementa.group(0) if ementa else "",
                })
    return todos


def main():
    chunks = processar_arquivos()
    if not chunks:
        return
    tams = [len(c["content"]) for c in chunks]
    print(f"\nTotal: {len(chunks)} chunks | tamanho médio {sum(tams)//len(tams)} | máx {max(tams)}")

    print("\nGerando embeddings (primeira execução baixa o modelo)...")
    vetores = codificar_passagens([c["content"] for c in chunks], mostrar_progresso=True)

    registros = []
    for c, v in zip(chunks, vetores):
        meta = {k: c[k] for k in ("fonte", "ato", "artigos", "secao", "pagina", "paginas", "edicao_doe")}
        registros.append({**c, "vector": v.tolist(), "meta_data": json.dumps(meta, ensure_ascii=False)})

    db = lancedb.connect(DB_PATH)
    # drop + create (em vez de mode="overwrite") para não acumular versões antigas em disco:
    # a base anterior chegou a 94 MB por causa do histórico de versões.
    db.drop_table(NOME_TABELA, ignore_missing=True)
    db.create_table(NOME_TABELA, data=registros)
    print(f"\n[SUCESSO] {len(registros)} chunks gravados em '{NOME_TABELA}'.")
    print("Próximo passo: python criar_indice_bm25.py")


if __name__ == "__main__":
    main()