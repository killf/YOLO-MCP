import styled from 'styled-components';
import { FlexLayout } from '@yolo-mcp/components-react';

import { ReactComponent as Logo } from '@/assets/svg/LOGO.svg';

export const NavigationWrapper = styled(FlexLayout)`
  height: var(--header-height);
  border-bottom: solid var(--color-border-secondary) 1px;
  box-sizing: border-box;
`;

export const YoloMcpLogo = styled(Logo)`
  width: 164px;
  height: 32px;
`;
