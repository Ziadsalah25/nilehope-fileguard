# Install dependencies in Chainguard's development image; the runtime image is distroless.
FROM chainguard/python:latest-dev AS build
USER root
WORKDIR /app
COPY requirements.container.txt ./
RUN python -m venv --without-pip /app/venv && pip --python /app/venv/bin/python install --no-cache-dir -r requirements.container.txt && mkdir /upload-data

FROM chainguard/python:latest
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
ENV PATH="/app/venv/bin:$PATH"
WORKDIR /app
COPY --from=build /app/venv /app/venv
COPY --from=build --chown=65532:65532 /upload-data/ /var/lib/fileguard/uploads/
COPY services/management/app ./app
COPY scripts/lab_fleet.py ./scripts/lab_fleet.py
EXPOSE 8000
ENTRYPOINT []
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
