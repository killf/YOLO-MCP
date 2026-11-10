import { useMutation } from '@tanstack/react-query';

import {
  addCollaborator,
  batchAddCollaborators,
  batchRemoveCollaborators,
  createProjectWithBasicConfig,
  removeCollaborator,
  updateProjectConfig,
} from '@/api/services/project';

import type { UpdateCommand } from '../types';

export function useAddProjectMutation() {
  return useMutation({
    mutationFn: createProjectWithBasicConfig,
  });
}

export function useUpdateProjectConfigMutation(projectId: number | string) {
  return useMutation({
    mutationFn: (payload: UpdateCommand) => updateProjectConfig(+projectId, payload),
  });
}

export function useAddCollaborator(projectId: number) {
  return useMutation({
    mutationFn: (userId: number) => addCollaborator(projectId, userId),
  });
}

export function useRemoveCollaborator(projectId: number) {
  return useMutation({
    mutationFn: (userId: number) => removeCollaborator(projectId, userId),
  });
}

export function useBatchAddCollaborators(projectId: number) {
  return useMutation({
    mutationFn: (userIds: number[]) => batchAddCollaborators(projectId, userIds),
  });
}

export function useBatchRemoveCollaborators(projectId: number) {
  return useMutation({
    mutationFn: (userIds: number[]) => batchRemoveCollaborators(projectId, userIds),
  });
}
