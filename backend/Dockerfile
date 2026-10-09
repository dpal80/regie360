FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY entrypoint.sh .

RUN useradd --system --uid 1000 crm && chmod +x entrypoint.sh
USER crm

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
