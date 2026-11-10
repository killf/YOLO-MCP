import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useRevalidator, useRouteLoaderData, useSearchParams } from 'react-router-dom';
import type { ColumnsType, TableProps } from 'antd/es/table';
import { Table, Select, Pagination, Button, Popconfirm, Tooltip, Avatar, Popover, Progress, message } from 'antd';
import { FlexLayout } from '@yolo-mcp/components-react';
import _ from 'lodash-es';
import formatter from '@yolo-mcp/formatter';
import styled from 'styled-components';
import { CheckCircleFilled, CloseCircleFilled, DownOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@yolo-mcp/i18n';

import type { DatasetSplit, SampleResponse } from '@/api/types';
import { MediaType, ProjectStatus } from '@/api/types';
import type { ProjectLoaderResult } from '@/loaders/project.loader';
import BlockContainer from '@/layouts/BlockContainer';
import { deleteSamples, updateSampleState, createAutoLabelJob, getAutoLabelJobStatus } from '@/api/services/samples';
import { UserAvatar } from '@/components/UserAvatar';
import useMe from '@/hooks/useMe';

import type { ProjectStatusProps } from './components/Statistical';
import CollaboratorPortal from './components/CollaboratorModal';
import Statistical, { ProjectStatus as ProjectStatusComponent } from './components/Statistical';
import GoToEditProject from './components/GoToEditProject';
import TrainingPanel from './components/TrainingPanel';
import type { ProjectSampleUser } from '../../hooks/useSampleWs';

const HeaderWrapper = styled(FlexLayout.Header)`
  background-color: #fff;
  min-height: 3.5rem;
  padding: 0.5rem 0;
`;

const Samples = () => {
  const navigate = useNavigate();
  const routerData = useRouteLoaderData('project') as ProjectLoaderResult;
  const samples = _.get(routerData, 'samples.data');
  const revalidator = useRevalidator();
  const project = routerData.project;
  const metaData = routerData?.samples?.meta_data;
  const routeParams = useParams();
  const projectId = +routeParams.projectId!;
  const { t } = useTranslation();
  const me = useMe();
  const isMeTheCreator = !!me.data?.is_admin || project?.created_by?.id === me?.data?.id;

  // 查询参数
  const [searchParams, setSearchParams] = useSearchParams(
    new URLSearchParams({
      // 默认按照最后更新时间倒序
      page: '1',
      size: '10',
    }),
  );

  const projectStatus = _.get(project, 'status');
  const isProjectReadyToAnnotate =
    ![ProjectStatus.DRAFT, ProjectStatus.IMPORTED].includes(projectStatus!) &&
    project?.config &&
    Object.keys(project?.config).length > 0;
  const [enterRowId, setEnterRowId] = useState<any>(undefined);

  // Batch auto-label state
  const [batchProgress, setBatchProgress] = useState<{
    processed: number;
    total: number;
    success: number;
    failed: number;
  } | null>(null);
  const [isBatchLabeling, setIsBatchLabeling] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const handleBatchAutoLabel = useCallback(async () => {
    if (!projectId) return;
    setIsBatchLabeling(true);
    try {
      const response = await createAutoLabelJob(projectId);
      const job = response.data;
      setBatchProgress({ processed: 0, total: job.sample_count, success: 0, failed: 0 });
      message.success(t('batchAutoLabelStarted'));

      // Start polling
      pollTimerRef.current = setInterval(async () => {
        try {
          const statusResp = await getAutoLabelJobStatus(projectId, job.id);
          const s = statusResp.data;
          setBatchProgress({
            processed: s.processed_count,
            total: s.sample_count,
            success: s.success_count,
            failed: s.failed_count,
          });

          if (s.status === 'COMPLETED' || s.status === 'FAILED') {
            stopPolling();
            setIsBatchLabeling(false);
            if (s.status === 'FAILED') {
              message.warning(s.error_message || `AI 标注结束：成功 ${s.success_count}，失败 ${s.failed_count}`);
            } else {
              message.success(t('batchAutoLabelCompleted', { success: s.success_count, failed: s.failed_count }));
            }
            revalidator.revalidate();
            setTimeout(() => setBatchProgress(null), 3000);
          }
        } catch {
          stopPolling();
          setIsBatchLabeling(false);
          setBatchProgress(null);
        }
      }, 2500);
    } catch {
      setIsBatchLabeling(false);
    }
  }, [projectId, t, revalidator, stopPolling]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const handleDeleteSample = async (ids: number[]) => {
    await deleteSamples({ project_id: projectId }, { sample_ids: ids });
    revalidator.revalidate();
  };

  const handleSplitChange = async (sampleId: number, split: DatasetSplit) => {
    await updateSampleState({ project_id: projectId, sample_id: sampleId }, { split });
    revalidator.revalidate();
  };

  const columns: ColumnsType<SampleResponse> = [
    {
      title: t('innerId'),
      dataIndex: 'inner_id',
      key: 'inner_id',
      align: 'left',
      sorter: true,
    },
    {
      title: t('filename'),
      dataIndex: ['file', 'filename'],
      key: 'filename',
      align: 'left',
      render: (filename) => formatter.format('ellipsis', filename ?? '', { maxWidth: 160, type: 'tooltip' }),
    },
    {
      title: '类型',
      dataIndex: 'split',
      key: 'split',
      render: (split: DatasetSplit, record) => {
        return (
          <Select
            aria-label="类型"
            value={split}
            style={{ width: 100 }}
            options={[
              { value: 'train', label: '训练集' },
              { value: 'test', label: '测试集' },
            ]}
            onChange={(value) => handleSplitChange(record.id!, value)}
          />
        );
      },
    },
    {
      title: t('dataPreview'),
      dataIndex: 'file',
      key: 'file',
      align: 'left',
      render: (data) => {
        const thumbnailUrl = data.thumbnail_url || data.url;
        return <img src={thumbnailUrl} style={{ width: '116px', height: '70px', objectFit: 'cover' }} />;
      },
    },
    {
      title: (
        <>
          {t('preAnnotation')} &nbsp;
          <Tooltip title={t('preAnnotationDescription')}>
            <QuestionCircleOutlined />
          </Tooltip>
        </>
      ),
      dataIndex: 'is_pre_annotated',
      key: 'is_pre_annotated',
      align: 'left',
      render: (value: boolean) => (value ? t('yes') : ''),
    },
    {
      title: t('annotationState'),
      dataIndex: 'state',
      key: 'state',
      align: 'left',
      width: 90,
      render: (text) => {
        if (!isProjectReadyToAnnotate) {
          return '-';
        }

        return <ProjectStatusComponent status={_.lowerCase(text) as ProjectStatusProps['status']} />;
      },
      sorter: true,
    },
    {
      title: t('annotationCount'),
      dataIndex: 'annotated_count',
      key: 'annotated_count',
      align: 'left',
      render: (_unused, record) => {
        let result = 0;
        const resultJson = record?.data?.result ? JSON.parse(record?.data?.result) : {};
        for (const key in resultJson) {
          if (key.indexOf('Tool') > -1 && key !== 'textTool' && key !== 'tagTool') {
            const tool = resultJson[key];
            if (!tool.result) {
              let _temp = 0;
              if (tool.length) {
                _temp = tool.length;
              }
              result = result + _temp;
            } else {
              result = result + tool.result.length;
            }
          }
        }
        return result;
      },
      sorter: true,
      width: 90,
    },
    {
      title: t('updaters'),
      dataIndex: 'updaters',
      key: 'updaters',
      align: 'center',
      render: (updaters: ProjectSampleUser[]) => {
        if (!isProjectReadyToAnnotate) {
          return '-';
        }

        if (!updaters || updaters.length === 0) {
          return '-';
        }

        if (updaters.length === 1) {
          return <UserAvatar user={updaters[0]} />;
        }

        return (
          <Button type="text" style={{ padding: '0.25rem', cursor: 'default' }}>
            <FlexLayout items="center" gap=".5rem">
              <Avatar.Group>
                {updaters?.slice(0, 3).map((updater, index) => (
                  <UserAvatar key={index} user={updater} />
                ))}
              </Avatar.Group>
              {updaters.length > 3 && <span>{updaters.length}</span>}
              <Popover
                title={null}
                arrow={false}
                placement="bottom"
                content={
                  <FlexLayout flex="column" gap="1rem">
                    {updaters.map((updater) => (
                      <UserAvatar
                        key={updater.user_id}
                        user={updater}
                        showTooltip={false}
                        shortName={false}
                        style={{ backgroundColor: 'var(--color-primary)', color: '#fff' }}
                      />
                    ))}
                  </FlexLayout>
                }
              >
                <DownOutlined />
              </Popover>
            </FlexLayout>
          </Button>
        );
      },
    },
    {
      title: t('updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      align: 'left',
      sorter: true,
      render: (updated_at) => {
        if (!isProjectReadyToAnnotate) {
          return '';
        }

        return formatter.format('dateTime', new Date(updated_at), { style: 'YYYY-MM-DD HH:mm' });
      },
    },
    {
      title: '',
      dataIndex: 'option',
      key: 'option',
      width: 140,
      align: 'center',
      fixed: 'right',
      render: (x, record) => {
        if (record.id !== enterRowId) {
          return '';
        }

        return (
          <FlexLayout items="center" gap="0.5rem">
            {isProjectReadyToAnnotate && (
              <Link to={`/projects/${projectId}/samples/${record.id}`}>
                <Button type="link">{t('startAnnotate')}</Button>
              </Link>
            )}
            {isMeTheCreator && (
              <Popconfirm title={t('deleteConfirm')} onConfirm={() => handleDeleteSample([record.id!])}>
                <Button type="link" danger>
                  {t('delete')}
                </Button>
              </Popconfirm>
            )}
          </FlexLayout>
        );
      },
    },
  ];

  const rowSelection: TableProps<SampleResponse>['rowSelection'] = {
    columnWidth: 58,
  };

  const handleTableChange: TableProps<SampleResponse>['onChange'] = (pagination, filters, sorter) => {
    if (!_.isEmpty(pagination)) {
      searchParams.set('page', `${pagination.current}`);
      searchParams.set('size', `${pagination.pageSize}`);
    }

    if (sorter) {
      let sortValue = '';
      // @ts-ignore
      switch (sorter.order) {
        case 'ascend':
          sortValue = 'asc';
          break;
        case 'descend':
          sortValue = 'desc';
          break;
        case undefined:
          sortValue = 'desc';
          break;
      }
      searchParams.set('sort', `${_.get(sorter, 'field')}:${sortValue}`);
    } else {
      searchParams.delete('sort');
    }

    setSearchParams(searchParams);
  };
  const handlePaginationChange = (page: number, pageSize: number) => {
    searchParams.set('page', `${page}`);
    searchParams.set('size', `${pageSize}`);
    setSearchParams(searchParams);
  };

  const onMouseEnterRow = (rowId: any) => {
    setEnterRowId(rowId);
  };
  const onRow = (record: any) => {
    return {
      onMouseLeave: () => setEnterRowId(undefined),
      onMouseOver: () => {
        onMouseEnterRow(record.id);
      },
    };
  };

  useLayoutEffect(() => {
    if (project?.media_type !== MediaType.AUDIO) {
      return;
    }

    const handleOnPlay = (e: Event) => {
      const audios = document.getElementsByTagName('audio');
      // 使当前只有一条音频在播放
      for (let i = 0, len = audios.length; i < len; i++) {
        if (audios[i] !== e.target) {
          (audios[i] as HTMLAudioElement).pause();
        }
      }
    };

    document.addEventListener('play', handleOnPlay, true);

    return () => {
      document.removeEventListener('play', handleOnPlay, true);
    };
  }, [project?.media_type]);

  const data = useMemo(() => {
    return samples ?? [];
  }, [samples]);

  const trainingActions = (
    <TrainingPanel projectId={projectId} canClean={isMeTheCreator} defaults={project?.training_config} />
  );

  return (
    <FlexLayout flex="column" full gap="2rem">
      <HeaderWrapper flex items="center">
        <FlexLayout.Content full>
          <BlockContainer>
            {isProjectReadyToAnnotate ? (
              <Statistical>{trainingActions}</Statistical>
            ) : (
              <FlexLayout justify="space-between" items="center">
                {isMeTheCreator ? (
                  <GoToEditProject projectStatus={projectStatus} />
                ) : (
                  <span>等待拥有者完成项目配置</span>
                )}
                <FlexLayout gap=".5rem">
                  {isMeTheCreator && <CollaboratorPortal />}
                  <Button onClick={() => navigate(`/projects/${projectId}/edit#upload`)}>上传图片</Button>
                  {trainingActions}
                </FlexLayout>
              </FlexLayout>
            )}
          </BlockContainer>
        </FlexLayout.Content>
      </HeaderWrapper>

      <FlexLayout.Content scroll>
        <FlexLayout justify="space-between" flex="column" gap="1rem" padding="0 1.5rem 1.5rem">
          <Table
            columns={columns}
            dataSource={data}
            pagination={false}
            rowKey={(record) => record.id!}
            rowSelection={rowSelection}
            onRow={onRow}
            onChange={handleTableChange}
          />
          <FlexLayout justify="space-between">
            <FlexLayout.Item gap="0.5rem" flex items="center">
              {project?.media_type === MediaType.IMAGE && (
                <Button type="link" onClick={handleBatchAutoLabel} disabled={isBatchLabeling} loading={isBatchLabeling}>
                  {t('batchAutoLabel')}
                </Button>
              )}
              {batchProgress && (
                <Progress
                  percent={Math.round((batchProgress.processed / batchProgress.total) * 100)}
                  size="small"
                  status={batchProgress.failed > 0 ? 'exception' : 'active'}
                  style={{ width: 200, display: 'inline-flex' }}
                  format={() => (
                    <FlexLayout items="center" gap="0.5rem">
                      <span>
                        {batchProgress.success} <CheckCircleFilled style={{ color: 'var(--color-success)' }} />
                      </span>
                      <span>
                        {batchProgress.failed} <CloseCircleFilled style={{ color: 'var(--color-error)' }} />
                      </span>
                      <span>/ {batchProgress.total}</span>
                    </FlexLayout>
                  )}
                />
              )}
            </FlexLayout.Item>
            <Pagination
              current={parseInt(searchParams.get('page') || '1')}
              pageSize={parseInt(searchParams.get('size') || '10')}
              total={metaData?.total}
              showSizeChanger
              showQuickJumper
              onChange={handlePaginationChange}
            />
          </FlexLayout>
        </FlexLayout>
      </FlexLayout.Content>
    </FlexLayout>
  );
};

export default Samples;
