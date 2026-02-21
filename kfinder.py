"""
K-FINDER v3.1 — KenLogic Solutions
Suporte a multiplas rotas simultaneas + link Google Flights
"""

import os
import re
import json
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
EMAIL_REMETENTE    = os.getenv("EMAIL_REMETENTE")
EMAIL_SENHA_APP    = os.getenv("EMAIL_SENHA_APP")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO")

CONFIG_FILE    = "config.json"
HISTORICO_FILE = "historico_precos.json"


# ══════════════════════════════════════════════════════════════════════════════
#  1. CONFIG — lista de rotas
# ══════════════════════════════════════════════════════════════════════════════

def ler_rotas() -> list:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Suporta tanto config nova (lista) quanto antiga (dict unico)
            if "rotas" in data:
                return data["rotas"]
            else:
                return [data]
    return [{
        "id": 1,
        "origem":       "LDB",
        "destino":      "BPS",
        "data_ida":     "2026-03-15",
        "data_volta":   "2026-03-22",
        "adultos":      1,
        "preco_minimo": 0,
        "preco_maximo": 600,
    }]


# ══════════════════════════════════════════════════════════════════════════════
#  2. LINK DO GOOGLE FLIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def gerar_link_google_flights(config: dict) -> str:
    """Gera link direto para o Google Flights com a rota e data."""
    origem  = config["origem"]
    destino = config["destino"]
    data    = config["data_ida"].replace("-", "")  # ex: 20260315

    if config.get("data_volta"):
        volta = config["data_volta"].replace("-", "")
        url = (
            f"https://www.google.com/travel/flights/search?"
            f"tfs=CBwQAhoeEgoyMDI2MDMxNQ*"  # template base
        )
        # Link simples e funcional
        url = f"https://www.google.com/travel/flights?q=Flights+from+{origem}+to+{destino}+on+{config['data_ida']}+returning+{config['data_volta']}"
    else:
        url = f"https://www.google.com/travel/flights?q=Flights+from+{origem}+to+{destino}+on+{config['data_ida']}"

    return url


# ══════════════════════════════════════════════════════════════════════════════
#  3. BUSCA DE PASSAGENS (Apify)
# ══════════════════════════════════════════════════════════════════════════════

def buscar_passagens(config: dict) -> list:
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("❌ Instale: pip install apify-client")
        return []

    APIFY_TOKEN = os.getenv("APIFY_TOKEN")
    if not APIFY_TOKEN:
        print("❌ APIFY_TOKEN nao encontrado")
        return []

    print(f"  Buscando: {config['origem']} -> {config['destino']} | {config['data_ida']} | ate R$ {config['preco_maximo']}")

    client = ApifyClient(APIFY_TOKEN)

    run_input = {
        "departure_id":  config["origem"],
        "arrival_id":    config["destino"],
        "outbound_date": config["data_ida"],
        "adults":        config["adultos"],
        "currency":      "BRL",
        "language":      "pt-BR",
        "country":       "BR",
    }
    if config.get("data_volta"):
        run_input["return_date"] = config["data_volta"]

    run = client.actor("johnvc/google-flights-data-scraper-flight-and-price-search").call(run_input=run_input)

    resultados = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        best  = item.get("best_flights")  or []
        other = item.get("other_flights") or []
        for voo in best + other:
            resultados.append(voo)

    print(f"  {len(resultados)} voo(s) encontrado(s).")
    return resultados


# ══════════════════════════════════════════════════════════════════════════════
#  4. FILTRO
# ══════════════════════════════════════════════════════════════════════════════

def extrair_preco(voo: dict):
    preco = voo.get("price") or voo.get("totalPrice") or voo.get("priceValue") or None
    if isinstance(preco, str):
        numeros = re.findall(r"[\d]+", preco.replace(".", "").replace(",", ""))
        preco = float(numeros[0]) if numeros else None
    return preco


def filtrar_ofertas(voos: list, config: dict) -> list:
    ofertas = []
    for voo in voos:
        preco = extrair_preco(voo)
        if preco is None:
            continue
        if config["preco_minimo"] <= preco <= config["preco_maximo"]:
            voos_internos = voo.get("flights") or [{}]
            primeiro      = voos_internos[0] if voos_internos else {}
            companhia     = primeiro.get("airline") or primeiro.get("name") or "N/A"
            horario       = primeiro.get("departure_airport", {}).get("time") or "N/A"
            layovers      = len(voo.get("layovers") or [])

            ofertas.append({
                "companhia":   companhia,
                "preco":       preco,
                "duracao":     str(voo.get("total_duration", "N/A")) + " min",
                "escalas":     layovers,
                "horario_ida": horario,
                "link":        gerar_link_google_flights(config),
            })

    ofertas.sort(key=lambda x: x["preco"])
    return ofertas


# ══════════════════════════════════════════════════════════════════════════════
#  5. HISTORICO (evita alertas repetidos)
# ══════════════════════════════════════════════════════════════════════════════

def ler_historico() -> dict:
    if os.path.exists(HISTORICO_FILE):
        with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_historico(chave: str, preco: float):
    hist = ler_historico()
    hist[chave] = {"preco": preco, "data": datetime.now().strftime("%d/%m/%Y %H:%M")}
    with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

def verificar_novidade(config: dict, ofertas: list) -> list:
    if not ofertas:
        return []
    chave = f"{config['origem']}-{config['destino']}-{config['data_ida']}"
    hist  = ler_historico()
    melhor = ofertas[0]["preco"]
    if chave in hist:
        anterior = hist[chave]["preco"]
        if melhor >= anterior:
            print(f"  Preco ({melhor}) nao menor que anterior ({anterior}). Sem alerta.")
            return []
        print(f"  Preco caiu! R$ {anterior} -> R$ {melhor}")
    salvar_historico(chave, melhor)
    return ofertas


# ══════════════════════════════════════════════════════════════════════════════
#  6. MONTA MENSAGEM
# ══════════════════════════════════════════════════════════════════════════════

def montar_mensagem(ofertas: list, config: dict) -> dict:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    volta = config.get("data_volta") or "so ida"

    if not ofertas:
        texto = (
            f"K-Finder — {agora}\n"
            f"{config['origem']} -> {config['destino']} | {config['data_ida']} | volta: {volta}\n\n"
            f"Nenhuma oferta abaixo de R$ {config['preco_maximo']} nesta verificacao."
        )
        return {
            "telegram": texto,
            "email_assunto": f"K-Finder: Sem ofertas — {config['origem']}->{config['destino']}",
            "email_corpo": f"<p>{texto.replace(chr(10), '<br>')}</p>"
        }

    link = ofertas[0]["link"]

    # Telegram
    tg  = f"*K-Finder — {len(ofertas)} oferta(s)*\n"
    tg += f"{agora}\n"
    tg += f"*{config['origem']} -> {config['destino']}*\n"
    tg += f"Ida: {config['data_ida']} | Volta: {volta}\n"
    tg += f"Criterio: ate R$ {config['preco_maximo']}\n"
    tg += "---\n\n"

    for i, o in enumerate(ofertas[:5], 1):
        tg += f"*{i}. {o['companhia']}*\n"
        tg += f"   R$ {o['preco']:.2f}\n"
        tg += f"   Duracao: {o['duracao']}\n"
        tg += f"   Escalas: {o['escalas']}\n"
        tg += f"   Saida: {o['horario_ida']}\n\n"

    tg += f"[Ver no Google Flights]({link})\n"
    tg += "_K-Finder · KenLogic Solutions_"

    # E-mail HTML
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:#1a73e8;color:white;padding:20px;">
        <h2 style="margin:0">K-Finder &mdash; Alerta de Voo</h2>
        <p style="margin:4px 0 0">{agora} &middot; {config['origem']} &rarr; {config['destino']} &middot; {config['data_ida']}</p>
      </div>
      <div style="padding:20px;">
        <p>Criterio: ate <strong>R$ {config['preco_maximo']}</strong> &mdash; {len(ofertas)} oferta(s)</p>
        <hr style="border:none;border-top:1px solid #eee;">
    """
    for i, o in enumerate(ofertas[:5], 1):
        html += f"""
        <div style="background:#f8f9fa;border-radius:6px;padding:12px;margin:10px 0;">
          <strong>{i}. {o['companhia']}</strong><br>
          <strong style="color:#1a73e8;font-size:18px">R$ {o['preco']:.2f}</strong>
          &nbsp;|&nbsp; {o['duracao']}
          &nbsp;|&nbsp; {o['escalas']} escala(s)
          &nbsp;|&nbsp; Saida: {o['horario_ida']}
        </div>"""
    html += f"""
        <div style="text-align:center;margin-top:20px;">
          <a href="{link}" style="background:#1a73e8;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">
            Ver no Google Flights
          </a>
        </div>
      </div>
      <div style="background:#f1f3f4;padding:12px;text-align:center;font-size:12px;color:#888;">
        K-Finder &middot; KenLogic Solutions
      </div>
    </div>"""

    return {
        "telegram": tg,
        "email_assunto": f"K-Finder: {len(ofertas)} oferta(s) — {config['origem']}->{config['destino']} ate R$ {config['preco_maximo']}",
        "email_corpo": html,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  7. ENVIOS
# ══════════════════════════════════════════════════════════════════════════════

def enviar_telegram(texto: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram nao configurado — pulando.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       texto,
            "parse_mode": "Markdown",
        }, timeout=10)
        if r.status_code == 200:
            print("  Telegram: enviado.")
        else:
            print(f"❌ Erro Telegram: {r.text}")
    except Exception as e:
        print(f"❌ Erro Telegram: {e}")


def enviar_email(assunto: str, corpo_html: str):
    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        print("  E-mail nao configurado — pulando.")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = EMAIL_REMETENTE
        msg["To"]      = EMAIL_DESTINATARIO
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
            server.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
        print("  E-mail: enviado.")
    except Exception as e:
        print(f"❌ Erro E-mail: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  8. EXECUCAO PRINCIPAL — processa todas as rotas
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  K-FINDER v3.1 — KenLogic Solutions")
    print("=" * 55)

    rotas = ler_rotas()
    print(f"\n{len(rotas)} rota(s) para verificar.\n")

    for i, config in enumerate(rotas, 1):
        print(f"--- Rota {i}/{len(rotas)} ---")
        voos    = buscar_passagens(config)
        ofertas = filtrar_ofertas(voos, config)
        novas   = verificar_novidade(config, ofertas)
        msgs    = montar_mensagem(novas, config)

        if novas:
            print(f"  Enviando alertas para rota {config['origem']}->{config['destino']}...")
            enviar_telegram(msgs["telegram"])
            enviar_email(msgs["email_assunto"], msgs["email_corpo"])
        print()

    print("K-Finder finalizado.")
