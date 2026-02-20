"""
K-FINDER — Bot Telegram v1.1
KenLogic Solutions

Versao sem GPT — usa comandos simples pelo Telegram.
Nao precisa de OpenAI API.

Como rodar:
    python bot.py
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CONFIG_FILE      = "config.json"

CONFIG_PADRAO = {
    "origem":       "LDB",
    "destino":      "BPS",
    "data_ida":     "2026-03-15",
    "data_volta":   "2026-03-22",
    "adultos":      1,
    "preco_minimo": 0,
    "preco_maximo": 600,
}

# Cidades mais comuns para facilitar digitacao
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
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def enviar(texto: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       texto,
            "parse_mode": "Markdown",
        }, timeout=10)
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAMENTO DE COMANDOS
# ══════════════════════════════════════════════════════════════════════════════

# Guarda o estado de cada conversa em andamento
# ex: {"aguardando": "origem", "nova_config": {...}}
estado = {}


def resolver_iata(texto: str) -> str:
    """Converte nome de cidade ou sigla para codigo IATA."""
    texto = texto.strip().lower()
    # Se ja e um codigo IATA de 3 letras, retorna em maiusculo
    if len(texto) == 3 and texto.isalpha():
        return texto.upper()
    # Busca no dicionario de cidades
    for nome, codigo in CIDADES.items():
        if nome in texto:
            return codigo
    return texto.upper()  # devolve o que o usuario digitou em maiusculo


def processar(texto: str):
    global estado
    texto = texto.strip()
    lower = texto.lower()

    # ── /ajuda ──────────────────────────────────────────────────────────────
    if lower in ["/ajuda", "/help", "/start"]:
        enviar(
            "*K-Finder — Comandos disponíveis:*\n\n"
            "/buscar — configurar nova busca (passo a passo)\n"
            "/status — ver configuracao atual\n"
            "/ajuda  — ver esta mensagem\n\n"
            "_O sistema busca automaticamente a cada 6h e te avisa quando encontrar oferta._"
        )
        return

    # ── /status ──────────────────────────────────────────────────────────────
    if lower in ["/status", "/config"]:
        c = ler_config()
        volta = c.get("data_volta") or "so ida"
        enviar(
            f"*Configuracao atual:*\n\n"
            f"Rota: *{c['origem']} -> {c['destino']}*\n"
            f"Ida: {c['data_ida']}\n"
            f"Volta: {volta}\n"
            f"Adultos: {c['adultos']}\n"
            f"Preco maximo: R$ {c['preco_maximo']}"
        )
        return

    # ── /buscar — inicia o fluxo passo a passo ───────────────────────────────
    if lower == "/buscar":
        estado = {"aguardando": "origem", "nova_config": {}}
        enviar(
            "*Nova busca — Passo 1 de 5*\n\n"
            "Qual a *cidade de origem*?\n\n"
            "Pode digitar o nome ou a sigla IATA:\n"
            "ex: _Londrina_ ou _LDB_"
        )
        return

    # ── Fluxo passo a passo ──────────────────────────────────────────────────
    if "aguardando" in estado:
        etapa = estado["aguardando"]
        cfg   = estado["nova_config"]

        if etapa == "origem":
            cfg["origem"] = resolver_iata(texto)
            estado["aguardando"] = "destino"
            enviar(
                f"Origem: *{cfg['origem']}*\n\n"
                "*Passo 2 de 5* — Qual o *destino*?\n"
                "ex: _Sao Paulo_, _GRU_, _Salvador_"
            )

        elif etapa == "destino":
            cfg["destino"] = resolver_iata(texto)
            estado["aguardando"] = "data_ida"
            enviar(
                f"Destino: *{cfg['destino']}*\n\n"
                "*Passo 3 de 5* — Qual a *data de ida*?\n"
                "Formato: DD/MM/AAAA\n"
                "ex: _15/05/2026_"
            )

        elif etapa == "data_ida":
            try:
                dt = datetime.strptime(texto.strip(), "%d/%m/%Y")
                cfg["data_ida"] = dt.strftime("%Y-%m-%d")
                estado["aguardando"] = "data_volta"
                enviar(
                    f"Ida: *{texto.strip()}*\n\n"
                    "*Passo 4 de 5* — Qual a *data de volta*?\n"
                    "Formato: DD/MM/AAAA\n"
                    "Se for so ida, mande: _nao_"
                )
            except ValueError:
                enviar("❌ Data invalida. Use o formato DD/MM/AAAA\nex: _15/05/2026_")

        elif etapa == "data_volta":
            if lower in ["nao", "não", "so ida", "só ida", "0", "-"]:
                cfg["data_volta"] = ""
            else:
                try:
                    dt = datetime.strptime(texto.strip(), "%d/%m/%Y")
                    cfg["data_volta"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    enviar("❌ Data invalida. Use DD/MM/AAAA ou mande _nao_ para so ida.")
                    return

            estado["aguardando"] = "preco"
            enviar(
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
                estado = {}

                volta = cfg.get("data_volta") or "so ida"
                enviar(
                    f"Configuracao salva!\n\n"
                    f"Rota: *{cfg['origem']} -> {cfg['destino']}*\n"
                    f"Ida: {cfg['data_ida']}\n"
                    f"Volta: {volta}\n"
                    f"Preco maximo: R$ {cfg['preco_maximo']:.0f}\n\n"
                    f"O K-Finder vai buscar automaticamente a cada 6h e te avisar quando encontrar oferta dentro desse criterio."
                )
            except ValueError:
                enviar("❌ Preco invalido. Digite apenas o numero.\nex: _600_")

        return

    # ── Mensagem nao reconhecida ──────────────────────────────────────────────
    enviar(
        "Nao entendi. Use um dos comandos:\n\n"
        "/buscar — configurar nova busca\n"
        "/status — ver configuracao atual\n"
        "/ajuda  — ajuda"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def rodar_bot():
    print("=" * 55)
    print("  K-FINDER BOT v1.1 — aguardando mensagens")
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
                if chat_id != str(TELEGRAM_CHAT_ID):
                    print(f"Mensagem ignorada de chat desconhecido: {chat_id}")
                    continue

                texto = msg.get("text", "")
                if texto:
                    print(f"Recebido: {texto}")
                    processar(texto)

        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    rodar_bot()
