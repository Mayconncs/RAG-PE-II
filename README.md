# 📚 RAG Híbrido Modular — PDF para LanceDB & Agno Agent

Um pipeline de **Retrieval-Augmented Generation (RAG)** modular e agnóstico de hardware. O projeto permite extrair texto de documentos PDF, processá-los em chunks, criar um banco de dados vetorial com busca híbrida (semântica + palavras-chave/BM25) e consultar as informações utilizando um agente de IA.

A arquitetura isola as particularidades do hardware (NVIDIA/CUDA ou AMD/ROCm) na etapa de extração dos PDFs. O restante do pipeline RAG funciona de maneira independente do fabricante da placa de vídeo.

---

## 📁 Estrutura do Projeto

```text
RAG-PE-II/
├── .env                    # OPENROUTER_API_KEY=... (criar manualmente)
├── config.py               # caminhos, modelo de embedding, tamanho dos chunks
├── embeddings.py           # embeddings compartilhados (prefixos query:/passage: do E5)
├── documentos_originais/   # PDFs de entrada (leis, portarias, trechos do DOE)
├── data_texto/             # texto extraído por página (gerado)
├── .lancedb_local/         # banco vetorial + índice BM25 (gerado)
│
├── extrair_pdfs.py         # 1) PDF -> texto por página (sem GPU; lê colunas do DOE)
├── fazer_chunks.py         # 2) segmenta por ATO/ARTIGO/ANEXO, gera embeddings, grava no LanceDB
├── criar_indice_bm25.py    # 3) índice de palavras-chave (BM25)
├── avaliar_busca.py        # (opcional) mede acertos da busca com perguntas de referência
├── testar_hibrido.py       # (opcional) compara vetorial x BM25 x híbrido para uma pergunta
├── main.py                 # agente de chat no terminal
└── setup/                  # Marker (NVIDIA/AMD): só para PDFs ESCANEADOS, sem camada de texto
```

---

## Interface web (HTML + Tailwind + TypeScript + Vite + FastAPI)

Com o ambiente virtual ativo, instale as dependências e abra a interface:

```powershell
python -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Acesse `http://127.0.0.1:8000`. Para encerrar o servidor, pressione `Ctrl+C` no terminal.
A interface usa o mesmo `.env` e a mesma base local do terminal. Se ainda não preparou a
base, execute `extrair_pdfs.py`, `fazer_chunks.py` e `criar_indice_bm25.py`, nessa ordem.

Inclui conversas salvas no navegador, nova conversa, exclusão individual, exportação em texto,
catálogo dos atos e trechos consultados com links para o PDF na página citada.
A primeira pergunta pode demorar para carregar ou baixar o modelo de embeddings.
As perguntas e os trechos recuperados são enviados ao OpenRouter; a chave fica no servidor.
`openrouter/free` identifica a rota configurada, não o modelo específico escolhido pelo provedor.
Após reindexar documentos ou alterar o `.env`, reinicie o backend para atualizar os caches.

Para desenvolver com atualização automática, rode `python -m uvicorn api:app --reload`
na raiz e, em outro terminal, `cd frontend` seguido de `npm run dev`.
Abra o endereço mostrado pelo Vite (normalmente `http://localhost:5173`). O proxy
encaminha `/api` para o backend, sem expor a chave no frontend.
Use Node.js 22 ou superior. O build gera `frontend/dist`, servido pelo FastAPI.
A API recebe até as duas últimas trocas; não guarda conversas no servidor. A interface
salva as conversas no localStorage e permite reabri-las após recarregar a página. Limpar os dados
do site apaga o histórico; não há sincronização entre navegadores ou endereços diferentes.
O servidor local processa uma consulta por vez para proteger o carregamento do modelo e o acesso à base.
A primeira consulta pode demorar enquanto o modelo é carregado. Os endpoints podem ser explorados em `/docs`.

A versão Streamlit está preservada na branch `feature/interface`, commit `dc60a50`.

O chat de terminal continua disponível com `python main.py`.

Os resultados da avaliação e seus limites estão em [VALIDACAO.md](VALIDACAO.md).

## 🚀 Como executar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crie o `.env` com `OPENROUTER_API_KEY=sua_chave`. Depois, na ordem:

```bash
python extrair_pdfs.py        # 1. texto dos PDFs  -> data_texto/
python fazer_chunks.py        # 2. chunks + embeddings -> .lancedb_local/  (1ª vez baixa o modelo, ~1 GB)
python criar_indice_bm25.py   # 3. índice BM25
python avaliar_busca.py       # (opcional) conferir a qualidade da busca
python main.py                # 4. conversar com o agente
```

Para trocar a base: apague os PDFs de `documentos_originais/`, coloque os novos e repita os passos 1 a 3.

Se um PDF for escaneado (o `extrair_pdfs.py` avisa quando uma página tem pouco texto), use o
Marker em `setup/` e adapte a leitura; para PDFs com texto nativo ele não é necessário.

### Como o chunking funciona (`fazer_chunks.py`)

- Cada PDF do Diário Oficial pode conter vários atos (e conteúdo de outros órgãos). O script separa
  por cabeçalho de ato (Lei, Portaria, Ata...) para que cada trecho seja atribuído à norma certa.
- Dentro do ato, corta por artigo/anexo/tabela, nunca no meio de um artigo (a menos que passe de `CHUNK_MAX`).
- Cada chunk começa com `[Lei nº 2.644/2012 | Art. 2º | CAPÍTULO ...]`, que entra no embedding e no BM25.
- As tabelas de vencimento viram linhas completas: `Padrão III — vencimento — Referência A: R$ ...; ...`.

### Embeddings

`config.py` usa `intfloat/multilingual-e5-base` (até 512 tokens). O modelo anterior
(`paraphrase-multilingual-MiniLM-L12-v2`) lê só 128 tokens (~450 caracteres), então a parte final de
chunks maiores era ignorada. Se voltar ao MiniLM, reduza `CHUNK_MAX` para ~450 em `config.py`.
**Trocou o modelo? Rode `fazer_chunks.py` e `criar_indice_bm25.py` de novo.**

---

## 🔎 Recursos Principais

- **Extração de PDFs:** texto nativo por página (PyMuPDF), com leitura por colunas do Diário Oficial.
- **Processamento em chunks:** divisão do conteúdo em fragmentos para facilitar a recuperação das informações.
- **Embeddings:** representação vetorial do conteúdo para busca semântica.
- **Busca híbrida:** combinação de busca semântica com busca por palavras-chave usando BM25.
- **Banco vetorial local:** armazenamento e consulta dos embeddings com LanceDB.
- **Agente de IA:** interação por terminal para consultar os documentos processados.
- **Suporte a diferentes hardwares:** scripts separados para configurações NVIDIA/CUDA e AMD/ROCm.

---

## 🛠️ Tecnologias Utilizadas

- [Python](https://www.python.org/)
- [PyMuPDF](https://pymupdf.readthedocs.io/) · [Marker](https://github.com/datalab-to/marker) (PDFs escaneados)
- [PyTorch](https://pytorch.org/)
- [LanceDB](https://lancedb.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [Agno](https://www.agno.com/)
- [OpenRouter](https://openrouter.ai/)
- BM25 para busca por palavras-chave
