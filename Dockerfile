# Lemma Enterprise - Offline Verifier Image
# This Docker image provides offline credential verification capabilities
# with signed cascade bundles for revocation checking.

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/instance/data/revocation/cascades \
    && mkdir -p /app/instance/data/keys \
    && mkdir -p /app/logs

# Set environment variables for offline mode
ENV LEMMA_OFFLINE_MODE=true
ENV LEMMA_AUTO_UPDATE=false
ENV LEMMA_STORAGE_DIR=/app/instance/data
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Create a non-root user for security
RUN useradd -m -u 1000 lemma && \
    chown -R lemma:lemma /app
USER lemma

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Expose port
EXPOSE 5000

# Default command - offline verifier mode
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]

# Labels for metadata
LABEL maintainer="Lemma Enterprise"
LABEL version="2.3.0"
LABEL description="Lemma Offline Verifier - Credential verification without internet dependency"
LABEL org.opencontainers.image.source="https://github.com/lemma-enterprise/lemma-enterprise"
LABEL org.opencontainers.image.documentation="https://github.com/lemma-enterprise/lemma-enterprise/blob/main/README.md" 