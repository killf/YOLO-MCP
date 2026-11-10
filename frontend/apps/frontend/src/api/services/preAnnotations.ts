import request from '../request';
import type { ListByApiV1ProjectsProjectIdSamplesGetParams, PreAnnotationListResponse } from '../types';

export async function getPreAnnotations({
  project_id,
  ...params
}: ListByApiV1ProjectsProjectIdSamplesGetParams & {
  sample_name?: string;
}): Promise<PreAnnotationListResponse> {
  return await request.get(`/v1/projects/${project_id}/pre_annotations`, {
    params: {
      ...params,
      page: typeof params.page === 'undefined' ? 0 : params.page - 1,
    },
  });
}
