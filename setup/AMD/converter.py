import os

# --- OVERRIDE DE ARQUITETURA PARA AMD RX 5700 XT (RDNA 1 / gfx1010) ---
# Força o ROCm a tratar a RX 5700 XT como uma GPU compatível (gfx1030)
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"
os.environ["HIP_VISIBLE_DEVICES"] = "0"

import json
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser

# Ajuste de caminhos relativos para funcionar a partir de setup/amd/
RAIZ_PROJETO = Path(__file__).resolve().parent.parent.parent
PDF = RAIZ_PROJETO / "documentos_originais" / "DeD.pdf"
OUT = RAIZ_PROJETO / "data_json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    config = {
        "mode": "fast",
        "disable_ocr": True,
        # "page_range": "0-9",      # Descomente se quiser limitar páginas
        "output_format": "json",
    }
    cp = ConfigParser(config)
    converter = PdfConverter(
        config=cp.generate_config_dict(),
        artifact_dict=create_model_dict(),
        processor_list=cp.get_processors(),
        renderer=cp.get_renderer(),
        llm_service=cp.get_llm_service(),
    )

    print(f"Lendo PDF em: {PDF}")
    rendered = converter(str(PDF))
    text, _, images = text_from_rendered(rendered)

    nome_base = PDF.stem
    (OUT / f"{nome_base}.json").write_text(text, encoding="utf-8")
    (OUT / f"{nome_base}.meta.json").write_text(
        json.dumps(rendered.metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for name, img in images.items():
        img.save(OUT / name)

    print(f"Pronto! Arquivos salvos em: {OUT / f'{nome_base}.json'}")


if __name__ == "__main__":
    main()