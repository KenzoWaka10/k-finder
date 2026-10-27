"""
K-FINDER — Bot Telegram v3.1
KenLogic Solutions

Novidades v3.1:
- Sistema de aprovacao de usuarios pelo admin
- Admin recebe notificacao quando alguem tenta usar o bot
- Aprovar/recusar com botoes
- Painel /admin para gerenciar usuarios
- Alertas vao para o chat correto de cada usuario
"""

import os
import json
import subprocess
import requests
import calendar
import re
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # admin (voce)
CONFIG_FILE      = "config.json"
ANSI             = re.compile(r"\x1b\[[0-9;]*m")  # remove cores do log

PRECOS_SUGERIDOS = [300, 500, 700, 900, 1200, 1500, 2000, 2500]
CIDADES_POR_PAG  = 8

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


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG — usuarios + rotas
#
#  Estrutura do config.json:
#  {
#    "usuarios_aprovados": {
#      "123456789": { "nome": "Padrasto", "aprovado_em": "..." },
#    },
#    "usuarios_pendentes": {
#      "987654321": { "nome": "Fulano", "pediu_em": "..." }
#    },
#    "usuarios": {
#      "123456789": { "rotas": [...] }
#    }
#  }
# ══════════════════════════════════════════════════════════════════════════════

def ler_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Migra formato antigo
            if "rotas" in data and "usuarios" not in data:
                chat_id_dono = str(TELEGRAM_CHAT_ID or "admin")
                return {
                    "usuarios_aprovados": {chat_id_dono: {"nome": "Admin"}},
                    "usuarios_pendentes": {},
                    "usuarios": {chat_id_dono: {"rotas": data["rotas"]}},
                }
            # Garante campos existem
            if "usuarios_aprovados" not in data:
                data["usuarios_aprovados"] = {}
            if "usuarios_pendentes" not in data:
                data["usuarios_pendentes"] = {}
            if "usuarios" not in data:
                data["usuarios"] = {}
            return data
    # Config novo vazio — admin ja aprovado automaticamente
    admin_id = str(TELEGRAM_CHAT_ID or "")
    return {
        "usuarios_aprovados": {admin_id: {"nome": "Admin", "aprovado_em": "inicio"}},
        "usuarios_pendentes": {},
        "usuarios": {},
    }

def salvar_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def is_admin(chat_id: str) -> bool:
    return str(chat_id) == str(TELEGRAM_CHAT_ID)

def is_aprovado(chat_id: str) -> bool:
    if is_admin(chat_id):
        return True
    config = ler_config()
    return str(chat_id) in config.get("usuarios_aprovados", {})

def is_pendente(chat_id: str) -> bool:
    config = ler_config()
    return str(chat_id) in config.get("usuarios_pendentes", {})

def aprovar_usuario(chat_id: str, nome: str):
    config = ler_config()
    config["usuarios_aprovados"][str(chat_id)] = {
        "nome": nome,
        "aprovado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    config["usuarios_pendentes"].pop(str(chat_id), None)
    salvar_config(config)

def recusar_usuario(chat_id: str):
    config = ler_config()
    config["usuarios_pendentes"].pop(str(chat_id), None)
    salvar_config(config)

def remover_usuario(chat_id: str):
    config = ler_config()
    config["usuarios_aprovados"].pop(str(chat_id), None)
    config["usuarios"].pop(str(chat_id), None)
    salvar_config(config)

def adicionar_pendente(chat_id: str, nome: str):
    config = ler_config()
    config["usuarios_pendentes"][str(chat_id)] = {
        "nome": nome,
        "pediu_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    salvar_config(config)

def ler_rotas(chat_id: str) -> list:
    config = ler_config()
    return config.get("usuarios", {}).get(str(chat_id), {}).get("rotas", [])

def salvar_rotas(chat_id: str, rotas: list):
    config = ler_config()
    if str(chat_id) not in config["usuarios"]:
        config["usuarios"][str(chat_id)] = {}
    config["usuarios"][str(chat_id)]["rotas"] = rotas
    salvar_config(config)

def proximo_id(rotas: list) -> int:
    return max((r.get("id", 0) for r in rotas), default=0) + 1


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM
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
    payload["reply_markup"] = {"inline_keyboard": teclado or []}
    return _post("editMessageText", payload)

def responder_callback(callback_id: str, texto: str = ""):
    _post("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto})


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO POR USUARIO
# ══════════════════════════════════════════════════════════════════════════════

estados = {}


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
    linhas = []
    for i in range(0, len(bloco), 2):
        linha = []
        for nome, cod in bloco[i:i+2]:
            linha.append({"text": nome, "callback_data": f"{prefixo}:{cod}"})
        linhas.append(linha)
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
    linhas = []
    nome_mes = ["","Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"][mes]
    linhas.append([
        {"text": "◀️", "callback_data": f"{prefixo}_mes:{ano}:{mes-1 if mes>1 else 12}:{ano if mes>1 else ano-1}"},
        {"text": f"  {nome_mes} {ano}  ", "callback_data": "ignore"},
        {"text": "▶️", "callback_data": f"{prefixo}_mes:{ano}:{mes+1 if mes<12 else 1}:{ano if mes<12 else ano+1}"},
    ])
    linhas.append([
        {"text": d, "callback_data": "ignore"}
        for d in ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]
    ])
    primeiro_dia, total_dias = calendar.monthrange(ano, mes)
    primeiro_dia = (primeiro_dia + 1) % 7
    hoje  = date.today()
    semana = ["  "] * primeiro_dia
    for dia in range(1, total_dias + 1):
        d = date(ano, mes, dia)
        if d < hoje:
            semana.append({"text": "·", "callback_data": "ignore"})
        else:
            semana.append({"text": str(dia), "callback_data": f"{prefixo}:{ano}-{mes:02d}-{dia:02d}"})
        if len(semana) == 7:
            linhas.append([b for b in semana if b != "  "])
            semana = []
    if semana:
        linhas.append([b for b in semana if b != "  "])
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

def teclado_menu_rotas(rotas: list, acao: str) -> list:
    linhas = []
    for r in rotas:
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

def teclado_aprovacao(chat_id: str, nome: str) -> list:
    return [[
        {"text": "✅ Aprovar",  "callback_data": f"aprovar:{chat_id}:{nome}"},
        {"text": "❌ Recusar", "callback_data": f"recusar:{chat_id}"},
    ]]

def teclado_admin_usuarios(usuarios: dict) -> list:
    linhas = []
    for uid, info in usuarios.items():
        nome = info.get("nome", uid)
        linhas.append([{
            "text": f"🗑️ Remover {nome}",
            "callback_data": f"admin_remover:{uid}"
        }])
    linhas.append([{"text": "✅ Fechar", "callback_data": "cancelar"}])
    return linhas


# ══════════════════════════════════════════════════════════════════════════════
#  FLUXO DE ADICIONAR / EDITAR
# ══════════════════════════════════════════════════════════════════════════════

def mostrar_passo_origem(chat_id: str, msg_id: int = None):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    texto  = f"{titulo}\n\n*Passo 1/5 — Cidade de origem:*\n_Selecione uma cidade:_"
    if cfg.get("origem"):
        texto = f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo 1/5 — Cidade de origem:*\n_Selecione uma cidade:_"
    teclado = teclado_cidades(0, "cidade_orig")
    if msg_id:
        editar(chat_id, msg_id, texto, teclado)
    else:
        r = enviar(chat_id, texto, teclado)
        estado["msg_id"] = r.get("result", {}).get("message_id")

def mostrar_passo_destino(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    editar(chat_id, estado["msg_id"],
        f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo 2/5 — Cidade de destino:*\n_Selecione uma cidade:_",
        teclado_cidades(0, "cidade_dest")
    )

def mostrar_passo_data_ida(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    hoje   = date.today()
    editar(chat_id, estado["msg_id"],
        f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo 3/5 — Data de ida:*\n_Selecione no calendário:_",
        teclado_calendario(hoje.year, hoje.month, "data_ida")
    )

def mostrar_passo_data_volta(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    if cfg.get("data_ida"):
        dt   = datetime.strptime(cfg["data_ida"], "%Y-%m-%d")
        ano, mes = dt.year, dt.month
    else:
        hoje = date.today()
        ano, mes = hoje.year, hoje.month
    cal = teclado_calendario(ano, mes, "data_volta")
    cal.insert(0, [{"text": "✈️ Só ida (sem volta)", "callback_data": "data_volta:nao"}])
    editar(chat_id, estado["msg_id"],
        f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo 4/5 — Data de volta:*\n_Selecione ou escolha só ida:_",
        cal
    )

def mostrar_passo_preco(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
    editar(chat_id, estado["msg_id"],
        f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo 5/5 — Preço máximo:*\n_Selecione ou digite um valor:_",
        teclado_preco()
    )

def mostrar_confirmacao(chat_id: str):
    estado = estados[chat_id]
    cfg    = estado["cfg"]
    modo   = estado["modo"]
    titulo = "✏️ Confirmar edição" if modo == "editar" else "✅ Confirmar nova rota"
    editar(chat_id, estado["msg_id"],
        f"*{titulo}*\n\n{resumo_cfg(cfg)}\n\n_Tudo certo?_",
        teclado_confirmar()
    )

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
            f"✅ *Rota #{rid} atualizada!*\n\n{resumo_cfg(cfg)}\n\nUse /menu para continuar."
        )
    else:
        cfg["id"] = proximo_id(rotas)
        rotas.append(cfg)
        salvar_rotas(chat_id, rotas)
        del estados[chat_id]
        editar(chat_id, msg_id,
            f"✅ *Rota #{cfg['id']} adicionada!*\n\n{resumo_cfg(cfg)}\n\n"
            f"📊 Total de rotas ativas: *{len(rotas)}*\n\nUse /menu para continuar."
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PAINEL ADMIN
# ══════════════════════════════════════════════════════════════════════════════

def mostrar_painel_admin(chat_id: str):
    config    = ler_config()
    aprovados = config.get("usuarios_aprovados", {})
    pendentes = config.get("usuarios_pendentes", {})

    # Remove o proprio admin da lista de gerenciamento
    outros = {k: v for k, v in aprovados.items() if k != str(TELEGRAM_CHAT_ID)}

    msg = "👑 *Painel Admin — K-Finder*\n\n"

    if pendentes:
        msg += f"⏳ *Pendentes ({len(pendentes)}):*\n"
        for uid, info in pendentes.items():
            msg += f"  • {info.get('nome', 'Desconhecido')} (`{uid}`) — {info.get('pediu_em','')}\n"
        msg += "\n"

    if outros:
        msg += f"✅ *Aprovados ({len(outros)}):*\n"
        for uid, info in outros.items():
            rotas = ler_rotas(uid)
            msg += f"  • {info.get('nome', 'Desconhecido')} (`{uid}`) — {len(rotas)} rota(s)\n"
        msg += "\n"
        enviar(chat_id, msg, teclado_admin_usuarios(outros))
    else:
        msg += "_Nenhum usuário aprovado além de você._"
        enviar(chat_id, msg)


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def processar_callback(chat_id: str, callback_id: str, data: str, message_id: int):
    responder_callback(callback_id)

    if data == "ignore":
        return

    # Cancelar
    if data == "cancelar":
        if chat_id in estados:
            msg_id = estados[chat_id].get("msg_id", message_id)
            del estados[chat_id]
            editar(chat_id, msg_id, "❌ *Operação cancelada.*\n\nUse /menu para voltar.")
        else:
            editar(chat_id, message_id, "✅ Fechado.")
        return

    # Confirmar salvar rota
    if data == "confirmar":
        if chat_id in estados:
            salvar_rota_atual(chat_id)
        return

    # Comandos do menu
    if data.startswith("cmd:"):
        processar_comando(chat_id, f"/{data.split(':')[1]}", message_id)
        return

    # ── APROVACAO DE USUARIOS ──

    if data.startswith("aprovar:"):
        partes   = data.split(":", 2)
        uid      = partes[1]
        nome     = partes[2] if len(partes) > 2 else "Usuário"
        aprovar_usuario(uid, nome)
        editar(chat_id, message_id,
            f"✅ *{nome} aprovado!*\n\nEle já pode usar o bot."
        )
        # Avisa o usuario aprovado
        enviar(uid,
            "✅ *Acesso aprovado!*\n\n"
            "Você já pode usar o K-Finder.\n"
            "Digite /menu para começar!",
            teclado_menu_principal()
        )
        return

    if data.startswith("recusar:"):
        uid = data.split(":")[1]
        config = ler_config()
        nome   = config.get("usuarios_pendentes", {}).get(uid, {}).get("nome", "Usuário")
        recusar_usuario(uid)
        editar(chat_id, message_id, f"❌ *{nome} recusado.*")
        enviar(uid, "❌ Seu acesso ao K-Finder foi recusado.")
        return

    if data.startswith("admin_remover:"):
        uid    = data.split(":")[1]
        config = ler_config()
        nome   = config.get("usuarios_aprovados", {}).get(uid, {}).get("nome", uid)
        remover_usuario(uid)
        editar(chat_id, message_id,
            f"🗑️ *{nome} removido.*\n\nEle não pode mais usar o bot."
        )
        enviar(uid, "⚠️ Seu acesso ao K-Finder foi removido.")
        return

    # ── VOLTAR PASSO ──

    if data.startswith("voltar:"):
        passo = data.split(":")[1]
        if chat_id not in estados:
            return
        estados[chat_id]["digitando_preco"] = False
        if passo in ["data_volta", "preco"]:
            mostrar_passo_data_ida(chat_id)
        elif passo in ["confirmar"]:
            mostrar_passo_preco(chat_id)
        elif passo == "destino":
            mostrar_passo_origem(chat_id, estados[chat_id]["msg_id"])
        elif passo == "data_ida":
            mostrar_passo_destino(chat_id)
        else:
            mostrar_passo_data_volta(chat_id)
        return

    # ── PAGINACAO CIDADES ──

    if "_pag:" in data:
        prefixo, resto = data.rsplit("_pag:", 1)
        pagina = int(resto)
        if chat_id not in estados:
            return
        editar(chat_id, estados[chat_id]["msg_id"],
            "Selecione uma cidade:",
            teclado_cidades(pagina, prefixo)
        )
        return

    # ── SELECAO CIDADE ──

    if data.startswith("cidade_orig:"):
        if chat_id not in estados: return
        estados[chat_id]["cfg"]["origem"] = data.split(":")[1]
        mostrar_passo_destino(chat_id)
        return

    if data.startswith("cidade_dest:"):
        if chat_id not in estados: return
        estados[chat_id]["cfg"]["destino"] = data.split(":")[1]
        mostrar_passo_data_ida(chat_id)
        return

    # ── NAVEGACAO CALENDARIO ──

    if "_mes:" in data:
        if chat_id not in estados: return
        partes      = data.split(":")
        prefixo_cal = partes[0].replace("_mes", "")
        mes         = int(partes[2])
        ano         = int(partes[3]) if len(partes) > 3 else int(partes[1])
        if mes == 0:   mes = 12; ano -= 1
        elif mes == 13: mes = 1;  ano += 1
        cfg    = estados[chat_id]["cfg"]
        modo   = estados[chat_id]["modo"]
        titulo = "✏️ Editando rota" if modo == "editar" else "➕ Nova rota"
        label  = "3/5 — Data de ida" if "ida" in prefixo_cal else "4/5 — Data de volta"
        cal    = teclado_calendario(ano, mes, prefixo_cal)
        if "volta" in prefixo_cal:
            cal.insert(0, [{"text": "✈️ Só ida (sem volta)", "callback_data": "data_volta:nao"}])
        editar(chat_id, estados[chat_id]["msg_id"],
            f"{titulo}\n\n{resumo_cfg(cfg)}\n\n*Passo {label}:*\n_Selecione no calendário:_",
            cal
        )
        return

    # ── SELECAO DATAS ──

    if data.startswith("data_ida:"):
        if chat_id not in estados: return
        estados[chat_id]["cfg"]["data_ida"] = data.split(":", 1)[1]
        mostrar_passo_data_volta(chat_id)
        return

    if data.startswith("data_volta:"):
        if chat_id not in estados: return
        val = data.split(":", 1)[1]
        estados[chat_id]["cfg"]["data_volta"] = "" if val == "nao" else val
        mostrar_passo_preco(chat_id)
        return

    # ── SELECAO PRECO ──

    if data.startswith("preco:"):
        if chat_id not in estados: return
        val = data.split(":", 1)[1]
        if val == "digitar":
            estados[chat_id]["digitando_preco"] = True
            editar(chat_id, estados[chat_id]["msg_id"],
                "💰 *Digite o preço máximo em reais:*\n_ex: 850_",
                [[{"text": "❌ Cancelar", "callback_data": "cancelar"}]]
            )
        else:
            estados[chat_id]["cfg"]["preco_maximo"] = float(val)
            estados[chat_id]["digitando_preco"]     = False
            mostrar_confirmacao(chat_id)
        return

    # ── EDITAR / REMOVER ROTA ──

    if data.startswith("sel_editar:"):
        rid   = int(data.split(":")[1])
        rotas = ler_rotas(chat_id)
        rota  = next((r for r in rotas if r["id"] == rid), None)
        if not rota:
            editar(chat_id, message_id, "❌ Rota não encontrada.")
            return
        estados[chat_id] = {
            "passo": "origem", "modo": "editar", "editando_id": rid,
            "cfg": {k: v for k, v in rota.items() if k != "id"},
            "msg_id": message_id, "digitando_preco": False,
        }
        mostrar_passo_origem(chat_id, message_id)
        return

    if data.startswith("sel_remover:"):
        rid   = int(data.split(":")[1])
        rotas = ler_rotas(chat_id)
        nova  = [r for r in rotas if r["id"] != rid]
        salvar_rotas(chat_id, nova)
        editar(chat_id, message_id,
            f"🗑️ *Rota #{rid} removida.*\n\n📊 Rotas restantes: *{len(nova)}*"
        )
        return


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR COMANDOS
# ══════════════════════════════════════════════════════════════════════════════

def processar_comando(chat_id: str, cmd: str, reply_msg_id: int = None):

    if cmd in ["/start", "/ajuda", "/help", "/menu"]:
        enviar(chat_id,
            "✈️ *K-Finder — rastreador de passagens*\n\nEscolha uma opção:",
            teclado_menu_principal()
        )
        return

    if cmd == "/admin":
        if not is_admin(chat_id):
            enviar(chat_id, "❌ Acesso negado.")
            return
        mostrar_painel_admin(chat_id)
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
            enviar(chat_id, "📭 Nenhuma rota para editar.")
            return
        enviar(chat_id, "✏️ *Qual rota deseja editar?*", teclado_menu_rotas(rotas, "sel_editar"))
        return

    if cmd == "/remover":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id, "📭 Nenhuma rota para remover.")
            return
        enviar(chat_id, "🗑️ *Qual rota deseja remover?*", teclado_menu_rotas(rotas, "sel_remover"))
        return

    if cmd == "/buscar_agora":
        rotas = ler_rotas(chat_id)
        if not rotas:
            enviar(chat_id, "📭 Nenhuma rota cadastrada. Use /adicionar primeiro.")
            return
        enviar(chat_id,
            f"🔍 *Iniciando busca para {len(rotas)} rota(s)...*\n⏳ Isso pode demorar ~30s por rota."
        )
        try:
            resultado = subprocess.run(
                ["python", "kfinder.py", "--chat-id", chat_id],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                enviar(chat_id, "✅ Busca concluída! Alertas enviados se houver ofertas.")
            else:
                saida = ANSI.sub("", resultado.stderr or resultado.stdout or "")
                enviar(chat_id, f"❌ Erro na busca:\n`{saida[-600:]}`")
        except subprocess.TimeoutExpired:
            enviar(chat_id, "❌ Busca demorou demais. Tente novamente.")
        except Exception as e:
            enviar(chat_id, f"❌ Erro: {e}")
        return


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAR TEXTO
# ══════════════════════════════════════════════════════════════════════════════

def processar_texto(chat_id: str, texto: str, nome_usuario: str):
    texto = texto.strip()

    # Comandos
    if texto.startswith("/"):
        cmd = texto.split()[0].lower()

        # /start sempre funciona (para pedir acesso)
        if cmd == "/start":
            if is_aprovado(chat_id):
                processar_comando(chat_id, "/menu")
            elif is_pendente(chat_id):
                enviar(chat_id,
                    "⏳ *Seu acesso ainda está pendente.*\n\n"
                    "Aguarde a aprovação do administrador."
                )
            else:
                # Pede acesso
                adicionar_pendente(chat_id, nome_usuario)
                enviar(chat_id,
                    "👋 Olá! Seu acesso ao *K-Finder* está sendo solicitado.\n\n"
                    "⏳ Aguarde a aprovação do administrador."
                )
                # Notifica o admin
                enviar(str(TELEGRAM_CHAT_ID),
                    f"🔔 *Nova solicitação de acesso!*\n\n"
                    f"👤 Nome: *{nome_usuario}*\n"
                    f"🆔 Chat ID: `{chat_id}`",
                    teclado_aprovacao(chat_id, nome_usuario)
                )
            return

        # Demais comandos so para aprovados
        if not is_aprovado(chat_id):
            enviar(chat_id,
                "⚠️ Você não tem acesso ao K-Finder.\n"
                "Digite /start para solicitar acesso."
            )
            return

        processar_comando(chat_id, cmd)
        return

    # Nao aprovado tentando mandar texto
    if not is_aprovado(chat_id):
        enviar(chat_id,
            "⚠️ Você não tem acesso ao K-Finder.\n"
            "Digite /start para solicitar acesso."
        )
        return

    # Preco digitado manualmente
    if chat_id in estados and estados[chat_id].get("digitando_preco"):
        try:
            preco = float(texto.replace("R$","").replace(".","").replace(",",".").strip())
            estados[chat_id]["cfg"]["preco_maximo"] = preco
            estados[chat_id]["digitando_preco"]     = False
            mostrar_confirmacao(chat_id)
        except ValueError:
            enviar(chat_id, "❌ Valor inválido. Digite só o número.\n_ex: 850_")
        return

    # Qualquer outra coisa
    enviar(chat_id, "👋 Use o menu abaixo:", teclado_menu_principal())


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def rodar_bot():
    print("=" * 55)
    print("  K-FINDER BOT v3.1 — aguardando mensagens")
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
                    texto   = msg.get("text", "")
                    nome    = msg.get("from", {}).get("first_name", "Usuário")
                    if texto:
                        print(f"[{chat_id}] {nome}: {texto}")
                        processar_texto(chat_id, texto, nome)

                # Clique em botao
                cb = update.get("callback_query", {})
                if cb:
                    chat_id    = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                    message_id = cb.get("message", {}).get("message_id")
                    cb_id      = cb.get("id", "")
                    cb_data    = cb.get("data", "")
                    print(f"[{chat_id}] callback: {cb_data}")
                    processar_callback(chat_id, cb_id, cb_data, message_id)

        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    rodar_bot()