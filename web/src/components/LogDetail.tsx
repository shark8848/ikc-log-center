import React from 'react';
import { Drawer, Descriptions, Tag, Typography } from 'antd';
import type { LogEntry } from '../types';

const { Paragraph } = Typography;

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARNING: 'orange',
  WARN: 'orange',
  ERROR: 'red',
  CRITICAL: 'magenta',
};

interface Props {
  record: LogEntry | null;
  open: boolean;
  onClose: () => void;
}

const LogDetail: React.FC<Props> = ({ record, open, onClose }) => {
  if (!record) return null;

  const { payload, ...meta } = record;

  return (
    <Drawer
      title="日志详情"
      open={open}
      onClose={onClose}
      width={560}
    >
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label="时间">{record.ts || '-'}</Descriptions.Item>
        <Descriptions.Item label="级别">
          <Tag color={levelColors[(record.level || '').toUpperCase()] || 'default'}>
            {record.level || '-'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Logger">{record.logger || '-'}</Descriptions.Item>
        <Descriptions.Item label="消息">{record.message || '-'}</Descriptions.Item>
        <Descriptions.Item label="Trace ID">{record.trace_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="Span ID">{record.span_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="Parent ID">{record.parent_id || '-'}</Descriptions.Item>
      </Descriptions>

      {payload && (
        <>
          <Typography.Title level={5} style={{ marginTop: 24 }}>
            Payload
          </Typography.Title>
          <Paragraph>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 6,
                fontSize: 12,
                maxHeight: 400,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(payload, null, 2)}
            </pre>
          </Paragraph>
        </>
      )}

      {/* Show extra fields not in standard schema */}
      {Object.keys(meta).length > 7 && (
        <>
          <Typography.Title level={5} style={{ marginTop: 24 }}>
            其他字段
          </Typography.Title>
          <Descriptions column={1} bordered size="small">
            {Object.entries(meta)
              .filter(([k]) => !['ts', 'level', 'logger', 'message', 'trace_id', 'span_id', 'parent_id'].includes(k))
              .map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')}
                </Descriptions.Item>
              ))}
          </Descriptions>
        </>
      )}
    </Drawer>
  );
};

export default LogDetail;
