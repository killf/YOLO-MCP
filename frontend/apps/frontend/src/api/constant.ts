import { i18n } from '@yolo-mcp/i18n';

const COMMON_INIT_CODE = 30000;
const USER_INIT_CODE = 40000;
const PROJECT_INIT_CODE = 50000;
const EXPORT_INIT_CODE = 60000;

export const ErrorMessages = {
  400: i18n.t('queryParamsError'),
  [COMMON_INIT_CODE]: i18n.t('sqlError'),
  [COMMON_INIT_CODE + 1]: i18n.t('forbidden'),
  [COMMON_INIT_CODE + 2]: i18n.t('validationFailed'),
  [COMMON_INIT_CODE + 3]: i18n.t('badRequest'),
  [USER_INIT_CODE]: i18n.t('invalidUserOrPassword'),
  [USER_INIT_CODE + 1]: i18n.t('userExists'),
  [USER_INIT_CODE + 2]: i18n.t('userNotExists'),
  [USER_INIT_CODE + 3]: i18n.t('certError'),
  [USER_INIT_CODE + 4]: i18n.t('unauthorized'),
  [PROJECT_INIT_CODE]: i18n.t('serverError'),
  [PROJECT_INIT_CODE + 1]: i18n.t('projectIsDone'),
  [PROJECT_INIT_CODE + 2]: i18n.t('projectNotFound'),
  [PROJECT_INIT_CODE + 1000]: i18n.t('fileUploadFailed'),
  [PROJECT_INIT_CODE + 1001]: i18n.t('fileNotFound'),
  [PROJECT_INIT_CODE + 1002]: i18n.t('duplicatedFile'),
  [PROJECT_INIT_CODE + 5001]: i18n.t('noSample'),
  [PROJECT_INIT_CODE + 5003]: i18n.t('sampleNameExists'),
  [EXPORT_INIT_CODE + 1000]: i18n.t('noDataExport'),
} as const;
