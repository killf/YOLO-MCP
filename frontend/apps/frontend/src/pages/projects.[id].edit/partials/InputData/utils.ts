import { v4 as uuid4 } from 'uuid';
import { i18n } from '@yolo-mcp/i18n';

import type { MediaType } from '@/api/types';
import { FileExtensionText } from '@/constants/mediaType';
import commonController from '@/utils/common';

export enum UploadStatus {
  Uploading = 'Uploading',
  Waiting = 'Waiting',
  Success = 'Success',
  Fail = 'Fail',
  Error = 'Error',
}

export const isCorrectFiles = (files: File[], type: MediaType) => {
  let result = true;

  for (let i = 0; i < files.length; i++) {
    const fileUnit = files[i];

    const isCorrectFileType = commonController.isCorrectFileType(fileUnit.name, type);

    if (!isCorrectFileType) {
      commonController.notificationErrorMessage({ message: `${i18n.t('fileTypeTips')}${FileExtensionText[type]}` }, 3);
      result = false;
      break;
    }
  }

  return result;
};

export const normalizeFiles = (files: File[]) => {
  return files.map((file) => {
    return {
      uid: uuid4(),
      name: file.name,
      size: file.size,
      status: UploadStatus.Waiting,
      file,
    };
  });
};
