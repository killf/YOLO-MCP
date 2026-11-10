# syntax=docker/dockerfile:1

# 1. 固定包管理器，依赖清单先于源码复制，避免源码改动使安装层失效。
FROM node:24-bookworm-slim AS frontend

WORKDIR /yolo-mcp/frontend

RUN npm install --global pnpm@12.3.4 --registry=https://registry.npmmirror.com

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./
COPY frontend/apps/frontend/package.json ./apps/frontend/package.json
COPY frontend/apps/website/package.json ./apps/website/package.json
COPY frontend/packages/audio-annotator-react/package.json ./packages/audio-annotator-react/package.json
COPY frontend/packages/audio-react/package.json ./packages/audio-react/package.json
COPY frontend/packages/components-react/package.json ./packages/components-react/package.json
COPY frontend/packages/formatter/package.json ./packages/formatter/package.json
COPY frontend/packages/i18n/package.json ./packages/i18n/package.json
COPY frontend/packages/image/package.json ./packages/image/package.json
COPY frontend/packages/image-annotator-react/package.json ./packages/image-annotator-react/package.json
COPY frontend/packages/interface/package.json ./packages/interface/package.json
COPY frontend/packages/video-annotator-react/package.json ./packages/video-annotator-react/package.json
COPY frontend/packages/video-react/package.json ./packages/video-react/package.json

RUN --mount=type=cache,id=labels-pnpm,target=/pnpm/store \
    pnpm --config.strictDepBuilds=false install --frozen-lockfile --ignore-scripts \
        --store-dir=/pnpm/store --package-import-method=copy

# 2. 源码变化只重新执行本地包构建与前端打包。
COPY frontend/ ./

RUN pnpm --filter @yolo-mcp/frontend run postinstall \
    && pnpm build:frontend

# 3. 同一运行镜像提供标注服务和训练，GPU 框架复用基础镜像。
FROM ultralytics/ultralytics

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    YOLO_AUTOINSTALL=false \
    YOLO_CONFIG_DIR=/data/.ultralytics \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,id=labels-pip,target=/root/.cache/pip \
    pip install --index-url https://mirrors.aliyun.com/pypi/simple/ uv==0.12.10

COPY backend/pyproject.toml backend/uv.lock ./

# 锁文件未变化时复用整个依赖层；不安装项目，也不替换基础镜像的 GPU 框架。
RUN --mount=type=cache,id=labels-uv,target=/root/.cache/uv \
    uv venv --system-site-packages .venv \
    && uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY README.md /app/README.md

# 4. 源码变化只重新安装项目，生成 Web 与训练两个命令入口。
RUN --mount=type=cache,id=labels-uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --from=frontend /yolo-mcp/frontend/apps/frontend/dist/ ./statics/

ENV PATH="/app/backend/.venv/bin:$PATH" \
    YOLO_MCP_DATA_DIR="/data"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
