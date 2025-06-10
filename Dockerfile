
FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libcairo2-dev \
    libpango1.0-dev \
    fonts-noto-cjk \
    fonts-dejavu-core \
    fontconfig \
    gcc \
    gobject-introspection \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .

CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
