import React, { useState, useEffect, useMemo, useRef, useCallback, useLayoutEffect } from 'react';
import { Button, Form } from 'antd';
import { useLocation, useNavigate, useParams, useRevalidator, useRouteLoaderData } from 'react-router-dom';
import _, { filter, isEmpty, size } from 'lodash-es';
import { omit } from 'lodash/fp';
import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { Bridge } from 'iframe-message-bridge';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { useTranslation } from '@yolo-mcp/i18n';

import { parseTrainingParameters, trainingFormValues } from '@/components/TrainingConfigFields';
import { message, modal } from '@/StaticAnt';
import type { OkRespCreateSampleResponse, ProjectResponse } from '@/api/types';
import { MediaType, ProjectStatus } from '@/api/types';
import { createSamples, deleteSamples } from '@/api/services/samples';
import { deleteFile, deleteProject } from '@/api/services/project';
import { convertAudioAndVideoConfig } from '@/utils/convertAudioAndVideoConfig';
import type { ProjectLoaderResult } from '@/loaders/project.loader';
import { useAddProjectMutation, useUpdateProjectConfigMutation } from '@/api/mutations/project';
import { convertImageConfig } from '@/utils/convertImageConfig';
import type { ToolsConfigState } from '@/types/toolConfig';
import useMe from '@/hooks/useMe';

import type { QueuedFile } from './partials/InputData';
import InputData from './partials/InputData';
import AnnotationConfig from './partials/AnnotationConfig';
import InputInfoConfig from './partials/InputInfoConfig';
import ModelConfig from './partials/ModelConfig';
import type { StepData } from './components/Step';
import Step from './components/Step';
import commonController from '../../utils/common';
import { ProjectCreationContext } from './projectCreation.context';
import { ContentWrapper, PreviewFrame, StepRow } from './style';
import { UploadStatus } from './partials/InputData/utils';

enum StepEnum {
  Basic = 'basic',

  Upload = 'upload',

  Config = 'config',

  Model = 'model',
}

const partialMapping = {
  [StepEnum.Basic]: InputInfoConfig,
  [StepEnum.Upload]: InputData,
  [StepEnum.Config]: AnnotationConfig,
  [StepEnum.Model]: ModelConfig,
};

const StyledFooter = styled.div`
  display: flex;
  justify-content: end;
  margin-top: 1rem;
  gap: 0.5rem;
`;

function isContainEmptyOption(config: ToolsConfigState) {
  for (const tool of config.tools) {
    const attributes = tool.config?.attributes ?? [];

    if (!attributes || attributes.length === 0) {
      return 'attribute';
    }

    const toolName = tool.tool;

    // 检查全局工具里的属性是否有空选项
    if (['tagTool', 'textTool'].includes(toolName)) {
      for (const attribute of attributes) {
        if (attribute.type === 'enum' && attribute.options.length === 0) {
          return 'option';
        }
      }
    }

    for (const attribute of attributes) {
      if (Array.isArray(attribute.attributes)) {
        for (const subAttribute of attribute.attributes) {
          if (subAttribute.type === 'enum' && subAttribute.options.length === 0) {
            return 'option';
          }
        }
      }
    }
  }
}

interface ProjectStep extends StepData {
  value: StepEnum;
}

export interface PartialConfigProps {
  project: ProjectResponse;
  updateFormData: (field: string) => (value: string) => void;
}

const CreateProject = () => {
  const revalidator = useRevalidator();
  const routerLoaderData = useRouteLoaderData('project') as ProjectLoaderResult;
  const projectData = _.get(routerLoaderData, 'project');
  const me = useMe();
  const canManage = !!me.data?.is_admin || projectData?.created_by?.id === me.data?.id || !projectData?.id;
  const samples = _.get(routerLoaderData, 'samples');
  const toolsConfig = projectData?.config;
  const navigate = useNavigate();
  const routeParams = useParams();
  const location = useLocation();
  const [annotationFormInstance] = Form.useForm();
  const [basicFormInstance] = Form.useForm();
  const [modelFormInstance] = Form.useForm();
  const modalRef = useRef<any>(null);
  const previewIframeRef = useRef<HTMLIFrameElement>(null);
  const bridgeRef = useRef<Bridge | null>(null);
  const { t } = useTranslation();

  const projectId = routeParams.projectId ? parseInt(routeParams.projectId, 10) : 0;
  const isExistProject = projectId > 0;
  const [currentStep, setCurrentStep] = useState<StepEnum>(
    isExistProject && location.hash ? (location.hash.replace('#', '') as StepEnum) : StepEnum.Basic,
  );
  const searchParams = new URLSearchParams(location.search);
  const isCreateNewProject = searchParams.get('isNew') === 'true';
  const [isAnnotationFormValid, toggleAnnotationFormValidation] = useState<boolean>(true);

  const addProject = useAddProjectMutation();
  const updateProjectConfig = useUpdateProjectConfigMutation(projectId);

  const isFetching = useIsFetching();
  const isMutating = useIsMutating();

  // 缓存上传的文件清单
  const [uploadFileList, setUploadFileList] = useState<QueuedFile[]>([]);

  const updateCurrentStep = useCallback(
    (step: StepEnum) => {
      if (!canManage && step !== StepEnum.Upload) return;
      setCurrentStep(step);
      navigate({
        pathname: location.pathname,
        hash: step,
        search: location.search,
      });
    },
    [canManage, location.pathname, location.search, navigate],
  );

  const stepTitleMapping = useMemo(
    () => ({
      [StepEnum.Basic]: t('basicConfig'),
      [StepEnum.Upload]: t('uploadData'),
      [StepEnum.Config]: t('annotationConfig'),
      [StepEnum.Model]: '模型设置',
    }),
    [t],
  );

  const partials = useMemo(() => {
    // 新建时只挂载基础表单，其余步骤依赖已保存的项目。
    return _.chain(partialMapping)
      .toPairs()
      .filter(([key]) => isExistProject || key === StepEnum.Basic)
      .map(([key, Partial], index) => {
        return (
          <FlexLayout.Content key={index} style={{ display: currentStep === key ? 'flex' : 'none' }} flex="column">
            <Partial />
          </FlexLayout.Content>
        );
      })
      .value();
  }, [currentStep, isExistProject]);
  const loading = isMutating > 0 || isFetching > 0;
  const projectStatus = _.get(projectData, 'status') as ProjectStatus;
  const stepDataSource: ProjectStep[] = useMemo(
    () => [
      {
        title: stepTitleMapping[StepEnum.Basic],
        value: StepEnum.Basic,
        isFinished: isExistProject,
      },
      {
        title: stepTitleMapping[StepEnum.Upload],
        value: StepEnum.Upload,
        isFinished: projectStatus && projectStatus !== ProjectStatus.DRAFT,
      },
      {
        title: stepTitleMapping[StepEnum.Config],
        value: StepEnum.Config,
        isFinished: [ProjectStatus.CONFIGURED, ProjectStatus.FINISHED, ProjectStatus.INPROGRESS].includes(
          projectStatus,
        ),
      },
      {
        title: stepTitleMapping[StepEnum.Model],
        value: StepEnum.Model,
        isFinished: Boolean(projectData?.ai_model_name),
      },
    ],
    [isExistProject, stepTitleMapping, projectStatus, projectData?.ai_model_name],
  );

  useEffect(() => {
    if (!location.hash) {
      return;
    }

    setCurrentStep(isExistProject ? (location.hash.replace('#', '') as StepEnum) : StepEnum.Basic);
  }, [isExistProject, location.hash]);

  // 将store中的project toolConfig数据同步到本地页面中
  useEffect(() => {
    annotationFormInstance.setFieldsValue(toolsConfig);
  }, [annotationFormInstance, toolsConfig]);

  useEffect(() => {
    basicFormInstance.setFieldsValue(projectData);
    modelFormInstance.setFieldsValue({
      ai_algorithm: projectData?.ai_algorithm ?? 'yolo',
      ai_model_name: projectData?.ai_model_name,
      training_config: trainingFormValues(projectData?.training_config),
    });
  }, [annotationFormInstance, basicFormInstance, modelFormInstance, projectData]);

  useEffect(() => {
    if (isEmpty(toolsConfig?.tools)) {
      toggleAnnotationFormValidation(false);
    }
  }, [toolsConfig?.tools]);

  const onAnnotationFormChange = useCallback(() => {
    annotationFormInstance.validateFields().then((values) => {
      toggleAnnotationFormValidation(size(values.tools) > 0);
    });
  }, [annotationFormInstance]);

  const [template, setTemplate] = useState<unknown>(null);

  const handleSave = useCallback(
    async function (isFromCancel?: boolean) {
      try {
        await annotationFormInstance.validateFields();
      } catch (err) {
        commonController.notificationErrorMessage({ message: t('pleaseCheckToolConfig') }, 2);
        return;
      }

      const annotationConfig = annotationFormInstance.getFieldsValue();
      try {
        await modelFormInstance.validateFields();
      } catch {
        return;
      }
      const emptyType = isContainEmptyOption(annotationConfig);

      if (emptyType === 'attribute') {
        commonController.notificationErrorMessage({ message: t('mustHaveAtLeastOneAttribute') }, 2);
        return;
      }

      if (emptyType === 'option') {
        commonController.notificationErrorMessage({ message: t('mustHaveAtLeastOneOption') }, 2);
        return;
      }

      if (
        _.chain(annotationConfig).get('tools').isEmpty().value() &&
        currentStep === StepEnum.Config &&
        !isFromCancel
      ) {
        commonController.notificationErrorMessage({ message: t('pleaseSelectTool') }, 2);
        return;
      }

      return updateProjectConfig
        .mutateAsync({
          ...projectData,
          ...basicFormInstance.getFieldsValue(),
          ...modelFormInstance.getFieldsValue(),
          ai_model_name: modelFormInstance.getFieldValue('ai_model_name') ?? null,
          training_config: parseTrainingParameters(modelFormInstance.getFieldValue('training_config')),
          config: JSON.stringify(annotationConfig),
        })
        .then(() => {
          navigate(`/projects/${projectData!.id}`);
          revalidator.revalidate();
        });
    },
    [
      annotationFormInstance,
      basicFormInstance,
      modelFormInstance,
      currentStep,
      navigate,
      revalidator,
      t,
      projectData,
      updateProjectConfig,
    ],
  );

  const [previewVisible, setPreviewVisible] = useState(false);
  const handleOpenPreview = useCallback(() => {
    annotationFormInstance
      .validateFields()
      .then(() => {
        setPreviewVisible(true);
      })
      .catch(() => {
        commonController.notificationErrorMessage({ message: t('pleaseCheckToolConfig') }, 1);
      });
  }, [annotationFormInstance, t]);

  const updateFileQueue = useCallback((files: any[], sampleIds: number[] | undefined = []) => {
    const fileIdSampleIdMapping = _.chain(files)
      .map((item, index) => {
        return [item.file_id, sampleIds[index]];
      })
      .fromPairs()
      .value();

    setUploadFileList((prev) => {
      return prev.map((item) => {
        if (fileIdSampleIdMapping[item.id!]) {
          return {
            ...item,
            refId: fileIdSampleIdMapping[item.id!],
          };
        }
        return item;
      });
    });
  }, []);

  const correctSampleIdsMappings = useMemo(
    () =>
      _.chain(samples)
        .get('data')
        .mapKeys((item) => {
          return item.file?.id;
        })
        .value(),
    [samples],
  );

  const submitForm: (isFromCancel?: boolean) => Promise<unknown> = useCallback(
    async function (isFromCancel) {
      let basicFormValues;
      try {
        basicFormValues = await basicFormInstance.validateFields();
        await modelFormInstance.validateFields();
      } catch (err) {
        return Promise.reject();
      }

      const mediaFileList = [];

      for (const file of uploadFileList) {
        if (file.status === UploadStatus.Success && _.isNil(file.refId)) {
          mediaFileList.push({
            file_id: file.id!,
            data: {
              result: '{}',
            },
          });
        }
      }

      if (isExistProject) {
        if (currentStep === StepEnum.Upload) {
          let response: OkRespCreateSampleResponse | undefined;
          if (!_.isEmpty(mediaFileList)) {
            response = await createSamples(projectId, mediaFileList);

            updateFileQueue(mediaFileList, response?.data?.ids);
          }
        }

        const annotationConfig = annotationFormInstance.getFieldsValue();
        const config = omit(['media_type'])(annotationConfig);

        revalidator.revalidate();

        return updateProjectConfig
          .mutateAsync({
            ...projectData,
            ...basicFormValues,
            ...modelFormInstance.getFieldsValue(),
            ai_model_name: modelFormInstance.getFieldValue('ai_model_name') ?? null,
            training_config: parseTrainingParameters(modelFormInstance.getFieldValue('training_config')),
            status: projectData?.status === ProjectStatus.DRAFT ? ProjectStatus.IMPORTED : projectData?.status,
            config: isCreateNewProject ? null : JSON.stringify(config),
          })
          .then(() => {
            if (isFromCancel) {
              navigate('/projects');
            }
          });
      } else {
        return addProject.mutateAsync(basicFormValues).then((res) => {
          const newProject = res.data;

          // 取消并保存时，跳转到项目列表页
          if (isFromCancel) {
            navigate('/projects');
          } else if (newProject) {
            navigate(`/projects/${newProject.id}/edit${location.search}#${StepEnum.Upload}`);
          }
          return Promise.reject();
        });
      }
    },
    [
      addProject,
      annotationFormInstance,
      basicFormInstance,
      modelFormInstance,
      currentStep,
      isCreateNewProject,
      isExistProject,
      location.search,
      navigate,
      revalidator,
      projectData,
      projectId,
      updateFileQueue,
      updateProjectConfig,
      uploadFileList,
    ],
  );

  const handleCancel = useCallback(async () => {
    // 在上传数据界面取消时，需要删除已上传的文件\删除已创建的项目
    const uploadedFiles = filter(uploadFileList, (item) => item.status === UploadStatus.Success);
    if (uploadedFiles.length > 0) {
      const uploadedSampleIds = uploadedFiles
        .filter((item) => correctSampleIdsMappings[item.id!])
        .map((item) => correctSampleIdsMappings[item.id!].id!);

      if (uploadedSampleIds.length > 0) {
        await deleteSamples(
          {
            project_id: projectId,
          },
          { sample_ids: uploadedSampleIds },
        );
      }

      const pendingFiles = uploadedFiles.filter((item) => !correctSampleIdsMappings[item.id!]);
      if (pendingFiles.length > 0) {
        await deleteFile({ project_id: projectId }, { attachment_ids: pendingFiles.map((item) => item.id!) });
      }
    }

    if (isCreateNewProject && isExistProject) {
      await deleteProject(projectId);
    }

    modalRef.current.destroy();
    navigate('/projects');
  }, [correctSampleIdsMappings, isCreateNewProject, isExistProject, navigate, projectId, uploadFileList]);

  const handleCancelConfirm = useCallback(() => {
    modalRef.current = modal.confirm({
      title: t('confirm'),
      content: t('saveUnModified'),
      okText: t('saveAndExit'),
      cancelText: t('dontSave'),
      closable: true,
      footer: (
        <StyledFooter>
          <Button onClick={handleCancel}>{t('dontSave')}</Button>
          <Button
            type="primary"
            onClick={async () => {
              modalRef.current.destroy();

              if (![StepEnum.Config, StepEnum.Model].includes(currentStep)) {
                await submitForm(true);
              } else {
                await handleSave(true);
              }
            }}
          >
            {t('saveAndExit')}
          </Button>
        </StyledFooter>
      ),
    });
  }, [t, handleCancel, currentStep, submitForm, handleSave]);

  const handleNextStep = useCallback(
    async function (step: ProjectStep | React.MouseEvent) {
      let nextStep = step;
      // 点击下一步时，step为事件参数
      if ((step as React.MouseEvent).target) {
        const stepIndex = stepDataSource.findIndex((item) => item.value === currentStep);
        nextStep = stepDataSource[stepIndex + 1];
      }

      // 如果是从基本信息步骤到下一步，需要校验基本信息表单
      if (currentStep === StepEnum.Basic) {
        try {
          await basicFormInstance.validateFields();
        } catch (err) {
          return;
        }
      }

      // 文件错误
      if (filter(uploadFileList, (item) => item.status === UploadStatus.Error).length > 0) {
        message.error(t('pleaseHandleErrorFile'));
        return;
      }

      submitForm()
        .then(() => {
          updateCurrentStep((nextStep as ProjectStep).value);
          revalidator.revalidate();
        })
        .catch(() => {});
    },
    [basicFormInstance, currentStep, revalidator, stepDataSource, submitForm, updateCurrentStep, uploadFileList, t],
  );

  const handlePrevStep = async (step: ProjectStep, lastStep: ProjectStep) => {
    // 如果是从标注配置步骤回到上一步，需要校验配置表单
    if (lastStep.value === StepEnum.Config) {
      try {
        await annotationFormInstance.validateFields();
      } catch (err) {
        message.error(t('pleaseCheckToolConfig'));
        return;
      }

      if (previewVisible) {
        setPreviewVisible(false);
      }
    }
    submitForm()
      .then(() => {
        updateCurrentStep(step.value);
      })
      .catch(() => {});
  };

  const actionNodes = useMemo(() => {
    if (!canManage) {
      return (
        <FlexLayout gap=".5rem">
          <Button onClick={() => navigate(`/projects/${projectId}`)}>返回项目</Button>
          <Button
            type="primary"
            loading={loading}
            onClick={async () => {
              const files = uploadFileList
                .filter((file) => file.status === UploadStatus.Success && !file.refId)
                .map((file) => ({ file_id: file.id!, data: { result: '{}' } }));
              if (files.length) {
                const result = await createSamples(projectId, files);
                updateFileQueue(files, result.data?.ids);
              }
              navigate(`/projects/${projectId}`);
              revalidator.revalidate();
            }}
          >
            保存图片
          </Button>
        </FlexLayout>
      );
    }
    if (currentStep === StepEnum.Model) {
      return (
        <FlexLayout gap=".5rem">
          <Button onClick={handleCancelConfirm}>{t('cancel')}</Button>
          <Button loading={loading} type="primary" onClick={() => void handleSave()}>
            {t('save')}
          </Button>
        </FlexLayout>
      );
    }
    if (currentStep === StepEnum.Config) {
      if (previewVisible) {
        return (
          <Button onClick={() => setPreviewVisible(false)}>
            <ArrowLeftOutlined />
            {t('exitPreview')}
          </Button>
        );
      }
      const previewDisabled = !isAnnotationFormValid || isEmpty(samples?.data);

      return (
        <FlexLayout gap=".5rem">
          <Button onClick={handleOpenPreview} disabled={previewDisabled}>
            {t('preview')}
            <ArrowRightOutlined />
          </Button>
          <Button onClick={handleCancelConfirm}>{t('cancel')}</Button>
          <Button loading={loading} type="primary" onClick={commonController.debounce(handleNextStep, 200)}>
            {t('nextStep')}
          </Button>
        </FlexLayout>
      );
    }

    return (
      <FlexLayout gap=".5rem">
        <Button onClick={handleCancelConfirm}>{t('cancel')}</Button>
        <Button loading={loading} type="primary" onClick={commonController.debounce(handleNextStep, 100)}>
          {t('nextStep')}
        </Button>
      </FlexLayout>
    );
  }, [
    canManage,
    navigate,
    projectId,
    uploadFileList,
    updateFileQueue,
    revalidator,
    currentStep,
    handleCancelConfirm,
    loading,
    handleNextStep,
    previewVisible,
    isAnnotationFormValid,
    samples?.data,
    handleOpenPreview,
    handleSave,
    t,
  ]);

  const projectCreationContextValue = useMemo(
    () => ({
      uploadFileList,
      setUploadFileList,
      annotationFormInstance,
      selectedTemplate: template,
      onTemplateSelect: setTemplate,
      basicFormInstance,
      modelFormInstance,
      project: projectData,
      onAnnotationFormChange,
    }),
    [
      uploadFileList,
      annotationFormInstance,
      template,
      basicFormInstance,
      modelFormInstance,
      projectData,
      onAnnotationFormChange,
    ],
  );

  useLayoutEffect(() => {
    if (!previewIframeRef.current) {
      return;
    }

    if (bridgeRef.current) {
      bridgeRef.current.destroy();
      bridgeRef.current = null;
    }

    bridgeRef.current = new Bridge(previewIframeRef.current.contentWindow!);
    bridgeRef.current.on('ready', () => {
      if (!projectData?.media_type) {
        return;
      }

      let _config;

      if ([MediaType.VIDEO, MediaType.AUDIO].includes(projectData?.media_type)) {
        _config = convertAudioAndVideoConfig(annotationFormInstance.getFieldsValue());
      } else if (projectData?.media_type === MediaType.IMAGE) {
        _config = convertImageConfig(annotationFormInstance.getFieldsValue());
      }

      if (bridgeRef.current) {
        bridgeRef.current.post('preview', _config);
      }
    });
  }, [previewVisible, annotationFormInstance, projectData?.media_type]);

  return (
    <FlexLayout.Content flex="column">
      <StepRow flex items="center" justify="space-between">
        <FlexLayout.Header>
          {canManage ? (
            <Step steps={stepDataSource} currentStep={currentStep} onNext={handleNextStep} onPrev={handlePrevStep} />
          ) : (
            <b>上传图片</b>
          )}
        </FlexLayout.Header>
        <FlexLayout.Footer>{actionNodes}</FlexLayout.Footer>
      </StepRow>
      <ContentWrapper scroll flex="column">
        <ProjectCreationContext.Provider value={projectCreationContextValue}>
          <FlexLayout.Content style={{ display: previewVisible ? 'none' : 'flex' }} flex="column">
            {canManage ? partials : <InputData />}
          </FlexLayout.Content>

          {previewVisible && (
            <PreviewFrame
              referrerPolicy="no-referrer"
              ref={previewIframeRef}
              src={`/projects/${projectData!.id}/samples/${samples?.data?.[0].id}?noSave=true`}
            />
          )}
        </ProjectCreationContext.Provider>
      </ContentWrapper>
    </FlexLayout.Content>
  );
};

export default CreateProject;
