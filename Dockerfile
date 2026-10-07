# InStock 镜像（用法见 README 与 docker-compose.yml）
# 第一阶段构建前端，第二阶段为 Python 运行环境；TA-Lib、mini-racer 均使用 PyPI 预编译 wheel

FROM node:22-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --registry=https://registry.npmmirror.com
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    INSTOCK_DATA_DIR=/data \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY instock ./instock
COPY --from=web /src/instock/web/dist ./instock/web/dist
VOLUME /data
EXPOSE 9988
CMD ["python", "-m", "instock", "web"]
