import { useState } from 'react';
import type { ReactNode } from 'react';
import { Alert, Button, Form, Modal, Select } from 'antd';
import type { ButtonProps } from 'antd';
import { useQuery } from '@tanstack/react-query';

import { getProjectModels } from '@/api/services/project';
import type { AutoLabelSelection } from '@/api/services/samples';
import type { ProjectResponse } from '@/api/types';

interface AutoLabelButtonProps {
  project: Pick<ProjectResponse, 'id' | 'ai_algorithm' | 'ai_model_name'>;
  onRun: (selection: AutoLabelSelection) => Promise<void>;
  loading: boolean;
  disabled?: boolean;
  type?: ButtonProps['type'];
  children: ReactNode;
}

/** 为单张和批量标注选择本次模型；启动时提交快照，不修改项目默认值。 */
export default function AutoLabelButton({ project, onRun, loading, disabled, type, children }: AutoLabelButtonProps) {
  const [open, setOpen] = useState(false);
  const [algorithm, setAlgorithm] = useState<AutoLabelSelection['algorithm']>(project.ai_algorithm ?? 'yolo');
  const [modelName, setModelName] = useState(project.ai_model_name ?? undefined);
  const models = useQuery({
    queryKey: ['annotationModels', project.id, algorithm],
    queryFn: () => getProjectModels(project.id!, algorithm),
    enabled: open && Boolean(project.id),
  });
  const validSelection = Boolean(modelName && models.data?.data.includes(modelName));

  const start = async () => {
    if (!validSelection || !modelName || loading || disabled) return;
    setOpen(false);
    await onRun({ algorithm, model_name: modelName });
  };

  return (
    <>
      <Button type={type} disabled={disabled || loading} loading={loading} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Modal
        title="选择 AI 标注模型"
        open={open}
        okText="开始标注"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={start}
        okButtonProps={{ disabled: !validSelection || models.isFetching || loading || disabled }}
      >
        <Form layout="vertical">
          <Form.Item label="自动标注算法" htmlFor="annotation-algorithm">
            <Select
              id="annotation-algorithm"
              value={algorithm}
              onChange={(value) => {
                setAlgorithm(value);
                setModelName(undefined);
              }}
              options={[
                { value: 'yolo', label: 'YOLO26 目标检测' },
                { value: 'florence2', label: 'Florence-2' },
                { value: 'grounding_dino_sam', label: 'GroundingDINO + SAM ViT-B' },
                { value: 'sam3', label: 'SAM 3' },
              ]}
            />
          </Form.Item>
          <Form.Item label="模型权重" htmlFor="annotation-model">
            <Select
              id="annotation-model"
              placeholder="选择模型"
              value={modelName}
              loading={models.isFetching}
              onChange={setModelName}
              options={models.data?.data.map((name) => ({ value: name, label: name }))}
              notFoundContent="暂无可用模型"
            />
          </Form.Item>
        </Form>
        {models.isError && <Alert type="error" message="模型列表加载失败，请重新打开重试" />}
        <Alert type="info" message="所选模型仅用于本次任务，开始标注后固定使用该模型。" />
      </Modal>
    </>
  );
}
