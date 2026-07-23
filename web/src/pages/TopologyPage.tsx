import React, { useRef, useEffect, useCallback } from 'react';
import { Card, Spin, Empty, Tag, Space, Typography, Row, Col, Statistic, Button, Tooltip } from 'antd';
import {
  ClusterOutlined, ReloadOutlined, ZoomInOutlined, ZoomOutOutlined,
  ExpandOutlined, RedoOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import { getNodes } from '../api';
import type { NodeInfo } from '../types';

const { Title, Text } = Typography;

interface GNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: 'center' | 'ip' | 'app';
  radius: number;
  color: string;
  stroke: string;
  logCount: number;
  errorCount: number;
  ip?: string;
  appName?: string;
  lastActive?: string | null;
}

interface GLink extends d3.SimulationLinkDatum<GNode> {
  source: string | GNode;
  target: string | GNode;
  color: string;
  width: number;
  dash?: string;
}

const TopologyPage: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<d3.Simulation<GNode, GLink> | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const selectedRef = useRef<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['nodes'],
    queryFn: getNodes,
    refetchInterval: 60000,
  });

  const nodes: NodeInfo[] = data?.nodes || [];

  const buildGraph = useCallback(() => {
    const gNodes: GNode[] = [];
    const gLinks: GLink[] = [];
    if (nodes.length === 0) return { gNodes, gLinks };

    const maxIpLog = Math.max(...nodes.map((n) => n.log_count), 1);

    // Center
    gNodes.push({
      id: 'log-center', label: 'Log Center', type: 'center',
      radius: 30, color: '#1677ff', stroke: '#0958d9',
      logCount: nodes.reduce((s, n) => s + n.log_count, 0),
      errorCount: nodes.reduce((s, n) => s + n.error_count, 0),
    });

    nodes.forEach((ipNode) => {
      const ipId = `ip-${ipNode.ip}`;
      const ratio = ipNode.log_count / maxIpLog;
      const hasErr = ipNode.error_count > 0;
      gNodes.push({
        id: ipId, label: ipNode.ip === 'unknown' ? '未知主机' : ipNode.ip,
        type: 'ip', radius: 20 + Math.round(ratio * 8),
        color: hasErr ? '#fff2e8' : '#f6ffed',
        stroke: hasErr ? '#fa8c16' : '#52c41a',
        logCount: ipNode.log_count, errorCount: ipNode.error_count, ip: ipNode.ip,
      });
      gLinks.push({
        source: ipId, target: 'log-center',
        color: hasErr ? '#ffd591' : '#b7eb8f', width: 2 + Math.round(ratio * 3),
      });

      const maxApp = Math.max(...ipNode.apps.map((a) => a.log_count), 1);
      ipNode.apps.forEach((app) => {
        const appId = `${ipId}::${app.name}`;
        const appRatio = app.log_count / maxApp;
        const appErr = app.error_count > 0;
        gNodes.push({
          id: appId, label: app.name, type: 'app',
          radius: 12 + Math.round(appRatio * 7),
          color: appErr ? '#ff4d4f' : '#1890ff',
          stroke: appErr ? '#cf1322' : '#096dd9',
          logCount: app.log_count, errorCount: app.error_count,
          ip: ipNode.ip, appName: app.name, lastActive: app.last_active,
        });
        gLinks.push({
          source: appId, target: ipId,
          color: appErr ? '#ffccc7' : '#91d5ff', width: 1 + Math.round(appRatio * 2),
          dash: '4,2',
        });
      });
    });
    return { gNodes, gLinks };
  }, [nodes]);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth || 800;
    const height = 520;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('width', width).attr('height', height).attr('viewBox', `0 0 ${width} ${height}`);

    const layer = svg.append('g');
    const { gNodes, gLinks } = buildGraph();

    // Neighbor map
    const neighbors = new Map<string, Set<string>>();
    gNodes.forEach((n) => neighbors.set(n.id, new Set()));
    gLinks.forEach((l) => {
      const sid = typeof l.source === 'string' ? l.source : l.source.id;
      const tid = typeof l.target === 'string' ? l.target : l.target.id;
      neighbors.get(sid)?.add(tid);
      neighbors.get(tid)?.add(sid);
    });
    const nodeById = new Map(gNodes.map((n) => [n.id, n]));

    // Simulation
    const simulation = d3.forceSimulation<GNode>(gNodes)
      .force('link', d3.forceLink<GNode, GLink>(gLinks).id((d) => d.id)
        .distance((l) => {
          const t = l.target as GNode;
          if (t.type === 'app') return 60;
          if (t.type === 'ip') return 120;
          return 140;
        }).strength(0.75))
      .force('charge', d3.forceManyBody().strength(-280))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<GNode>().radius((d) => d.radius + 10).iterations(2));
    simRef.current = simulation;

    // Links
    const link = layer.append('g').selectAll('line').data(gLinks).join('line')
      .attr('stroke', (d) => d.color).attr('stroke-width', (d) => d.width)
      .attr('stroke-dasharray', (d) => d.dash || null).attr('stroke-opacity', 0.85);

    // Nodes
    const node = layer.append('g').selectAll('circle').data(gNodes).join('circle')
      .attr('r', (d) => d.radius).attr('fill', (d) => d.color)
      .attr('stroke', (d) => d.stroke).attr('stroke-width', 2.5)
      .style('cursor', 'pointer');

    // Labels
    const label = layer.append('g').selectAll('text').data(gNodes).join('text')
      .attr('dy', (d) => d.radius + 13).attr('text-anchor', 'middle')
      .attr('font-size', (d) => d.type === 'center' ? 12 : d.type === 'ip' ? 11 : 9)
      .attr('fill', '#333').attr('pointer-events', 'none')
      .text((d) => d.label.length > 16 ? d.label.slice(0, 14) + '…' : d.label);

    // Tooltip
    const tooltip = d3.select(container).selectAll('.topo-tip').data([0]).join('div')
      .attr('class', 'topo-tip')
      .style('position', 'absolute').style('display', 'none')
      .style('background', 'rgba(0,0,0,0.82)').style('color', '#fff')
      .style('padding', '8px 12px').style('border-radius', '6px')
      .style('font-size', '12px').style('pointer-events', 'none')
      .style('z-index', '10').style('max-width', '260px').style('line-height', '1.6');

    node.on('mouseenter', (event, d) => {
      const lines = [`<b>${d.label}</b>`];
      if (d.type === 'ip') lines.push(`日志: ${d.logCount} 条 | 错误: ${d.errorCount}`);
      if (d.type === 'app') {
        lines.push(`日志: ${d.logCount} 条 | 错误: ${d.errorCount}`);
        if (d.lastActive) lines.push(`最近: ${d.lastActive.replace('T', ' ').slice(0, 19)}`);
      }
      if (d.type === 'center') lines.push(`总日志: ${d.logCount} | 总错误: ${d.errorCount}`);
      tooltip.html(lines.join('<br/>')).style('display', 'block');
    }).on('mousemove', (event) => {
      const rect = container.getBoundingClientRect();
      tooltip.style('left', `${event.clientX - rect.left + 12}px`)
        .style('top', `${event.clientY - rect.top - 10}px`);
    }).on('mouseleave', () => tooltip.style('display', 'none'));

    // Selection highlight
    function updateSelection() {
      const sel = selectedRef.current;
      if (!sel) {
        node.style('opacity', 1).attr('stroke-width', 2.5);
        link.style('opacity', 0.85).attr('stroke', (d) => d.color).attr('stroke-width', (d) => d.width);
        label.style('opacity', 1).style('font-weight', '400');
        return;
      }
      const near = neighbors.get(sel) || new Set();
      node.style('opacity', (d) => d.id === sel || near.has(d.id) ? 1 : 0.15)
        .attr('stroke-width', (d) => d.id === sel ? 4 : 2.5);
      link.style('opacity', (d) => {
        const sid = (d.source as GNode).id; const tid = (d.target as GNode).id;
        if (sid === sel || tid === sel) return 1;
        return 0.05;
      }).attr('stroke', (d) => {
        const sid = (d.source as GNode).id; const tid = (d.target as GNode).id;
        return sid === sel || tid === sel ? '#f59e0b' : d.color;
      }).attr('stroke-width', (d) => {
        const sid = (d.source as GNode).id; const tid = (d.target as GNode).id;
        return sid === sel || tid === sel ? d.width + 1.5 : d.width;
      });
      label.style('opacity', (d) => d.id === sel || near.has(d.id) ? 1 : 0.2)
        .style('font-weight', (d) => d.id === sel ? '700' : '400');
    }

    // Click
    node.on('click', (event, d) => {
      event.stopPropagation();
      selectedRef.current = selectedRef.current === d.id ? null : d.id;
      updateSelection();
    });
    svg.on('click', () => { selectedRef.current = null; updateSelection(); });

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 4.5])
      .on('zoom', (event) => layer.attr('transform', event.transform));
    svg.call(zoom);
    zoomRef.current = zoom;

    // Fit to view
    function fitView(animate: boolean) {
      const gNode = layer.node();
      if (!gNode) return;
      const box = gNode.getBBox();
      if (!box || box.width <= 0 || box.height <= 0) return;
      const scale = Math.max(0.3, Math.min(2.5, 0.88 / Math.max(box.width / width, box.height / height)));
      const tx = width / 2 - (box.x + box.width / 2) * scale;
      const ty = height / 2 - (box.y + box.height / 2) * scale;
      const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
      const target = animate ? svg.transition().duration(300) : svg;
      (target as any).call(zoom.transform, transform);
    }

    // Drag with neighbor following
    const drag = d3.drag<SVGCircleElement, GNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.35).restart();
        d.fx = d.x; d.fy = d.y;
        event.sourceEvent?.stopPropagation?.();
      })
      .on('drag', (event, d) => {
        const dx = event.x - (d.x || event.x);
        const dy = event.y - (d.y || event.y);
        d.fx = event.x; d.fy = event.y;
        const near = neighbors.get(d.id) || new Set();
        near.forEach((nid) => {
          const nb = nodeById.get(nid);
          if (nb && nb !== d) { nb.x = (nb.x || 0) + dx * 0.3; nb.y = (nb.y || 0) + dy * 0.3; }
        });
        simulation.alpha(0.22).restart();
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
        setTimeout(() => fitView(true), 200);
      });
    node.call(drag);

    // Tick
    simulation.on('tick', () => {
      link.attr('x1', (d) => (d.source as GNode).x!).attr('y1', (d) => (d.source as GNode).y!)
        .attr('x2', (d) => (d.target as GNode).x!).attr('y2', (d) => (d.target as GNode).y!);
      node.attr('cx', (d) => d.x!).attr('cy', (d) => d.y!);
      label.attr('x', (d) => d.x!).attr('y', (d) => d.y!);
    });

    // Initial fit after stabilization
    simulation.on('end', () => fitView(true));
    setTimeout(() => fitView(true), 800);

    // Expose controls
    (container as any).__zoomIn = () => svg.transition().duration(200).call(zoom.scaleBy, 1.25);
    (container as any).__zoomOut = () => svg.transition().duration(200).call(zoom.scaleBy, 0.8);
    (container as any).__fitView = () => fitView(true);
    (container as any).__reset = () => {
      selectedRef.current = null; updateSelection();
      simulation.alpha(0.5).restart();
      setTimeout(() => fitView(true), 300);
    };

    return () => { simulation.stop(); };
  }, [nodes, buildGraph]);

  const handleControl = (action: string) => {
    const el = containerRef.current as any;
    if (!el) return;
    if (action === 'in') el.__zoomIn?.();
    if (action === 'out') el.__zoomOut?.();
    if (action === 'fit') el.__fitView?.();
    if (action === 'reset') el.__reset?.();
  };

  const totalLogs = nodes.reduce((s, n) => s + n.log_count, 0);
  const totalErrors = nodes.reduce((s, n) => s + n.error_count, 0);
  const totalApps = nodes.reduce((s, n) => s + n.apps.length, 0);

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" tip="加载节点..." /></div>;
  }

  return (
    <div>
      <Space align="center" style={{ marginBottom: 16 }}>
        <ClusterOutlined style={{ fontSize: 24, color: '#1677ff' }} />
        <Title level={4} style={{ margin: 0 }}>服务拓扑</Title>
        <Tooltip title="刷新数据"><ReloadOutlined onClick={() => refetch()} style={{ cursor: 'pointer', fontSize: 16 }} /></Tooltip>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}><Card size="small"><Statistic title="接入主机" value={nodes.length} suffix="台" /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="接入应用" value={totalApps} suffix="个" /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="总日志量" value={totalLogs} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="错误日志" value={totalErrors} valueStyle={{ color: totalErrors > 0 ? '#ff4d4f' : undefined }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="错误率" value={totalLogs > 0 ? ((totalErrors / totalLogs) * 100).toFixed(1) : '0'} suffix="%" valueStyle={{ color: totalErrors > 0 ? '#ff4d4f' : '#52c41a' }} /></Card></Col>
      </Row>

      {nodes.length === 0 ? (
        <Empty description="暂无接入节点，等待服务上报日志..." />
      ) : (
        <Card
          title="节点拓扑图"
          extra={
            <Space>
              <Tag color="blue">应用</Tag><Tag color="green">主机正常</Tag>
              <Tag color="orange">主机有错误</Tag><Tag color="red">应用有错误</Tag>
              <span style={{ borderLeft: '1px solid #d9d9d9', paddingLeft: 8 }}>
                <Button size="small" icon={<ZoomInOutlined />} onClick={() => handleControl('in')} />
                <Button size="small" icon={<ZoomOutOutlined />} onClick={() => handleControl('out')} />
                <Button size="small" icon={<ExpandOutlined />} onClick={() => handleControl('fit')} title="适应画布" />
                <Button size="small" icon={<RedoOutlined />} onClick={() => handleControl('reset')} title="重置布局" />
              </span>
            </Space>
          }
          styles={{ body: { padding: 0, position: 'relative', height: 520, overflow: 'hidden' } }}
        >
          <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
            <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
          </div>
        </Card>
      )}

      {nodes.length > 0 && (
        <Card title="节点详情" size="small" style={{ marginTop: 16 }}>
          <Row gutter={[16, 16]}>
            {nodes.map((ipNode) => (
              <Col key={ipNode.ip} xs={24} sm={12} lg={8} xl={6}>
                <Card size="small"
                  title={<Space><Text strong>{ipNode.ip === 'unknown' ? '未知主机' : ipNode.ip}</Text><Tag color={ipNode.error_count > 0 ? 'orange' : 'green'}>{ipNode.log_count} 条</Tag></Space>}
                  style={{ borderLeft: `3px solid ${ipNode.error_count > 0 ? '#fa8c16' : '#52c41a'}` }}
                >
                  {ipNode.apps.map((app) => (
                    <div key={app.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', borderBottom: '1px solid #f5f5f5' }}>
                      <Text ellipsis style={{ maxWidth: '55%', fontSize: 12 }}>{app.name}</Text>
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 11 }}>{app.log_count}条</Text>
                        {app.error_count > 0 && <Tag color="red" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{app.error_count} err</Tag>}
                      </Space>
                    </div>
                  ))}
                </Card>
              </Col>
            ))}
          </Row>
        </Card>
      )}
    </div>
  );
};

export default TopologyPage;
