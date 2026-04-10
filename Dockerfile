# Dockerfile
# Multi-stage build for NL→DB Agent
# Runs FastAPI backend on port 8000

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed the database during build
RUN python db/seed_data.py

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]