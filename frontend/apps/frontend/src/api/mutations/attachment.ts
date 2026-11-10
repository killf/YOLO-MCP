import { useMutation } from '@tanstack/react-query';

import { uploadFile } from '@/api/services/project';

export function useUploadFileMutation() {
  return useMutation({
    mutationFn: uploadFile,
  });
}
