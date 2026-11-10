import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { Button } from 'antd';
import { useTranslation } from '@yolo-mcp/i18n';
import { FlexLayout } from '@yolo-mcp/components-react';

import { ReactComponent as CreateProjectIcon } from '@/assets/svg/create-project.svg';

const Wrapper = styled(FlexLayout.Item)`
  display: flex;
  flex-direction: column;
  width: 288px;
  height: 220px;
  background: #fbfcff;
  border: 1px dashed #d0dfff;
  border-radius: 8px;
  justify-content: center;
  align-items: center;
  cursor: pointer;
`;

const NullProject = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const createProject = () => {
    navigate('/projects/0/edit?isNew=true');
  };

  return (
    <FlexLayout flex="column" full items="center" justify="center">
      <Wrapper data-wiz="project-create" onClick={createProject} gap="1rem">
        <CreateProjectIcon />
        <Button type="primary">{t('createProject')}</Button>
      </Wrapper>
    </FlexLayout>
  );
};
export default NullProject;
