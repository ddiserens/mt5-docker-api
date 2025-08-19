FROM python:3.13-slim

# Install system dependencies and add i386 architecture for Wine
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg2 \
    software-properties-common \
    ca-certificates \
    xvfb \
    x11vnc \
    novnc \
    supervisor \
    net-tools \
    iproute2 && \
    dpkg --add-architecture i386 && \
    rm -rf /var/lib/apt/lists/*

# Install Wine using the modern and secure key management method
RUN mkdir -p /etc/apt/keyrings && \
    wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/winehq-archive.gpg] https://dl.winehq.org/wine-builds/debian/ bullseye main" > /etc/apt/sources.list.d/winehq.list && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-stable && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /tmp/requirements.txt

# Install Python packages from requirements
# Note: mt5linux is installed separately and may fail on some architectures
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt && \
    (pip install --no-cache-dir mt5linux==0.1.* || echo "Warning: mt5linux installation failed, will try MetaTrader5 package in Wine")

# Environment variables
ENV WINEPREFIX=/config/.wine
ENV WINEARCH=win64
ENV WINEDEBUG=-all
ENV DISPLAY=:1

# Create directories and copy application files
RUN mkdir -p /app /config /var/log/supervisor
COPY src/ /app/
COPY Metatrader/ /Metatrader/

# Make scripts executable
RUN chmod +x /Metatrader/*.py 2>/dev/null || true

# Supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 3000 8000 8001

# Volume
VOLUME /config

# Set working directory
WORKDIR /app

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]





