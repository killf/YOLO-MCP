import { useState } from 'react';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Typography } from 'antd';

import { getTrainingParameters } from '@/api/services/training';
import type { TrainingParameters } from '@/api/services/training';

export type TrainingFormValues = Omit<TrainingParameters, 'extra_params'> & { extra_params?: string };

const defaults: TrainingParameters = {
  algorithm: 'yolo26_detect',
  initial_model: 'yolo26s.pt',
  epochs: 100,
  imgsz: 1024,
  batch: 2,
  lr0: 0.01,
  augmentation: true,
  training_scope: 'full',
  unfreeze_steps: 100,
};

export function trainingFormValues(config?: TrainingParameters | null): TrainingFormValues {
  return {
    ...defaults,
    ...config,
    extra_params: config?.extra_params ? JSON.stringify(config.extra_params, null, 2) : '',
  };
}

function parseExtraParams(value?: string): Record<string, unknown> {
  let parameters: unknown;
  try {
    parameters = value?.trim() ? JSON.parse(value) : {};
  } catch {
    throw new Error('请输入合法的 JSON');
  }
  if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) {
    throw new Error('自定义训练参数必须是 JSON 对象');
  }
  return parameters as Record<string, unknown>;
}

export function parseTrainingParameters(values: TrainingFormValues = trainingFormValues()): TrainingParameters {
  return { ...defaults, ...values, extra_params: parseExtraParams(values.extra_params) };
}

export default function TrainingConfigFields({
  projectId,
  models,
  prefix,
  showImageSettings = true,
}: {
  projectId: number;
  models: string[];
  prefix?: string;
  showImageSettings?: boolean;
}) {
  const [showParameters, setShowParameters] = useState(false);
  const form = Form.useFormInstance();
  const scope = Form.useWatch(prefix ? [prefix, 'training_scope'] : 'training_scope', form);
  const [search, setSearch] = useState('');
  const parameters = useQuery({
    queryKey: ['trainingParameters', projectId],
    queryFn: () => getTrainingParameters(projectId),
    enabled: showParameters,
  });
  const name = (key: string) => (prefix ? [prefix, key] : key);
  const grid = { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 };

  return (
    <>
      <div style={grid}>
        <Form.Item name={name('algorithm')} label="算法" rules={[{ required: true }]}>
          <Select options={[{ value: 'yolo26_detect', label: 'YOLO26 目标检测' }]} />
        </Form.Item>
        <Form.Item name={name('initial_model')} label="初始权重" rules={[{ required: true }]}>
          <Select
            options={[
              {
                label: '官方预训练权重',
                options: ['n', 's', 'm', 'l', 'x'].map((size) => ({
                  value: `yolo26${size}.pt`,
                  label: `YOLO26${size}`,
                })),
              },
              { label: '本项目权重', options: models.map((value) => ({ value, label: value })) },
            ]}
          />
        </Form.Item>
      </div>
      <div style={{ ...grid, gridTemplateColumns: scope === 'head_then_full' ? '1fr 2fr 1fr' : '1fr 2fr' }}>
        <Form.Item
          name={name('augmentation')}
          label="图像增强"
          valuePropName="checked"
          tooltip="开启时使用框架增强，可在 JSON 中细调；关闭时只做必要的尺寸适配。"
        >
          <Switch checkedChildren="开启" unCheckedChildren="关闭" />
        </Form.Item>
        <Form.Item
          name={name('training_scope')}
          label="训练范围"
          tooltip="检测头模式冻结 backbone、neck 及其 BN 统计；全部参数模式保留框架固定层。"
        >
          <Select
            options={[
              { value: 'full', label: '全部参数' },
              { value: 'head', label: '仅检测头' },
              { value: 'head_then_full', label: '先检测头后全部' },
            ]}
          />
        </Form.Item>
        {scope === 'head_then_full' && (
          <Form.Item
            name={name('unfreeze_steps')}
            label="解冻 step"
            tooltip="检测头完成指定次数的优化器更新后解冻；梯度累积和 AMP 跳过的更新不计数。"
            rules={[{ required: true }]}
          >
            <InputNumber min={1} max={10000000} precision={0} style={{ width: '100%' }} />
          </Form.Item>
        )}
      </div>
      <div style={{ ...grid, gridTemplateColumns: `repeat(${showImageSettings ? 4 : 2}, minmax(0, 1fr))` }}>
        <Form.Item name={name('epochs')} label="Epoch" rules={[{ required: true }]}>
          <InputNumber min={1} max={10000} precision={0} style={{ width: '100%' }} />
        </Form.Item>
        {showImageSettings && (
          <>
            <Form.Item
              name={name('imgsz')}
              label="图片尺寸"
              rules={[
                { required: true },
                {
                  validator: (_, value) =>
                    value % 32 === 0 ? Promise.resolve() : Promise.reject(new Error('图片尺寸需要是 32 的倍数')),
                },
              ]}
            >
              <InputNumber min={32} max={4096} step={32} precision={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name={name('batch')}
              label="每批图片数"
              rules={[
                { required: true },
                {
                  validator: (_, value) =>
                    value === -1 || value > 0 ? Promise.resolve() : Promise.reject(new Error('请输入 -1 或正整数')),
                },
              ]}
            >
              <InputNumber min={-1} max={1024} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </>
        )}
        <Form.Item
          name={name('lr0')}
          label="学习率"
          tooltip="初始学习率 lr0；optimizer=auto 时由框架决定。可在 JSON 中选择 optimizer，例如 AdamW。"
        >
          <InputNumber min={0} max={1} step={0.001} style={{ width: '100%' }} />
        </Form.Item>
      </div>
      <Form.Item
        name={name('extra_params')}
        dependencies={[name('lr0')]}
        label={
          <Space size={4}>
            自定义训练参数（JSON）
            <Button
              type="text"
              size="small"
              aria-label="查看可修改的训练参数"
              icon={<QuestionCircleOutlined />}
              onClick={() => setShowParameters(true)}
            />
          </Space>
        }
        rules={[
          {
            validator: (_, value) => {
              try {
                const extra = parseExtraParams(value);
                if (form.getFieldValue(name('lr0')) != null && 'lr0' in extra) {
                  throw new Error('学习率已单独设置，JSON 中不能重复设置 lr0');
                }
                return Promise.resolve();
              } catch (error) {
                return Promise.reject(error);
              }
            },
          },
        ]}
      >
        <Input.TextArea
          rows={5}
          spellCheck={false}
          style={{ fontFamily: 'monospace' }}
          placeholder={'{\n  "optimizer": "AdamW",\n  "amp": false\n}'}
        />
      </Form.Item>
      <Modal
        title="自定义训练参数说明"
        open={showParameters}
        onCancel={() => setShowParameters(false)}
        footer={null}
        width={900}
      >
        <Typography.Paragraph type="secondary">
          可在 JSON 中追加下列参数。学习率在上方设置后，不能再重复填写 lr0；其余基础表单和项目路径由系统管理。
          部分参数仅适用于其他算法、推理或导出，YOLO26 目标检测训练时可能不生效。
        </Typography.Paragraph>
        <Input.Search
          aria-label="搜索训练参数"
          placeholder="搜索参数名或说明"
          allowClear
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ marginBottom: 12 }}
        />
        {parameters.isError ? (
          <Alert
            type="error"
            message="无法加载参数说明"
            action={<Button onClick={() => void parameters.refetch()}>重试</Button>}
          />
        ) : (
          <Table
            rowKey="name"
            size="small"
            loading={parameters.isFetching}
            pagination={false}
            scroll={{ y: 420, x: 650 }}
            dataSource={parameters.data?.data.filter((parameter) =>
              `${parameter.name} ${parameter.description}`.toLowerCase().includes(search.trim().toLowerCase()),
            )}
            columns={[
              { title: '参数', dataIndex: 'name', width: 160 },
              {
                title: '默认值',
                width: 130,
                render: (_, parameter) => <code>{JSON.stringify(parameter.default)}</code>,
              },
              { title: '说明', dataIndex: 'description' },
            ]}
          />
        )}
      </Modal>
    </>
  );
}
