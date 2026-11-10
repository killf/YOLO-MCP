import type { ImageAnnotatorProps } from '@yolo-mcp/image-annotator-react';
import type { ToolName } from '@yolo-mcp/image';
import { TOOL_NAMES } from '@yolo-mcp/image';

import type { ToolsConfigState } from '@/types/toolConfig';

export function convertImageConfig(projectConfig?: ToolsConfigState) {
  const editorConfig: NonNullable<ImageAnnotatorProps['config']> = {
    showOrder: true,
  } as NonNullable<ImageAnnotatorProps['config']>;
  const commonLabels = projectConfig?.attributes ?? [];

  projectConfig?.tools?.forEach((item) => {
    const toolName = item.tool.replace(/Tool$/, '') as ToolName | 'tag' | 'text';

    if (TOOL_NAMES.includes(toolName as ToolName)) {
      if (!editorConfig[toolName]) {
        editorConfig[toolName] = {} as any;
      }

      // @ts-ignore
      editorConfig[toolName] = {
        labels: [...commonLabels, ...(item.config.attributes ?? [])],
        // @ts-ignore
        outOfImage: Boolean(projectConfig.drawOutsideTarget),
      };

      if (toolName === 'line') {
        editorConfig.line!.edgeAdsorptive = Boolean(item.config.edgeAdsorption);
        editorConfig.line!.lineType = item.config.lineType === 0 ? 'line' : 'spline';
        editorConfig.line!.minPointAmount = item.config.lowerLimitPointNum;
        editorConfig.line!.maxPointAmount = item.config.upperLimitPointNum;
        editorConfig.line!.style = {
          ...editorConfig.line!.style,
          arrowType: item.config.arrowType,
        };
      }

      if (toolName === 'relation') {
        editorConfig.relation!.style = {
          lineStyle: item.config.lineStyle,
          arrowType: item.config.arrowType,
        };
      }

      if (toolName === 'point') {
        editorConfig.point!.maxPointAmount = item.config.upperLimit;
      }

      if (toolName === 'rect') {
        editorConfig.rect!.minWidth = item.config.minWidth;
        editorConfig.rect!.minHeight = item.config.minHeight;
      }

      if (toolName === 'polygon') {
        editorConfig.polygon!.edgeAdsorptive = Boolean(item.config.edgeAdsorption);
        editorConfig.polygon!.lineType = item.config.lineType === 0 ? 'line' : 'spline';

        editorConfig.polygon!.minPointAmount = item.config.lowerLimitPointNum;
        editorConfig.polygon!.maxPointAmount = item.config.upperLimitPointNum;
      }
    }

    if (toolName === 'tag') {
      editorConfig.tag = item.config.attributes;
    }

    if (toolName === 'text') {
      editorConfig.text = item.config.attributes;
    }
  });

  return editorConfig;
}
