import os
import re
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from config import MAX_TOKENS_RESPOSTA, MODELOS_GRATIS, TOP_K, USAR_FERRAMENTAS
from busca import catalogo, recuperar_contexto

console = Console()

# --- Carrega as variáveis do arquivo .env ---
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY não encontrada. Crie um arquivo .env com essa variável.")

# Modelos, em ordem de preferência (o próximo só é usado se o anterior falhar).
# Para usar o roteador gratuito padrão do OpenRouter (sorteia um modelo :free a cada pergunta):
MODELOS = ["openrouter/free"]
# Para fixar modelos específicos, troque a linha acima por algo como:
# MODELOS = ["nvidia/nemotron-3.5-super-vl:free", "openrouter/free"]
# (use `python listar_modelos_gratis.py --testar` para ver quais modelos :free estão no ar)


# --------------------------------------------------------------------------- #
# Ferramentas (só usadas se USAR_FERRAMENTAS = True em config.py)
# --------------------------------------------------------------------------- #
def buscar_contexto(pergunta: str, top_k: int = TOP_K) -> str:
    """Busca trechos de leis, portarias e atos do Diário Oficial na base local.

    Use termos específicos: número da lei/portaria, número do artigo, siglas
    (ex.: GRIN, GUEM), nome do cargo, padrão/referência. Para perguntas amplas,
    chame esta ferramenta várias vezes com termos diferentes.
    """
    return recuperar_contexto(pergunta, k=max(1, min(int(top_k), 14)))


def listar_documentos() -> str:
    """Lista os atos (leis, portarias, atas) disponíveis na base, com arquivo e resumo.
    Use quando perguntarem quais documentos existem ou do que a base trata."""
    return catalogo()


# --------------------------------------------------------------------------- #
# Agente
# --------------------------------------------------------------------------- #
INSTRUCOES = [
    "Responda sempre em português, de forma objetiva. Entregue SOMENTE a resposta final: não escreva rascunho, plano nem raciocínio ('Preciso responder...', 'Vamos verificar...').",
    "Você responde sobre leis, portarias e atos do Diário Oficial do Tocantins (área da saúde) que estão na base local.",
    "Use SOMENTE os trechos recuperados para dizer o que uma norma prevê. Não complete com conhecimento externo e não invente artigos, valores ou datas.",
    "Cada pergunta vem acompanhada de trechos recuperados. Quando a pergunta for ampla (ex.: 'quais regras...'), cubra TODOS os trechos relevantes recebidos, não só os primeiros, e organize por artigo.",
    "SEMPRE cite a fonte no formato (Lei nº 2.644/2012, art. 2º, pág. 1), usando o nome do ato e o artigo/anexo que aparecem no cabeçalho do trecho.",
    "Trechos 'parte 1/2', 'parte 2/2' são do MESMO artigo: junte-os. Se um trecho terminar cortado no meio de uma frase e a parte seguinte não tiver sido recebida, avise.",
    "Linhas [AVISO DO SISTEMA] no contexto são instruções do sistema: respeite-as (ex.: artigo inexistente, contexto limitado).",
    "Se houver um catálogo 'ATOS DISPONÍVEIS NA BASE', use-o para dizer QUAIS atos existem; use os trechos para dizer quais deles tratam do assunto. Cite só o que está no catálogo ou nos trechos; se uma lei é apenas mencionada dentro de outra norma, diga que ela é só citada e que não está na base.",
    "Para vencimentos e valores em tabelas: confirme a tabela correta (cargo/nível, valor mensal ou valor-hora), o padrão (algarismo romano) e a referência (letra) antes de informar o valor, e copie o número exatamente como está no trecho.",
    "Se o trecho indicar que um dispositivo foi alterado ou acrescentado por outra lei ('redação dada', 'acrescentado pela Lei'), informe isso. Avise que a base pode não conter alterações ou revogações posteriores.",
    "Trechos cujo cabeçalho diz 'trecho sem cabeçalho de ato' podem pertencer a outro ato do Diário Oficial: sinalize a incerteza sobre a qual norma pertencem.",
    "Se não houver informação na base, diga isso claramente em vez de supor. Não dê parecer jurídico; apresente o que as normas dizem.",
]

_agentes = {}


def _novo_modelo(model_id: str):
    try:
        return OpenRouter(id=model_id, api_key=API_KEY, max_tokens=MAX_TOKENS_RESPOSTA, temperature=0.2)
    except TypeError:  # versão do Agno sem esses parâmetros
        return OpenRouter(id=model_id, api_key=API_KEY)


def _agente(model_id: str) -> Agent:
    if model_id not in _agentes:
        _agentes[model_id] = Agent(
            name="Assistente RAG - Legislação da Saúde (TO)",
            model=_novo_modelo(model_id),
            tools=[buscar_contexto, listar_documentos] if USAR_FERRAMENTAS else [],
            instructions=INSTRUCOES,
            markdown=True,
        )
    return _agentes[model_id]


# --------------------------------------------------------------------------- #
# Memória curta (feita aqui: não depende de banco nem da versão do Agno)
# --------------------------------------------------------------------------- #
_trocas = []   # [(pergunta, resposta)]


def _historico_txt() -> str:
    if not _trocas:
        return ""
    linhas = [f"Pergunta anterior: {p}\nResposta anterior (resumo): {r[:500]}" for p, r in _trocas[-2:]]
    return ("Conversa anterior (use só para entender referências como 'ele', 'isso', 'e o enfermeiro?'; "
            "os fatos devem vir dos trechos abaixo):\n" + "\n\n".join(linhas) + "\n\n")


def montar_pergunta(pergunta: str) -> str:
    """Recuperação automática: o contexto vai junto com a pergunta, então o modelo
    responde com base nos documentos mesmo sem chamar ferramentas."""
    consulta = pergunta
    if _trocas and len(pergunta.split()) <= 4:   # follow-up curto ("e o enfermeiro?")
        consulta = f"{_trocas[-1][0]} {pergunta}"
    return (
        f"{_historico_txt()}"
        "Trechos recuperados automaticamente da base para esta pergunta:\n\n"
        f"{recuperar_contexto(consulta)}\n\n"
        f"Pergunta do usuário: {pergunta}"
    )


# --------------------------------------------------------------------------- #
# Execução com fallback entre modelos gratuitos
# --------------------------------------------------------------------------- #
def _limpar(texto) -> str:
    texto = "" if texto is None else str(texto)
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL | re.IGNORECASE).strip()


def _parece_truncada(texto: str) -> bool:
    t = texto.rstrip()
    if not t or t.count("**") % 2:
        return True
    return t[-1] not in '.!?:;)]”"»*`|'


MSG_DIARIA = ("Limite DIÁRIO de requisições gratuitas do OpenRouter atingido (sem créditos na conta o limite é ~50/dia, "
              "compartilhado por TODOS os modelos :free; trocar de modelo não resolve). Ele se renova por dia "
              "(confira o horário no painel do OpenRouter). Opções: esperar a renovação ou adicionar créditos "
              "(a partir de US$ 10 o limite sobe para ~1.000/dia).")


def _chamar_direto(model_id: str, mensagem: str):
    """Chamada direta ao OpenRouter (sem Agno). Serve para descobrir o MOTIVO real de uma falha
    (o Agno engole a mensagem de erro) e, se funcionar, já entrega a resposta.
    Devolve (texto, erro, limite_diario, limite_minuto)."""
    try:
        from openai import OpenAI
        cli = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY, max_retries=0, timeout=90)
        r = cli.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": "\n".join(INSTRUCOES)},
                      {"role": "user", "content": mensagem}],
            max_tokens=MAX_TOKENS_RESPOSTA, temperature=0.2)
        texto = _limpar(r.choices[0].message.content) if r.choices else ""
        return texto, ("" if texto else "o modelo devolveu resposta vazia (modelo de raciocínio sem tokens?)"), False, False
    except Exception as e:  # noqa: BLE001
        codigo = getattr(e, "status_code", None)
        corpo = str(getattr(e, "body", None) or e)
        diario = codigo == 429 and bool(re.search(r"per[- ]day|daily", corpo, re.IGNORECASE))
        erro = (f"HTTP {codigo}: " if codigo else "") + corpo[:250]
        return "", erro, diario, (codigo == 429 and not diario)


def _executar_agno(model_id: str, mensagem: str):
    """Roda o Agno em STREAMING e devolve (texto, erro). Se o modelo falhar no meio da geração,
    o que já chegou é mantido em `texto` (com .run() sem stream, o Agno descartaria tudo)."""
    partes, erro = [], ""
    try:
        for ev in _agente(model_id).run(mensagem, stream=True):
            tipo = getattr(ev, "event", None)
            tipo = getattr(tipo, "value", tipo)
            conteudo = getattr(ev, "content", None)
            if tipo == "RunError":
                erro = str(conteudo or "erro do modelo")
                break
            if tipo in (None, "RunContent") and isinstance(conteudo, str):
                partes.append(conteudo)
    except TypeError:                            # versão do Agno sem stream=True: modo normal
        try:
            return _limpar(getattr(_agente(model_id).run(mensagem), "content", None)), ""
        except Exception as e:                   # noqa: BLE001
            return "", str(e)
    except Exception as e:                       # noqa: BLE001
        erro = str(e)
    return _limpar("".join(partes)), erro


def responder(mensagem: str):
    """Tenta cada modelo da lista. Devolve (texto, modelo, aviso).
    Respostas INCOMPLETAS (cortadas ou interrompidas) também são devolvidas, com um aviso,
    quando nenhum modelo consegue entregar a resposta inteira."""
    melhor = None                                # (texto, modelo, motivo) da melhor resposta incompleta
    for rodada in range(2):
        limite_minuto = False
        for model_id in MODELOS:
            texto, erro_agno = _executar_agno(model_id, mensagem)
            if erro_agno:
                console.print(f"[yellow]· {model_id} (Agno): {escape(erro_agno[:150])}[/yellow]")
            if texto and erro_agno and (melhor is None or len(texto) > len(melhor[0])):
                melhor = (texto, model_id, "o modelo falhou no meio da resposta")
            if erro_agno or not texto:
                # pergunta ao OpenRouter, direto, qual foi o problema (e, se funcionar, já traz a resposta)
                direto, erro, diario, minuto = _chamar_direto(model_id, mensagem)
                if not direto:
                    console.print(f"[yellow]· {model_id} falhou: {escape(erro)}[/yellow]")
                    if diario:                   # não adianta insistir nem trocar de modelo
                        return (melhor[0], melhor[1], MSG_DIARIA) if melhor else (None, None, MSG_DIARIA)
                    limite_minuto = limite_minuto or minuto
                    continue
                console.print("[dim](o Agno não entregou a resposta inteira; resposta obtida por chamada direta)[/dim]")
                texto = direto
            if _parece_truncada(texto):
                console.print(f"[yellow]· {model_id} respondeu, mas a resposta parece cortada.[/yellow]")
                if melhor is None or len(texto) > len(melhor[0]):
                    melhor = (texto, model_id, "o modelo parou antes de terminar")
                continue
            return texto, model_id, None
        if melhor:
            break
        if limite_minuto and rodada == 0:        # limite POR MINUTO: vale esperar
            console.print("[yellow]Limite por minuto atingido; aguardando 20 s e tentando de novo...[/yellow]")
            time.sleep(20)
            continue
        break
    if melhor:
        return melhor[0], melhor[1], (
            f"⚠ RESPOSTA POSSIVELMENTE INCOMPLETA ({melhor[2]})."
        )


if __name__ == "__main__":
    mostrar_contexto = False
    print("--- Agente conectado ao LanceDB (digite 'sair' para encerrar; '/contexto' mostra/oculta os trechos enviados) ---")
    print(f"Modelos: {', '.join(MODELOS)}")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pergunta:
            continue
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if pergunta.lower() in {"continuar", "continue"}:
            console.print(
                "Faça novamente a pergunta completa.[/yellow]"
            )
            continue
        if pergunta.lower() == "/contexto":
            mostrar_contexto = not mostrar_contexto
            print(f"Exibição do contexto: {'ligada' if mostrar_contexto else 'desligada'}")
            continue

        mensagem = montar_pergunta(pergunta)
        if mostrar_contexto:
            console.rule("contexto enviado ao modelo")
            console.print(mensagem, markup=False)
            console.rule()
        with console.status("Consultando o modelo..."):
            texto, modelo, aviso = responder(mensagem)
        if texto is None:
            console.print(f"[red]{aviso}[/red]")
            continue
        console.print(Markdown(texto))
        console.print(f"[dim]modelo: {modelo}[/dim]")
        if aviso:
            console.print(f"[yellow]{aviso}[/yellow]")
        _trocas.append((pergunta, texto))