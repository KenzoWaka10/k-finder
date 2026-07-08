"""
K-FINDER — Bot Telegram v3.0
KenLogic Solutions

Novidades v3.0:
- Inline keyboard em todos os passos
- Selecao de cidades por botoes (paginado)
- Selecao de data por calendario de botoes
- Precos sugeridos + digitar manual
- Voltar passo, cancelar, confirmar antes de salvar
- Multi-usuario real
"""

import os
import json
import subprocess
import requests
import calendar
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CONFIG_FILE      = "config.json"

USUARIOS_PERMITIDOS = [
    os.getenv("TELEGRAM_CHAT_ID"),
    # "123456789",
    # "987654321",
]

# Cidades ordenadas por popularidade para exibir nos botoes
CIDADES_LISTA = [
    ("São Paulo (GRU)",    "GRU"),
    ("São Paulo (CGH)",    "CGH"),
    ("Rio de Janeiro",     "GIG"),
    ("Brasília",           "BSB"),
    ("Curitiba",           "CWB"),
    ("Porto Alegre",       "POA"),
    ("Florianópolis",      "FLN"),
    ("Belo Horizonte",     "CNF"),
    ("Salvador",           "SSA"),
    ("Recife",             "REC"),
    ("Fortaleza",          "FOR"),
    ("Londrina",           "LDB"),
    ("Campinas",           "VCP"),
    ("Maceió",             "MCZ"),
    ("Natal",              "NAT"),
    ("João Pessoa",        "JPA"),
    ("Manaus",             "MAO"),
    ("Belém",              "BEL"),
    ("Porto Seguro",       "BPS"),
    ("Foz do Iguaçu",     "IGU"),
    ("Campo Grande",       "CGR"),
    ("Vitória",            "VIX"),
    ("Goiânia",            "GYN"),
    ("Aracaju",            "AJU"),
    ("São Luís",           "SLZ"),
    ("Teresina",           "THE"),
    ("Cuiabá",             "CGB"),
    ("Porto Velho",        "PVH"),
    ("Macapá",             "MCP"),
    ("Boa Vista",          "BVB"),
    ("Palmas",             "PMW"),
]

PRECOS_SUGERIDOS = [300, 500, 700, 900, 1200, 1500, 2000, 2500]
CIDADES_POR_PAG  = 8   # botoes de cidade por pagina (2 colunas = 4 linhas)


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def ler_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "rotas" in data and "usuarios" not in data:
                chat_id_dono = str(TELEGRAM_CHAT_ID or "admin")
                return {"usuarios": {chat_id_dono: {"rotas": data["rotas"]}}}
            if "usuarios" in data:
                return data
    return {"usuarios": {}}

def salvar_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def ler_rotas(chat_id: str) -> list:
    config = ler_config()
    return config.get("usuarios", {}).get(str(chat_id), {}).get("rotas", [])

def salvar_rotas(chat_id: str, rotas: list):
    config = ler_config()
    if "usuarios" not in config:
        config["usuarios"] = {}
    if str(chat_id) not in config["usuarios"]:
        config["usuarios"][str(chat_id)] = {}
    config["usuarios"][str(chat_id)]["rotas"] = rotas
    salvar_config(config)

def proximo_id(rotas: list) -> int:
    return max((r.get("id", 0) for r in rotas), default=0) + 1


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM — mensagens e callbacks
# ══════════════════════════════════════════════════════════════════════════════

def _post(endpoint: str, payload: dict):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{endpoint}"
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"❌ Erro Telegram [{endpoint}]: {e}")
        return {}

def enviar(chat_id: str, texto: str, teclado=None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = {"inline_keyboard": teclado}
    return _post("sendMessage", payload)

def editar(chat_id: str, message_id: int, texto: str, teclado=None):
    payload = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       texto,
        "parse_mode": "Markdown",
    }
    if teclado:
        payload["reply_markup"] = {"inline_keyboard": teclado}
    else:
        payload["reply_markup"] = {"inline_keyboard": []}
    return _post("editMessageText", payload)

def responder_callback(callback_id: str, texto: str = ""):
    _post("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto})


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO POR USUARIO
# ══════════════════════════════════════════════════════════════════════════════

estados = {}
# {
#   chat_id: {
#     "passo": "origem" | "destino" | "data_ida" | "data_volta" | "preco" | "confirmar",
#     "modo":  "adicionar" | "editar",
#     "editando_id": N,
#     "cfg": { origem, destino, data_ida, data_volta, preco_maximo },
#     "msg_id": message_id do menu atual (para editar no lugar),
#     "digitando_preco": bool,
#   }
# }


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def formatar_data(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_iso

def resumo_cfg(cfg: dict) -> str:
    volta = formatar_data(cfg["data_volta"]) if cfg.get("data_volta") else "só ida"
    preco = f"R$ {cfg['preco_maximo']:.0f}" if cfg.get("preco_maximo") else "—"
    return (
        f"✈️ *{cfg.get('origem', '—')} → {cfg.get('destino', '—')}*\n"
        f"📅 Ida: {formatar_data(cfg['data_ida']) if cfg.get('data_ida') else '—'}  |  Volta: {volta}\n"
        f"💰 Preço máximo: {preco}"
    )

def resumo_rota(r: dict) -> str:
    volta = formatar_data(r["data_volta"]) if r.get("data_volta") else "só ida"
    return (
        f"*#{r['id']} — {r['origem']} ✈️ {r['destino']}*\n"
        f"   📅 Ida: {formatar_data(r['data_ida'])}  |  Volta: {volta}\n"
        f"   💰 Preço máximo: R$ {r['preco_maximo']:.0f}"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  TECLADOS
# ══════════════════════════════════════════════════════════════════════════════

def teclado_cidades(pagina: int = 0, prefixo: str = "cidade_orig") -> list:
    inicio = pagina * CIDADES_POR_PAG
    fim    = inicio + CIDADES_POR_PAG
    bloco  = CIDADES_LISTA[inicio:fim]

    # 2 botoes por linha
    linhas = []
    for i in range(0, len(bloco), 2):
        linha = []
        for nome, cod in bloco[i:i+2]:
            linha.append({"text": nome, "callback_data": f"{prefixo}:{cod}"})
        linhas.append(linha)

    # Navegacao
    nav = []
    if pagina > 0:
        nav.append({"text": "⬅️ Anterior", "callback_data": f"{prefixo}_pag:{pagina-1}"})
    if fim < len(CIDADES_LISTA):
        nav.append({"text": "Próxima ➡️", "callback_data": f"{prefixo}_pag:{pagina+1}"})
    if nav:
        linhas.append(nav)

    linhas.append([{"text": "❌ Cancelar", "callback_data": "cancelar"}])
    return linhas

def teclado_calendario(ano: int, mes: int, prefixo: str) -> list:
    """Calendário de dias como inline keyboard."""
    linhas = []

    # Cabeçalho: mês/ano + navegação
    nome_mes = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"][mes]
    linhas.append([
        {"text": "◀️", "callback_data": f"{prefixo}_mes:{ano}:{mes-1 if mes > 1 else 12}:{1 if mes > 1 else ano-1}"},
        {"text": f"  {nome_mes} {ano}  ", "callback_data": "ignore"},
        {"text": "▶️", "callback_data": f"{prefixo}_mes:{ano}:{mes+1 if mes < 12 else 1}:{ano if mes < 12 else ano+1}"},
    ])

    # Dias da semana
    linhas.append([
        {"text": "Dom", "callback_data": "ignore"},
        {"text": "Seg", "callback_data": "ignore"},
        {"text": "Ter", "callback_data": "ignore"},
        {"text": "Qua", "callback_data": "ignore"},
        {"text": "Qui", "callback_data": "ignore"},
        {"text": "Sex", "callback_data": "ignore"},
        {"text": "Sáb", "callback_data": "ignore"},
    ])

    # Dias do mes
    primeiro_dia, total_dias = calendar.monthrange(ano, mes)
    primeiro_dia = (primeiro_dia + 1) % 7  # calendario br: domingo=0
    hoje = date.today()

    semana = ["  "] * primeiro_dia
    for dia in range(1, total_dias + 1):
        d = date(ano, mes, dia)
        if d < hoje:
            semana.append({"text": "·", "callback_data": "ignore"})
        else:
            semana.append({
                "text": str(dia),
                "callback_data": f"{prefixo}:{ano}-{mes:02d}-{dia:02d}"
            })
        if len(semana) == 7:
            linhas.append([b for b in semana if b != "  "])
            semana = []
    if semana:
        linhas.append([b for b in semana if b != "  "])

    # Rodape
    volta_cb = "voltar_para_data_ida" if "volta" in prefixo else "voltar_para_origem"
    # Ajusta o voltar conforme o passo
    linhas.append([
        {"text": "⬅️ Voltar",    "callback_data": f"voltar:{prefixo}"},
        {"text": "❌ Cancelar", "callback_data": "cancelar"},
    ])
    return linhas

def teclado_preco() -> list:
    linhas = []
    for i in range(0, len(PRECOS_SUGERIDOS), 4):
        linha = []
        for p in PRECOS_SUGERIDOS[i:i+4]:
            linha.append({"text": f"R$ {p}", "callback_data": f"preco:{p}"})
        linhas.append(linha)
    linhas.append([{"text": "✏️ Digitar valor", "callback_data": "preco:digitar"}])
    linhas.append([
        {"text": "⬅️ Voltar",    "callback_data": "voltar:preco"},
        {"text": "❌ Cancelar", "callback_data": "cancelar"},
    ])
    return linhas

def teclado_confirmar() -> list:
    return [
        [
            {"text": "✅ Confirmar", "callback_data": "confirmar"},
            {"text": "✏️ Editar",    "callback_data": "voltar:confirmar"},
        ],
        [{"text": "❌ Cancelar", "callback_data": "cancelar"}],
    ]

def teclado_volta_opcional() -> list:
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    return [
        [{"text": "✈️ Só ida (sem volta)", "callback_data": "data_volta:nao"}],
        [
            {"text": "⬅️ Voltar",    "callback_data": "voltar:data_volta"},
            {"text": "❌ Cancelar", "callback_data": "cancelar"},
        ],
    ]

def teclado_menu_rotas(rotas: list, acao: str) -> list:
    """Lista de rotas como botoes para selecionar."""
    linhas = []
    for r in rotas:
        volta = formatar_data(r["data_volta"]) if r.get("data_volta") else "só ida"
        label = f"#{r['id']} {r['origem']}→{r['destino']} | {formatar_data(r['data_ida'])}"
        linhas.append([{"text": label, "callback_data": f"{acao}:{r['id']}"}])
    linhas.append([{"text": "❌ Cancelar", "callback_data": "cancelar"}])
    return linhas

def teclado_menu_principal() -> list:
    return [
        [
            {"text": "➕ Adicionar rota",  "callback_data": "cmd:adicionar"},
            {"text": "🗺️ Listar rotas",    "callback_data": "cmd:listar"},
        ],
        [
            {"text": "✏️ Editar rota",     "callback_data": "cmd:editar"},
            {"text": "🗑️ Remover rota",    "callback_data": "cmd:remover"},
        ],
        [{"text": "🔍 Buscar agora",       "callback_data": "cmd:buscar_agora"}],
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  FLUXO: iniciar passo de cidade
# ══════════════════════════════════════════════════════════════════════════════

def mostrar_passo_origem(chat_id: str, msg_id: int = None):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    texto  = (
        f"{titulo}\n\n"
        f"{resumo_cfg(cfg) if cfg.get('origem') else ''}\n\n"
        f"*Passo 1/5 — Cidade de origem:*\n"
        "_Selecione uma cidade:_"
    ).strip()

    teclado = teclado_cidades(0, "cidade_orig")
    if msg_id:
        editar(chat_id, msg_id, texto, teclado)
    else:
        r = enviar(chat_id, texto, teclado)
        estado["msg_id"] = r.get("result", {}).get("message_id")

def mostrar_passo_destino(chat_id: str):
    estado  = estados[chat_id]
    cfg     = estado["cfg"]
    msg_id  = estado["msg_id"]
    modo    = estado["modo"]
    titulo  = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    texto   = (
        f"{titulo}\n\n"
        f"{resumo_cfg(cfg)}\n\n"
        f"*Passo 2/5 — Cidade de destino:*\n"
        "_Selecione uma cidade:_"
    )
    editar(chat_id, msg_id, texto, teclado_cidades(0, "cidade_dest"))

def mostrar_passo_data_ida(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    msg_id = estado["msg_id"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    hoje   = date.today()
    ano, mes = hoje.year, hoje.month
    texto  = (
        f"{titulo}\n\n"
        f"{resumo_cfg(cfg)}\n\n"
        f"*Passo 3/5 — Data de ida:*\n"
        "_Selecione no calendário:_"
    )
    editar(chat_id, msg_id, texto, teclado_calendario(ano, mes, "data_ida"))

def mostrar_passo_data_volta(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    msg_id = estado["msg_id"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    hoje   = date.today()
    # Começa no mesmo mês da ida ou mês atual
    if cfg.get("data_ida"):
        dt_ida = datetime.strptime(cfg["data_ida"], "%Y-%m-%d")
        ano, mes = dt_ida.year, dt_ida.month
    else:
        ano, mes = hoje.year, hoje.month

    cal = teclado_calendario(ano, mes, "data_volta")
    # Adiciona botao "so ida" no topo
    cal.insert(0, [{"text": "✈️ Só ida (sem volta)", "callback_data": "data_volta:nao"}])

    texto = (
        f"{titulo}\n\n"
        f"{resumo_cfg(cfg)}\n\n"
        f"*Passo 4/5 — Data de volta:*\n"
        "_Selecione ou escolha só ida:_"
    )
    editar(chat_id, msg_id, texto, cal)

def mostrar_passo_preco(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    msg_id = estado["msg_id"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    texto  = (
        f"{titulo}\n\n"
        f"{resumo_cfg(cfg)}\n\n"
        f"*Passo 5/5 — Preço máximo:*\n"
        "_Selecione ou digite um valor:_"
    )
    editar(chat_id, msg_id, texto, teclado_preco())

def mostrar_confirmacao(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    msg_id = estado["msg_id"]
    modo   = estado["modo"]
    titulo = "✏️ Confirmar edição" if modo == "editar" else "✅ Confirmar nova rota"
    texto  = (
        f"*{titulo}*\n\n"
        f"{resumo_cfg(cfg)}\n\n"
        "_Tudo certo?_"
    )
    editar(chat_id, msg_id, texto, teclado_confirmar())


# ══════════════════════════════════════════════════════════════════════════════
#  SALVAR ROTA
# ══════════════════════════════════════════════════════════════════════════════

def salvar_rota_atual(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    msg_id = estado["msg_id"]

    cfg["preco_minimo"] = 0
    cfg["adultos"]      = 1

    rotas = ler_rotas(chat_id)

    if modo == "editar":
        rid = estado["editando_id"]
        for i, r in enumerate(rotas):
            if r["id"] == rid:
                cfg["id"] = rid
                rotas[i]  = cfg
                break
        salvar_rotas(chat_id, rotas)
        del estados[chat_id]
        editar(chat_id, msg_id,
            f"✅ *Rota #{rid} atualizada!*\n\n"
            f"{resumo_cfg(cfg)}\n\n"
            "Use /buscar\\_agora ou o menu para continuar.",
        )
    else:
        cfg["id"] = proximo_id(rotas)
        rotas.append(cfg)
        salvar_rotas(chat_id, rotas)
        del estados[chat_id]
        editar(chat_id, msg_id,
            f"✅ *Rota #{cfg['id']} adicionada!*\n\n"
            f"{resumo_cfg(cfg)}\n\n"
            f"📊 Total de rotas ativas: *{len(rotas)}*\n\n"
            "Use /menu para continuar.",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR CALLBACKS (cliques nos botoes)
# ══════════════════════════════════════════════════════════════════════════════

def processar_callback(chat_id: str, callback_id: str, data: str, message_id: int):
    responder_callback(callback_id)

    # Ignorar botoes decorativos
    if data == "ignore":
        return

    # Cancelar
    if data == "cancelar":
        if chat_id in estados:
            msg_id = estados[chat_id].get("msg_id", message_id)
            del estados[chat_id]
            editar(chat_id, msg_id,
                "❌ *Operação cancelada.*\n\nUse /menu para voltar ao início."
            )
        return

    # Confirmar salvar
    if data == "confirmar":
        if chat_id in estados:
            salvar_rota_atual(chat_id)
        return

    # Comandos do menu principal
    if data.startswith("cmd:"):
        cmd = data.split(":")[1]
        processar_comando(chat_id, f"/{cmd}", message_id)
        return

    # Voltar passo
    if data.startswith("voltar:"):
        passo_atual = data.split(":")[1]
        if chat_id not in estados:
            return
        estado = estados[chat_id]
        estado["cfg"].pop("digitando_preco", None)
        estado["digitando_preco"] = False
        if passo_atual in ["data_volta", "preco", "data_ida_cal"]:
            mostrar_passo_data_ida(chat_id)
        elif passo_atual == "data_volta_cal":
            mostrar_passo_data_volta(chat_id)
        elif passo_atual in ["confirmar", "preco"]:
            mostrar_passo_preco(chat_id)
        elif passo_atual == "destino":
            mostrar_passo_origem(chat_id, estado["msg_id"])
        else:
            mostrar_passo_data_volta(chat_id)
        return

    # Paginacao de cidades
    if "pag:" in data:
        prefixo, resto = data.rsplit("_pag:", 1)
        pagina = int(resto)
        if chat_id not in estados:
            return
        msg_id = estados[chat_id]["msg_id"]
        editar(chat_id, msg_id,
            estados[chat_id].get("_ultimo_texto", "Selecione uma cidade:"),
            teclado_cidades(pagina, prefixo)
        )
        return

    # Selecao de cidade de origem
    if data.startswith("cidade_orig:"):
        if chat_id not in estados:
            return
        cod = data.split(":")[1]
        estados[chat_id]["cfg"]["origem"] = cod
        estados[chat_id]["passo"] = "destino"
        mostrar_passo_destino(chat_id)
        return

    # Selecao de cidade de destino
    if data.startswith("cidade_dest:"):
        if chat_id not in estados:
            return
        cod = data.split(":")[1]
        estados[chat_id]["cfg"]["destino"] = cod
        estados[chat_id]["passo"] = "data_ida"
        mostrar_passo_data_ida(chat_id)
        return

    # Navegacao do calendario
    if data.startswith("data_ida_mes:") or data.startswith("data_volta_mes:"):
        if chat_id not in estados:
            return
        partes = data.split(":")
        prefixo_cal = partes[0].replace("_mes", "")
        ano  = int(partes[1])
        mes  = int(partes[2])
        ano_real = int(partes[3]) if len(partes) > 3 else ano
        msg_id = estados[chat_id]["msg_id"]
        # Corrige navegacao de ano
        if mes == 0:
            mes = 12; ano_real -= 1
        elif mes == 13:
            mes = 1; ano_real += 1
        else:
            ano_real = ano
        cfg = estados[chat_id]["cfg"]
        modo = estados[chat_id]["modo"]
        titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
        passo_label = "3/5 — Data de ida" if "ida" in prefixo_cal else "4/5 — Data de volta"

        cal = teclado_calendario(ano_real, mes, prefixo_cal)
        if "volta" in prefixo_cal:
            cal.insert(0, [{"text": "✈️ Só ida (sem volta)", "callback_data": "data_volta:nao"}])

        editar(chat_id, msg_id,
            f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo {passo_label}:*\n_Selecione no calendário:_",
            cal
        )
        return

    # Selecao de data de ida
    if data.startswith("data_ida:"):
        if chat_id not in estados:
            return
        data_iso = data.split(":", 1)[1]
        estados[chat_id]["cfg"]["data_ida"] = data_iso
        estados[chat_id]["passo"] = "data_volta"
        mostrar_passo_data_volta(chat_id)
        return

    # Selecao de data de volta
    if data.startswith("data_volta:"):
        if chat_id not in estados:
            return
        val = data.split(":", 1)[1]
        estados[chat_id]["cfg"]["data_volta"] = "" if val == "nao" else val
        estados[chat_id]["passo"] = "preco"
        mostrar_passo_preco(chat_id)
        return

    # Selecao de preco
    if data.startswith("preco:"):
        if chat_id not in estados:
            return
        val = data.split(":", 1)[1]
        if val == "digitar":
            estados[chat_id]["digitando_preco"] = True
            msg_id = estados[chat_id]["msg_id"]
            editar(chat_id, msg_id,
                "💰 *Digite o preço máximo em reais:*\n_ex: 850_",
                [[{"text": "❌ Cancelar", "callback_data": "cancelar"}]]
            )
        else:
            estados[chat_id]["cfg"]["preco_maximo"] = float(val)
            estados[chat_id]["passo"] = "confirmar"
            estados[chat_id]["digitando_preco"] = False
            mostrar_confirmacao(chat_id)
        return

    # Selecao de rota para editar
    if data.startswith("sel_editar:"):
        rid = int(data.split(":")[1])
        rotas = ler_rotas(chat_id)
        rota  = next((r for r in rotas if r["id"] == rid), None)
        if not rota:
            editar(chat_id, message_id, "❌ Rota não encontrada.")
            return
        estados[chat_id] = {
            "passo":        "origem",
            "modo":         "editar",
            "editando_id":  rid,
            "cfg":          {k: v for k, v in rota.items() if k != "id"},
            "msg_id":       message_id,
            "digitando_preco": False,
        }
        mostrar_passo_origem(chat_id, message_id)
        return

    # Selecao de rota para remover
    if data.startswith("sel_remover:"):
        rid   = int(data.split(":")[1])
        rotas = ler_rotas(chat_id)
        nova  = [r for r in rotas if r["id"] != rid]
        salvar_rotas(chat_id, nova)
        editar(chat_id, message_id,
            f"🗑️ *Rota #{rid} removida.*\n\n"
            f"📊 Rotas restantes: *{len(nova)}*\n\n"
            "Use /menu para continuar."
        )
        return


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR COMANDOS DE TEXTO
# ══════════════════════════════════════════════════════════════════════════════

def processar_comando(chat_id: str, cmd: str, reply_to_msg_id: int = None):

    if cmd in ["/start", "/ajuda", "/help", "/menu"]:
        enviar(chat_id,
            "✈️ *K-Finder — rastreador de passagens*\n\n"
            "Escolha uma opção:",
            teclado_menu_principal()
        )
        return

    if cmd == "/adicionar":
        estados[chat_id] = {
            "passo": "origem", "modo": "adicionar",
            "cfg": {}, "msg_id": None, "digitando_preco": False,
        }
        mostrar_passo_origem(chat_id)
        return

    if cmd == "/listar":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id,
                "📭 *Nenhuma rota cadastrada ainda.*\n\nUse /adicionar para começar!",
                [[{"text": "➕ Adicionar rota", "callback_data": "cmd:adicionar"}]]
            )
            return
        msg = f"🗺️ *Suas rotas ativas ({len(rotas)}):*\n\n"
        for r in rotas:
            msg += resumo_rota(r) + "\n\n"
        msg += "━━━━━━━━━━━━━━━━━"
        enviar(chat_id, msg, [
            [
                {"text": "✏️ Editar",  "callback_data": "cmd:editar"},
                {"text": "🗑️ Remover", "callback_data": "cmd:remover"},
            ],
            [{"text": "🔍 Buscar agora", "callback_data": "cmd:buscar_agora"}],
        ])
        return

    if cmd == "/editar":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id, "📭 Nenhuma rota para editar.\nUse /adicionar para começar.")
            return
        enviar(chat_id,
            "✏️ *Qual rota deseja editar?*",
            teclado_menu_rotas(rotas, "sel_editar")
        )
        return

    if cmd == "/remover":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id, "📭 Nenhuma rota para remover.")
            return
        enviar(chat_id,
            "🗑️ *Qual rota deseja remover?*",
            teclado_menu_rotas(rotas, "sel_remover")
        )
        return

    if cmd == "/buscar_agora":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id, "📭 Nenhuma rota cadastrada. Use /adicionar primeiro.")
            return
        enviar(chat_id,
            f"🔍 *Iniciando busca para {len(rotas)} rota(s)...*\n"
            "⏳ Isso pode demorar ~30s por rota."
        )
        try:
            resultado = subprocess.run(
                ["python", "kfinder.py", "--chat-id", chat_id],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                enviar(chat_id, "✅ Busca concluída! Alertas enviados se houver ofertas.")
            else:
                enviar(chat_id, f"❌ Erro na busca:\n`{resultado.stderr[:400]}`")
        except subprocess.TimeoutExpired:
            enviar(chat_id, "❌ Busca demorou demais (>5min). Tente novamente.")
        except Exception as e:
            enviar(chat_id, f"❌ Erro inesperado: {e}")
        return


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR MENSAGENS DE TEXTO (apenas para preco digitado)
# ══════════════════════════════════════════════════════════════════════════════

def processar_texto(chat_id: str, texto: str):
    texto = texto.strip()
    lower = texto.lower()

    # Comandos sempre funcionam
    if texto.startswith("/"):
        processar_comando(chat_id, texto.split()[0])
        return

    # Unico caso de texto livre: digitar preco manualmente
    if chat_id in estados and estados[chat_id].get("digitando_preco"):
        try:
            preco = float(texto.replace("R$", "").replace(".", "").replace(",", ".").strip())
            estados[chat_id]["cfg"]["preco_maximo"] = preco
            estados[chat_id]["passo"] = "confirmar"
            estados[chat_id]["digitando_preco"] = False
            mostrar_confirmacao(chat_id)
        except ValueError:
            enviar(chat_id, "❌ Valor inválido. Digite só o número.\n_ex: 850_")
        return

    # Qualquer outra coisa: mostrar menu
    enviar(chat_id,
        "👋 Use o menu abaixo para navegar:",
        teclado_menu_principal()
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def rodar_bot():
    print("=" * 55)
    print("  K-FINDER BOT v3.0 — aguardando mensagens")
    print("  Envie /menu no Telegram para começar")
    print("  Pressione Ctrl+C para parar")
    print("=" * 55)

    ultimo_update_id = None

    while True:
        try:
            url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": ultimo_update_id}
            r      = requests.get(url, params=params, timeout=35)
            data   = r.json()

            for update in data.get("result", []):
                ultimo_update_id = update["update_id"] + 1

                # Mensagem de texto
                msg = update.get("message", {})
                if msg:
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id not in [str(u) for u in USUARIOS_PERMITIDOS if u]:
                        print(f"⚠️  Ignorado: {chat_id}")
                        continue
                    texto = msg.get("text", "")
                    if texto:
                        print(f"[{chat_id}] {texto}")
                        processar_texto(chat_id, texto)

                # Clique em botao
                cb = update.get("callback_query", {})
                if cb:
                    chat_id    = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                    message_id = cb.get("message", {}).get("message_id")
                    cb_id      = cb.get("id", "")
                    cb_data    = cb.get("data", "")
                    if chat_id not in [str(u) for u in USUARIOS_PERMITIDOS if u]:
                        continue
                    print(f"[{chat_id}] callback: {cb_data}")
                    processar_callback(chat_id, cb_id, cb_data, message_id)

        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    rodar_bot()