# QTT WebDAV gateway (Office Pulse Files as a drive) — /opt/qtt-workplace/dav on QTT-AI-OS, see gateway.py
FROM python:3.12-slim
RUN useradd -r -u 10001 dav
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway.py .
USER dav
EXPOSE 8080
CMD ["python", "gateway.py"]
