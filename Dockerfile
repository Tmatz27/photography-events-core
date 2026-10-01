FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home core
COPY pyproject.toml alembic.ini /app/
COPY src /app/src
COPY migrations /app/migrations
COPY tests/fixtures /app/tests/fixtures
COPY scripts/start.py /app/scripts/start.py
ENV PYTHONPATH=/app/src
USER 10001:10001
EXPOSE 8099
CMD ["python", "scripts/start.py"]
