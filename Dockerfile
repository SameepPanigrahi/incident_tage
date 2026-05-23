# ====================================================================
# AI Incident Root Cause Assistant — Production Dockerfile
# ====================================================================
FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
        build-essential curl && \\
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy English model (for Presidio PII detection)
RUN python -m spacy download en_core_web_lg || \\
    python -m spacy download en_core_web_sm || \\
    echo "spaCy model download skipped — regex PII fallback will be used"

# Copy application code
COPY src/ ./src/
COPY mock_data/ ./mock_data/

# Create directories for persistent data
RUN mkdir -p chroma_db

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \\
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the API server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]