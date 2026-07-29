# Hugging Face Docker Space runtime for the Streamlit NL→SQL demo.
# SQLite-only (psycopg is pruned from requirements.txt).
FROM python:3.13-slim

WORKDIR /app

# onnxruntime (via chromadb) needs libgomp on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src

EXPOSE 7860

CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
