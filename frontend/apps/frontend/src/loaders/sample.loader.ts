import type { LoaderFunctionArgs } from 'react-router';

import queryClient from '@/api/queryClient';
import { sampleKey } from '@/api/queryKeyFactories';
import { getSample } from '@/api/services/samples';
import { preAnnotationKey } from '@/api/queryKeyFactories/preAnnotation';
import { getPreAnnotations } from '@/api/services/preAnnotations';

export async function sampleLoader({ params }: LoaderFunctionArgs) {
  const queryKey = sampleKey.detail(params.sampleId!);

  const result: {
    sample: Awaited<ReturnType<typeof getSample>> | undefined;
    preAnnotation: Awaited<ReturnType<typeof getPreAnnotations>> | undefined;
  } = {
    sample: undefined,
    preAnnotation: undefined,
  };

  result.sample = await queryClient.fetchQuery({
    queryKey,
    queryFn: () =>
      getSample({
        sample_id: +params.sampleId!,
        project_id: +params.projectId!,
      }),
  });

  const preAnnotationQueryKey = preAnnotationKey.listWithSampleName({
    project_id: +params.projectId!,
    sample_name: result?.sample?.data?.file?.filename,
  });

  result.preAnnotation = await queryClient.fetchQuery({
    queryKey: preAnnotationQueryKey,
    queryFn: () =>
      getPreAnnotations({
        project_id: +params.projectId!,
        sample_name: result?.sample?.data?.file?.filename,
      }),
  });

  return result;
}
