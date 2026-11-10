import type { ListByApiV1ProjectsProjectIdSamplesGetParams } from '../types';

// 数据样本
export const sampleKey = {
  all: ['sampleKey'] as const,
  lists: () => [...sampleKey.all, 'list'] as const,
  list: (filter: ListByApiV1ProjectsProjectIdSamplesGetParams) => [...sampleKey.lists(), filter] as const,
  details: () => [...sampleKey.all, 'details'] as const,
  detail: (id: string | number) => [...sampleKey.details(), id] as const,
};
