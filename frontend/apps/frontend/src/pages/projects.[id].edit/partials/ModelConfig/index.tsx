import { useContext } from 'react';
import { Button, Form, Select } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { FlexLayout } from '@yolo-mcp/components-react';

import { getProjectModels } from '@/api/services/project';
import TrainingConfigFields from '@/components/TrainingConfigFields';

import { ProjectCreationContext } from '../../projectCreation.context';

export default function ModelConfig() {
  const { modelFormInstance, project } = useContext(ProjectCreationContext);
  const projectId = project?.id;
  const algorithm = Form.useWatch('ai_algorithm', modelFormInstance) ?? 'yolo';
  const models = useQuery({
    queryKey: ['annotationModels', project?.id, algorithm],
    queryFn: () => getProjectModels(projectId!, algorithm),
    enabled: Boolean(project?.id),
  });
  const trainingModels = useQuery({
    queryKey: ['projectModels', project?.id],
    queryFn: () => getProjectModels(projectId!),
    enabled: Boolean(project?.id),
  });

  if (!projectId) return null;

  return (
    <FlexLayout flex="column" padding="1.5rem" gap="1rem" style={{ maxWidth: 820, margin: '0 auto', width: '100%' }}>
      <h2>模型设置</h2>
      <Form form={modelFormInstance} layout="vertical" initialValues={{ ai_algorithm: 'yolo' }}>
        <h3>自动标注</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 2fr)', gap: 12 }}>
          <Form.Item name="ai_algorithm" label="自动标注算法" rules={[{ required: true }]}>
            <Select
              onChange={() => modelFormInstance.setFieldValue('ai_model_name', null)}
              options={[
                { value: 'yolo', label: 'YOLO26 目标检测' },
                { value: 'florence2', label: 'Florence-2' },
                { value: 'grounding_dino_sam', label: 'GroundingDINO + SAM ViT-B' },
                { value: 'sam3', label: 'SAM 3' },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="模型权重"
            htmlFor="ai_model_name"
            tooltip={
              algorithm === 'yolo'
                ? '只显示当前项目可用的模型。未选择模型时，可继续人工标注。'
                : '选择算法对应的权重。本机需预先安装推理依赖并准备权重缓存；未选择时可继续人工标注。'
            }
          >
            <FlexLayout items="center" gap=".5rem">
              <Form.Item name="ai_model_name" noStyle>
                <Select
                  allowClear
                  placeholder="选择模型"
                  style={{ flex: 1, minWidth: 0 }}
                  loading={models.isFetching}
                  options={models.data?.data.map((name) => ({ value: name, label: name }))}
                  onDropdownVisibleChange={(open) => {
                    if (open) void models.refetch();
                  }}
                />
              </Form.Item>
              <Button loading={models.isFetching} onClick={() => void models.refetch()}>
                刷新
              </Button>
            </FlexLayout>
          </Form.Item>
        </div>
        <h3>训练模型</h3>
        <TrainingConfigFields
          projectId={projectId}
          models={trainingModels.data?.data ?? []}
          prefix="training_config"
          showImageSettings={false}
        />
      </Form>
    </FlexLayout>
  );
}
