"""
Extrai o texto dos PDFs de `documentos_originais/` para `data_texto/<nome>.json`.

Por que existe (em vez do Marker):
  - Os PDFs desta base (leis, portarias, trechos do Diário Oficial) têm camada de
    texto nativa. Não precisam de GPU nem de OCR.
  - As páginas do Diário Oficial são diagramadas em 2 colunas com assuntos
    DIFERENTES em cada coluna. Ler a página "de ponta a ponta" mistura atos
    distintos; aqui a leitura é feita coluna por coluna.
  - O Marker continua disponível em setup/ para PDFs escaneados (sem texto).

Saída: lista de páginas  [{"pagina": 1, "texto": "..."}, ...]
"""
import json
import re
import sys
from pathlib import Path

import pymupdf  # PyMuPDF

RAIZ = Path(__file__).resolve().parent
PASTA_PDFS = RAIZ / "documentos_originais"
PASTA_SAIDA = RAIZ / "data_texto"

# Se uma página tiver menos caracteres que isso, provavelmente é imagem (precisa de OCR)
MIN_CHARS_PAGINA = 80


def _bloco_texto(b):
    return re.sub(r"[ \t]+", " ", b[4]).strip()


def _ler_blocos(pagina):
    """Blocos de texto (x0, y0, x1, y1, texto) sem blocos vazios/imagens."""
    blocos = []
    for b in pagina.get_text("blocks"):
        if b[6] != 0:  # 0 = texto; 1 = imagem
            continue
        t = _bloco_texto(b)
        if t:
            blocos.append((b[0], b[1], b[2], b[3], t))
    return blocos


def _detectar_duas_colunas(blocos, largura):
    """True se a página parece ter 2 colunas de texto lado a lado."""
    meio = largura / 2
    esquerda = [b for b in blocos if b[2] <= meio + 15]
    direita = [b for b in blocos if b[0] >= meio - 15]
    largos = [b for b in blocos if (b[2] - b[0]) > largura * 0.65]
    # precisa de conteúdo relevante nas duas metades e poucos blocos "largos"
    return (
        len(esquerda) >= 3
        and len(direita) >= 3
        and sum(len(b[4]) for b in esquerda) > 300
        and sum(len(b[4]) for b in direita) > 300
        and len(largos) <= max(2, len(blocos) // 5)
    )


def _ordenar_leitura(blocos, largura):
    """Ordem de leitura: blocos largos (cabeçalhos) separam 'faixas'; dentro de
    cada faixa lê-se a coluna esquerda inteira e depois a direita."""
    meio = largura / 2
    blocos = sorted(blocos, key=lambda b: (b[1], b[0]))

    def largo(b):
        return (b[0] < meio - 30) and (b[2] > meio + 30)

    faixas, atual = [], []
    for b in blocos:
        if largo(b):
            if atual:
                faixas.append(("colunas", atual))
                atual = []
            faixas.append(("largo", [b]))
        else:
            atual.append(b)
    if atual:
        faixas.append(("colunas", atual))

    ordenados = []
    for tipo, itens in faixas:
        if tipo == "largo":
            ordenados.extend(itens)
        else:
            esq = sorted([b for b in itens if (b[0] + b[2]) / 2 < meio], key=lambda b: b[1])
            dir_ = sorted([b for b in itens if (b[0] + b[2]) / 2 >= meio], key=lambda b: b[1])
            ordenados.extend(esq + dir_)
    return ordenados


_ESTRUTURA = re.compile(
    r"^(\*?Art\.|\*?§|Parágrafo|[IVXLC]+\s*[-–—]|[a-z]\)|\d+(\.\d+)*[.)]?\s|"
    r"CAP[ÍI]TULO|SE[ÇC][ÃA]O|T[ÍI]TULO|ANEXO|PORTARIA|LEI N|DECRETO|ATA |EXTRATO|\d{1,3}(\.\d{3})*,\d{2})"
)


def _limpar_bloco(texto):
    """Limpa UM bloco do PDF: desfaz hifenização e junta as quebras de linha que
    são só diagramação, preservando linhas que iniciam estrutura legal."""
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    saida = []
    for ln in texto.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if saida and not _ESTRUTURA.match(ln) and not re.search(r"[.:;!?]$", saida[-1]):
            saida[-1] += " " + ln
        else:
            saida.append(ln)
    return re.sub(r"[ \t]{2,}", " ", "\n".join(saida)).strip()


def extrair_pdf(caminho):
    doc = pymupdf.open(caminho)
    paginas, suspeitas = [], []
    for i, pg in enumerate(doc, start=1):
        blocos = _ler_blocos(pg)
        largura = pg.rect.width
        if blocos and _detectar_duas_colunas(blocos, largura):
            blocos = _ordenar_leitura(blocos, largura)
            modo = "2 colunas"
        else:
            blocos = sorted(blocos, key=lambda b: (round(b[1] / 4), b[0]))
            modo = "1 coluna"
        texto = "\n".join(_limpar_bloco(b[4]) for b in blocos)
        if len(texto) < MIN_CHARS_PAGINA:
            suspeitas.append(i)
        paginas.append({"pagina": i, "texto": texto, "layout": modo})
    return paginas, suspeitas


def main():
    PASTA_SAIDA.mkdir(exist_ok=True)
    pdfs = sorted(PASTA_PDFS.glob("*.pdf"))
    if not pdfs:
        print(f"[ERRO] Nenhum PDF em {PASTA_PDFS}")
        sys.exit(1)

    for pdf in pdfs:
        paginas, suspeitas = extrair_pdf(pdf)
        total = sum(len(p["texto"]) for p in paginas)
        layout = {p["layout"] for p in paginas}
        print(f"{pdf.name}: {len(paginas)} pág., {total} caracteres, layout={sorted(layout)}")
        if suspeitas:
            print(f"   [AVISO] páginas com pouco texto (talvez escaneadas): {suspeitas}"
                  f" -> use o Marker em setup/ para elas.")
        (PASTA_SAIDA / f"{pdf.stem}.json").write_text(
            json.dumps(paginas, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(f"\n[OK] Texto salvo em {PASTA_SAIDA}")


if __name__ == "__main__":
    main()
