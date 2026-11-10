# `@yolo-mcp/formatter`

> 本目录属于 YOLO MCP 本地工作区，`@yolo-mcp/*` 未发布到 npm。请在 `frontend/` 目录安装依赖；项目来源见仓库根 README。

A formatter set for sinan.

## Usage

```bash
pnpm install --frozen-lockfile --ignore-scripts
# or
pnpm install --frozen-lockfile --ignore-scripts
```

## basename

```typescript
import formatter from '@yolo-mcp/formatter';

formatter.format('basename', 'foo/bar/baz/asdf/quux.html');
// => 'quux.html'
```

## fileSize

> See more options in [filesize.js](https://github.com/avoidwork/filesize.js).

```typescript
import formatter from '@yolo-mcp/formatter';

formatter.format('fileSize', 265318);
// => '259.1 KB'
```

## date

> See more options in [dayjs](https://github.com/iamkun/dayjs).

```typescript
import formatter from '@yolo-mcp/formatter';

formatter.format('date', 1670916924956, {
  style: 'YYYY-MM-DD HH:mm',
});
// => '2022-12-13 15:36'
```

## extension

```typescript
import formatter from '@yolo-mcp/formatter';

formatter.format('extension', 'foo/bar/baz/asdf/quux.html');
// => 'html'
```

### Add Your Own Formatter

```typescript
import formatter from '@yolo-mcp/formatter';

formatter.add('foo', (value: string) => {
  return value + 'foo';
});
```
