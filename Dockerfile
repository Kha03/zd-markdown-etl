FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY scraper.py .
COPY gemini_store.py .
COPY articles ./articles

CMD ["python", "main.py"]