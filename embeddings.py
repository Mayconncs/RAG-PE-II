"""Embeddings compartilhados por fazer_chunks.py, main.py e testar_hibrido.py."""
from config import MODELO_EMBEDDING

_modelo = None


def _carregar():
    global _modelo
    if _modelo is None:
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(MODELO_EMBEDDING)
    return _modelo


def _usa_prefixos():
    # a família E5 exige "query: " / "passage: " para funcionar bem
    return "e5" in MODELO_EMBEDDING.lower()


def codificar_passagens(textos, mostrar_progresso=False):
    prefixo = "passage: " if _usa_prefixos() else ""
    return _carregar().encode(
        [prefixo + t for t in textos],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=mostrar_progresso,
    )


def codificar_consulta(texto):
    prefixo = "query: " if _usa_prefixos() else ""
    return _carregar().encode(prefixo + texto, normalize_embeddings=True).tolist()
