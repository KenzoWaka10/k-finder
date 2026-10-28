# ✈️ K-Finder

Monitor de preços de passagens aéreas em Python. O usuário cadastra rotas e um preço máximo por um bot do Telegram; o sistema consulta voos do Google Flights pela plataforma Apify e avisa por Telegram e e-mail quando encontra uma oferta dentro do limite definido.

> Projeto pessoal de estudo, desenvolvido para praticar consumo de APIs, automação e integração entre serviços. Veja a seção [Estado atual](#estado-atual) para saber exatamente o que já foi validado.

## Estado atual

| Parte | Situação |
|---|---|
| Busca de voos via Apify | ✅ Funciona. A execução do actor conclui com sucesso e o resultado é lido pelo código |
| Bot do Telegram (cadastro de rotas, `/buscar_agora`) | ✅ Responde e executa a busca. Rodando no Fly.io |
| Alertas por Telegram e e-mail | 🔄 Implementado, em validação |
| Execução agendada (GitHub Actions, a cada 6 h) | 🔄 Configurada, em validação |
| Controle de acesso multiusuário (aprovação pelo admin) | 🧪 Implementado, ainda sem testes com outros usuários |
| Histórico de preços (alertar só quando o preço cai) | ⚠️ Funciona dentro de uma execução. No GitHub Actions o histórico não é mantido entre execuções (veja [Limitações](#limitações-conhecidas)) |
| Testes automatizados | ❌ Não há |

## Como funciona

```
Usuário ──(Telegram)──► bot.py ──► config.json (rotas por usuário)
                                        │
        GitHub Actions (cron 6 h)  ou  /buscar_agora
                                        ▼
                                   kfinder.py
                         Apify (Google Flights) → filtra por preço
                                        ▼
                     compara com historico_precos.json
                                        ▼
                   alerta por Telegram + e-mail (HTML)
```

1. No Telegram, o usuário escolhe origem, destino, datas e preço máximo por botões.
2. O `kfinder.py` consulta os voos da rota, usando um actor do Apify.
3. Os voos dentro da faixa de preço são ordenados e comparados com o menor preço já registrado.
4. Se houver oferta nova, o sistema envia a mensagem com companhia, preço, duração, escalas e um link direto para a busca no Google Flights.

## Funcionalidades

- Cadastro, listagem, edição e remoção de rotas pelo Telegram (`/adicionar`, `/listar`, `/editar`, `/remover`)
- Seleção de cidades (31 opções), datas por calendário e preço por botões inline
- Busca manual com `/buscar_agora`
- Várias rotas por usuário e vários usuários, com aprovação do administrador (`/admin`)
- Alertas por Telegram e por e-mail em HTML, com link para o Google Flights
- Busca agendada pelo GitHub Actions, com disparo manual pela aba Actions
- Credenciais lidas de variáveis de ambiente, sem chaves no código

## Tecnologias

Python 3.12 · `requests` · `python-dotenv` · `apify-client` · Telegram Bot API · SMTP (Gmail) · GitHub Actions · Docker · Fly.io

## Estrutura

```
├── bot.py              # Bot do Telegram: menus, rotas, usuários, aprovação
├── kfinder.py          # Busca no Apify, filtro, histórico e envio de alertas
├── config.json         # Rotas e usuários
├── historico_precos.json
├── Dockerfile / fly.toml   # Deploy do bot no Fly.io
├── requirements.txt
└── .github/workflows/busca.yml   # Busca agendada
```

## Configuração

Crie um arquivo `.env` (nunca o envie ao Git) com base no `.env.example`:

| Variável | Para que serve |
|---|---|
| `APIFY_TOKEN` | Token da API do Apify |
| `TELEGRAM_TOKEN` | Token do bot, gerado no @BotFather |
| `TELEGRAM_CHAT_ID` | ID do chat do administrador |
| `EMAIL_REMETENTE` | Conta Gmail que envia os alertas |
| `EMAIL_SENHA_APP` | Senha de app do Gmail (exige verificação em duas etapas) |
| `EMAIL_DESTINATARIO` | E-mail que recebe os alertas |

## Como executar

**Localmente**

```bash
pip install -r requirements.txt
python bot.py        # inicia o bot (envie /menu no Telegram)
python kfinder.py    # roda uma busca para todas as rotas do config.json
```

**GitHub Actions:** cadastre as seis variáveis acima em *Settings → Secrets and variables → Actions*. O workflow roda a cada 6 horas e pode ser disparado manualmente.

**Fly.io (bot):**

```bash
fly secrets set APIFY_TOKEN='...' TELEGRAM_TOKEN='...' TELEGRAM_CHAT_ID='...' \
  EMAIL_REMETENTE='...' EMAIL_SENHA_APP='...' EMAIL_DESTINATARIO='...'
fly deploy
```

## Limitações conhecidas

- **Histórico no GitHub Actions:** o workflow não guarda o `historico_precos.json` entre execuções, então ali o sistema pode repetir alertas.
- **Duas configurações separadas:** as rotas cadastradas pelo bot ficam no container do Fly.io; o Actions lê o `config.json` do repositório. As duas não são sincronizadas automaticamente.
- **Sem armazenamento persistente no Fly.io:** um novo deploy reinicia o `config.json` e o histórico a partir da imagem.
- **Depende de um actor de terceiros do Apify** para obter os dados de voos.
- Sem testes automatizados.

## Próximos passos

- Persistir histórico e rotas (volume no Fly.io ou um banco simples)
- Unificar a fonte de configuração entre o bot e o agendamento
- Testes automatizados e fixação das versões das dependências

## Segurança

Tokens e senhas ficam em variáveis de ambiente (`.env` local, Secrets do GitHub e secrets do Fly.io). O `.env` está no `.gitignore`.

## Autor

Gabriel Kenzo · [GitHub](https://github.com/KenzoWaka10) · [LinkedIn](https://linkedin.com/in/gabriel-kenzo-5b86a52a9)
