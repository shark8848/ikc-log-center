import React, { useState } from 'react';
import { Card, Col, Row, Statistic, Spin, Empty, Segmented } from 'antd';
import {
  FileTextOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Line, Pie } from '@ant-design/charts';
import { getStats } from '../api';

const DashboardPage: React.FC = () => {
  const [granularity, setGranularity] = useState<string>('hour');

  const { data, isLoading } = useQuery({
    queryKey: ['stats', granularity],
    queryFn: () => getStats(granularity),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  if (!data) {
    return <Empty description="暂无数据" />;
  }

  const { total, levels, trend } = data;

  const pieData = Object.entries(levels).map(([level, count]) => ({
    type: level,
    value: count,
  }));

  const pieConfig = {
    data: pieData,
    angleField: 'value',
    colorField: 'type',
    radius: 0.8,
    label: {
      text: (d: { type: string; value: number }) => `${d.type}: ${d.value}`,
    },
    legend: { position: 'bottom' as const },
  };

  const lineConfig = {
    data: trend.map((t) => ({ time: t.time?.slice(5) || '', count: t.count })),
    xField: 'time',
    yField: 'count',
    smooth: true,
    point: { shapeField: 'circle', sizeField: 3 },
    axis: { y: { title: '日志数' } },
    style: { lineWidth: 2 },
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="总日志数" value={total} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="ERROR"
              value={levels['ERROR'] || 0}
              prefix={<CloseCircleOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="WARNING"
              value={levels['WARNING'] || levels['WARN'] || 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="INFO"
              value={levels['INFO'] || 0}
              prefix={<InfoCircleOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="日志级别分布" style={{ marginBottom: 16 }}>
            {pieData.length > 0 ? (
              <Pie {...pieConfig} height={280} />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title="日志趋势"
            extra={
              <Segmented
                size="small"
                value={granularity}
                onChange={(v) => setGranularity(v as string)}
                options={[
                  { label: '分钟', value: 'minute' },
                  { label: '小时', value: 'hour' },
                  { label: '日', value: 'day' },
                  { label: '月', value: 'month' },
                ]}
              />
            }
          >
            {trend.length > 0 ? (
              <Line {...lineConfig} height={280} />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DashboardPage;
