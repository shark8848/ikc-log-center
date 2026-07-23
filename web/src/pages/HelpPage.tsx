import React, { useState } from 'react';
import { Card, Typography, Tabs, Alert, Table, Tag, Space, Divider, Descriptions } from 'antd';
import {
  QuestionCircleOutlined, CopyOutlined, CheckOutlined,
  CloudServerOutlined, AppstoreAddOutlined, RobotOutlined,
} from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;

const CodeBlock: React.FC<{ code: string; title?: string }> = ({ code, title }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div style={{ position: 'relative', marginBottom: 16 }}>
      {title && <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>}
      <pre
        style={{
          background: '#1e1e2e',
          color: '#cdd6f4',
          padding: '16px 20px',
          borderRadius: 8,
          overflow: 'auto',
          fontSize: 13,
          lineHeight: 1.6,
          margin: '4px 0 0',
        }}
      >
        {code}
      </pre>
      <span
        onClick={handleCopy}
        style={{ position: 'absolute', top: title ? 24 : 8, right: 12, cursor: 'pointer', color: '#89b4fa' }}
      >
        {copied ? <CheckOutlined /> : <CopyOutlined />}
      </span>
    </div>
  );
};

/* ============================ 服务器 ============================ */

const serverInstallCmd = `# 安装服务端（含 SQLite 存储）
pip install ikc-log-center

# 按需安装存储后端
pip install ikc-log-center[pg]    # PostgreSQL
pip install ikc-log-center[mysql] # MySQL
pip install ikc-log-center[es]    # Elasticsearch
pip install ikc-log-center[grpc]  # gRPC 接收
pip install ikc-log-center[all]   # 全部`;

const serverStartCmd = `# 方式一：一键脚本（推荐）
./start_log_center.sh --ui          # 启动 HTTP + Web UI
./start_log_center.sh --ui --grpc   # 同时启动 gRPC
./stop_log_center.sh                # 停止
./show_log_center.sh                # 查看状态

# 方式二：手动启动
python -m log_center_server --host 0.0.0.0 --port 9315 --ui

# 开发模式（热重载）
python -m log_center_server --reload`;

const serverEnvData = [
  { key: '1', name: 'LOG_CENTER_PORT', def: '9315', desc: 'HTTP API 端口' },
  { key: '2', name: 'LOG_CENTER_HOST', def: '0.0.0.0', desc: '绑定地址' },
  { key: '3', name: 'LOG_CENTER_STORE', def: 'local', desc: '存储后端：local / pg / mysql / es' },
  { key: '4', name: 'LOG_CENTER_DB_PATH', def: 'data/log_center/log_center.db', desc: 'SQLite 数据库文件路径' },
  { key: '5', name: 'LOG_CENTER_PG_HOST / PORT / USER / PASSWORD / DB', def: '-', desc: 'PostgreSQL 连接参数' },
  { key: '6', name: 'LOG_CENTER_ES_URL', def: '-', desc: 'Elasticsearch 地址' },
  { key: '7', name: 'LOG_CENTER_AUTH_ENABLED', def: 'false', desc: '是否启用 Bearer Token 鉴权' },
];

const tokenCmd = `# 生成 Token
python -m log_center_server --gen-token "prod-ingest"

# 列出所有 Token
python -m log_center_server --list-tokens

# 吊销 Token（按前缀）
python -m log_center_server --revoke-token sk-lc-abc123`;

const apiListData = [
  { key: '1', method: 'POST', path: '/ingest', desc: '接收日志（SDK 投递入口）' },
  { key: '2', method: 'GET', path: '/search', desc: '按 trace_id / 级别 / 关键词检索日志' },
  { key: '3', method: 'GET', path: '/api/trace/{trace_id}', desc: '获取完整调用链路（按时间正序）' },
  { key: '4', method: 'GET', path: '/api/stats', desc: '日志统计（仪表盘）' },
  { key: '5', method: 'GET', path: '/api/nodes', desc: '接入节点（服务拓扑）' },
  { key: '6', method: 'GET/POST/DELETE', path: '/api/tokens', desc: 'Token 管理' },
];

const ServerSection: React.FC = () => (
  <div>
    <Title level={5}>安装</Title>
    <CodeBlock title="pip install" code={serverInstallCmd} />

    <Divider />
    <Title level={5}>启动服务</Title>
    <CodeBlock title="启动 / 停止" code={serverStartCmd} />
    <Alert
      type="success"
      showIcon
      message="启动后访问 http://localhost:9315 即可打开 Web 管理平台"
      style={{ marginBottom: 16 }}
    />

    <Divider />
    <Title level={5}>环境变量</Title>
    <Table
      size="small"
      pagination={false}
      dataSource={serverEnvData}
      columns={[
        { title: '变量名', dataIndex: 'name', key: 'name', render: (t: string) => <Text code>{t}</Text> },
        { title: '默认值', dataIndex: 'def', key: 'def' },
        { title: '说明', dataIndex: 'desc', key: 'desc' },
      ]}
    />

    <Divider />
    <Title level={5}>Token 管理（鉴权）</Title>
    <Paragraph type="secondary">
      启用 <Text code>LOG_CENTER_AUTH_ENABLED=true</Text> 后，所有 API 调用需携带 Bearer Token：
    </Paragraph>
    <CodeBlock title="CLI Token 管理" code={tokenCmd} />

    <Divider />
    <Title level={5}>主要 API</Title>
    <Table
      size="small"
      pagination={false}
      dataSource={apiListData}
      columns={[
        { title: '方法', dataIndex: 'method', key: 'method', width: 130, render: (t: string) => <Tag color="blue">{t}</Tag> },
        { title: '路径', dataIndex: 'path', key: 'path', render: (t: string) => <Text code>{t}</Text> },
        { title: '说明', dataIndex: 'desc', key: 'desc' },
      ]}
    />
  </div>
);

/* ============================ 客户端集成 ============================ */

const sdkInstallCmd = `# 安装 SDK
pip install ikc-log-center

# 按需安装框架集成
pip install ikc-log-center[fastapi]  # FastAPI / Starlette
pip install ikc-log-center[flask]    # Flask
pip install ikc-log-center[celery]   # Celery
pip install ikc-log-center[grpc]     # gRPC 投递`;

const sdkQuickStart = `# 1. 配置 SDK（应用启动时调用一次）
import log_center_sdk

log_center_sdk.configure(module_name="my-service")

# 2. 获取 logger 并记录日志
logger = log_center_sdk.get_logger("my-service")
logger.info("订单创建成功", extra={"order_id": "12345"})
logger.error("支付失败", extra={"code": "PAY_TIMEOUT"})`;

const sdkEnvData = [
  { key: '1', name: 'LOG_CENTER_SERVER_URL', def: 'http://localhost:9315', desc: '日志服务器地址' },
  { key: '2', name: 'LOG_CENTER_DELIVERY', def: 'api', desc: '投递方式：api（HTTP）/ grpc / celery（必须为 api 才能经 HTTP 送达）' },
  { key: '3', name: 'LOG_CENTER_TOKEN', def: '-', desc: 'Bearer Token（服务器启用鉴权时必填）' },
  { key: '4', name: 'LOG_LEVEL', def: 'INFO', desc: '日志级别' },
  { key: '5', name: 'LOG_JSON', def: 'true', desc: '是否输出 JSON 格式' },
  { key: '6', name: 'LOG_FILE_PATH', def: 'logs/{module}.log', desc: '本地滚动日志文件路径' },
];

const instrumentedExample = `from log_center_sdk import instrumented

# 自动记录函数耗时、入参、异常
@instrumented("document_parse")
def parse(path, fmt="pdf"):
    ...

# 只记录指定参数，并脱敏敏感字段
@instrumented("llm_call", log_args={"model"}, redact_args={"api_key"})
async def call_llm(prompt, model, api_key):
    ...

# 慢调用告警（超过阈值记录 WARNING）
@instrumented("es_query", slow_threshold_ms=500)
def search(query):
    ...`;

const fastapiExample = `from fastapi import FastAPI
from log_center_sdk.integrations.fastapi import TraceMiddleware
import log_center_sdk

log_center_sdk.configure(module_name="order-service")

app = FastAPI()
# 自动提取 X-Trace-Id / X-Span-Id / X-Request-Id 请求头
app.add_middleware(TraceMiddleware)

@app.post("/orders")
def create_order():
    log_center_sdk.get_logger("order").info("creating order")
    return {"ok": True}`;

const flaskExample = `from flask import Flask
from log_center_sdk.integrations.flask import init_trace_hooks
import log_center_sdk

log_center_sdk.configure(module_name="user-service")

app = Flask(__name__)
# 注册 before/after request 钩子，自动传递 trace 上下文
init_trace_hooks(app)`;

const celeryExample = `from celery import Celery
from log_center_sdk import patch_celery_app
import log_center_sdk

log_center_sdk.configure(module_name="worker")

celery_app = Celery("tasks", broker="redis://localhost:6379/0")
# worker fork 后自动重新初始化日志（避免句柄失效）
patch_celery_app(celery_app)`;

const tracePropagate = `# 跨服务传递 trace 上下文（HTTP 调用时携带请求头）
import requests

requests.get(
    "http://downstream/api",
    headers={
        "X-Trace-Id": "trace-abc-123",
        "X-Span-Id": "span-001",
        "X-Request-Id": "req-xyz",
    },
)`;

const ClientSection: React.FC = () => (
  <div>
    <Title level={5}>安装 SDK</Title>
    <CodeBlock title="pip install" code={sdkInstallCmd} />

    <Divider />
    <Title level={5}>快速开始</Title>
    <CodeBlock title="configure + get_logger" code={sdkQuickStart} />

    <Divider />
    <Title level={5}>客户端环境变量</Title>
    <Table
      size="small"
      pagination={false}
      dataSource={sdkEnvData}
      columns={[
        { title: '变量名', dataIndex: 'name', key: 'name', render: (t: string) => <Text code>{t}</Text> },
        { title: '默认值', dataIndex: 'def', key: 'def' },
        { title: '说明', dataIndex: 'desc', key: 'desc' },
      ]}
    />
    <Alert
      type="warning"
      showIcon
      message="LOG_CENTER_DELIVERY 必须设为 'api' 才能通过 HTTP 正确送达日志"
      style={{ marginTop: 12, marginBottom: 16 }}
    />

    <Divider />
    <Title level={5}>@instrumented 自动埋点</Title>
    <Paragraph type="secondary">
      装饰器自动记录函数耗时、入参、返回值与异常，无需手动打点：
    </Paragraph>
    <CodeBlock title="instrumented 装饰器" code={instrumentedExample} />

    <Divider />
    <Title level={5}>框架集成</Title>
    <Tabs
      type="card"
      items={[
        { key: 'fastapi', label: 'FastAPI', children: <CodeBlock code={fastapiExample} /> },
        { key: 'flask', label: 'Flask', children: <CodeBlock code={flaskExample} /> },
        { key: 'celery', label: 'Celery', children: <CodeBlock code={celeryExample} /> },
      ]}
    />

    <Divider />
    <Title level={5}>跨服务 Trace 传递</Title>
    <Paragraph type="secondary">
      调用下游服务时携带 trace 请求头，即可在「日志链路」中串联完整调用链：
    </Paragraph>
    <CodeBlock title="传递 trace 上下文" code={tracePropagate} />
  </div>
);

/* ============================ AI Agent MCP 接入 ============================ */

const toolColumns = [
  { title: '工具名', dataIndex: 'name', key: 'name', render: (t: string) => <Tag color="blue">{t}</Tag> },
  { title: '参数', dataIndex: 'params', key: 'params' },
  { title: '说明', dataIndex: 'desc', key: 'desc' },
];

const toolData = [
  { key: '1', name: 'search_logs', params: 'trace_id, level, message_substr, limit', desc: '按 trace_id / 日志级别 / 消息关键词检索日志' },
  { key: '2', name: 'get_log_stats', params: 'granularity (minute|hour|day|month)', desc: '获取日志统计：总数、各级别分布、时间趋势' },
  { key: '3', name: 'list_log_levels', params: '无', desc: '列出存储中所有日志级别及对应数量' },
  { key: '4', name: 'get_trace_chain', params: 'trace_id', desc: '获取指定 Trace ID 的完整调用链路（按时间正序）' },
];

const mcpInstallCmd = `# 安装 MCP 服务依赖（服务端）
pip install ikc-log-center[mcp]

# 安装 MCP Python 客户端 SDK（用于编程调用）
pip install mcp`;

const stdioConfig = `{
  "mcpServers": {
    "log-center": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "log_center_server.mcp_server"],
      "env": {
        "LOG_CENTER_STORE": "local",
        "LOG_CENTER_DB_PATH": "/path/to/data/log_center/log_center.db"
      }
    }
  }
}`;

const stdioAuthConfig = `{
  "mcpServers": {
    "log-center": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "log_center_server.mcp_server"],
      "env": {
        "LOG_CENTER_STORE": "local",
        "LOG_CENTER_DB_PATH": "/path/to/data/log_center/log_center.db",
        "LOG_CENTER_AUTH_ENABLED": "true",
        "LOG_CENTER_MCP_TOKEN": "sk-lc-your-token-here"
      }
    }
  }
}`;

const httpConfig = `{
  "mcpServers": {
    "log-center": {
      "url": "http://your-server:9318/mcp",
      "headers": {
        "Authorization": "Bearer sk-lc-your-token-here"
      }
    }
  }
}`;

const startHttpCmd = `# 启动 MCP HTTP 服务（带 Token 鉴权）
LOG_CENTER_STORE=local \\
LOG_CENTER_DB_PATH=/path/to/log_center.db \\
LOG_CENTER_AUTH_ENABLED=true \\
log-center-mcp --transport http --host 0.0.0.0 --port 9318

# 或通过启动脚本一键启动（HTTP Server + MCP）
LOG_CENTER_AUTH_ENABLED=true ./start_log_center.sh --ui --mcp`;

const callExample = `# AI Agent 对话示例（自然语言 → MCP 工具调用）

用户: "帮我查一下最近有没有 ERROR 日志"
Agent → search_logs(level="ERROR", limit=20)

用户: "查看 trace_id 为 abc123 的完整调用链"
Agent → get_trace_chain(trace_id="abc123")

用户: "这个请求经过了哪些服务？帮我排查一下"
Agent → get_trace_chain(trace_id="trace-7511-199")

用户: "今天日志整体情况怎么样？"
Agent → get_log_stats(granularity="hour")

用户: "有哪些级别的日志？"
Agent → list_log_levels()`;

const pythonCallExample = `# Python MCP 客户端调用示例
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = StdioServerParameters(
        command="/path/to/.venv/bin/python",
        args=["-m", "log_center_server.mcp_server"],
        env={
            "LOG_CENTER_STORE": "local",
            "LOG_CENTER_DB_PATH": "/path/to/log_center.db",
        },
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 搜索 ERROR 日志
            result = await session.call_tool(
                "search_logs", {"level": "ERROR", "limit": 10}
            )
            data = json.loads(result.content[0].text)
            print(f"找到 {data['count']} 条 ERROR 日志")

            # 获取完整调用链路
            chain = await session.call_tool(
                "get_trace_chain", {"trace_id": "trace-7511-199"}
            )
            chain_data = json.loads(chain.content[0].text)
            print(f"链路共 {chain_data['count']} 条日志")

asyncio.run(main())`;

const McpSection: React.FC = () => (
  <div>
    <Alert
      type="info"
      showIcon
      message="MCP (Model Context Protocol) 让 AI Agent 能够直接检索和分析日志"
      description="通过 MCP 协议，Claude、Cursor、Qoder 等 AI 客户端可以调用 search_logs、get_trace_chain 等工具，实现自然语言日志查询与全链路追踪。"
      style={{ marginBottom: 20 }}
    />

    <Title level={5}>安装</Title>
    <CodeBlock title="pip install" code={mcpInstallCmd} />

    <Divider />
    <Title level={5}>stdio 模式（本地 AI 客户端）</Title>
    <Paragraph type="secondary">
      适用于 Claude Desktop、Cursor、Qoder 等本地 AI 客户端，将 MCP 服务作为子进程启动。
    </Paragraph>
    <CodeBlock title="mcp.json / claude_desktop_config.json" code={stdioConfig} />

    <Divider />
    <Title level={5}>stdio + Token 鉴权</Title>
    <Alert
      type="warning"
      showIcon
      message="启用鉴权后，stdio 模式需在 env 中配置 LOG_CENTER_MCP_TOKEN"
      style={{ marginBottom: 12 }}
    />
    <CodeBlock title="带鉴权的 stdio 配置" code={stdioAuthConfig} />

    <Divider />
    <Title level={5}>HTTP 模式（远程访问）</Title>
    <Paragraph type="secondary">
      MCP 服务以独立 HTTP 服务运行，AI 客户端通过网络连接。适合团队共享或远程部署。
    </Paragraph>
    <CodeBlock title="启动 HTTP 服务" code={startHttpCmd} />
    <CodeBlock title="AI 客户端配置（streamable-http）" code={httpConfig} />

    <Divider />
    <Title level={5}>MCP 工具列表</Title>
    <Paragraph type="secondary">
      MCP 服务对外暴露以下 4 个工具，AI Agent 可根据用户意图自动选择调用：
    </Paragraph>
    <Table columns={toolColumns} dataSource={toolData} pagination={false} size="middle" />

    <Divider />
    <Title level={5}>调用示例（自然语言 → 工具映射）</Title>
    <CodeBlock code={callExample} />

    <Divider />
    <Title level={5}>Python MCP 客户端</Title>
    <Paragraph type="secondary">
      使用官方 <Text code>mcp</Text> SDK 以编程方式连接 MCP 服务并调用工具：
    </Paragraph>
    <CodeBlock title="pip install mcp" code={pythonCallExample} />
  </div>
);

/* ============================ 页面 ============================ */

const HelpPage: React.FC = () => {
  const tabItems = [
    {
      key: 'server',
      label: <span><CloudServerOutlined /> 服务器</span>,
      children: <ServerSection />,
    },
    {
      key: 'client',
      label: <span><AppstoreAddOutlined /> 客户端集成</span>,
      children: <ClientSection />,
    },
    {
      key: 'mcp',
      label: <span><RobotOutlined /> AI Agent MCP 接入</span>,
      children: <McpSection />,
    },
  ];

  return (
    <div>
      <Space align="center" style={{ marginBottom: 16 }}>
        <QuestionCircleOutlined style={{ fontSize: 24, color: '#1677ff' }} />
        <Title level={4} style={{ margin: 0 }}>使用帮助</Title>
      </Space>
      <Descriptions
        size="small"
        column={3}
        style={{ marginBottom: 16 }}
        items={[
          { key: '1', label: '服务器', children: '部署、启动、环境变量与 API' },
          { key: '2', label: '客户端集成', children: 'SDK 安装、埋点与框架集成' },
          { key: '3', label: 'AI Agent MCP', children: '让 AI 直接检索分析日志' },
        ]}
      />
      <Card>
        <Tabs items={tabItems} />
      </Card>
    </div>
  );
};

export default HelpPage;
