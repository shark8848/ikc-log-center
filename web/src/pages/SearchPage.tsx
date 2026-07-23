import React, { useState, useCallback } from 'react';
import { message } from 'antd';
import SearchForm from '../components/SearchForm';
import type { SearchValues } from '../components/SearchForm';
import LogTable from '../components/LogTable';
import LogDetail from '../components/LogDetail';
import TraceChain from '../components/TraceChain';
import { searchLogs } from '../api';
import type { LogEntry } from '../types';

const SearchPage: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);

  const handleSearch = useCallback(async (values: SearchValues) => {
    setLoading(true);
    try {
      const res = await searchLogs({
        trace_id: values.trace_id || undefined,
        level: values.level || undefined,
        message_substr: values.message_substr || undefined,
        limit: values.limit || 100,
      });
      setLogs(res.items || []);
      message.success(`查询到 ${res.count} 条日志`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '查询失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRowClick = useCallback((record: LogEntry) => {
    setSelected(record);
    setDrawerOpen(true);
  }, []);

  const handleTraceChain = useCallback((record: LogEntry) => {
    setTraceId(record.trace_id || null);
    setTraceOpen(true);
  }, []);

  return (
    <div>
      <SearchForm onSearch={handleSearch} loading={loading} />
      <LogTable data={logs} loading={loading} onRowClick={handleRowClick} onTraceChain={handleTraceChain} />
      <LogDetail
        record={selected}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
      <TraceChain
        traceId={traceId}
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
      />
    </div>
  );
};

export default SearchPage;
