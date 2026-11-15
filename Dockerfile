FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.container.txt ./
RUN pip install --no-cache-dir -r requirements.container.txt && adduser -D -u 10001 appuser
COPY --chown=appuser:appuser services/management/app ./app
COPY --chown=appuser:appuser scripts/lab_fleet.py ./scripts/lab_fleet.py
USER 10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
