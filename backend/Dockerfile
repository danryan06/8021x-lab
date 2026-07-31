FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# Install deps first for clearer failure modes; editable install for Alembic/app layout.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Ensure runtime dirs exist even before volumes are mounted.
RUN mkdir -p /var/lib/dot1x-lab/freeradius /var/lib/dot1x-lab/ca /app/services/freeradius/templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
