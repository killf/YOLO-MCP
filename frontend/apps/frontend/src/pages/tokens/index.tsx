import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';

import { createToken, getTokens, getUsers, revokeToken } from '@/api/services/user';
import type { PersonalToken } from '@/api/services/user';
import useMe from '@/hooks/useMe';

export default function Tokens() {
  const me = useMe();
  const [userId, setUserId] = useState<number>();
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState('');
  const [form] = Form.useForm<{ name: string; expires_days: number | null }>();
  const tokens = useQuery({ queryKey: ['personal-tokens', userId], queryFn: () => getTokens(userId) });
  const users = useQuery({
    queryKey: ['token-users'],
    queryFn: () => getUsers({ page: 0, size: 1000 }),
    enabled: !!me.data?.is_admin,
  });
  const create = useMutation({
    mutationFn: createToken,
    onSuccess: (result) => {
      setOpen(false);
      form.resetFields();
      setSecret(result.data.token);
      tokens.refetch();
    },
  });
  const revoke = useMutation({
    mutationFn: revokeToken,
    onSuccess: () => {
      tokens.refetch();
    },
  });
  const date = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          访问令牌 / MCP
        </Typography.Title>
        <Space>
          {me.data?.is_admin && (
            <Select
              style={{ minWidth: 220 }}
              placeholder="我的令牌"
              allowClear
              showSearch
              optionFilterProp="label"
              value={userId}
              onChange={setUserId}
              options={users.data?.data.map((user) => ({ label: user.username, value: user.id }))}
            />
          )}
          <Button type="primary" onClick={() => setOpen(true)}>
            创建个人令牌
          </Button>
        </Space>
      </Space>
      <Typography.Paragraph>
        MCP 地址：<Typography.Text copyable>{`${window.location.origin}/mcp`}</Typography.Text>
      </Typography.Paragraph>
      <Typography.Paragraph>
        传输方式为 Streamable HTTP。客户端需设置 Authorization: Bearer &lt;个人令牌&gt;。令牌继承账号当前项目权限。
      </Typography.Paragraph>
      <Table<PersonalToken>
        rowKey="id"
        loading={tokens.isFetching}
        dataSource={tokens.data?.data}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '创建时间', dataIndex: 'created_at', render: date },
          { title: '到期时间', dataIndex: 'expires_at', render: (value) => (value ? date(value) : '永不过期') },
          { title: '最近使用', dataIndex: 'last_used_at', render: date },
          {
            title: '状态',
            render: (_, token) => (
              <Tag>
                {token.revoked_at
                  ? '已撤销'
                  : token.expires_at && new Date(token.expires_at).getTime() <= Date.now()
                  ? '已过期'
                  : '有效'}
              </Tag>
            ),
          },
          {
            title: '操作',
            render: (_, token) => (
              <Popconfirm
                title="撤销后，使用此令牌的请求将被拒绝。继续？"
                onConfirm={() => revoke.mutateAsync(token.id)}
              >
                <Button type="link" danger disabled={!!token.revoked_at || revoke.isPending}>
                  撤销
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
      <Modal
        title="创建个人访问令牌"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ expires_days: 90 }}
          onFinish={(values) => create.mutate({ ...values, expires_days: values.expires_days || null })}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, max: 64 }]}>
            <Input placeholder="例如：桌面 MCP 客户端" />
          </Form.Item>
          <Form.Item name="expires_days" label="有效期">
            <Select
              options={[
                { label: '30 天', value: 30 },
                { label: '90 天', value: 90 },
                { label: '365 天', value: 365 },
                { label: '永不过期', value: 0 },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="请保存访问令牌"
        open={!!secret}
        onCancel={() => {
          setSecret('');
          create.reset();
        }}
        onOk={() => {
          setSecret('');
          create.reset();
        }}
        cancelButtonProps={{ style: { display: 'none' } }}
      >
        <Typography.Paragraph>明文只显示这一次，关闭后无法再次查看。</Typography.Paragraph>
        <Typography.Paragraph copyable style={{ overflowWrap: 'anywhere' }}>
          {secret}
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
