FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[api]"
RUN useradd --create-home --uid 10001 omega && chown -R omega:omega /app
USER omega
EXPOSE 8000
CMD ["uvicorn","omega.api.app:app","--host","0.0.0.0","--port","8000"]
