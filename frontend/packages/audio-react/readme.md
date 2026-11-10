# @yolo-mcp/audio-react

> 本目录属于 YOLO MCP 本地工作区，`@yolo-mcp/*` 未发布到 npm。请在 `frontend/` 目录安装依赖；项目来源见仓库根 README。


## 安装

```bash
pnpm install --frozen-lockfile --ignore-scripts
```

## 使用

> [example](./src/example)

```tsx
import React from 'react';
import Audio from '@yolo-mcp/audio-react';

function App() {
  const [annotations, setAnnotations] = useState([]);
  return (
    <AudioAnnotator
      editingLabel="abc"
      src="https://exmaple/audio.mp3"
      editingType="segment"
      annotations={annotations}
      toolConfig={{
        segment: [
          {
            type: 'segment',
            attributes: [
              {
                color: '#ff0000',
                type: 'string',
                key: 'label',
                value: 'abc',
              },
            ],
          },
        ],
      }}
      onChange={setAnnotations}
    />
  );
}
```

## API

[Documentation](https://github.com/killf/LabelS#readme)
