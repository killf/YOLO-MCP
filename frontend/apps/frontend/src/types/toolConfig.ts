import type { Attribute } from '@yolo-mcp/interface';

export interface ToolsConfigState {
  tools: any[];
  tagList: any[];
  attributes: Attribute[];
  textConfig: any;
  commonAttributeConfigurable: boolean;
}
