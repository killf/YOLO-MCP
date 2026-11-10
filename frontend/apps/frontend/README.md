# YOLO MCP 管理与标注页面

在 `frontend/` 工作区安装和运行：

```bash
pnpm --config.strictDepBuilds=false install --frozen-lockfile --ignore-scripts
pnpm --filter @yolo-mcp/frontend run postinstall
pnpm --filter @yolo-mcp/frontend start --host 127.0.0.1
pnpm build:frontend
```

开发页面使用 3004 端口，API 与 WebSocket 代理至 `127.0.0.1:8002`。后端启动、存储配置和参考项目见[根 README](../../../README.md)。
