"""
K-FINDER v3.2 — KenLogic Solutions
- Suporte a multi-usuario (rotas por chat_id)
- Argumento --chat-id para busca manual pelo bot
- Sem --chat-id: processa todos os usuarios (GitHub Actions)
- Alerta vai para o chat do dono da rota
"""

import os
import re
import sys
import json
import smtplib
import requests
import argparse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def _env(nome: str):
    """Le variavel de ambiente removendo espacos e quebras de linha das pontas."""
    return (os.getenv(nome) or "").strip() or None

TELEGRAM_TOKEN     = _env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = _env("TELEGRAM_CHAT_ID")
EMAIL_REMETENTE    = _env("EMAIL_REMETENTE")
EMAIL_SENHA_APP    = _env("EMAIL_SENHA_APP")
EMAIL_DESTINATARIO = _env("EMAIL_DESTINATARIO")

CONFIG_FILE    = "config.json"
HISTORICO_FILE = "historico_precos.json"

# ══════════════════════════════════════════════════════════════════════════════
#  1. CONFIG
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

def ler_rotas_usuario(chat_id: str) -> list:
    config = ler_config()
    return config.get("usuarios", {}).get(str(chat_id), {}).get("rotas", [])

def ler_todos_usuarios() -> dict:
    config = ler_config()
    result = {}
    for cid, dados in config.get("usuarios", {}).items():
        rotas = dados.get("rotas", [])
        if rotas:
            result[cid] = rotas
    return result

# ══════════════════════════════════════════════════════════════════════════════
#  2. LINK DO GOOGLE FLIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def gerar_link_google_flights(config: dict) -> str:
    origem  = config["origem"]
    destino = config["destino"]
    if config.get("data_volta"):
        return (
            f"https://www.google.com/travel/flights?q=Flights+from+{origem}+to+"
            f"{destino}+on+{config['data_ida']}+returning+{config['data_volta']}"
        )
    return (
        f"https://www.google.com/travel/flights?q=Flights+from+{origem}+to+"
        f"{destino}+on+{config['data_ida']}"
    )

# ══════════════════════════════════════════════════════════════════════════════
#  3. BUSCA DE PASSAGENS (Apify)
# ══════════════════════════════════════════════════════════════════════════════

def buscar_passagens(config: dict) -> list:
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("❌ Instale: pip install apify-client")
        return []

    APIFY_TOKEN = _env("APIFY_TOKEN")
    if not APIFY_TOKEN:
        print("❌ APIFY_TOKEN nao encontrado")
        return []

    print(f"  Buscando: {config['origem']} -> {config['destino']} | {config['data_ida']} | ate R$ {config['preco_maximo']}")

    client = ApifyClient(APIFY_TOKEN)
    run_input = {
        "departure_id":  config["origem"],
        "arrival_id":    config["destino"],
        "outbound_date": config["data_ida"],
        "adults":        config.get("adultos", 1),
        "currency":      "BRL",
        "language":      "pt-BR",
        "country":       "BR",
    }
    if config.get("data_volta"):
        run_input["return_date"] = config["data_volta"]

    run = client.actor("johnvc/google-flights-data-scraper-flight-and-price-search").call(run_input=run_input)

    resultados = []
    if run is None:
        print("  Apify nao retornou resultado da execucao.")
        return []
    # apify-client novo devolve objeto (run.default_dataset_id); o antigo devolvia dict
    dataset_id = run["defaultDatasetId"] if isinstance(run, dict) else run.default_dataset_id
    for item in client.dataset(dataset_id).iterate_items():
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
        if config.get("preco_minimo", 0) <= preco <= config["preco_maximo"]:
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
#  5. HISTORICO
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
    chave  = f"{config['origem']}-{config['destino']}-{config['data_ida']}"
    hist   = ler_historico()
    melhor = ofertas[0]["preco"]
    if chave in hist:
        anterior = hist[chave]["preco"]
        if melhor >= anterior:
            print(f"  Preco ({melhor}) nao menor que anterior ({anterior}). Sem alerta.")
            return []
        print(f"  💰 Preco caiu! R$ {anterior} -> R$ {melhor}")
    salvar_historico(chave, melhor)
    return ofertas

# ══════════════════════════════════════════════════════════════════════════════
#  6. MONTA MENSAGEM
# ══════════════════════════════════════════════════════════════════════════════

def formatar_data(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_iso

def montar_mensagem(ofertas: list, config: dict) -> dict:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    volta = formatar_data(config["data_volta"]) if config.get("data_volta") else "so ida"
    ida   = formatar_data(config["data_ida"])

    if not ofertas:
        texto = (
            f"🔍 K-Finder — {agora}\n"
            f"{config['origem']} ✈️ {config['destino']} | {ida} | volta: {volta}\n\n"
            f"Nenhuma oferta abaixo de R$ {config['preco_maximo']} nesta verificacao."
        )
        return {
            "telegram": texto,
            "email_assunto": f"K-Finder: Sem ofertas — {config['origem']}->{config['destino']}",
            "email_corpo": f"<p>{texto.replace(chr(10), '<br>')}</p>"
        }

    link = ofertas[0]["link"]

    tg  = f"🚨 *K-Finder — {len(ofertas)} oferta(s) encontrada(s)!*\n"
    tg += f"_{agora}_\n\n"
    tg += f"✈️ *{config['origem']} → {config['destino']}*\n"
    tg += f"📅 Ida: {ida}  |  Volta: {volta}\n"
    tg += f"💰 Criterio: ate R$ {config['preco_maximo']:.0f}\n"
    tg += "━━━━━━━━━━━━━━━━━\n\n"
    for i, o in enumerate(ofertas[:5], 1):
        tg += f"*{i}. {o['companhia']}*\n"
        tg += f"   💵 R$ {o['preco']:.2f}\n"
        tg += f"   ⏱ Duracao: {o['duracao']}\n"
        tg += f"   🔄 Escalas: {o['escalas']}\n"
        tg += f"   🕐 Saida: {o['horario_ida']}\n\n"
    tg += f"[🔗 Ver no Google Flights]({link})\n"
    tg += "_K-Finder · KenLogic Solutions_"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:#1a73e8;color:white;padding:20px;">
        <h2 style="margin:0">✈️ K-Finder — Alerta de Voo</h2>
        <p style="margin:4px 0 0">{agora} &middot; {config['origem']} &rarr; {config['destino']} &middot; {ida}</p>
      </div>
      <div style="padding:20px;">
        <p>Criterio: ate <strong>R$ {config['preco_maximo']:.0f}</strong> &mdash; <strong>{len(ofertas)} oferta(s)</strong></p>
        <hr style="border:none;border-top:1px solid #eee;">"""
    for i, o in enumerate(ofertas[:5], 1):
        html += f"""
        <div style="background:#f8f9fa;border-radius:6px;padding:12px;margin:10px 0;">
          <strong>{i}. {o['companhia']}</strong><br>
          <strong style="color:#1a73e8;font-size:18px">R$ {o['preco']:.2f}</strong>
          &nbsp;|&nbsp; {o['duracao']} &nbsp;|&nbsp; {o['escalas']} escala(s) &nbsp;|&nbsp; Saida: {o['horario_ida']}
        </div>"""
    html += f"""
        <div style="text-align:center;margin-top:20px;">
          <a href="{link}" style="background:#1a73e8;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">Ver no Google Flights</a>
        </div>
      </div>
      <div style="background:#f1f3f4;padding:12px;text-align:center;font-size:12px;color:#888;">K-Finder &middot; KenLogic Solutions</div>
    </div>"""

    return {
        "telegram": tg,
        "email_assunto": f"K-Finder: {len(ofertas)} oferta(s) — {config['origem']}->{config['destino']} ate R$ {config['preco_maximo']:.0f}",
        "email_corpo": html,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  7. ENVIOS
# ══════════════════════════════════════════════════════════════════════════════

def enviar_telegram(chat_id: str, texto: str):
    if not TELEGRAM_TOKEN:
        print("  Telegram nao configurado — pulando.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}, timeout=10)
        if r.status_code == 200:
            print(f"  Telegram [{chat_id}]: enviado.")
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
#  8. EXECUCAO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def processar_rotas(chat_id: str, rotas: list):
    print(f"\n  Usuario {chat_id}: {len(rotas)} rota(s)\n")
    for i, config in enumerate(rotas, 1):
        print(f"  --- Rota {i}/{len(rotas)} ---")
        voos    = buscar_passagens(config)
        ofertas = filtrar_ofertas(voos, config)
        novas   = verificar_novidade(config, ofertas)
        msgs    = montar_mensagem(novas, config)
        if novas:
            print(f"  Enviando alertas para {config['origem']}->{config['destino']}...")
            enviar_telegram(chat_id, msgs["telegram"])
            enviar_email(msgs["email_assunto"], msgs["email_corpo"])
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", help="Processar somente as rotas deste usuario")
    args = parser.parse_args()

    print("=" * 55)
    print("  K-FINDER v3.2 — KenLogic Solutions")
    print("=" * 55)

    if args.chat_id:
        rotas = ler_rotas_usuario(args.chat_id)
        if not rotas:
            print(f"Nenhuma rota para o usuario {args.chat_id}.")
        else:
            processar_rotas(args.chat_id, rotas)
    else:
        todos = ler_todos_usuarios()
        if not todos:
            print("Nenhuma rota cadastrada.")
        else:
            total = sum(len(r) for r in todos.values())
            print(f"\n{len(todos)} usuario(s), {total} rota(s) no total.")
            for cid, rotas in todos.items():
                processar_rotas(cid, rotas)

    print("\nK-Finder finalizado.")