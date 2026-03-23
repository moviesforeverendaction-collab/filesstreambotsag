FROM python:3.11-slim

WORKDIR /app

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Kurigram is a Pyrogram fork — installs under the 'pyrogram' namespace.
# All imports in this project use: from pyrogram import ...
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify install resolves correctly before copying app code
RUN python -c "from pyrogram import Client; print('pyrogram import OK')"

COPY . .

CMD ["python", "run.py"]
