FROM python:3.12-slim

WORKDIR /app

# Update CA certificates for outbound HTTPS requests.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["python", "run.py"]
