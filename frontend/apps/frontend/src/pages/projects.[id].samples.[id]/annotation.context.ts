import type { Dispatch, SetStateAction } from 'react';
import React from 'react';

import type { SampleResponse } from '@/api/types';
import type { ProjectLoaderResult } from '@/loaders/project.loader';

import type { ProjectSampleUser } from '../../hooks/useSampleWs';

export interface AnnotationContextValue {
  samples: SampleResponse[];
  project: ProjectLoaderResult['project'];
  setSamples: Dispatch<SetStateAction<SampleResponse[]>>;
  isEnd: boolean;

  currentEditingUser: ProjectSampleUser;
  projectConnections: ProjectSampleUser[];
}

const AnnotationContext = React.createContext<AnnotationContextValue>({} as AnnotationContextValue);

export default AnnotationContext;
