import type { ListByApiV1ProjectsGetParams } from '../types';

// 标注项目
export const projectKey = {
  all: ['projectKey'] as const,
  lists: () => [...projectKey.all, 'list'] as const,
  list: (filter: ListByApiV1ProjectsGetParams) => [...projectKey.lists(), filter] as const,
  details: () => [...projectKey.all, 'details'] as const,
  detail: (id: string | number) => [...projectKey.details(), id] as const,
  collaborators: () => [...projectKey.all, 'collaborators'] as const,
};
