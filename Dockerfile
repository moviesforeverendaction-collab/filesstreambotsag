FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from pyrogram import Client; print('pyrogram import OK')"

# Create sessions directory — Pyrogram writes .session files here.
# On Railway, mount a persistent volume at /app/sessions so DC auth keys
# survive redeployments (prevents re-auth delay on every restart).
RUN mkdir -p /app/sessions

COPY . .

CMD ["python", "run.py"]
