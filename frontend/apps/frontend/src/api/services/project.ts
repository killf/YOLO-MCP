import type { AxiosResponse } from 'axios';

import request, { requestWithHeaders } from '../request';
import type {
  BasicConfigCommand,
  OkRespCommonDataResp,
  OkRespProjectResponse,
  ProjectListResponseWithStatics,
  OkRespProjectResponseWithStatics,
  UpdateCommand,
  ListByApiV1ProjectsGetParams,
  OkRespAttachmentResponse,
  CreateApiV1ProjectsProjectIdAttachmentsPostParams,
  DeleteApiV1ProjectsProjectIdAttachmentsDeleteParams,
  AttachmentDeleteCommand,
  ListResponseWithMeta,
  UserResponse,
  OkResponse,
} from '../types';

export async function getProject(projectId: number): Promise<OkRespProjectResponseWithStatics> {
  return await request.get(`/v1/projects/${projectId}`, {
    params: {
      project_id: projectId,
    },
  });
}

export async function getProjectCollaborators(projectId: number): Promise<ListResponseWithMeta<UserResponse>> {
  return await request.get(`/v1/projects/${projectId}/collaborators`);
}

export async function removeCollaborator(projectId: number, userId: number) {
  return await request.delete(`/v1/projects/${projectId}/collaborators/${userId}`);
}

export async function addCollaborator(projectId: number, userId: number) {
  return await request.post(`/v1/projects/${projectId}/collaborators`, {
    user_id: userId,
  });
}

export async function batchAddCollaborators(projectId: number, userIds: number[]): Promise<OkResponse<UserResponse>> {
  return await request.post(`/v1/projects/${projectId}/collaborators/batch_add`, {
    user_ids: userIds,
  });
}

export async function batchRemoveCollaborators(projectId: number, userIds: number[]): Promise<OkRespCommonDataResp> {
  return await request.post(`/v1/projects/${projectId}/collaborators/batch_remove`, {
    user_ids: userIds,
  });
}

export async function createProjectWithBasicConfig(data: BasicConfigCommand): Promise<OkRespProjectResponse> {
  return await request.post('/v1/projects', data);
}

export async function uploadFile(
  params: CreateApiV1ProjectsProjectIdAttachmentsPostParams & {
    file: File;
  },
): Promise<OkRespAttachmentResponse> {
  const data = new FormData();

  if (params.file) {
    data.append('file', params.file);
  }

  return await request.post(`/v1/projects/${params.project_id}/attachments`, data, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
}

export async function deleteFile(
  { project_id, ...restParams }: DeleteApiV1ProjectsProjectIdAttachmentsDeleteParams,
  body: AttachmentDeleteCommand,
): Promise<OkRespCommonDataResp> {
  return await request.delete(`/v1/projects/${project_id}/attachments`, {
    params: restParams,
    data: body,
  });
}

export async function updateProjectConfig(
  projectId: number,
  projectConfig: UpdateCommand,
): Promise<OkRespProjectResponse> {
  return await request.patch(`/v1/projects/${projectId}`, projectConfig);
}

export async function getProjectList({
  page,
  ...params
}: ListByApiV1ProjectsGetParams): Promise<AxiosResponse<ProjectListResponseWithStatics>> {
  return await requestWithHeaders.get('/v1/projects', {
    timeout: 0,
    params: {
      size: 16,
      page: page ? page - 1 : 0,
      ...params,
    },
  });
}

export async function deleteProject(projectId: number): Promise<OkRespCommonDataResp> {
  return await request.delete(`/v1/projects/${projectId}`, {
    params: {
      project_id: projectId,
    },
  });
}

export async function getProjectModels(projectId: number, algorithm = 'yolo'): Promise<OkResponse<string[]>> {
  return await request.get(`/v1/projects/${projectId}/models`, { params: { algorithm } });
}
