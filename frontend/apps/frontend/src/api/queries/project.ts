import { useQuery } from '@tanstack/react-query';

import { getProjectCollaborators } from '../services/project';
import { projectKey } from '../queryKeyFactories';

export function useCollaborators(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: projectKey.collaborators(),
    queryFn: () => getProjectCollaborators(projectId),
    enabled: enabled && projectId > 0,
    select: (data) => data?.data,
  });
}
