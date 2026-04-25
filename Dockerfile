FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY server.py ./server.py

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

CMD ["python", "server.py", "--port", "8080"]
