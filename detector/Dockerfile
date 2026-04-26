FROM python:3.12-slim

# prevent python from writing .pyc files
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# create non-root user
RUN useradd -m appuser

# set working directory
WORKDIR /app

# install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy application code
COPY . .

# change ownership of the application files to the non-root user
RUN chown -R appuser:appuser /app

# create directory for audit logs and set ownership
RUN mkdir -p /var/log/detector && \
    chown -R appuser:appuser /var/log/detector

# switch to non-root user
USER appuser

# health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:5000/ || exit 1

# expose the application port
EXPOSE 5000

# start the application
CMD ["python", "main.py"]