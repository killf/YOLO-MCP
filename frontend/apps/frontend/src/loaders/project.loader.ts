import type { LoaderFunctionArgs } from 'react-router';

import { sampleKey, projectKey } from '@/api/queryKeyFactories';
import { getProjectList, getProject } from '@/api/services/project';
import queryClient from '@/api/queryClient';
import { getSamples } from '@/api/services/samples';
import type { ListByApiV1ProjectsProjectIdSamplesGetParams, SampleListResponse, ProjectResponseWithStatics } from '@/api/types';
import type { ToolsConfigState } from '@/types/toolConfig';

export async function projectsLoader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const searchParams = new URLSearchParams(url.search);
  const queryParams = Object.fromEntries(searchParams.entries());

  if (searchParams.has('clientId')) {
    return null;
  }

  return await queryClient.fetchQuery({
    queryKey: projectKey.list(queryParams),
    queryFn: () => getProjectList(queryParams),
  });
}

export type ProjectInLoader = Omit<ProjectResponseWithStatics, 'config'> & {
  config: ToolsConfigState;
};

export interface ProjectLoaderResult {
  samples?: SampleListResponse;
  project?: ProjectInLoader;
}

export async function projectLoader({ params, request }: LoaderFunctionArgs) {
  const result: ProjectLoaderResult = {
    samples: undefined,
    project: undefined,
  };

  // projectId 为 0 时，表示新建项目
  if (!params?.projectId || params.projectId === '0') {
    return result;
  }

  const url = new URL(request.url);
  const searchParams = new URLSearchParams(url.search);
  const queryParams = {
    project_id: +params.projectId,
    ...Object.fromEntries(searchParams.entries()),
  } as ListByApiV1ProjectsProjectIdSamplesGetParams;

  // project page
  if (params.projectId && !params.sampleId && !queryParams.size) {
    queryParams.size = 10;
  }

  const sampleQueryKey = sampleKey.list(queryParams);

  result.samples = await queryClient.fetchQuery({
    queryKey: sampleQueryKey,
    queryFn: () => getSamples(queryParams),
  });

  const projectDetail = await queryClient.fetchQuery({
    queryKey: projectKey.detail(params.projectId),
    queryFn: () => getProject(+params.projectId!),
  });

  if (projectDetail?.data) {
    result.project = {
      ...projectDetail.data,
      config: projectDetail.data.config ? JSON.parse(projectDetail.data.config) : null,
    };
  }

  return result;
}
