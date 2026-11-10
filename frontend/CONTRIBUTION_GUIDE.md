# YOLO MCP 前端开发

项目说明和参考项目见[根 README](../README.md)，工作区启动与构建命令见[前端 README](./README.md)。

## 目录与依赖

- `apps/frontend`：管理、数据源、项目与标注页面。
- `apps/website`：组件示例页面。
- `packages/*`：`@yolo-mcp/*` 标注引擎、React 组件、共享类型及语言包。

内部包通过 `workspace:*` 引用本地源码，不发布到 npm。示例子目录通过 `file:` 引用本地包。修改包名时同步更新导入、脚本和锁文件。

## 验证

按修改范围检查代码与构建；后端测试从 `backend/` 目录运行。完整 TypeScript 检查的既有问题见根 README，不在无关修改中扩展清理。

本项目不接入 CI 或自动 Review；不包含上游发布、在线体验部署或外部统计上报流程。
