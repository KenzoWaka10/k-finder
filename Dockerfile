FROM python:3.12-slim

WORKDIR /app

# Instala dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do projeto
COPY bot.py .
COPY kfinder.py .
COPY config.json .

# Cria historico_precos.json vazio se nao existir
RUN echo '{}' > historico_precos.json

CMD ["python", "bot.py"]
