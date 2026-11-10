import { BulbOutlined } from '@ant-design/icons';
import { Button, Popover } from 'antd';
import { useRouteLoaderData } from 'react-router';
import { useTranslation } from '@yolo-mcp/i18n';

import type { ProjectLoaderResult } from '@/loaders/project.loader';

export default function ProjectTip({ visible }: { visible: boolean }) {
  const { project } = (useRouteLoaderData('project') ?? {}) as ProjectLoaderResult;
  const { t } = useTranslation();

  if (!visible) {
    return null;
  }

  return (
    <Popover content={<div style={{ maxWidth: 420 }}>{project?.tips ?? t('noneProjectTip')}</div>}>
      <Button type="link" style={{ color: 'rgba(0, 0, 0, 0.85)' }} icon={<BulbOutlined />}>
        {t('projectTip')}
      </Button>
    </Popover>
  );
}
