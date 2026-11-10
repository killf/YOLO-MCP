import { InfoCircleOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router';
import { Button } from 'antd';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useTranslation } from '@yolo-mcp/i18n';

import { ProjectStatus } from '@/api/types';

const GoToEditProject = (props: any) => {
  const { t } = useTranslation();
  const { projectStatus } = props;
  const navigate = useNavigate();
  const routeParams = useParams();
  const projectId = +routeParams.projectId!;

  const handleConfigClick = () => {
    if (projectId > 0) {
      let tail = 'basic';
      switch (projectStatus) {
        case ProjectStatus.DRAFT:
          tail = 'basic';
          break;
        case ProjectStatus.IMPORTED:
        case ProjectStatus.CONFIGURED:
          tail = 'config';
          break;
      }
      navigate('/projects/' + projectId + '/edit#' + tail);
    }
  };

  return (
    <FlexLayout items="center" gap=".5rem">
      <InfoCircleOutlined style={{ color: '#F5483B' }} />
      <div>{t('configBeforeStart')}</div>
      <Button type="primary" ghost onClick={handleConfigClick}>
        {t('configProject')}
      </Button>
    </FlexLayout>
  );
};
export default GoToEditProject;
