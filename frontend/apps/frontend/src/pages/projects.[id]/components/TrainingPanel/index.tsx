import { useState } from 'react';
import { HistoryOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Drawer, Form, Modal, Popconfirm, Popover, Space, Table, Tag, Tooltip, Typography } from 'antd';

import { getProjectModels } from '@/api/services/project';
import {
  clearTrainingLogs,
  deleteTrainingRun,
  downloadModel,
  getTrainingLog,
  getTrainingRuns,
  startTraining,
  pauseTraining,
  resumeTraining,
} from '@/api/services/training';
import type { TrainingParameters, TrainingRun, TrainingStatus } from '@/api/services/training';
import { message } from '@/StaticAnt';
import TrainingConfigFields, { parseTrainingParameters, trainingFormValues } from '@/components/TrainingConfigFields';
import type { TrainingFormValues } from '@/components/TrainingConfigFields';

const statuses: Record<TrainingStatus, { text: string; color: string }> = {
  PENDING: { text: '等待启动', color: 'default' },
  RUNNING: { text: '训练中', color: 'processing' },
  PAUSING: { text: '等待暂停', color: 'processing' },
  PAUSED: { text: '已暂停', color: 'warning' },
  SUCCEEDED: { text: '成功', color: 'success' },
  FAILED: { text: '失败', color: 'error' },
  INTERRUPTED: { text: '已中断', color: 'warning' },
};

const active = (status: TrainingStatus) => ['PENDING', 'RUNNING', 'PAUSING'].includes(status);
const time = (value: string | null) => (value ? new Date(value).toLocaleString() : '-');

export default function TrainingPanel({
  projectId,
  canClean,
  defaults,
}: {
  projectId: number;
  canClean: boolean;
  defaults?: TrainingParameters | null;
}) {
  const [showStart, setShowStart] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [selectedRun, setSelectedRun] = useState<TrainingRun>();
  const [page, setPage] = useState(1);
  const [cleaning, setCleaning] = useState<number>();
  const [form] = Form.useForm<TrainingFormValues>();
  const runs = useQuery({
    queryKey: ['trainingRuns', projectId, page],
    queryFn: () => getTrainingRuns(projectId, page - 1),
    refetchInterval: (query) => (query.state.data?.data.some((run) => active(run.status)) ? 2000 : false),
  });
  const models = useQuery({
    queryKey: ['projectModels', projectId],
    queryFn: () => getProjectModels(projectId),
    enabled: showStart || showHistory,
  });
  const logs = useQuery({
    queryKey: ['trainingLog', projectId, selectedRun?.id],
    queryFn: () => getTrainingLog(projectId, selectedRun!.id),
    enabled: Boolean(selectedRun),
    refetchInterval: () =>
      runs.data?.data.some((run) => run.id === selectedRun?.id && active(run.status)) ? 2000 : false,
  });
  const start = useMutation({
    mutationFn: (values: TrainingParameters) => startTraining(projectId, values),
    onSuccess: () => {
      setShowStart(false);
      setPage(1);
      setShowHistory(true);
      void runs.refetch();
      message.success('训练已提交，可在训练记录中查看状态');
    },
  });
  const busy = runs.data?.data.some((run) => active(run.status));
  const control = useMutation({
    mutationFn: ({ run, action }: { run: TrainingRun; action: 'pause' | 'resume' }) =>
      action === 'pause' ? pauseTraining(projectId, run.id) : resumeTraining(projectId, run.id),
    onSuccess: (_, { action }) => {
      message.success(action === 'pause' ? '将在当前 epoch 保存完成后暂停' : '已提交继续训练');
      void runs.refetch();
    },
  });
  const cleanup = async (run: TrainingRun, includeModel: boolean) => {
    setCleaning(run.id);
    try {
      if (includeModel) await deleteTrainingRun(projectId, run.id);
      else await clearTrainingLogs(projectId, run.id);
      if (selectedRun?.id === run.id) setSelectedRun(undefined);
      message.success(includeModel ? '执行记录、模型和日志已删除' : '日志已清理，执行记录和模型已保留');
      await runs.refetch();
      if (includeModel) await models.refetch();
    } finally {
      setCleaning(undefined);
    }
  };

  return (
    <>
      <Button
        type="primary"
        ghost
        onClick={() => {
          form.setFieldsValue(trainingFormValues(defaults));
          setShowStart(true);
        }}
      >
        开始训练
      </Button>
      <Modal
        title={
          <Space size={4}>
            开始训练
            <Tooltip title={busy ? '训练记录（训练中）' : '训练记录'}>
              <Button
                type="text"
                size="small"
                aria-label="训练记录"
                icon={<HistoryOutlined />}
                onClick={() => {
                  setPage(1);
                  setShowHistory(true);
                  void runs.refetch();
                }}
              />
            </Tooltip>
          </Space>
        }
        open={showStart}
        onCancel={() => setShowStart(false)}
        confirmLoading={start.isPending}
        okButtonProps={{ disabled: busy }}
        onOk={() => form.submit()}
        okText="开始训练"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => start.mutate(parseTrainingParameters(values))}
          initialValues={trainingFormValues(defaults)}
        >
          <TrainingConfigFields projectId={projectId} models={models.data?.data ?? []} />
        </Form>
      </Modal>
      <Drawer title="训练记录" open={showHistory} onClose={() => setShowHistory(false)} width={1080}>
        <Table<TrainingRun>
          rowKey="id"
          loading={runs.isFetching && !runs.data}
          dataSource={runs.data?.data ?? []}
          pagination={{ current: page, pageSize: 10, total: runs.data?.meta_data.total, onChange: setPage }}
          columns={[
            { title: '编号', dataIndex: 'id', width: 65 },
            {
              title: '状态',
              render: (_, run) => <Tag color={statuses[run.status].color}>{statuses[run.status].text}</Tag>,
            },
            {
              title: '初始模型',
              render: (_, run) => (
                <Button
                  type="link"
                  disabled={!models.data?.data.includes(run.initial_model)}
                  style={{ padding: 0 }}
                  onClick={() => void downloadModel(projectId, run.initial_model)}
                >
                  {run.initial_model}
                </Button>
              ),
            },
            {
              title: '参数',
              render: (_, run) => (
                <Popover
                  trigger="click"
                  title="训练参数"
                  content={
                    <pre style={{ margin: 0, maxHeight: 360, maxWidth: 480, overflow: 'auto' }}>
                      {JSON.stringify(run.parameters, null, 2)}
                    </pre>
                  }
                >
                  <Button type="link" style={{ padding: 0, height: 'auto', whiteSpace: 'normal', textAlign: 'left' }}>
                    {run.parameters.epochs} 轮 / {run.parameters.imgsz}px / batch {run.parameters.batch}
                  </Button>
                </Popover>
              ),
            },
            { title: '开始时间', render: (_, run) => time(run.started_at) },
            { title: '结束时间', render: (_, run) => time(run.finished_at) },
            {
              title: '产出模型',
              render: (_, run) =>
                run.model_name ? (
                  <Button
                    type="link"
                    disabled={!run.model_available}
                    style={{ padding: 0 }}
                    onClick={() => void downloadModel(projectId, run.model_name!)}
                  >
                    {run.model_name}
                  </Button>
                ) : (
                  '-'
                ),
            },
            {
              title: '操作',
              width: 230,
              render: (_, run) => (
                <Space size={0} wrap>
                  {run.pause_available && (
                    <Button
                      type="link"
                      loading={control.isPending && control.variables?.run.id === run.id}
                      onClick={() => control.mutate({ run, action: 'pause' })}
                    >
                      暂停训练
                    </Button>
                  )}
                  {run.status === 'PAUSED' && (
                    <Button
                      type="link"
                      disabled={!run.resume_available || busy}
                      loading={control.isPending && control.variables?.run.id === run.id}
                      onClick={() => control.mutate({ run, action: 'resume' })}
                    >
                      继续训练
                    </Button>
                  )}
                  <Button
                    type="link"
                    disabled={!run.log_available && !active(run.status)}
                    onClick={() => setSelectedRun(run)}
                  >
                    查看日志
                  </Button>
                  <Popconfirm title="清理日志和中间文件？执行记录及模型会保留。" onConfirm={() => cleanup(run, false)}>
                    <Button
                      type="link"
                      disabled={
                        !canClean ||
                        active(run.status) ||
                        run.status === 'PAUSED' ||
                        !run.log_available ||
                        cleaning === run.id
                      }
                    >
                      清理日志
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    title="删除此记录、产出模型和全部日志？此操作不可恢复。"
                    onConfirm={() => cleanup(run, true)}
                  >
                    <Button type="link" danger disabled={!canClean || active(run.status) || cleaning === run.id}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
          expandable={{
            expandedRowRender: (run) => (
              <>
                {run.error_message && <Alert type="error" message={run.error_message} />}
                <Typography.Paragraph>
                  指标：
                  {Object.entries(run.metrics)
                    .map(([key, value]) => `${key.replace(/^metrics\//, '')}: ${value.toFixed(4)}`)
                    .join('；') || '暂无'}
                </Typography.Paragraph>
              </>
            ),
          }}
        />
      </Drawer>
      <Drawer
        title={`训练日志 #${selectedRun?.id ?? ''}`}
        open={Boolean(selectedRun)}
        onClose={() => setSelectedRun(undefined)}
        width={1000}
      >
        <Button onClick={() => void logs.refetch()} style={{ marginBottom: 12 }}>
          刷新日志
        </Button>
        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12 }}>
          {logs.data || '等待日志输出…'}
        </pre>
      </Drawer>
    </>
  );
}
