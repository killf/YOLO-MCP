# YOLO MCP 运行与开发指南

首次使用请从[项目首页](../README.md)开始。本文介绍配置、权限、开发和构建；模型依赖与参数见[训练指南](training/README.md)。

## 运行与配置

```bash
yolo-mcp --host 127.0.0.1 --port 8000
```

网页和 API 文档分别位于 `http://127.0.0.1:8000` 和 `http://127.0.0.1:8000/docs`。首次启动会初始化空库并生成签名密钥。

以下配置均为可选项，通过环境变量设置。项目配置统一使用 `YOLO_MCP_` 前缀，旧的无前缀名称不再生效；Ultralytics、Python 等第三方运行时变量保留原名。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `YOLO_MCP_DATA_DIR` | `~/.yolo-mcp` | 图片、模型、日志和默认数据库的根目录 |
| `YOLO_MCP_DATABASE_URL` | `YOLO_MCP_DATA_DIR/labels.sqlite` 对应的 SQLite URL | 自定义数据库连接 |
| `YOLO_MCP_USE_AUTO_LABEL` | `true` | 是否启用 AI 标注 |
| `YOLO_MCP_DEVICE` | 空 | 自动选择 CUDA/ROCm、MPS 或 CPU；也可指定 `0`、`cuda:0`、`cpu` |

例如，在 PowerShell 中指定目录和设备：

```powershell
$env:YOLO_MCP_DATA_DIR = "D:/yolo-data"
$env:YOLO_MCP_DEVICE = "0"
yolo-mcp --host 127.0.0.1 --port 8000
```

也可显式加载 `.env` 文件，示例见 [.env.example](.env.example)：

```bash
python -m uvicorn backend.main:app --env-file /path/to/.env --host 127.0.0.1 --port 8000
```

签名密钥在首次启动时自动生成，之后读取同一文件。

## 账号、权限与 MCP

空库允许一次管理员初始化，完成后关闭公开注册。管理员在“用户管理”中添加账号、设置系统角色、启停账号或重置密码。

| 身份 | 权限 |
| --- | --- |
| 系统管理员 | 管理全部用户、项目和访问令牌 |
| 项目拥有者 | 配置项目、管理成员、上传、标注、训练、下载及删除 |
| 项目协作者 | 查看、上传、标注、运行 AI 标注、训练和下载 |

普通用户可以创建自己的项目，拥有者在“项目成员”中添加协作者。协作者可撤回本人尚未提交成样本的上传。系统保留至少一名启用的管理员；停用或重置密码会撤销该账号的旧会话与个人令牌。

个人令牌在网页“访问令牌 / MCP”中管理，支持到期和撤销。明文只在创建时显示一次，数据库保存摘要。MCP 与网页共用权限，令牌不能用于管理账号或创建更多令牌。

MCP 地址为 `/mcp`，使用 Streamable HTTP 和 `Authorization: Bearer <个人令牌>`，配置见[首页示例](../README.md#连接-mcp)。上传工具接收 Base64 图片，模型下载工具返回需携带同一令牌的 HTTP 路径。

默认仅接受本机 Host / Origin。远程部署时通过 HTTPS 代理访问，并填写实际域名的 JSON 数组：

```dotenv
YOLO_MCP_MCP_ALLOWED_HOSTS=["yolo.example.com"]
YOLO_MCP_MCP_ALLOWED_ORIGINS=["https://yolo.example.com"]
```

## 数据与备份

默认目录为 `~/.yolo-mcp/`：

```text
.yolo-mcp/
├── secret.key
├── labels.sqlite
├── models/
│   ├── ultralytics/
│   └── huggingface/
└── projects/<项目 ID>/
    ├── images/
    ├── thumbnails/
    ├── models/
    └── runs/<记录 ID>/
```

原图位于 `images/`，缩略图单独位于 `thumbnails/`。标注、类别和数据划分保存在数据库中。每个附件对应一个样本；删除样本会删除对应图片及缩略图，已提交的附件应从样本列表删除。项目改名不改变目录。项目数据总览支持标注状态与训练／测试类型组合筛选，点击“总计”清除筛选。

训练开始时才生成该次数据快照，结构见[项目目录](training/README.md#项目目录)。旧附件按数据库中的路径读取，已有 `uploads/` 不会自动搬迁。

备份时保留整个数据目录，包括密钥、数据库、图片和模型。保留 `secret.key` 可让登录令牌和图片签名跨重启继续使用。

仓库仅维护 [001_init_db.py](migrations/versions/001_init_db.py)。结构调整后需使用新库；重复初始化不会改造已有库。当前未提供历史结构升级或数据搬迁工具。SQLite 连接启用外键约束。

## Docker 部署

从完整仓库根目录构建：

```bash
docker build -t yolo-mcp:local .
```

将已创建的数据目录挂载到容器，下方路径需替换为实际路径：

```bash
docker run --rm -p 8000:8000 \
  --mount type=bind,source=/absolute/path/to/data,target=/data \
  yolo-mcp:local
```

打开 `http://127.0.0.1:8000`。镜像使用 `ultralytics/ultralytics` GPU 环境并包含前端；GPU 可用性取决于基础镜像与宿主机。离线训练见[共用服务镜像](training/README.md#共用服务镜像)。

## 开发与构建

### 准备环境

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 24 和 pnpm 12.3.4。

```bash
git clone https://github.com/killf/LabelS.git
cd LabelS
```

### 后端开发

从仓库根目录进入后端：

```bash
cd backend
uv sync --python 3.11 --frozen --group test
uv run --no-sync uvicorn backend.main:app --host 127.0.0.1 --port 8002 --reload
```

`uv sync` 使用可编辑安装，源码包名为 `backend`。已有 GPU 环境时可从仓库根目录执行 `python -m pip install -e ./backend`，用该环境启动服务；模型依赖另行准备。

### 前端开发

在另一个终端，从仓库根目录执行：

```bash
cd frontend
pnpm --config.strictDepBuilds=false install --frozen-lockfile --ignore-scripts
pnpm --filter @yolo-mcp/frontend run postinstall
pnpm --filter @yolo-mcp/frontend start --host 127.0.0.1
```

打开 `http://127.0.0.1:3004`。Vite 将 API、WebSocket 和 MCP 请求转发到后端 `8002` 端口。

### 检查

在 `backend/` 下执行：

```bash
uv run --no-sync black --check .
uv run --no-sync flake8 .
uv run --no-sync pytest
```

后端测试使用隔离 SQLite 和临时数据目录。在 `frontend/` 下执行：

```bash
pnpm --filter @yolo-mcp/frontend test:unit
pnpm --filter @yolo-mcp/frontend type-check
pnpm lint 'apps/frontend/src/**/*.{ts,tsx}'
pnpm build:frontend
```

### 构建发行包

准备好前端依赖后，在仓库根目录执行：

```bash
uv build --project backend --out-dir dist
```

构建会重新编译前端，将页面写入源码包与 wheel。PyPI 介绍自动读取根 README，图片和文档链接转换为 GitHub 绝对地址。从源码包构建 wheel 无需 Node.js；可编辑安装跳过前端编译。

在目标环境安装生成的 wheel：

```bash
python -m pip install ./dist/yolo_mcp-2.0.3-py3-none-any.whl
yolo-mcp --host 127.0.0.1 --port 8000
```
