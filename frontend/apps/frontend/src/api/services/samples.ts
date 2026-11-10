import request from '../request';
import {
  type AutoLabelJobResponse,
  type DeleteApiV1ProjectsProjectIdDeleteParams,
  type DeleteSampleCommand,
  type GetApiV1ProjectsProjectIdSamplesSampleIdGetParams,
  type GetPreApiV1ProjectsProjectIdSamplesSampleIdPreGetParams,
  type ListByApiV1ProjectsProjectIdSamplesGetParams,
  type OkRespCommonDataResp,
  type OkRespCreateSampleResponse,
  type OkRespAutoLabelResponse,
  type OkRespSampleResponse,
  type PatchSampleCommand,
  type SampleData,
  type SampleListResponse,
  type SampleResponse,
  type UpdateApiV1ProjectsProjectIdSamplesSampleIdPatchParams,
} from '../types';

export async function createSamples(
  projectId: number,
  data: {
    file_id: number;
    data: SampleData;
  }[],
): Promise<OkRespCreateSampleResponse> {
  return await request.post(`/v1/projects/${projectId}/samples`, data);
}

export async function getSamples({
  project_id,
  ...params
}: ListByApiV1ProjectsProjectIdSamplesGetParams): Promise<SampleListResponse> {
  return await request.get(`/v1/projects/${project_id}/samples`, {
    params: {
      ...params,
      page: typeof params.page === 'undefined' ? 0 : params.page - 1,
    },
  });
}

export async function getSample({
  project_id,
  sample_id,
}: GetApiV1ProjectsProjectIdSamplesSampleIdGetParams): Promise<OkRespSampleResponse> {
  return await request.get(`/v1/projects/${project_id}/samples/${sample_id}`);
}

export async function updateSampleState(
  { project_id, sample_id, ...params }: UpdateApiV1ProjectsProjectIdSamplesSampleIdPatchParams,
  body: PatchSampleCommand,
): Promise<SampleResponse> {
  return await request.patch(`/v1/projects/${project_id}/samples/${sample_id}`, body, {
    params: {
      sample_id,
      ...params,
    },
  });
}

export async function updateSampleAnnotationResult(
  projectId: number,
  sampleId: number,
  data: SampleResponse,
): Promise<SampleResponse> {
  return await request.patch(
    `/v1/projects/${projectId}/samples/${sampleId}`,
    {
      data: data.data,
      state: data.state,
      annotated_count: data.annotated_count,
    },
    {
      params: {
        sample_id: sampleId,
      },
    },
  );
}

export async function autoLabelSample(projectId: number, sampleId: number): Promise<OkRespAutoLabelResponse> {
  return await request.post(`/v1/projects/${projectId}/samples/${sampleId}/auto_label`, undefined, {
    timeout: 5 * 60 * 1000,
    params: {
      sample_id: sampleId,
    },
  });
}

export async function createAutoLabelJob(projectId: number): Promise<{ data: AutoLabelJobResponse }> {
  return await request.post(`/v1/projects/${projectId}/auto_label_job`);
}

export async function getAutoLabelJobStatus(projectId: number, jobId: number): Promise<{ data: AutoLabelJobResponse }> {
  return await request.get(`/v1/projects/${projectId}/auto_label_job/${jobId}`);
}

export async function deleteSamples(
  { project_id }: DeleteApiV1ProjectsProjectIdDeleteParams,
  body: DeleteSampleCommand,
): Promise<OkRespCommonDataResp> {
  return await request.delete(`/v1/projects/${project_id}/samples`, {
    data: body,
  });
}

export async function getPreSample({
  sample_id,
  project_id,
}: GetPreApiV1ProjectsProjectIdSamplesSampleIdPreGetParams): Promise<OkRespSampleResponse> {
  return await request.get(`/v1/projects/${project_id}/samples/${sample_id}/pre`);
}
