FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc iputils-ping mariadb-client curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 安装 Docker CLI（用于备份时导出镜像）
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
    -o /tmp/docker.tgz && \
    tar xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1 docker/docker && \
    rm /tmp/docker.tgz && \
    chmod +x /usr/local/bin/docker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
