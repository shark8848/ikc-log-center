import React from 'react';
import { Form, Input, Select, InputNumber, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

export interface SearchValues {
  trace_id?: string;
  level?: string;
  message_substr?: string;
  limit?: number;
}

interface Props {
  onSearch: (values: SearchValues) => void;
  loading?: boolean;
}

const SearchForm: React.FC<Props> = ({ onSearch, loading }) => {
  const [form] = Form.useForm<SearchValues>();

  const handleFinish = (values: SearchValues) => {
    onSearch(values);
  };

  return (
    <Form
      form={form}
      layout="inline"
      onFinish={handleFinish}
      initialValues={{ limit: 100 }}
      style={{ marginBottom: 16, flexWrap: 'wrap', gap: 8 }}
    >
      <Form.Item name="trace_id" label="Trace ID">
        <Input placeholder="可选" allowClear style={{ width: 200 }} />
      </Form.Item>
      <Form.Item name="level" label="级别">
        <Select
          placeholder="全部"
          allowClear
          style={{ width: 130 }}
          options={[
            { value: 'DEBUG', label: 'DEBUG' },
            { value: 'INFO', label: 'INFO' },
            { value: 'WARNING', label: 'WARNING' },
            { value: 'ERROR', label: 'ERROR' },
            { value: 'CRITICAL', label: 'CRITICAL' },
          ]}
        />
      </Form.Item>
      <Form.Item name="message_substr" label="关键词">
        <Input placeholder="消息包含..." allowClear style={{ width: 200 }} />
      </Form.Item>
      <Form.Item name="limit" label="条数">
        <InputNumber min={1} max={500} style={{ width: 90 }} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={loading}>
          查询
        </Button>
      </Form.Item>
    </Form>
  );
};

export default SearchForm;
