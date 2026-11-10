# YOLO MCP Frontend workspace

![YOLO MCP](./images/yolo-mcp-logo.svg)

YOLO MCP management pages, annotation components and examples. See the [root README](../README.md#致谢) for upstream projects and licenses.

`@yolo-mcp/*` packages are local to this repository, linked with `workspace:*`. They are not published on npm. Development and production builds use workspace sources.

```bash
pnpm --config.strictDepBuilds=false install --frozen-lockfile --ignore-scripts
pnpm --filter @yolo-mcp/frontend run postinstall
pnpm --filter @yolo-mcp/frontend start --host 127.0.0.1
# Production build
pnpm build:frontend
```

| Package | Description |
| --- | --- |
| [@yolo-mcp/image](./packages/image) | Image annotation engine |
| [@yolo-mcp/i18n](./packages/i18n) | Internationalization |
| [@yolo-mcp/interface](./packages/interface) | Shared types |
| [@yolo-mcp/formatter](./packages/formatter) | Data formatters |
| [@yolo-mcp/components-react](./packages/components-react) | Shared React components |
| [@yolo-mcp/image-annotator-react](./packages/image-annotator-react) | Image annotator |
| [@yolo-mcp/audio-react](./packages/audio-react) | Audio components |
| [@yolo-mcp/audio-annotator-react](./packages/audio-annotator-react) | Audio annotator |
| [@yolo-mcp/video-react](./packages/video-react) | Video components |
| [@yolo-mcp/video-annotator-react](./packages/video-annotator-react) | Video annotator |

Apache-2.0. See [LICENSE](./LICENSE).
