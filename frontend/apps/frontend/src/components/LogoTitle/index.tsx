import styled from 'styled-components';
import { useTranslation } from '@yolo-mcp/i18n';
import { FlexLayout } from '@yolo-mcp/components-react';

import { ReactComponent as Logo } from '@/assets/svg/LOGO.svg';

const Description = styled.span`
  text-align: center;
  color: var(--color-text-secondary);
`;

const LogoTitle = () => {
  const { t } = useTranslation();
  return (
    <FlexLayout flex="column" items="center" gap="1rem">
      <Logo />
      <Description>
        <div>{t('yoloMcpDescription')}</div>
        <div>{t('yoloMcpKeywords')}</div>
      </Description>
    </FlexLayout>
  );
};
export default LogoTitle;
