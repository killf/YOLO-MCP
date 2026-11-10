# YOLO MCP 前端工作区

![YOLO MCP](./images/yolo-mcp-logo.svg)

YOLO MCP 的管理页面、标注组件和示例。上游来源与许可证说明见[根 README](../README.md#致谢)。

`@yolo-mcp/*` 是本仓库的本地包，使用 `workspace:*` 引用；未发布到 npm。开发和生产构建均使用工作区源码。

```bash
pnpm --config.strictDepBuilds=false install --frozen-lockfile --ignore-scripts
pnpm --filter @yolo-mcp/frontend run postinstall
pnpm --filter @yolo-mcp/frontend start --host 127.0.0.1
# Production build
pnpm build:frontend
```

| Package | Description |
| --- | --- |
| [@yolo-mcp/image](./packages/image) | 图片标注引擎 |
| [@yolo-mcp/i18n](./packages/i18n) | 国际化语言包 |
| [@yolo-mcp/interface](./packages/interface) | 基础类型定义 |
| [@yolo-mcp/formatter](./packages/formatter) | 数据格式化 |
| [@yolo-mcp/components-react](./packages/components-react) | 基础 React 组件 |
| [@yolo-mcp/image-annotator-react](./packages/image-annotator-react) | 图片标注套件 |
| [@yolo-mcp/audio-react](./packages/audio-react) | 音频组件 |
| [@yolo-mcp/audio-annotator-react](./packages/audio-annotator-react) | 音频标注套件 |
| [@yolo-mcp/video-react](./packages/video-react) | 视频组件 |
| [@yolo-mcp/video-annotator-react](./packages/video-annotator-react) | 视频标注套件 |

Apache-2.0. See [LICENSE](./LICENSE).
