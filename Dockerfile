FROM python:3.9-alpine

WORKDIR /app

COPY requirements.txt .

# Устанавливаем зависимости
RUN apk add --no-cache gcc musl-dev linux-headers && \
    pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
