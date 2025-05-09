FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_DEBUG=False
ENV PYTHONUNBUFFERED=1
ENV LEMMA_STORAGE_DIR=/data/.lemma_enterprise

# Create volume directory
RUN mkdir -p /data/.lemma_enterprise && chmod 777 /data/.lemma_enterprise

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--workers", "4", "--timeout", "120"]
