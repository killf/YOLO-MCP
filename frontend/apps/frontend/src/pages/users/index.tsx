import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Checkbox, Form, Input, Modal, Popconfirm, Result, Space, Spin, Table, Tag, Typography } from 'antd';

import { createUser, getUsers, updateUser } from '@/api/services/user';
import type { UserResponse } from '@/api/types';
import useMe from '@/hooks/useMe';
import { userKey } from '@/api/queryKeyFactories/user';

interface UserForm {
  username: string;
  password: string;
  is_admin: boolean;
}

export default function Users() {
  const me = useMe();
  const cache = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [resetUser, setResetUser] = useState<UserResponse>();
  const [form] = Form.useForm<UserForm>();
  const [passwordForm] = Form.useForm<{ password: string }>();
  const users = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => getUsers({ page: page - 1, size: 10 }),
    enabled: !!me.data?.is_admin,
  });
  const refresh = () => cache.invalidateQueries({ queryKey: ['admin-users'] });
  const create = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      setOpen(false);
      form.resetFields();
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: Parameters<typeof updateUser>[1] }) => updateUser(id, changes),
    onSuccess: () => {
      setResetUser(undefined);
      passwordForm.resetFields();
      refresh();
      cache.invalidateQueries({ queryKey: userKey.me() });
    },
  });

  if (me.isPending) return <Spin style={{ margin: 48 }} />;
  if (!me.data?.is_admin) return <Result status="403" title="仅管理员可以管理用户" />;

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          用户管理
        </Typography.Title>
        <Button type="primary" onClick={() => setOpen(true)}>
          添加用户
        </Button>
      </Space>
      <Table<UserResponse>
        rowKey="id"
        loading={users.isFetching}
        dataSource={users.data?.data}
        pagination={{ current: page, pageSize: 10, total: users.data?.meta_data?.total, onChange: setPage }}
        columns={[
          { title: '邮箱', dataIndex: 'username' },
          { title: '角色', render: (_, user) => (user.is_admin ? '管理员' : '普通用户') },
          {
            title: '状态',
            render: (_, user) => (
              <Tag color={user.is_active ? 'green' : 'default'}>{user.is_active ? '启用' : '停用'}</Tag>
            ),
          },
          {
            title: '操作',
            render: (_, user) => (
              <Space>
                <Popconfirm
                  title={user.is_active ? '停用账号并撤销其会话和令牌？' : '启用账号？'}
                  onConfirm={() => update.mutateAsync({ id: user.id!, changes: { is_active: !user.is_active } })}
                >
                  <Button type="link" disabled={update.isPending}>
                    {user.is_active ? '停用' : '启用'}
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title="确认修改系统角色？"
                  onConfirm={() => update.mutateAsync({ id: user.id!, changes: { is_admin: !user.is_admin } })}
                >
                  <Button type="link" disabled={update.isPending}>
                    {user.is_admin ? '设为普通用户' : '设为管理员'}
                  </Button>
                </Popconfirm>
                <Button type="link" onClick={() => setResetUser(user)}>
                  重置密码
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="添加用户"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ is_admin: false }}
          onFinish={(values) => create.mutate(values)}
        >
          <Form.Item name="username" label="邮箱" rules={[{ required: true, type: 'email' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6, max: 18 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="is_admin" valuePropName="checked">
            <Checkbox>系统管理员</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`重置密码：${resetUser?.username ?? ''}`}
        open={!!resetUser}
        onCancel={() => {
          setResetUser(undefined);
          passwordForm.resetFields();
        }}
        onOk={() => passwordForm.submit()}
        confirmLoading={update.isPending}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={(values) => update.mutate({ id: resetUser!.id!, changes: values })}
        >
          <Form.Item name="password" label="新密码" rules={[{ required: true, min: 6, max: 18 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
