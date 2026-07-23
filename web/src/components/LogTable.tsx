import React, { useState } from 'react';
import { Table, Tag, Tooltip, Space, Popover, Checkbox, Button } from 'antd';
import { EyeOutlined, NodeIndexOutlined, SettingOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { LogEntry } from '../types';

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARNING: 'orange',
  WARN: 'orange',
  ERROR: 'red',
  CRITICAL: 'magenta',
};

// 可筛选展示的字段（默认全选）
const FIELD_OPTIONS = [
  { label: '时间', value: 'ts' },
  { label: '级别', value: 'level' },
  { label: 'Logger', value: 'logger' },
  { label: '消息', value: 'message' },
  { label: 'Trace ID', value: 'trace_id' },
  { label: 'Span ID', value: 'span_id' },
  { label: 'Parent ID', value: 'parent_id' },
];
const ALL_FIELD_KEYS = FIELD_OPTIONS.map((o) => o.value);

interface Props {
  data: LogEntry[];
  loading?: boolean;
  onRowClick: (record: LogEntry) => void;
  onTraceChain: (record: LogEntry) => void;
}

const LogTable: React.FC<Props> = ({ data, loading, onRowClick, onTraceChain }) => {
  // 默认展示全部字段
  const [visibleFields, setVisibleFields] = useState<string[]>(ALL_FIELD_KEYS);

  // 全部可切换的数据列（按顺序）
  const allDataColumns: ColumnsType<LogEntry> = [
    {
      title: '时间',
      dataIndex: 'ts',
      key: 'ts',
      width: 200,
      ellipsis: true,
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => (
        <Tag color={levelColors[level?.toUpperCase()] || 'default'}>
          {level || '-'}
        </Tag>
      ),
    },
    {
      title: 'Logger',
      dataIndex: 'logger',
      key: 'logger',
      width: 180,
      ellipsis: true,
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: 'Trace ID',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 170,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: 'Span ID',
      dataIndex: 'span_id',
      key: 'span_id',
      width: 140,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: 'Parent ID',
      dataIndex: 'parent_id',
      key: 'parent_id',
      width: 140,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
  ];

  const columns: ColumnsType<LogEntry> = [
    ...allDataColumns.filter((c) => visibleFields.includes(c.key as string)),
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: LogEntry) => (
        <Space size={4}>
          <Tooltip title="查看详细日志">
            <EyeOutlined
              style={{ fontSize: 15, color: '#1677ff', cursor: 'pointer' }}
              onClick={(e) => { e.stopPropagation(); onRowClick(record); }}
            />
          </Tooltip>
          <Tooltip title="日志链路">
            <NodeIndexOutlined
              style={{ fontSize: 15, color: '#722ed1', cursor: 'pointer' }}
              onClick={(e) => { e.stopPropagation(); onTraceChain(record); }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <Popover
          title="选择展示的字段"
          trigger="click"
          placement="bottomRight"
          content={
            <div>
              <Space style={{ marginBottom: 8 }} size={4}>
                <Button size="small" type="link" onClick={() => setVisibleFields(ALL_FIELD_KEYS)}>全选</Button>
                <Button size="small" type="link" onClick={() => setVisibleFields([])}>清空</Button>
              </Space>
              <Checkbox.Group
                options={FIELD_OPTIONS}
                value={visibleFields}
                onChange={(vals) => setVisibleFields(vals as string[])}
                style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
              />
            </div>
          }
        >
          <Button size="small" icon={<SettingOutlined />}>
            列设置 ({visibleFields.length}/{ALL_FIELD_KEYS.length})
          </Button>
        </Popover>
      </div>
      <Table<LogEntry>
        columns={columns}
        dataSource={data}
        loading={loading}
        rowKey={(_, idx) => String(idx)}
        size="small"
        pagination={{
          defaultPageSize: 50,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100', '200', '500'],
          showTotal: (t) => `共 ${t} 条`,
        }}
        onRow={(record) => ({
          onClick: () => onRowClick(record),
          style: { cursor: 'pointer' },
        })}
        scroll={{ x: 1100 }}
      />
    </div>
  );
};

export default LogTable;
