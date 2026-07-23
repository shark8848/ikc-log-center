import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from './components/Layout';
import SearchPage from './pages/SearchPage';
import DashboardPage from './pages/DashboardPage';
import TokensPage from './pages/TokensPage';
import HelpPage from './pages/HelpPage';
import TopologyPage from './pages/TopologyPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10000,
    },
  },
});

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<SearchPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/topology" element={<TopologyPage />} />
              <Route path="/tokens" element={<TokensPage />} />
              <Route path="/help" element={<HelpPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
};

export default App;
