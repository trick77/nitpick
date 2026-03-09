FROM python:3.12-slim
WORKDIR /app
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY prompts/ prompts/
RUN chmod -R g=u /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
