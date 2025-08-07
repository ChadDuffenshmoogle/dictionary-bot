# Use a specific, stable Python slim-buster image.
FROM python:3.11-slim-buster

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure Python output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED 1

# Set working directory inside the container
WORKDIR /app

# Install Python dependencies first, to take advantage of Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code into the container
COPY . .

# The key fix: run Python as a module from the parent directory
# This makes the relative imports work properly
CMD ["python", "-m", "src.main"]

# Create a non-root user for enhanced security
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser