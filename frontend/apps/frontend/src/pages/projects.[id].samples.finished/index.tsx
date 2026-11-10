import { CheckOutlined } from '@ant-design/icons';
import { useNavigate, useParams, useRevalidator, useRouteLoaderData } from 'react-router';
import { Button } from 'antd';
import styled from 'styled-components';
import { useTranslation } from '@yolo-mcp/i18n';
import { FlexLayout } from '@yolo-mcp/components-react';

import type { ProjectLoaderResult } from '@/loaders/project.loader';

const Wrapper = styled(FlexLayout)`
  background: #fff;
  height: calc(100vh - var(--header-height));
`;

const Inner = styled(FlexLayout.Item)`
  width: 312px;
  height: 290px;
`;

const CircleCheck = styled(FlexLayout.Item)`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background-color: var(--color-success-bg);
`;

const Statistic = styled(FlexLayout)`
  font-size: 1rem;
`;

const ButtonWrapper = styled(FlexLayout)`
  button {
    padding: 0.375rem 2.5rem !important;
    height: 3rem !important;
  }
`;

const SamplesFinished = () => {
  const { project: projectData } = useRouteLoaderData('project') as ProjectLoaderResult;
  const routeParams = useParams();
  const projectId = +routeParams.projectId!;
  const navigate = useNavigate();
  const revalidator = useRevalidator();
  const handleGoHome = () => {
    navigate(`/projects/${projectId}?t=${Date.now()}`);
    setTimeout(revalidator.revalidate);
  };
  const { t } = useTranslation();

  return (
    <Wrapper flex="column" items="center" justify="center">
      <Inner flex="column" justify="space-between" items="center">
        <CircleCheck items="center" justify="center" flex>
          <CheckOutlined style={{ color: 'var(--color-success)', fontSize: '40px' }} />
        </CircleCheck>
        <h1>{t('finished')}</h1>
        <Statistic>
          <div>
            {t('annotated')} {projectData?.stats?.done}，
          </div>
          <div>
            {t('unannotated')} <span style={{ color: 'red' }}>{projectData?.stats?.new}</span>，
          </div>
          <div>
            {t('skipped')} {projectData?.stats?.skipped}
          </div>
        </Statistic>
        <ButtonWrapper gap="1.5rem">
          <Button type="default" size="large" onClick={handleGoHome}>
            {t('backToSamples')}
          </Button>
        </ButtonWrapper>
      </Inner>
    </Wrapper>
  );
};

export default SamplesFinished;
