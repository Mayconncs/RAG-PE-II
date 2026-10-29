import json
import os
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser

# Descobre a raiz do projeto (duas pastas acima de setup/NVIDIA/)
RAIZ_PROJETO = Path(__file__).resolve().parent.parent.parent

# Pastas de entrada e saída
PASTA_ORIGINAIS = RAIZ_PROJETO / "documentos_originais"
OUT_DIR = RAIZ_PROJETO / "data_json"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Busca todos os arquivos .pdf da pasta
    arquivos_pdf = list(PASTA_ORIGINAIS.glob("*.pdf"))

    if not arquivos_pdf:
        print(f"[AVISO] Nenhum arquivo .pdf foi encontrado na pasta: {PASTA_ORIGINAIS}")
        return

    print(f"Foram encontrados {len(arquivos_pdf)} PDF(s) para conversão.\n")

    config = {
        "mode": "fast",
        "disable_ocr": True,
        # "page_range": "0-9",       # Descomente se quiser limitar páginas para testes
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

    for pdf_path in arquivos_pdf:
        nome_base = pdf_path.stem
        print(f"--> Processando: {pdf_path.name}...")

        try:
            rendered = converter(str(pdf_path))
            text, _, images = text_from_rendered(rendered)

            # Salva o arquivo JSON do documento
            (OUT_DIR / f"{nome_base}.json").write_text(text, encoding="utf-8")
            
            # Salva os metadados do documento
            (OUT_DIR / f"{nome_base}.meta.json").write_text(
                json.dumps(rendered.metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            
            # Salva imagens extraídas, se houver
            for name, img in images.items():
                img.save(OUT_DIR / name)

            print(f"    [OK] Salvo em: {OUT_DIR / f'{nome_base}.json'}\n")

        except Exception as e:
            print(f"    [ERRO] Falha ao processar {pdf_path.name}: {e}\n")

    print("Processamento concluído para todos os documentos!")


if __name__ == "__main__":
    main()