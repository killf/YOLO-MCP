import { useContext, useState } from 'react';
import { Button, Popconfirm, Table, Tag } from 'antd';
import { FileOutlined } from '@ant-design/icons';
import type { RcFile } from 'antd/lib/upload/interface';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useRevalidator } from 'react-router';

import NativeUpload from '@/components/NativeUpload';
import { useUploadFileMutation } from '@/api/mutations/attachment';
import { deleteFile } from '@/api/services/project';
import { deleteSamples } from '@/api/services/samples';
import { message } from '@/StaticAnt';
import { getErrorMessage } from '@/utils';

import { ProjectCreationContext } from '../../projectCreation.context';
import { normalizeFiles, UploadStatus } from './utils';

export interface QueuedFile {
  id?: number;
  url?: string;
  uid: string;
  name: string;
  size: number;
  status: UploadStatus;
  reason?: string;
  file: File;
  refId?: number;
}

const statusText = {
  [UploadStatus.Waiting]: '等待上传',
  [UploadStatus.Uploading]: '上传中',
  [UploadStatus.Success]: '上传成功',
  [UploadStatus.Fail]: '上传失败',
  [UploadStatus.Error]: '文件错误',
};

export default function InputData() {
  const { uploadFileList: files, setUploadFileList, project } = useContext(ProjectCreationContext);
  const upload = useUploadFileMutation();
  const revalidator = useRevalidator();
  const [uploading, setUploading] = useState(false);

  const update = (uid: string, changes: Partial<QueuedFile>) => {
    setUploadFileList((previous) => previous.map((file) => (file.uid === uid ? { ...file, ...changes } : file)));
  };

  // 1. 只接受图片，按队列上传；失败项保留，供用户明确重试。
  const process = async (queue: QueuedFile[]) => {
    if (!project?.id) return;
    setUploading(true);
    try {
      for (const file of queue) {
        update(file.uid, { status: UploadStatus.Uploading, reason: undefined });
        try {
          const { data } = await upload.mutateAsync({ project_id: project.id!, file: file.file });
          update(file.uid, { id: data.id, url: data.url, status: UploadStatus.Success });
        } catch (error) {
          update(file.uid, { status: UploadStatus.Fail, reason: getErrorMessage(error, '上传失败，请重试') });
        }
      }
    } finally {
      setUploading(false);
    }
  };

  const onFiles = (selected: RcFile[]) => {
    const supported = /\.(jpe?g|png|bmp|webp|tiff?)$/i;
    const images = selected.filter((file) => supported.test(file.name));
    if (images.length !== selected.length) message.warning('已忽略非图片文件，仅支持 JPG、PNG、BMP、WEBP、TIFF');
    if (!images.length) return;
    const queue = normalizeFiles(images);
    setUploadFileList((previous) => [...previous, ...queue]);
    void process(queue);
  };

  // 2. 已创建样本通过样本接口清理，未提交队列只清理上传附件。
  const remove = async (file: QueuedFile) => {
    if (!project?.id) return;
    if (file.refId) {
      await deleteSamples({ project_id: project.id! }, { sample_ids: [file.refId] });
    } else if (file.id) {
      await deleteFile({ project_id: project.id! }, { attachment_ids: [file.id] });
    }
    setUploadFileList((previous) => previous.filter((item) => item.uid !== file.uid));
    revalidator.revalidate();
  };

  return (
    <FlexLayout flex="column" padding="1.5rem" gap="1rem">
      <FlexLayout justify="space-between" items="center" gap="1rem">
        <FlexLayout flex="column" gap=".25rem">
          <h2 style={{ margin: 0 }}>图片上传</h2>
          <span style={{ color: 'var(--color-text-secondary)' }}>
            支持 JPG、PNG、BMP、WEBP、TIFF，单张图片最大 200 MB。
          </span>
        </FlexLayout>
        <NativeUpload
          type="primary"
          icon={<FileOutlined />}
          multiple
          directory={false}
          disabled={uploading || !project?.id}
          accept=".jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff"
          onChange={onFiles}
        >
          上传图片
        </NativeUpload>
      </FlexLayout>
      <Table<QueuedFile>
        rowKey="uid"
        dataSource={files}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: '文件名', dataIndex: 'name' },
          { title: '大小', render: (_, file) => `${(file.size / 1024).toFixed(1)} KB` },
          {
            title: '状态',
            render: (_, file) => (
              <>
                <Tag color={file.status === UploadStatus.Success ? 'success' : undefined}>{statusText[file.status]}</Tag>
                {file.reason && <span style={{ display: 'block', color: 'var(--color-error)' }}>{file.reason}</span>}
              </>
            ),
          },
          {
            title: '操作',
            render: (_, file) => (
              <>
                {file.status === UploadStatus.Fail && (
                  <Button type="link" disabled={uploading} onClick={() => void process([file])}>
                    重试
                  </Button>
                )}
                <Popconfirm title="确定删除这张图片？" onConfirm={() => remove(file)}>
                  <Button type="link" danger disabled={uploading}>
                    删除
                  </Button>
                </Popconfirm>
              </>
            ),
          },
        ]}
      />
    </FlexLayout>
  );
}
