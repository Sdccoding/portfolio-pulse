FROM python:3.11-slim

WORKDIR /app

# Ensure standard output flows properly without buffering
ENV PYTHONUNBUFFERED=1

# Copy dependencies list first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all the application files
COPY . .

# Run the interactive bot (Cloud Run web server via python-telegram-bot HTTP webhook)
CMD ["python", "interactive_bot.py"]
