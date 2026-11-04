# Validação do chatbot

Avaliação local em 4 de novembro de 2026, usando a base atual e o modelo E5 em cache.

## Busca documental

Comando: `python avaliar_busca.py`. São 17 verificações de trechos esperados
(há perguntas repetidas com fontes esperadas diferentes). O teste confere o nome do
ato e a presença de texto no chunk; não avalia a correção da resposta gerada.

| Método | Acertos |
|---|---|
| Vetorial, top 5 | 15/17 |
| BM25, top 5 | 13/17 |
| Híbrido simples, top 5 | 17/17 |
| Híbrido com pool | 12/17 |
| Híbrido com pool e reescrita | 12/17 |
| Pipeline usado pelo chat | 16/17 (94,1%) |

O pipeline expande artigos e usa limites próprios: seus resultados não representam
um top 5 estrito. Falhou ao incluir o trecho esperado da Lei nº 2.644/2012 na pergunta
“Quais leis tratam de gratificações para servidores da saúde?”. Isso indica uma lacuna
na cobertura de perguntas amplas. O catálogo pode listar um ato sem que o trecho relevante
dele chegue à resposta. Não se deve declarar a qualidade de busca como perfeita.

Não houve avaliação de respostas reais do OpenRouter nesta rodada. Precisão factual,
adequação das citações e comportamento diante de perguntas fora da base ainda precisam
de revisão com respostas reais. O conjunto pequeno e específico também não mede generalização.

## Persistência

As conversas e os trechos ficam no localStorage do navegador, com lista para reabrir,
nova consulta e exclusão individual. Os dados sobrevivem à atualização da página e ao
fechamento da aba em navegação normal. Limpar os dados do site os remove; não há sincronização
entre dispositivos. Endereços diferentes (por exemplo, localhost:5173 e 127.0.0.1:8000)
têm históricos separados. Falhas de gravação mostram um aviso para exportar a conversa.

Os testes de armazenamento validam gravação/leitura, exclusão, dados inválidos e falha de quota.
Não foi feita inspeção manual em navegador nesta rodada.

## Conferência das fontes

Cada trecho inclui link para o PDF original na primeira página do intervalo citado.
A navegação até a página depende do leitor de PDF do navegador. O endpoint limita o acesso
a PDFs diretamente na pasta documentos_originais. Os testes verificam conteúdo PDF real,
arquivo inexistente e rejeição de caminhos inválidos.

## Comandos

```powershell
python -m unittest test_api -v
cd frontend
node --test test-history.mjs
npm run build
```
