import React, { useEffect, useState } from 'react';
import { Drawer, Timeline, Tag, Typography, Spin, Empty, Space, Badge } from 'antd';
import {
  ClockCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined,
  WarningOutlined, BugOutlined, StopOutlined,
} from '@ant-design/icons';
import { getTraceChain } from '../api';
import type { LogEntry } from '../types';

const { Text, Paragraph } = Typography;

const levelConfig: Record<string, { color: string; icon: React.ReactNode }> = {
  DEBUG: { color: '#8c8c8c', icon: <ClockCircleOutlined /> },
  INFO: { color: '#1677ff', icon: <InfoCircleOutlined /> },
  WARNING: { color: '#fa8c16', icon: <WarningOutlined /> },
  WARN: { color: '#fa8c16', icon: <WarningOutlined /> },
  ERROR: { color: '#ff4d4f', icon: <BugOutlined /> },
  CRITICAL: { color: '#cf1322', icon: <StopOutlined /> },
};

interface Props {
  traceId: string | null;
  open: boolean;
  onClose: () => void;
}

const TraceChain: React.FC<Props> = ({ traceId, open, onClose }) => {
  const [items, setItems] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!traceId || !open) return;
    setLoading(true);
    getTraceChain(traceId)
      .then((res) => setItems(res.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [traceId, open]);

  const errorCount = items.filter((i) => ['ERROR', 'CRITICAL'].includes((i.level || '').toUpperCase())).length;

  return (
    <Drawer
      title={
        <Space>
          <span>日志链路</span>
          {traceId && <Tag color="blue">{traceId}</Tag>}
        </Space>
      }
      open={open}
      onClose={onClose}
      width={620}
      extra={
        items.length > 0 && (
          <Space>
            <Badge count={items.length} style={{ backgroundColor: '#1677ff' }} overflowCount={999} />
            <Text type="secondary">条日志</Text>
            {errorCount > 0 && (
              <>
                <Badge count={errorCount} style={{ backgroundColor: '#ff4d4f' }} />
                <Text type="danger">条异常</Text>
              </>
            )}
          </Space>
        )
      }
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin tip="加载链路..." /></div>
      ) : items.length === 0 ? (
        <Empty description="该 Trace ID 无关联日志" />
      ) : (
        <Timeline
          items={items.map((item, idx) => {
            const lvl = (item.level || 'INFO').toUpperCase();
            const cfg = levelConfig[lvl] || levelConfig.INFO;
            return {
              key: idx,
              color: cfg.color,
              dot: cfg.icon,
              children: (
                <div style={{ paddingBottom: 4 }}>
                  <Space size={8} wrap>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.ts || '-'}</Text>
                    <Tag color={lvl === 'ERROR' || lvl === 'CRITICAL' ? 'red' : lvl === 'WARNING' || lvl === 'WARN' ? 'orange' : lvl === 'DEBUG' ? 'default' : 'blue'} style={{ fontSize: 11 }}>
                      {item.level}
                    </Tag>
                    <Tag style={{ fontSize: 11 }}>{item.logger || '-'}</Tag>
                    {item.source_ip && <Tag color="geekblue" style={{ fontSize: 11 }}>{String(item.source_ip)}</Tag>}
                  </Space>
                  <Paragraph
                    style={{ margin: '4px 0 0', fontSize: 13 }}
                    ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                  >
                    {item.message || '-'}
                  </Paragraph>
                  {item.span_id && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      span: {item.span_id}{item.parent_id ? ` ← parent: ${item.parent_id}` : ''}
                    </Text>
                  )}
                  {item.payload && Object.keys(item.payload).length > 0 && (
                    <pre style={{ background: '#f6f6f6', padding: '6px 8px', borderRadius: 4, fontSize: 11, marginTop: 4, maxHeight: 120, overflow: 'auto' }}>
                      {JSON.stringify(item.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ),
            };
          })}
        />
      )}
    </Drawer>
  );
};

export default TraceChain;
