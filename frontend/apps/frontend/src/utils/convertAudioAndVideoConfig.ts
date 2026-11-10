import type { MediaAnnotatorConfig } from '@yolo-mcp/audio-annotator-react';

import type { ToolsConfigState } from '@/types/toolConfig';

export function convertAudioAndVideoConfig(projectConfig?: ToolsConfigState) {
  const editorConfig: MediaAnnotatorConfig = {} as MediaAnnotatorConfig;

  projectConfig?.tools?.forEach((item) => {
    if (['videoSegmentTool', 'audioSegmentTool'].includes(item.tool)) {
      editorConfig.segment = [...(editorConfig.segment ?? []), ...(item.config.attributes ?? [])];

      if (projectConfig.attributes) {
        editorConfig.segment = [...editorConfig.segment, ...projectConfig.attributes];
      }
    }

    if (['videoFrameTool', 'audioFrameTool'].includes(item.tool)) {
      editorConfig.frame = [...(editorConfig.frame ?? []), ...(item.config.attributes ?? [])];

      if (projectConfig.attributes) {
        editorConfig.frame = [...editorConfig.frame, ...projectConfig.attributes];
      }
    }

    if (item.tool === 'tagTool') {
      editorConfig.tag = item.config.attributes;
    }

    if (item.tool === 'textTool') {
      editorConfig.text = item.config.attributes;
    }
  });

  return editorConfig;
}
