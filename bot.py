"""
K-FINDER — Bot Telegram v1.2
KenLogic Solutions

Melhorias:
- Responde para cada usuario no chat certo
- Comando /buscar_agora para buscar na hora
- Lista de usuarios permitidos facil de editar
"""

import os
import json
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CONFIG_FILE      = "config.json"

# ══════════════════════════════════════════════════════════════════════════════
#  USUARIOS PERMITIDOS
#  Para adicionar alguem novo:
#  1. Peca para a pessoa mandar qualquer msg pro bot (ex: /start)
#  2. O terminal mostra: "Mensagem ignorada de chat desconhecido: 123456789"
#  3. Copie esse numero e adicione na lista abaixo (remova o # da frente)
# ══════════════════════════════════════════════════════════════════════════════

USUARIOS_PERMITIDOS = [
    os.getenv("TELEGRAM_CHAT_ID"),   # voce (dono do bot)
    # "123456789",                   # padrasto
    # "987654321",                   # outro usuario
]

CONFIG_PADRAO = {
    "origem":       "LDB",
    "destino":      "BPS",
    "data_ida":     "2026-03-15",
    "data_volta":   "2026-03-22",
    "adultos":      1,
    "preco_minimo": 0,
    "preco_maximo": 600,
}

CIDADES = {
    "londrina": "LDB", "sao paulo": "GRU", "guarulhos": "GRU",
    "congonhas": "CGH", "rio de janeiro": "GIG", "rio": "GIG",
    "curitiba": "CWB", "florianopolis": "FLN", "porto alegre": "POA",
    "belo horizonte": "CNF", "salvador": "SSA", "recife": "REC",
    "fortaleza": "FOR", "manaus": "MAO", "belem": "BEL",
    "brasilia": "BSB", "porto seguro": "BPS", "foz do iguacu": "IGU",
    "natal": "NAT", "maceio": "MCZ", "campo grande": "CGR",
    "campinas": "VCP", "vitoria": "VIX", "aracaju": "AJU",
    "joao pessoa": "JPA", "teresina": "THE", "sao luis": "SLZ",
    "cuiaba": "CGB", "porto velho": "PVH", "macapa": "MCP",
    "boa vista": "BVB", "palmas": "PMW", "goiania": "GYN",
}


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def ler_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return CONFIG_PADRAO.copy()


def salvar_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM — envia para o chat de quem mandou a mensagem
# ══════════════════════════════════════════════════════════════════════════════

def enviar(chat_id: str, texto: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id":    chat_id,
            "text":       texto,
            "parse_mode": "Markdown",
        }, timeout=10)
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO DE CADA USUARIO (cada um tem seu proprio fluxo)
# ══════════════════════════════════════════════════════════════════════════════

estados = {}  # { "chat_id": {"aguardando": "origem", "nova_config": {...}} }


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAMENTO DE COMANDOS
# ══════════════════════════════════════════════════════════════════════════════

def resolver_iata(texto: str) -> str:
    texto = texto.strip().lower()
    if len(texto) == 3 and texto.isalpha():
        return texto.upper()
    for nome, codigo in CIDADES.items():
        if nome in texto:
            return codigo
    return texto.upper()


def processar(chat_id: str, texto: str):
    texto = texto.strip()
    lower = texto.lower()

    # ── /ajuda ────────────────────────────────────────────────────────────────
    if lower in ["/ajuda", "/help", "/start"]:
        enviar(chat_id,
            "*K-Finder — Comandos:*\n\n"
            "/buscar       — configurar nova busca\n"
            "/buscar\\_agora — buscar passagens agora mesmo\n"
            "/status       — ver configuracao atual\n"
            "/ajuda        — ver esta mensagem\n\n"
            "_O sistema tambem busca automaticamente a cada 6h._"
        )
        return

    # ── /status ───────────────────────────────────────────────────────────────
    if lower in ["/status", "/config"]:
        c = ler_config()
        volta = c.get("data_volta") or "so ida"
        enviar(chat_id,
            f"*Configuracao atual:*\n\n"
            f"Rota: *{c['origem']} -> {c['destino']}*\n"
            f"Ida: {c['data_ida']}\n"
            f"Volta: {volta}\n"
            f"Adultos: {c['adultos']}\n"
            f"Preco maximo: R$ {c['preco_maximo']}"
        )
        return

    # ── /buscar_agora — roda o kfinder.py imediatamente ──────────────────────
    if lower == "/buscar_agora":
        c = ler_config()
        enviar(chat_id,
            f"Iniciando busca agora...\n"
            f"Rota: *{c['origem']} -> {c['destino']}* | {c['data_ida']}\n"
            f"Isso pode demorar ~30 segundos."
        )
        try:
            resultado = subprocess.run(
                ["python", "kfinder.py"],
                capture_output=True, text=True, timeout=120
            )
            if resultado.returncode == 0:
                enviar(chat_id, "Busca concluida! Verifique as notificacoes acima.")
            else:
                enviar(chat_id, f"❌ Erro na busca:\n{resultado.stderr[:500]}")
        except subprocess.TimeoutExpired:
            enviar(chat_id, "❌ A busca demorou demais. Tente novamente.")
        except Exception as e:
            enviar(chat_id, f"❌ Erro: {e}")
        return

    # ── /buscar — inicia fluxo passo a passo ─────────────────────────────────
    if lower == "/buscar":
        estados[chat_id] = {"aguardando": "origem", "nova_config": {}}
        enviar(chat_id,
            "*Nova busca — Passo 1 de 5*\n\n"
            "Qual a *cidade de origem*?\n\n"
            "Pode digitar o nome ou a sigla IATA:\n"
            "ex: _Londrina_ ou _LDB_"
        )
        return

    # ── Fluxo passo a passo ───────────────────────────────────────────────────
    if chat_id in estados:
        etapa = estados[chat_id]["aguardando"]
        cfg   = estados[chat_id]["nova_config"]

        if etapa == "origem":
            cfg["origem"] = resolver_iata(texto)
            estados[chat_id]["aguardando"] = "destino"
            enviar(chat_id,
                f"Origem: *{cfg['origem']}*\n\n"
                "*Passo 2 de 5* — Qual o *destino*?\n"
                "ex: _Sao Paulo_, _GRU_, _Salvador_"
            )

        elif etapa == "destino":
            cfg["destino"] = resolver_iata(texto)
            estados[chat_id]["aguardando"] = "data_ida"
            enviar(chat_id,
                f"Destino: *{cfg['destino']}*\n\n"
                "*Passo 3 de 5* — Qual a *data de ida*?\n"
                "Formato: DD/MM/AAAA\n"
                "ex: _15/05/2026_"
            )

        elif etapa == "data_ida":
            try:
                dt = datetime.strptime(texto.strip(), "%d/%m/%Y")
                cfg["data_ida"] = dt.strftime("%Y-%m-%d")
                estados[chat_id]["aguardando"] = "data_volta"
                enviar(chat_id,
                    f"Ida: *{texto.strip()}*\n\n"
                    "*Passo 4 de 5* — Qual a *data de volta*?\n"
                    "Formato: DD/MM/AAAA\n"
                    "Se for so ida, mande: _nao_"
                )
            except ValueError:
                enviar(chat_id, "❌ Data invalida. Use DD/MM/AAAA\nex: _15/05/2026_")

        elif etapa == "data_volta":
            if lower in ["nao", "não", "so ida", "só ida", "0", "-"]:
                cfg["data_volta"] = ""
            else:
                try:
                    dt = datetime.strptime(texto.strip(), "%d/%m/%Y")
                    cfg["data_volta"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    enviar(chat_id, "❌ Data invalida. Use DD/MM/AAAA ou _nao_ para so ida.")
                    return

            estados[chat_id]["aguardando"] = "preco"
            enviar(chat_id,
                f"Volta: *{cfg.get('data_volta') or 'so ida'}*\n\n"
                "*Passo 5 de 5* — Qual o *preco maximo* em reais?\n"
                "ex: _600_ ou _1500_"
            )

        elif etapa == "preco":
            try:
                preco = float(texto.replace("R$", "").replace(".", "").replace(",", ".").strip())
                cfg["preco_maximo"] = preco
                cfg["preco_minimo"] = 0
                cfg["adultos"]      = cfg.get("adultos", 1)

                salvar_config(cfg)
                del estados[chat_id]

                volta = cfg.get("data_volta") or "so ida"
                enviar(chat_id,
                    f"Configuracao salva!\n\n"
                    f"Rota: *{cfg['origem']} -> {cfg['destino']}*\n"
                    f"Ida: {cfg['data_ida']}\n"
                    f"Volta: {volta}\n"
                    f"Preco maximo: R$ {cfg['preco_maximo']:.0f}\n\n"
                    f"Use /buscar\\_agora para buscar imediatamente\n"
                    f"ou aguarde a busca automatica a cada 6h."
                )
            except ValueError:
                enviar(chat_id, "❌ Preco invalido. Digite apenas o numero.\nex: _600_")

        return

    # ── Mensagem nao reconhecida ──────────────────────────────────────────────
    enviar(chat_id,
        "Nao entendi. Use:\n\n"
        "/buscar       — nova busca\n"
        "/buscar\\_agora — buscar agora\n"
        "/status       — configuracao atual\n"
        "/ajuda        — ajuda"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def rodar_bot():
    print("=" * 55)
    print("  K-FINDER BOT v1.2 — aguardando mensagens")
    print("  Envie /ajuda no Telegram para comecar")
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

                msg = update.get("message", {})
                if not msg:
                    continue

                chat_id = str(msg.get("chat", {}).get("id", ""))

                if chat_id not in [str(u) for u in USUARIOS_PERMITIDOS if u]:
                    print(f"Mensagem ignorada de chat desconhecido: {chat_id}")
                    continue

                texto = msg.get("text", "")
                if texto:
                    print(f"[{chat_id}] Recebido: {texto}")
                    processar(chat_id, texto)

        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    rodar_bot()
