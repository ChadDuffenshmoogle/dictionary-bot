# Use a specific, stable Python slim-buster image.
# 'slim-buster' is good for Debian-based systems, but if you want something even more minimal,
# you could consider 'python:3.11-alpine' (requires different package names if you add system deps).
FROM python:3.11-slim-buster

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure Python output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED 1

# Set working directory inside the container
# This is where your application will live
WORKDIR /app

# Install Python dependencies first, to take advantage of Docker layer caching.
# If requirements.txt doesn't change, this layer won't be rebuilt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code into the container
# This copies your 'src' directory, fly.toml, etc.
COPY . .

# IMPORTANT: Adjust the CMD to point to your new main.py location
# Since you refactored into a 'src' directory
CMD ["python", "src/main.py"]

# Optional: Create a non-root user for enhanced security.
# This is a good practice, though not strictly required for every Fly.io app.
# If you run into permissions issues with certain libraries, you might temporarily
# comment this out for debugging, but aim to keep it for production.
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser
