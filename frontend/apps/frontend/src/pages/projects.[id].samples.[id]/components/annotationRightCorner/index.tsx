import { useEffect, useCallback, useContext, useState } from 'react';
import { useNavigate, useParams, useRevalidator, useRouteLoaderData, useSearchParams } from 'react-router-dom';
import { Button, Tooltip } from 'antd';
import _, { debounce } from 'lodash-es';
import { set } from 'lodash/fp';
import { useTranslation } from '@yolo-mcp/i18n';
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { useHotkeys } from 'react-hotkeys-hook';
import { FlexLayout } from '@yolo-mcp/components-react';
import { QuestionCircleOutlined } from '@ant-design/icons';

import { ReactComponent as SparklesIcon } from '@/assets/svg/spark.svg';
import commonController from '@/utils/common';
import { imageAnnotationRef, videoAnnotationRef, audioAnnotationRef } from '@/pages/projects.[id].samples.[id]';
import type { SampleListResponse, SampleResponse } from '@/api/types';
import { MediaType, SampleState } from '@/api/types';
import type { getSample } from '@/api/services/samples';
import { autoLabelSample, updateSampleState, updateSampleAnnotationResult } from '@/api/services/samples';
import { message } from '@/StaticAnt';
import useMe from '@/hooks/useMe';
import { UserAvatar } from '@/components/UserAvatar';
import { generateDefaultValues } from '@/utils/generateGlobalToolDefaultValues';

import AnnotationContext from '../../annotation.context';

interface AnnotationRightCornerProps {
  // 用于标注预览
  noSave?: boolean;

  fetchNext?: () => void;

  totalSize: number;

  isLastPage: boolean;
}

export const SAMPLE_CHANGED = 'sampleChanged';

type StoredToolName =
  | 'pointTool'
  | 'rectTool'
  | 'polygonTool'
  | 'lineTool'
  | 'cuboidTool'
  | 'relationTool'
  | 'tagTool'
  | 'textTool'
  | 'videoFrameTool'
  | 'videoSegmentTool'
  | 'audioFrameTool'
  | 'audioSegmentTool';
type StoredAnnotation = { width?: number; height?: number; rotate?: number; duration?: number } & Partial<
  Record<StoredToolName, { toolName: StoredToolName; result: unknown[] }>
>;

function getAnnotationCount(_result: string | object) {
  const resultParsed = typeof _result !== 'object' ? JSON.parse(_result as string) : _result;
  let result = 0;

  for (const key in resultParsed) {
    if (key.indexOf('Tool') > -1 && key !== 'textTool' && key !== 'tagTool') {
      const tool = resultParsed[key];

      if (!tool.result) {
        let temp = 0;

        if (tool.length) {
          temp = tool.length;
        }

        result = result + temp;
      } else {
        result = result + tool.result.length;
      }
    }
  }

  return result;
}

export interface AnnotationLoaderData {
  sample: SampleResponse;
  samples: SampleListResponse;
}

const AnnotationRightCorner = ({ noSave, fetchNext, totalSize, isLastPage }: AnnotationRightCornerProps) => {
  const isFetching = useIsFetching();
  const isMutating = useIsMutating();
  const isGlobalLoading = isFetching > 0 || isMutating > 0;
  const navigate = useNavigate();
  const routeParams = useParams();
  const revalidator = useRevalidator();
  const projectId = routeParams.projectId;
  const sampleId = routeParams.sampleId;
  const { samples, setSamples, project, currentEditingUser } = useContext(AnnotationContext);
  const sampleIndex = _.findIndex(samples, (sample: SampleResponse) => sample.id === +sampleId!);
  const isLastSample = _.findIndex(samples, { id: +sampleId! }) === samples.length - 1;
  const isFirstSample = _.findIndex(samples, { id: +sampleId! }) === 0;
  const routeSample = (useRouteLoaderData('annotation') as any).sample as Awaited<ReturnType<typeof getSample>>;
  const currentSample = routeSample.data;
  const isSampleSkipped = currentSample?.state === SampleState.SKIPPED;
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const me = useMe();
  const isMeTheCurrentUser = currentEditingUser && me.data && currentEditingUser?.user_id === me.data?.id;
  const [isAutoLabeling, setIsAutoLabeling] = useState(false);

  // 第一次进入就是40的倍数时，获取下一页数据
  useEffect(() => {
    if (isLastSample && samples.length < totalSize && !isLastPage) {
      // TODO: fetchNext 调用两次
      fetchNext?.();
    }
  }, [fetchNext, isLastSample, samples.length, totalSize, isLastPage]);

  const navigateWithSearch = useCallback(
    (to: string) => {
      const searchStr = searchParams.toString();

      if (searchStr) {
        navigate(`${to}?${searchStr}`);
      } else {
        navigate(to);
      }
    },
    [navigate, searchParams],
  );

  const saveCurrentSample = useCallback(async () => {
    if (
      currentSample?.state === SampleState.SKIPPED ||
      noSave ||
      !project?.media_type ||
      // 非当前用户标注的文件，不保存
      !isMeTheCurrentUser
    ) {
      return;
    }

    const result: StoredAnnotation = {};
    let innerSample;

    if (project.media_type === MediaType.IMAGE) {
      const exportedResult = (await imageAnnotationRef.current?.getAnnotations()) ?? {};
      const engine = await imageAnnotationRef.current?.getEngine();

      result.width = engine?.backgroundRenderer?.image?.width ?? 0;
      result.height = engine?.backgroundRenderer?.image?.height ?? 0;
      result.rotate = engine?.backgroundRenderer?.rotate ?? 0;

      innerSample = await imageAnnotationRef?.current?.getSample();

      Object.entries(exportedResult).forEach(([item, annotations]) => {
        if (annotations?.length) {
          const toolName = `${item}Tool` as StoredToolName;
          result[toolName] = {
            toolName,
            result: annotations,
          };
        }
      });
    } else if (project.media_type === MediaType.VIDEO) {
      const videoAnnotations = await videoAnnotationRef.current?.getAnnotations();
      const player = await videoAnnotationRef.current?.getPlayer();

      result.width = player?.videoWidth();
      result.height = player?.videoHeight();
      result.duration = player?.duration();

      Object.keys(videoAnnotations ?? {}).forEach((toolName) => {
        if (toolName === 'tag') {
          if (!result.tagTool) {
            result.tagTool = {
              toolName: 'tagTool',
              result: [],
            };
          }

          result.tagTool.result.push(...(videoAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'text') {
          if (!result.textTool) {
            result.textTool = {
              toolName: 'textTool',
              result: [],
            };
          }

          result.textTool.result.push(...(videoAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'frame') {
          if (!result.videoFrameTool) {
            result.videoFrameTool = {
              toolName: 'videoFrameTool',
              result: [],
            };
          }

          result.videoFrameTool.result.push(...(videoAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'segment') {
          if (!result.videoSegmentTool) {
            result.videoSegmentTool = {
              toolName: 'videoSegmentTool',
              result: [],
            };
          }

          result.videoSegmentTool.result.push(...(videoAnnotations?.[toolName] ?? []));
        }
      });

      innerSample = await videoAnnotationRef?.current?.getSample();
    } else if (project.media_type === MediaType.AUDIO) {
      const audioAnnotations = await audioAnnotationRef.current?.getAnnotations();
      const player = await audioAnnotationRef.current?.getPlayer();

      result.duration = player?.getDuration();

      Object.keys(audioAnnotations ?? {}).forEach((toolName) => {
        if (toolName === 'tag') {
          if (!result.tagTool) {
            result.tagTool = {
              toolName: 'tagTool',
              result: [],
            };
          }

          result.tagTool.result.push(...(audioAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'text') {
          if (!result.textTool) {
            result.textTool = {
              toolName: 'textTool',
              result: [],
            };
          }

          result.textTool.result.push(...(audioAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'frame') {
          if (!result.audioFrameTool) {
            result.audioFrameTool = {
              toolName: 'audioFrameTool',
              result: [],
            };
          }

          result.audioFrameTool.result.push(...(audioAnnotations?.[toolName] ?? []));
        }

        if (toolName === 'segment') {
          if (!result.audioSegmentTool) {
            result.audioSegmentTool = {
              toolName: 'audioSegmentTool',
              result: [],
            };
          }

          result.audioSegmentTool.result.push(...(audioAnnotations?.[toolName] ?? []));
        }
      });

      innerSample = await audioAnnotationRef?.current?.getSample();
    }

    if (!innerSample) return;

    // 全局标注没有值的话，填充默认值
    const tagConfig = project.config.tools.find((tool) => tool.tool === 'tagTool');
    if (!result.tagTool?.result?.length && tagConfig) {
      result.tagTool = {
        toolName: 'tagTool',
        result: generateDefaultValues(tagConfig?.config.attributes),
      };
    }

    const textConfig = project.config.tools.find((tool) => tool.tool === 'textTool');
    if (!result.textTool?.result?.length && textConfig) {
      result.textTool = {
        toolName: 'textTool',
        result: generateDefaultValues(textConfig?.config.attributes),
      };
    }

    // 防止sampleid保存错乱，使用标注时传入的sampleid
    const body = set('data.result')(JSON.stringify(result))(currentSample);

    await updateSampleAnnotationResult(+projectId!, +innerSample.id!, {
      ...body,
      annotated_count: getAnnotationCount(body.data!.result),
      state: SampleState.DONE,
    });
  }, [currentSample, isMeTheCurrentUser, noSave, project?.config?.tools, project?.media_type, projectId]);

  const handleComplete = useCallback(async () => {
    await saveCurrentSample();
    navigateWithSearch(`/projects/${projectId}/samples/finished`);
    setTimeout(revalidator.revalidate);
  }, [saveCurrentSample, navigateWithSearch, projectId, revalidator.revalidate]);

  const handleCancelSkipSample = async () => {
    if (noSave || !isMeTheCurrentUser) {
      return;
    }

    await updateSampleState(
      {
        project_id: +projectId!,
        sample_id: +sampleId!,
      },
      {
        state: SampleState.NEW,
      },
    );

    setSamples(
      samples.map((sample: SampleResponse) =>
        sample.id === +sampleId! ? { ...sample, state: SampleState.NEW } : sample,
      ),
    );

    revalidator.revalidate();
  };

  const handleSkipSample = async () => {
    if (noSave || !isMeTheCurrentUser) {
      return;
    }

    await updateSampleState(
      {
        project_id: +projectId!,
        sample_id: +sampleId!,
      },
      {
        state: SampleState.SKIPPED,
      },
    );

    setSamples(
      samples.map((sample: SampleResponse) =>
        sample.id === +sampleId! ? { ...sample, state: SampleState.SKIPPED } : sample,
      ),
    );

    // 切换到下一个文件
    if (!isLastSample) {
      navigateWithSearch(`/projects/${projectId}/samples/${_.get(samples, `[${sampleIndex + 1}].id`)}`);
    } else {
      navigateWithSearch(`/projects/${projectId}/samples/finished`);
    }
  };

  const handleNextSample = useCallback(() => {
    // 到达分页边界，触发加载下一页
    if (sampleIndex === samples.length - 2 && samples.length < totalSize) {
      fetchNext?.();
    }

    if (noSave) {
      navigateWithSearch(`/projects/${projectId}/samples/${_.get(samples, `[${sampleIndex + 1}].id`)}`);

      return;
    }

    if (isLastSample) {
      handleComplete();
    } else {
      saveCurrentSample().then(() => {
        navigateWithSearch(`/projects/${projectId}/samples/${_.get(samples, `[${sampleIndex + 1}].id`)}`);
      });
    }
  }, [
    sampleIndex,
    samples,
    totalSize,
    noSave,
    isLastSample,
    fetchNext,
    navigateWithSearch,
    projectId,
    handleComplete,
    saveCurrentSample,
  ]);

  const handleAutoLabel = useCallback(async () => {
    if (noSave || !isMeTheCurrentUser || !projectId || !sampleId || project?.media_type !== MediaType.IMAGE) {
      return;
    }

    setIsAutoLabeling(true);
    try {
      const response = await autoLabelSample(+projectId, +sampleId);
      await revalidator.revalidate();
      if (response.data.warning_message) {
        message.warning(response.data.warning_message);
      } else {
        message.success(t('aiAutoLabelSuccess'));
      }
    } catch {
      // 请求层已展示具体原因，保留当前标注供用户重试。
    } finally {
      setIsAutoLabeling(false);
    }
  }, [isMeTheCurrentUser, noSave, revalidator, sampleId, t, project?.media_type, projectId]);

  const handlePrevSample = useCallback(async () => {
    if (sampleIndex === 0) {
      return;
    }

    if (!noSave) {
      await saveCurrentSample();
    }

    navigateWithSearch(`/projects/${projectId}/samples/${_.get(samples, `[${sampleIndex - 1}].id`)}`);
  }, [sampleIndex, noSave, navigateWithSearch, projectId, samples, saveCurrentSample]);

  const onKeyDown = debounce(
    useCallback(
      (e: KeyboardEvent) => {
        const key = e.key;
        if (key === 'a' && sampleIndex > 0) {
          handlePrevSample();
        } else if (key === 'd') {
          handleNextSample();
        }
      },
      [handleNextSample, handlePrevSample, sampleIndex],
    ),
    500,
  );

  useHotkeys(
    'ctrl+space, meta+space',
    () => {
      if (noSave) {
        return;
      }

      if (currentSample.state === SampleState.SKIPPED) {
        handleCancelSkipSample();
      } else {
        handleSkipSample();
      }
    },
    {
      keyup: true,
      keydown: false,
    },
    [handleSkipSample, handleCancelSkipSample, currentSample],
  );

  useEffect(() => {
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [onKeyDown]);

  useHotkeys(
    'ctrl+s,meta+s',
    () => {
      if (noSave) {
        return;
      }

      saveCurrentSample().then(() => {
        message.success(t('saved'));
      });
    },
    {
      preventDefault: true,
    },
    [saveCurrentSample, noSave],
  );

  // 从外部触发上下翻页，比如快捷键，不知道上下sample的id
  useEffect(() => {
    const handleSampleChanged = (e: CustomEvent) => {
      const changeType = _.get(e, 'detail');

      if (changeType === 'next') {
        handleNextSample();
      } else if (changeType === 'prev') {
        handlePrevSample();
      }
    };

    document.addEventListener(SAMPLE_CHANGED, handleSampleChanged as EventListener);

    return () => {
      document.removeEventListener(SAMPLE_CHANGED, handleSampleChanged as EventListener);
    };
  }, [handleNextSample, handlePrevSample]);

  // 监听标注主页的左侧文件切换
  useEffect(() => {
    const saveCurrentSampleFromOutside = (e: CustomEvent) => {
      const _sampleId = _.get(e, 'detail.sampleId');

      if (noSave) {
        navigateWithSearch(`/projects/${projectId}/samples/${_sampleId}`);

        return;
      }

      saveCurrentSample().then(() => {
        if (_.isNil(_sampleId)) {
          return;
        }

        navigateWithSearch(`/projects/${projectId}/samples/${_sampleId}`);
      });
    };

    document.addEventListener(SAMPLE_CHANGED, saveCurrentSampleFromOutside as EventListener);

    return () => {
      document.removeEventListener(SAMPLE_CHANGED, saveCurrentSampleFromOutside as EventListener);
    };
  }, [navigateWithSearch, noSave, saveCurrentSample, projectId]);

  if (noSave) {
    return null;
  }

  return (
    <FlexLayout items="center" gap=".5rem">
      <FlexLayout items="center" gap=".5rem">
        {currentEditingUser && (
          <>
            {currentEditingUser.user_id !== me.data?.id && (
              <>
                <UserAvatar key={currentEditingUser.user_id} user={currentEditingUser} />
                {t('isAnnotating')}
                <Tooltip title={t('collaboratorTips')} placement="bottom">
                  <QuestionCircleOutlined />
                </Tooltip>
              </>
            )}
          </>
        )}
      </FlexLayout>
      {project?.media_type === MediaType.IMAGE && (
        <Button
          type="text"
          onClick={commonController.debounce(handleAutoLabel, 100)}
          disabled={isGlobalLoading || isAutoLabeling || !isMeTheCurrentUser}
        >
          <FlexLayout items="center" gap="0.5rem">
            <SparklesIcon />
            {isAutoLabeling ? t('aiAutoLabeling') : t('aiAutoLabel')}
          </FlexLayout>
        </Button>
      )}
      {isSampleSkipped ? (
        <Button
          type="text"
          onClick={commonController.debounce(handleCancelSkipSample, 100)}
          disabled={isGlobalLoading || !isMeTheCurrentUser}
        >
          {t('cancelSkip')}
        </Button>
      ) : (
        <Button
          type="text"
          onClick={commonController.debounce(handleSkipSample, 100)}
          disabled={isGlobalLoading || !isMeTheCurrentUser}
        >
          {t('skip')}
        </Button>
      )}
      {!isFirstSample && (
        <Button onClick={commonController.debounce(handlePrevSample, 100)} disabled={isGlobalLoading}>
          {t('previous')}
        </Button>
      )}
      {isLastSample ? (
        <Button
          type="primary"
          onClick={commonController.debounce(handleComplete, 100)}
          disabled={isGlobalLoading || !isMeTheCurrentUser}
        >
          {t('finish')}
        </Button>
      ) : (
        <Button type="primary" onClick={commonController.debounce(handleNextSample, 100)} disabled={isGlobalLoading}>
          {t('next')}
        </Button>
      )}
    </FlexLayout>
  );
};
export default AnnotationRightCorner;
