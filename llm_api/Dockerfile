FROM python:3.10-slim-buster

WORKDIR /app

# Install build dependencies for llama-cpp-python, including git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install llama-cpp-python with server extras
# Use --no-cache-dir to save space
RUN pip install --no-cache-dir "llama-cpp-python[server]"

COPY ./app /app

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]