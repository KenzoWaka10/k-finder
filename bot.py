"""
K-FINDER — Bot Telegram v1.3
KenLogic Solutions

- Responde para cada usuario no chat certo
- /buscar_agora busca e responde para quem pediu
- Multiplas rotas (adicionar/remover/listar)
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
#  1. Peca para a pessoa mandar /start pro bot
#  2. Terminal mostra: "Mensagem ignorada de chat desconhecido: 123456789"
#  3. Copie o numero e adicione abaixo (remova o #)
# ══════════════════════════════════════════════════════════════════════════════

USUARIOS_PERMITIDOS = [
    os.getenv("TELEGRAM_CHAT_ID"),   # voce (dono)
    # "123456789",                   # padrasto
    # "987654321",                   # outro usuario
]

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
#  CONFIG — lista de rotas
# ══════════════════════════════════════════════════════════════════════════════

def ler_rotas() -> list:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "rotas" in data:
                return data["rotas"]
            return [data]
    return []

def salvar_rotas(rotas: list):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"rotas": rotas}, f, ensure_ascii=False, indent=2)

def proximo_id(rotas: list) -> int:
    if not rotas:
        return 1
    return max(r.get("id", 0) for r in rotas) + 1


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM — envia para o chat de quem pediu
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
        print(f"❌ Erro Telegram: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO POR USUARIO
# ══════════════════════════════════════════════════════════════════════════════

estados = {}  # { chat_id: { "aguardando": "...", "nova_config": {...} } }


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSAMENTO
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

    # /ajuda
    if lower in ["/ajuda", "/help", "/start"]:
        enviar(chat_id,
            "*K-Finder — Comandos:*\n\n"
            "/adicionar     — adicionar nova rota\n"
            "/listar        — ver todas as rotas ativas\n"
            "/remover       — remover uma rota\n"
            "/buscar\\_agora — buscar passagens agora\n"
            "/ajuda         — esta mensagem\n\n"
            "_Busca automatica a cada 6h pelo GitHub Actions._"
        )
        return

    # /listar
    if lower == "/listar":
        rotas = ler_rotas()
        if not rotas:
            enviar(chat_id, "Nenhuma rota cadastrada.\nUse /adicionar para comecar.")
            return
        msg = "*Rotas ativas:*\n\n"
        for r in rotas:
            volta = r.get("data_volta") or "so ida"
            msg += (
                f"*#{r['id']} — {r['origem']} -> {r['destino']}*\n"
                f"   Ida: {r['data_ida']} | Volta: {volta}\n"
                f"   Preco maximo: R$ {r['preco_maximo']}\n\n"
            )
        msg += "_Use /remover para excluir uma rota._"
        enviar(chat_id, msg)
        return

    # /remover
    if lower == "/remover":
        rotas = ler_rotas()
        if not rotas:
            enviar(chat_id, "Nenhuma rota para remover.")
            return
        msg = "*Qual rota deseja remover?*\n\n"
        for r in rotas:
            msg += f"#{r['id']} — {r['origem']} -> {r['destino']} | {r['data_ida']} | ate R$ {r['preco_maximo']}\n"
        msg += "\nDigite o numero da rota (ex: _1_)"
        estados[chat_id] = {"aguardando": "remover_id"}
        enviar(chat_id, msg)
        return

    # /adicionar
    if lower == "/adicionar":
        estados[chat_id] = {"aguardando": "origem", "nova_config": {}}
        enviar(chat_id,
            "*Adicionar rota — Passo 1 de 5*\n\n"
            "Qual a *cidade de origem*?\n"
            "ex: _Londrina_ ou _LDB_"
        )
        return

    # /buscar_agora
    if lower == "/buscar_agora":
        rotas = ler_rotas()
        if not rotas:
            enviar(chat_id, "Nenhuma rota cadastrada. Use /adicionar primeiro.")
            return
        enviar(chat_id,
            f"Iniciando busca para {len(rotas)} rota(s)...\n"
            "Isso pode demorar ~30s por rota."
        )
        try:
            resultado = subprocess.run(
                ["python", "kfinder.py"],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                enviar(chat_id, "Busca concluida! Alertas enviados se houver ofertas.")
            else:
                enviar(chat_id, f"❌ Erro na busca:\n`{resultado.stderr[:400]}`")
        except subprocess.TimeoutExpired:
            enviar(chat_id, "❌ Busca demorou demais. Tente novamente.")
        except Exception as e:
            enviar(chat_id, f"❌ Erro: {e}")
        return

    # Fluxo passo a passo
    if chat_id in estados:
        etapa = estados[chat_id]["aguardando"]

        # Remover rota
        if etapa == "remover_id":
            try:
                rid   = int(texto.strip().replace("#", ""))
                rotas = ler_rotas()
                nova  = [r for r in rotas if r.get("id") != rid]
                if len(nova) == len(rotas):
                    enviar(chat_id, f"❌ Rota #{rid} nao encontrada.")
                else:
                    salvar_rotas(nova)
                    enviar(chat_id, f"Rota #{rid} removida.\n\nRotas restantes: {len(nova)}")
                del estados[chat_id]
            except ValueError:
                enviar(chat_id, "❌ Digite apenas o numero da rota.\nex: _1_")
            return

        cfg = estados[chat_id].get("nova_config", {})

        if etapa == "origem":
            cfg["origem"] = resolver_iata(texto)
            estados[chat_id]["aguardando"] = "destino"
            enviar(chat_id,
                f"Origem: *{cfg['origem']}*\n\n"
                "*Passo 2 de 5* — Qual o *destino*?\n"
                "ex: _Salvador_, _SSA_, _Porto Seguro_"
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
                    "Para so ida, mande: _nao_"
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
                    enviar(chat_id, "❌ Data invalida. Use DD/MM/AAAA ou _nao_.")
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
                cfg["adultos"]      = 1

                rotas = ler_rotas()
                cfg["id"] = proximo_id(rotas)
                rotas.append(cfg)
                salvar_rotas(rotas)
                del estados[chat_id]

                volta = cfg.get("data_volta") or "so ida"
                enviar(chat_id,
                    f"Rota #{cfg['id']} adicionada!\n\n"
                    f"*{cfg['origem']} -> {cfg['destino']}*\n"
                    f"Ida: {cfg['data_ida']} | Volta: {volta}\n"
                    f"Preco maximo: R$ {cfg['preco_maximo']:.0f}\n\n"
                    f"Total de rotas ativas: {len(rotas)}\n\n"
                    f"Use /buscar\\_agora para buscar imediatamente\n"
                    f"ou /listar para ver todas as rotas."
                )
            except ValueError:
                enviar(chat_id, "❌ Preco invalido. Digite apenas o numero.\nex: _600_")

        return

    # Mensagem nao reconhecida
    enviar(chat_id,
        "Nao entendi. Use:\n\n"
        "/adicionar     — nova rota\n"
        "/listar        — ver rotas\n"
        "/remover       — remover rota\n"
        "/buscar\\_agora — buscar agora\n"
        "/ajuda         — ajuda"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def rodar_bot():
    print("=" * 55)
    print("  K-FINDER BOT v1.3 — aguardando mensagens")
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
                    print(f"Ignorado: {chat_id}")
                    continue

                texto = msg.get("text", "")
                if texto:
                    print(f"[{chat_id}] {texto}")
                    processar(chat_id, texto)

        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


if __name__ == "__main__":
    rodar_bot()
