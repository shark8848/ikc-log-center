import React from 'react';
import { Layout as AntLayout, Menu } from 'antd';
import {
  SearchOutlined,
  DashboardOutlined,
  KeyOutlined,
  QuestionCircleOutlined,
  ClusterOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

const { Sider, Content, Header } = AntLayout;

const menuItems = [
  { key: '/', icon: <SearchOutlined />, label: '日志搜索' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/topology', icon: <ClusterOutlined />, label: '服务拓扑' },
  { key: '/tokens', icon: <KeyOutlined />, label: 'Token 管理' },
  { key: '/help', icon: <QuestionCircleOutlined />, label: '使用帮助' },
];

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" breakpoint="lg" collapsedWidth="60">
        <div
          style={{
            height: 48,
            margin: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 700,
            fontSize: 16,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          Log Center
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <h3 style={{ margin: 0 }}>日志中心管理平台</h3>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default AppLayout;
