import { useState, createRef, useMemo, useCallback, useRef, useLayoutEffect, useEffect } from 'react';
import _ from 'lodash-es';
import { Empty, Spin, message } from 'antd';
import { Annotator } from '@yolo-mcp/video-annotator-react';
import type { AudioAndVideoAnnotatorRef } from '@yolo-mcp/audio-annotator-react';
import { Annotator as AudioAnnotator } from '@yolo-mcp/audio-annotator-react';
import { useSearchParams, useParams, useRouteLoaderData } from 'react-router-dom';
import { Bridge } from 'iframe-message-bridge';
import type { ImageAnnotatorProps, AnnotatorRef as ImageAnnotatorRef } from '@yolo-mcp/image-annotator-react';
import { Annotator as ImageAnnotator } from '@yolo-mcp/image-annotator-react';
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { FlexLayout } from '@yolo-mcp/components-react';
import type { ToolName } from '@yolo-mcp/image';
import type { ILabel } from '@yolo-mcp/interface';
import { useTranslation } from '@yolo-mcp/i18n';

import { MediaType, SampleState, type SampleResponse } from '@/api/types';
import { useScrollFetch } from '@/hooks/useScrollFetch';
import type { getSample } from '@/api/services/samples';
import { getSamples } from '@/api/services/samples';
import { convertAudioAndVideoConfig } from '@/utils/convertAudioAndVideoConfig';
import { convertAudioAndVideoSample, convertMediaAnnotations } from '@/utils/convertAudioAndVideoSample';
import type { ProjectLoaderResult } from '@/loaders/project.loader';
import { convertImageConfig } from '@/utils/convertImageConfig';
import { convertImageAnnotations, convertImageSample } from '@/utils/convertImageSample';
import { TOOL_NAME } from '@/constants/toolName';
import useMe from '@/hooks/useMe';

import SlideLoader from './components/slideLoader';
import AnnotationRightCorner from './components/annotationRightCorner';
import AnnotationContext from './annotation.context';
import { LoadingWrapper, Wrapper } from './style';
import useSampleWs from '../../hooks/useSampleWs';

type AllToolName = ToolName | 'segment' | 'frame' | 'tag' | 'text';

export const imageAnnotationRef = createRef<ImageAnnotatorRef>();
export const videoAnnotationRef = createRef<AudioAndVideoAnnotatorRef>();
export const audioAnnotationRef = createRef<AudioAndVideoAnnotatorRef>();

const PREVIEW_OFFSET_TOP = 102;
const OFFSET_TOP = 158;

const AnnotationPage = () => {
  const routeParams = useParams();
  const { project } = useRouteLoaderData('project') as ProjectLoaderResult;
  const sample = (useRouteLoaderData('annotation') as any).sample as Awaited<ReturnType<typeof getSample>>;
  const preAnnotation = (useRouteLoaderData('annotation') as any).preAnnotation;
  const { t } = useTranslation();
  const activePreAnnotation = useMemo(() => {
    // AI 结果按样本 ID 区分，避免不同目录中的同名图片取到彼此的框。
    const matching = preAnnotation?.data?.filter((item: { data: string }) => {
      const payload = JSON.parse(item.data);
      return payload?.meta?.source_type !== 'ai_generated' || payload.meta.sample_id === +routeParams.sampleId!;
    });
    return _.last(matching);
  }, [preAnnotation, routeParams.sampleId]);

  const preAnnotationConfig = useMemo(() => {
    const result: Partial<Record<AllToolName, any>> = {};

    if (activePreAnnotation) {
      const preAnnotationResult = JSON.parse(_.get(activePreAnnotation, 'data', 'null'));

      if (!preAnnotationResult) {
        return {};
      }

      const config = preAnnotationResult.config;

      if (!config) {
        return {};
      }

      Object.keys(preAnnotationResult.config).forEach((key) => {
        let toolName = key.replace(/Tool$/, '') as AllToolName;

        if (key.includes('audio') || key.includes('video')) {
          // audioSegmentTool => segment
          toolName = toolName.replace(/audio|video/, '').toLowerCase() as AllToolName;
        }

        result[toolName] = preAnnotationResult.config[key as keyof typeof config];
      });
    }

    return result;
  }, [activePreAnnotation]);
  const preAnnotations = useMemo(() => {
    if (!activePreAnnotation) {
      return {};
    }

    const preAnnotationResult = JSON.parse(_.get(activePreAnnotation, 'data', 'null'));
    let _annotations = _.get(preAnnotationResult, 'annotations', {});
    const preAnnotationFile = (_.get(activePreAnnotation, 'file', {}) ?? {}) as {
      filename?: string;
    };
    // 兼容json预标注
    if (preAnnotationFile.filename?.endsWith('.json')) {
      const annotations: { toolName: string; result: unknown[] }[] = preAnnotationResult.result?.annotations ?? [];
      _annotations = Object.fromEntries(annotations.map(({ toolName, result }) => [toolName, { toolName, result }]));
    }

    if (project?.media_type === MediaType.IMAGE) {
      return convertImageAnnotations(_annotations);
    } else if (project?.media_type === MediaType.VIDEO || project?.media_type === MediaType.AUDIO) {
      return convertMediaAnnotations(project.media_type, _annotations);
    }

    return {};
  }, [activePreAnnotation, project?.media_type]);

  const [searchParams] = useSearchParams();
  const projectConfig = _.get(project, 'config');
  const isFetching = useIsFetching();
  const isMutating = useIsMutating();
  const me = useMe();
  const [currentSampleConns, projectConns] = useSampleWs();
  const isMeTheCurrentEditingUser = currentSampleConns?.[0]?.user_id === me.data?.id;

  // TODO： labels/image中的错误定义
  const onError = useCallback(
    (err: any) => {
      const value = err.value;

      if (err.type === 'rotate') {
        message.error(t('cannotRotateWhenAnnotationExist'));
      }

      if (err.type === 'minPointAmount') {
        message.error(`${t('minPointAmountCannotSmallThan')} ${value}`);
      }

      if (err.type === 'maxPointAmount') {
        message.error(`${t('maxPointAmountCannotExceed')} ${value}`);
      }

      if (err.type === 'minWidth') {
        message.error(`${t('minWidthCannotSmallThan')}${value}`);
      }

      if (err.type === 'minHeight') {
        message.error(`${t('minHeightCannotSmallThan')} ${value}`);
      }
    },
    [t],
  );

  // 默认加载数量常量
  const PAGE_SIZE = 40;
  // 滚动加载
  const [totalCount, setTotalCount] = useState<number>(0);
  const [serverPage, setServerPage] = useState<number>(1);
  const currentPage = useRef<number>(1);
  if (currentPage.current === 1) {
    currentPage.current = sample?.data.inner_id ? Math.floor(sample.data.inner_id / PAGE_SIZE) + 1 : 1;
  }

  const fetchSamples = useCallback(async () => {
    if (!routeParams.projectId) {
      return Promise.resolve([]);
    }

    const { data, meta_data } = await getSamples({
      project_id: +routeParams.projectId!,
      page: currentPage.current,
      size: PAGE_SIZE,
    });

    currentPage.current += 1;
    setTotalCount(meta_data?.total ?? 0);
    setServerPage(meta_data?.page ?? 1);
    return data;
  }, [routeParams.projectId]);
  const [samples = [] as SampleResponse[], loading, setSamples, svc] = useScrollFetch<SampleResponse[]>(
    fetchSamples,
    () =>
      document.querySelector('.yolo-mcp-image__sidebar div') ||
      document.querySelector('.yolo-mcp-audio__sidebar div') ||
      document.querySelector('.yolo-mcp-video__sidebar div'),
    {
      isEnd: (allData) => totalCount === (allData?.length ?? 0) || serverPage === Math.ceil(totalCount / PAGE_SIZE),
    },
  );

  const leftSiderContent = useMemo(() => <SlideLoader />, []);

  const topActionContent = (
    <AnnotationRightCorner
      totalSize={totalCount}
      fetchNext={svc}
      isLastPage={serverPage >= Math.ceil(totalCount / PAGE_SIZE)}
      noSave={!!searchParams.get('noSave')}
    />
  );

  const annotationContextValue = useMemo(() => {
    return {
      samples,
      setSamples,
      projectConnections: projectConns,
      project,
      currentEditingUser: currentSampleConns[0],
      isEnd: totalCount === samples.length,
    };
  }, [currentSampleConns, projectConns, samples, setSamples, project, totalCount]);

  let content = null;

  const editorConfig = useMemo(() => {
    if (project?.media_type === MediaType.VIDEO || project?.media_type === MediaType.AUDIO) {
      return convertAudioAndVideoConfig(projectConfig);
    }

    return convertImageConfig(projectConfig);
  }, [project?.media_type, projectConfig]);

  const imageSample = useMemo(() => convertImageSample(sample?.data), [sample?.data]);
  const mediaSample = useMemo(
    () =>
      project?.media_type === MediaType.VIDEO || project?.media_type === MediaType.AUDIO
        ? convertAudioAndVideoSample(sample?.data, project.media_type)
        : undefined,
    [sample?.data, project?.media_type],
  );

  const renderSidebar = useMemo(() => {
    return () => leftSiderContent;
  }, [leftSiderContent]);

  // =================== preview config ===================
  const [configFromParent, setConfigFromParent] = useState<any>();
  useLayoutEffect(() => {
    const bridge = new Bridge(window.parent);

    bridge.on('preview', (data) => {
      setConfigFromParent(data);
    });

    bridge.post('ready').catch(() => {});

    return () => bridge.destroy();
  }, []);

  const isLoading = useMemo(() => loading || isFetching > 0 || isMutating > 0, [loading, isFetching, isMutating]);

  const config = useMemo(() => {
    return configFromParent || editorConfig;
  }, [configFromParent, editorConfig]);

  useEffect(() => {
    if (me.data && currentSampleConns?.[0] && !isMeTheCurrentEditingUser) {
      message.destroy();
      message.error(t('currentSampleIsAnnotating'));
    }
  }, [currentSampleConns, isMeTheCurrentEditingUser, me.data, t]);

  const requestEdit = useCallback<
    (
      type: Parameters<NonNullable<ImageAnnotatorProps['requestEdit']>>[0],
      payload: { toolName?: AllToolName; label?: string },
    ) => boolean
  >(
    (editType, { toolName, label }) => {
      if (!toolName) {
        return false;
      }

      const toolConfig = config[toolName];
      const toolNameKey =
        (toolName.includes('frame') || toolName.includes('segment')
          ? project!.media_type?.toLowerCase() + _.upperFirst(toolName)
          : toolName) + 'Tool';

      if (editType === 'create' && !toolConfig?.labels?.find((item: ILabel) => item.value === label)) {
        message.destroy();
        message.error(`${t('currentTool')}【${TOOL_NAME[toolNameKey]}】${t('doesntInclude')}【${label}】`);

        return false;
      }

      if (editType === 'update' && !config[toolName]) {
        message.destroy();
        message.error(`${t('currentConfigDoesntInclude')}【${TOOL_NAME[toolNameKey]}】`);
        return false;
      }

      return true;
    },
    [config, project, t],
  );

  const [currentTool, setCurrentTool] = useState<any>();
  const [labelMapping, setLabelMapping] = useState<Record<any, string>>();

  const handleLabelChange = useCallback((toolName: any, label: ILabel | undefined) => {
    if (!label) {
      return;
    }

    // 缓存当前标签
    setLabelMapping((prev) => {
      return {
        ...prev,
        [toolName]: label.value,
      };
    });
  }, []);

  const handleToolChange = useCallback((toolName: any) => {
    setCurrentTool(toolName);
  }, []);

  const currentLabel = useMemo(() => {
    return labelMapping?.[currentTool];
  }, [currentTool, labelMapping]);

  const disabled = useMemo(() => {
    return me.data && currentSampleConns[0] && !isMeTheCurrentEditingUser;
  }, [currentSampleConns, isMeTheCurrentEditingUser, me.data]);

  if (project?.media_type === MediaType.IMAGE) {
    content = (
      <ImageAnnotator
        renderSidebar={renderSidebar}
        toolbarRight={topActionContent}
        ref={imageAnnotationRef}
        onError={onError}
        // windows platform pixel issue
        offsetTop={configFromParent ? PREVIEW_OFFSET_TOP : OFFSET_TOP}
        editingSample={imageSample}
        config={config}
        disabled={disabled}
        requestEdit={requestEdit}
        onLabelChange={handleLabelChange}
        onToolChange={handleToolChange}
        selectedTool={disabled ? undefined : currentTool}
        selectedLabel={disabled ? undefined : currentLabel}
        preAnnotationLabels={preAnnotationConfig}
        preAnnotations={sample.data.state === SampleState.NEW ? preAnnotations : undefined}
      />
    );
  } else if (project?.media_type === MediaType.VIDEO) {
    content = (
      <Annotator
        primaryColor="#0d53de"
        ref={videoAnnotationRef}
        offsetTop={configFromParent ? PREVIEW_OFFSET_TOP : OFFSET_TOP}
        samples={[]}
        editingSample={mediaSample}
        config={config}
        toolbarRight={topActionContent}
        renderSidebar={renderSidebar}
        disabled={disabled}
        requestEdit={requestEdit}
        onLabelChange={handleLabelChange}
        onToolChange={handleToolChange}
        selectedTool={disabled ? undefined : currentTool}
        selectedLabel={disabled ? undefined : currentLabel}
        preAnnotationLabels={preAnnotationConfig}
        preAnnotations={sample.data.state === SampleState.NEW ? preAnnotations : undefined}
      />
    );
  } else if (project?.media_type === MediaType.AUDIO) {
    content = (
      <AudioAnnotator
        primaryColor="#0d53de"
        ref={audioAnnotationRef}
        offsetTop={configFromParent ? PREVIEW_OFFSET_TOP : OFFSET_TOP}
        samples={[]}
        editingSample={mediaSample}
        config={config}
        disabled={disabled}
        toolbarRight={topActionContent}
        renderSidebar={renderSidebar}
        requestEdit={requestEdit}
        onLabelChange={handleLabelChange}
        onToolChange={handleToolChange}
        selectedTool={disabled ? undefined : currentTool}
        selectedLabel={disabled ? undefined : currentLabel}
        preAnnotationLabels={preAnnotationConfig}
        preAnnotations={sample.data.state === SampleState.NEW ? preAnnotations : undefined}
      />
    );
  }

  if (_.isEmpty(sample.data.file)) {
    return (
      <FlexLayout.Content items="center" justify="center" flex>
        <Empty description={t('noSample')} />
      </FlexLayout.Content>
    );
  }

  if (_.isEmpty(projectConfig?.tools) && _.isEmpty(configFromParent)) {
    return (
      <FlexLayout.Content items="center" justify="center" flex>
        <Empty description={t('noTool')} />
      </FlexLayout.Content>
    );
  }

  return (
    <AnnotationContext.Provider value={annotationContextValue}>
      {isLoading && (
        <LoadingWrapper items="center" justify="center" flex>
          <Spin spinning />
        </LoadingWrapper>
      )}
      <Wrapper flex="column" full loading={isLoading}>
        {content}
      </Wrapper>
    </AnnotationContext.Provider>
  );
};

export default AnnotationPage;
