import { useState } from 'react';
import { useRouteLoaderData } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Modal, Select, Space, Table } from 'antd';
import { TeamOutlined } from '@ant-design/icons';

import { getUserDirectory } from '@/api/services/user';
import { useCollaborators } from '@/api/queries/project';
import { useAddCollaborator, useRemoveCollaborator } from '@/api/mutations/project';
import type { ProjectLoaderResult } from '@/loaders/project.loader';
import type { UserResponse } from '@/api/types';

export default function CollaboratorPortal() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number>();
  const { project } = useRouteLoaderData('project') as ProjectLoaderResult;
  const id = project!.id!;
  const members = useCollaborators(id, open);
  const users = useQuery({ queryKey: ['user-directory'], queryFn: getUserDirectory, enabled: open });
  const add = useAddCollaborator(id);
  const remove = useRemoveCollaborator(id);
  const available = users.data?.data.filter(
    (user) => user.id !== project?.created_by?.id && !members.data?.some((member) => member.id === user.id),
  );

  return (
    <>
      <Button type="text" icon={<TeamOutlined />} onClick={() => setOpen(true)}>
        项目成员
      </Button>
      <Modal title="项目成员" open={open} onCancel={() => setOpen(false)} footer={null}>
        <p>拥有者：{project?.created_by?.username}</p>
        <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
          <Select
            style={{ flex: 1 }}
            placeholder="选择协作者"
            showSearch
            optionFilterProp="label"
            value={selected}
            onChange={setSelected}
            options={available?.map((user) => ({ label: user.username, value: user.id }))}
          />
          <Button
            disabled={!selected}
            loading={add.isPending}
            onClick={async () => {
              await add.mutateAsync(selected!);
              setSelected(undefined);
              members.refetch();
            }}
          >
            添加
          </Button>
        </Space.Compact>
        <Table<UserResponse>
          rowKey="id"
          dataSource={members.data}
          pagination={false}
          columns={[
            { title: '协作者', dataIndex: 'username' },
            { title: '状态', render: (_, user) => (user.is_active ? '启用' : '停用') },
            {
              title: '操作',
              render: (_, user) => (
                <Button
                  type="link"
                  danger
                  loading={remove.isPending}
                  onClick={async () => {
                    await remove.mutateAsync(user.id!);
                    members.refetch();
                  }}
                >
                  移除
                </Button>
              ),
            },
          ]}
        />
      </Modal>
    </>
  );
}
