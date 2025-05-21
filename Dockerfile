FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PORT=5000

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD gunicorn wsgi:app
