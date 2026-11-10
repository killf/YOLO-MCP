import React from 'react';
import type { FormInstance } from 'antd';

import type { ProjectInLoader } from '@/loaders/project.loader';

import type { QueuedFile } from './partials/InputData';

export interface ProjectCreationContextValue {
  project?: ProjectInLoader;
  uploadFileList: QueuedFile[];
  setUploadFileList: React.Dispatch<React.SetStateAction<QueuedFile[]>>;
  annotationFormInstance: FormInstance;
  basicFormInstance: FormInstance;
  modelFormInstance: FormInstance;
  onAnnotationFormChange: () => void;
  selectedTemplate: unknown;
  onTemplateSelect: (template: unknown) => void;
}

export const ProjectCreationContext = React.createContext<ProjectCreationContextValue>({} as ProjectCreationContextValue);
