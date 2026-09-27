FROM python:3.11-slim-bookworm

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY solix_sim ./solix_sim

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "solix_sim.main"]
