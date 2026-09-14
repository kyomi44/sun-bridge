FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY deploy/gmail-push/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --no-create-home --uid 10001 appuser
COPY sunbridge/__init__.py sunbridge/gmail_listener.py sunbridge/gmail_cloud.py sunbridge/mail.py /app/sunbridge/
USER 10001:10001
# Cloud Run IAM authentication is mandatory. Do not grant allUsers invoker.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "--timeout", "240", "--graceful-timeout", "15", "--max-requests", "500", "--max-requests-jitter", "50", "sunbridge.gmail_cloud:create_app()"]
