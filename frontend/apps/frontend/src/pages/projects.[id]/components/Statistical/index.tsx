import { SettingOutlined } from '@ant-design/icons';
import { useNavigate, useRouteLoaderData, useSearchParams } from 'react-router-dom';
import { Button } from 'antd';
import _ from 'lodash-es';
import styled from 'styled-components';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useTranslation } from '@yolo-mcp/i18n';

import type { ProjectLoaderResult } from '@/loaders/project.loader';
import type { DatasetSplit } from '@/api/types';
import useMe from '@/hooks/useMe';

import commonController from '../../../../utils/common';
import CollaboratorPortal from '../CollaboratorModal';

const Circle = styled.div<{
  color: string;
}>`
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: ${({ color }) => color};
`;

export interface ProjectStatusProps {
  status?: 'done' | 'new' | 'skipped';
  count?: number;
}

export function ProjectStatus({ children, status, count }: React.PropsWithChildren<ProjectStatusProps>) {
  const { t } = useTranslation();
  const colorMapping = {
    done: 'var(--color-primary)',
    new: 'var(--color-text-tertiary)',
    skipped: 'var(--orange)',
  };

  const textMapping = {
    done: t('annotated'),
    new: t('new'),
    skipped: t('skipped'),
  };

  const color = status ? colorMapping[status] : colorMapping.new;
  const title = status ? textMapping[status] : children;

  return (
    <FlexLayout items="center" gap=".5rem">
      {status && <Circle color={color} />}
      <b>{title}</b>
      {count !== undefined && <b>{count}</b>}
    </FlexLayout>
  );
}

const Statistical = ({ children }: React.PropsWithChildren) => {
  const routerLoaderData = useRouteLoaderData('project') as ProjectLoaderResult;
  const projectData = routerLoaderData.project;
  const { stats = {} } = projectData || {};
  const projectId = _.get(projectData, 'id');
  const { t } = useTranslation();
  const me = useMe();
  const isMeTheCreator = !!me.data?.is_admin || projectData?.created_by?.id === me.data?.id;

  const samples = routerLoaderData.samples;

  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedSplit = searchParams.get('split');
  const selectedState = searchParams.get('state');

  const filterSplit = (split?: DatasetSplit) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      if (split && selectedSplit !== split) next.set('split', split);
      else next.delete('split');
      if (!split) next.delete('state');
      next.set('page', '1');
      next.delete('after');
      next.delete('before');
      return next;
    });
  };

  const filterState = (state: string) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      if (selectedState === state) next.delete('state');
      else next.set('state', state);
      next.set('page', '1');
      next.delete('after');
      next.delete('before');
      return next;
    });
  };

  const handleGoAnnotation = () => {
    if (!samples || samples.data.length === 0) {
      return;
    }

    navigate(`/projects/${projectId}/samples/${samples.data[0].id}`);
  };
  const handleGoConfig = () => {
    navigate(`/projects/${projectId}/edit#config`);
  };
  const handleGoUpload = () => {
    navigate(`/projects/${projectId}/edit#upload`);
  };

  return (
    <FlexLayout justify="space-between" items="center" gap=".75rem 1rem" style={{ flexWrap: 'wrap' }}>
      <FlexLayout items="center" gap="1.5rem" style={{ flexWrap: 'wrap', whiteSpace: 'nowrap' }}>
        <b>{t('dataOverview')}</b>
        {(['done', 'new', 'skipped'] as const).map((status) => (
          <Button
            key={status}
            type={selectedState === status.toUpperCase() ? 'primary' : 'text'}
            ghost={selectedState === status.toUpperCase()}
            size="small"
            aria-pressed={selectedState === status.toUpperCase()}
            onClick={() => filterState(status.toUpperCase())}
          >
            <ProjectStatus status={status} count={stats[status]} />
          </Button>
        ))}
        <Button type="text" size="small" aria-pressed={!selectedSplit && !selectedState} onClick={() => filterSplit()}>
          <ProjectStatus count={(stats.done ?? 0) + (stats.new ?? 0) + (stats.skipped ?? 0)}>
            {t('total')}
          </ProjectStatus>
        </Button>
        <Button
          type={selectedSplit === 'train' ? 'primary' : 'text'}
          ghost={selectedSplit === 'train'}
          size="small"
          aria-pressed={selectedSplit === 'train'}
          onClick={() => filterSplit('train')}
        >
          <ProjectStatus count={stats.train ?? 0}>{t('trainingSamples')}</ProjectStatus>
        </Button>
        <Button
          type={selectedSplit === 'test' ? 'primary' : 'text'}
          ghost={selectedSplit === 'test'}
          size="small"
          aria-pressed={selectedSplit === 'test'}
          onClick={() => filterSplit('test')}
        >
          <ProjectStatus count={stats.test ?? 0}>{t('testSamples')}</ProjectStatus>
        </Button>
      </FlexLayout>
      <FlexLayout gap=".5rem">
        {isMeTheCreator && <CollaboratorPortal />}
        {isMeTheCreator && (
          <Button type="text" icon={<SettingOutlined />} onClick={handleGoConfig}>
            {t('projectConfig')}
          </Button>
        )}
        <Button type="primary" ghost onClick={handleGoUpload}>
          {t('uploadImages')}
        </Button>
        <Button type="primary" onClick={commonController.debounce(handleGoAnnotation, 100)}>
          {t('startAnnotate')}
        </Button>
        {children}
      </FlexLayout>
    </FlexLayout>
  );
};
export default Statistical;
