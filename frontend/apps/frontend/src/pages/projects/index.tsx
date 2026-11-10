import { Alert, Button, Pagination, Popover } from 'antd';
import { useNavigate, useRouteLoaderData, useSearchParams } from 'react-router-dom';
import _ from 'lodash';
import styled from 'styled-components';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useTranslation } from '@yolo-mcp/i18n';

import type { getProjectList } from '@/api/services/project';
import { ResponsiveGrid } from '@/components/ResponsiveGrid';

import ProjectCard from './components/projectCard';
import NullProject from './components/nullProject';

const Wrapper = styled(FlexLayout)`
  height: calc(100vh - var(--header-height));
  padding: 0 1.5rem;
  box-sizing: border-box;
`;

const CardsWrapper = styled(ResponsiveGrid)`
  height: 100%;
`;

const Header = styled(FlexLayout.Header)`
  padding: 1rem 0;
`;

const Footer = styled(FlexLayout.Footer)`
  padding: 1rem 0;
`;

const AppVersion = styled(FlexLayout.Footer)`
  text-align: center;
  color: var(--color-text-tertiary);
`;

const ProjectCardItem = styled(ProjectCard)``;

const ProjectList = () => {
  const navigate = useNavigate();
  const routerLoaderData = useRouteLoaderData('projects') as Awaited<ReturnType<typeof getProjectList>>;
  const projectsResponse = routerLoaderData?.data;
  const projects = projectsResponse?.data ?? [];
  const meta_data = projectsResponse?.meta_data;
  const labelsVersion = _.get(routerLoaderData, ['headers', 'yolo-mcp-version']);
  const { t } = useTranslation();

  const [searchParams, setSearchParams] = useSearchParams();
  const finalPageSize = searchParams.get('size') ? +searchParams.get('size')! : 16;

  const createProject = () => {
    navigate('/projects/0/edit?isNew=true');
  };

  const versionInfo = (
    <div>
      frontend: {_.get(window.__frontend, 'version', 'unknown')}
      <br />
      {_.chain(window.__frontend.deps)
        .keys()
        .map((key) => {
          return (
            <div key={key}>
              {key}: {window.__frontend.deps[key]}
            </div>
          );
        })
        .value()}
    </div>
  );

  return (
    <Wrapper flex="column">
      <FlexLayout.Content scroll flex="column">
        {window.IS_ONLINE && (
          <Alert
            type="info"
            style={{
              marginTop: '1rem',
            }}
            showIcon
            message={
              <div>
                {t('demoTips')}
                <a
                  data-wiz="local-deploy-alert"
                  href="https://github.com/killf/LabelS#readme"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t('localDeploy')}
                </a>
              </div>
            }
          />
        )}
        {projects.length > 0 && (
          <Header>
            <Button type="primary" onClick={createProject}>
              {t('Create Project')}
            </Button>
          </Header>
        )}
        <FlexLayout.Content scroll>
          {meta_data && meta_data?.total > 0 ? (
            <CardsWrapper>
              {projects.map((cardInfo: any, cardInfoIndex: number) => {
                return <ProjectCardItem key={cardInfoIndex} cardInfo={cardInfo} />;
              })}
            </CardsWrapper>
          ) : (
            <NullProject />
          )}
        </FlexLayout.Content>
      </FlexLayout.Content>
      <Footer flex="row" items="flex-between" justify="space-between">
        <AppVersion>
          <Popover content={versionInfo}>YOLO MCP @{labelsVersion}</Popover>
        </AppVersion>
        {meta_data && searchParams && meta_data?.total > finalPageSize && (
          <Pagination
            defaultCurrent={searchParams.get('page') ? +searchParams.get('page')! : 1}
            total={meta_data?.total ?? 0}
            pageSize={finalPageSize}
            onChange={(value: number, _pageSize: number) => {
              searchParams.set('size', String(_pageSize));
              searchParams.set('page', String(value));
              setSearchParams(searchParams);
            }}
          />
        )}
      </Footer>
    </Wrapper>
  );
};

export default ProjectList;
