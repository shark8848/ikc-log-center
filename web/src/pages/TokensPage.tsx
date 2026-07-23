import React, { useState } from 'react';
import {
  Table, Button, Tag, Modal, Input, message, Popconfirm, Typography, Alert,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listTokens, createToken, revokeToken } from '../api';
import type { TokenInfo } from '../types';

const { Paragraph } = Typography;

const TokensPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [description, setDescription] = useState('');
  const [newToken, setNewToken] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['tokens'],
    queryFn: listTokens,
  });

  const createMutation = useMutation({
    mutationFn: (desc: string) => createToken(desc),
    onSuccess: (res) => {
      setNewToken(res.token);
      queryClient.invalidateQueries({ queryKey: ['tokens'] });
    },
    onError: () => message.error('创建 Token 失败'),
  });

  const revokeMutation = useMutation({
    mutationFn: (prefix: string) => revokeToken(prefix),
    onSuccess: () => {
      message.success('Token 已撤销');
      queryClient.invalidateQueries({ queryKey: ['tokens'] });
    },
    onError: () => message.error('撤销失败'),
  });

  const handleCreate = () => {
    createMutation.mutate(description);
  };

  const closeCreateModal = () => {
    setCreateOpen(false);
    setDescription('');
    setNewToken(null);
  };

  const columns = [
    {
      title: 'Prefix',
      dataIndex: 'prefix',
      key: 'prefix',
      width: 140,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 200,
    },
    {
      title: '状态',
      dataIndex: 'active',
      key: 'active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>{active ? '活跃' : '已撤销'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: TokenInfo) =>
        record.active ? (
          <Popconfirm
            title="确认撤销此 Token？"
            onConfirm={() => revokeMutation.mutate(record.prefix)}
          >
            <Button type="link" danger icon={<DeleteOutlined />} size="small">
              撤销
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>API Token 管理</h3>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          生成 Token
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data?.tokens || []}
        loading={isLoading}
        rowKey="prefix"
        size="small"
        pagination={false}
      />

      <Modal
        title="生成新 Token"
        open={createOpen}
        onCancel={closeCreateModal}
        footer={
          newToken
            ? [<Button key="close" type="primary" onClick={closeCreateModal}>完成</Button>]
            : [
                <Button key="cancel" onClick={closeCreateModal}>取消</Button>,
                <Button key="ok" type="primary" loading={createMutation.isPending} onClick={handleCreate}>
                  生成
                </Button>,
              ]
        }
      >
        {!newToken ? (
          <div>
            <p>输入 Token 描述（可选）：</p>
            <Input
              placeholder="例如：production-server"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        ) : (
          <div>
            <Alert
              type="warning"
              message="请立即保存此 Token，关闭后将无法再次查看！"
              style={{ marginBottom: 16 }}
            />
            <Paragraph copyable={{ text: newToken }}>
              <code style={{ fontSize: 13, wordBreak: 'break-all' }}>{newToken}</code>
            </Paragraph>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default TokensPage;
