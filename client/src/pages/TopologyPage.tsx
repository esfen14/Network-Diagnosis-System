import { useState, useCallback } from 'react'
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, type Node, type Edge } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

type SelectedItem =
  | { type: 'device'; id: string }
  | { type: 'link'; source: string; target: string }
  | null

const initialNodes: Node[] = [
  { id: 'core-sw', position: { x: 400, y: 50 }, data: { label: 'Core Switch' } },
  { id: 'router-1', position: { x: 200, y: 200 }, data: { label: 'Router 1' } },
  { id: 'router-2', position: { x: 600, y: 200 }, data: { label: 'Router 2' } },
  { id: 'sw-01', position: { x: 100, y: 350 }, data: { label: 'SW-01' } },
  { id: 'sw-02', position: { x: 300, y: 350 }, data: { label: 'SW-02' } },
  { id: 'sw-03', position: { x: 500, y: 350 }, data: { label: 'SW-03' } },
  { id: 'sw-04', position: { x: 700, y: 350 }, data: { label: 'SW-04' } },
  { id: 'pc-01', position: { x: 50, y: 500 }, data: { label: 'PC-001' } },
  { id: 'pc-02', position: { x: 150, y: 500 }, data: { label: 'PC-002' } },
  { id: 'pc-03', position: { x: 250, y: 500 }, data: { label: 'PC-003' } },
  { id: 'pc-04', position: { x: 350, y: 500 }, data: { label: 'PC-004' } },
  { id: 'pc-05', position: { x: 450, y: 500 }, data: { label: 'PC-005' } },
  { id: 'pc-06', position: { x: 550, y: 500 }, data: { label: 'PC-006' } },
  { id: 'pc-07', position: { x: 650, y: 500 }, data: { label: 'PC-007' } },
  { id: 'pc-08', position: { x: 750, y: 500 }, data: { label: 'PC-008' } },
]

const initialEdges: Edge[] = [
  { id: 'e1', source: 'core-sw', target: 'router-1', style: { stroke: '#10b981' } },
  { id: 'e2', source: 'core-sw', target: 'router-2', style: { stroke: '#10b981' } },
  { id: 'e3', source: 'router-1', target: 'sw-01', style: { stroke: '#f59e0b' } },
  { id: 'e4', source: 'router-1', target: 'sw-02', style: { stroke: '#10b981' } },
  { id: 'e5', source: 'router-2', target: 'sw-03', style: { stroke: '#10b981' } },
  { id: 'e6', source: 'router-2', target: 'sw-04', style: { stroke: '#ef4444' } },
  { id: 'e7', source: 'sw-01', target: 'pc-01', style: { stroke: '#10b981' } },
  { id: 'e8', source: 'sw-01', target: 'pc-02', style: { stroke: '#10b981' } },
  { id: 'e9', source: 'sw-02', target: 'pc-03', style: { stroke: '#f59e0b' } },
  { id: 'e10', source: 'sw-02', target: 'pc-04', style: { stroke: '#10b981' } },
  { id: 'e11', source: 'sw-03', target: 'pc-05', style: { stroke: '#10b981' } },
  { id: 'e12', source: 'sw-03', target: 'pc-06', style: { stroke: '#ef4444' } },
  { id: 'e13', source: 'sw-04', target: 'pc-07', style: { stroke: '#10b981' } },
  { id: 'e14', source: 'sw-04', target: 'pc-08', style: { stroke: '#10b981' } },
]

const deviceInfo: Record<string, { deviceId: string; hostName: string; vendor: string; osVersion: string; powerStatus: string; uptime: string; lastScanned: string }> = {
  'core-sw': { deviceId: 'D-001', hostName: 'Core-SW', vendor: 'Cisco', osVersion: 'IOS-XE 17.9', powerStatus: 'Online', uptime: '17:40:22', lastScanned: '2025-10-12 15:25:34' },
  'router-1': { deviceId: 'D-002', hostName: 'R1', vendor: 'Cisco', osVersion: 'IOS-XE 17.6', powerStatus: 'Online', uptime: '10:22:11', lastScanned: '2025-10-12 15:25:34' },
  'router-2': { deviceId: 'D-003', hostName: 'R2', vendor: 'Cisco', osVersion: 'IOS-XE 17.6', powerStatus: 'Online', uptime: '09:15:44', lastScanned: '2025-10-12 15:25:34' },
  'sw-01': { deviceId: 'D-004', hostName: 'SW-01', vendor: 'Cisco', osVersion: 'IOS 15.2', powerStatus: 'Online', uptime: '05:30:00', lastScanned: '2025-10-12 15:25:34' },
  'sw-02': { deviceId: 'D-005', hostName: 'SW-02', vendor: 'Cisco', osVersion: 'IOS 15.2', powerStatus: 'Offline', uptime: '00:00:00', lastScanned: '2025-10-12 15:25:34' },
}

export function TopologyPage() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const [selected, setSelected] = useState<SelectedItem>(null)

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelected({ type: 'device', id: node.id })
  }, [])

  const onEdgeClick = useCallback((_: unknown, edge: Edge) => {
    setSelected({ type: 'link', source: edge.source, target: edge.target })
  }, [])

  const onPaneClick = useCallback(() => {
    setSelected(null)
  }, [])

  const device = selected?.type === 'device' ? deviceInfo[selected.id] : null

  return (
    <main className="ml-[220px] flex-1">
      <div className="rounded-3xl bg-[#1a1f26] p-8 shadow-lg">
        <h1 className="text-2xl font-semibold text-white">Topology</h1>
        <p className="mt-2 text-gray-400">Visual representation of the network's structure and architecture.</p>

        <div className="mt-6 flex gap-4">
          {/* Network Map */}
          <div className="flex-1 rounded-2xl overflow-hidden bg-[#0d1117]" style={{ height: '600px' }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              onPaneClick={onPaneClick}
              fitView
            >
              <Background color="#333" />
              <Controls />
            </ReactFlow>
          </div>

          {/* Side Panel */}
          {selected && (
            <div className="w-72 shrink-0 space-y-4">
              {selected.type === 'device' && device && (
                <>
                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <h2 className="text-white font-semibold text-sm">Device Information</h2>
                    <div className="space-y-1 text-sm">
                      <p className="text-gray-400">Device ID: <span className="text-white">{device.deviceId}</span></p>
                      <p className="text-gray-400">Host Name: <span className="text-white">{device.hostName}</span></p>
                      <p className="text-gray-400">Vendor: <span className="text-white">{device.vendor}</span></p>
                      <p className="text-gray-400">OS Version: <span className="text-white">{device.osVersion}</span></p>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <p className="text-white text-sm font-medium">Device Utilization</p>
                      <p className="text-gray-400 text-xs">Last 5</p>
                    </div>
                    <div className="h-24 flex items-center justify-center">
                      <p className="text-gray-500 text-xs">Chart goes here</p>
                    </div>
                    <div className="space-y-1 text-xs">
                      <p className="text-gray-400">● Temperature</p>
                      <p className="text-gray-400">● CPU Utilization</p>
                      <p className="text-gray-400">● Memory Utilization</p>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2 text-sm">
                    <p className="text-gray-400">Power Status: <span className={device.powerStatus === 'Online' ? 'text-green-400' : 'text-red-400'}>{device.powerStatus}</span></p>
                    <p className="text-gray-400">Uptime (HH:mm:ss): <span className="text-white">{device.uptime}</span></p>
                    <p className="text-gray-400">Last Scanned: <span className="text-white">{device.lastScanned}</span></p>
                  </div>
                </>
              )}

              {selected.type === 'link' && (
                <>
                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <h2 className="text-white font-semibold text-sm">Link Summary</h2>
                    <div className="space-y-1 text-sm">
                      <p className="text-gray-400">From: <span className="text-white">{selected.source}</span></p>
                      <p className="text-gray-400">To: <span className="text-white">{selected.target}</span></p>
                      <p className="text-gray-400">Last Scanned: <span className="text-white">2025-10-12 15:25:34</span></p>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <p className="text-white text-sm font-medium">Utilization</p>
                      <p className="text-gray-400 text-xs">Last 5 Hours</p>
                    </div>
                    <div className="h-24 flex items-center justify-center">
                      <p className="text-gray-500 text-xs">Chart goes here</p>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <p className="text-white text-sm font-medium">Ingress/Egress Traffic</p>
                      <p className="text-gray-400 text-xs">Last 5 Hours</p>
                    </div>
                    <div className="h-24 flex items-center justify-center">
                      <p className="text-gray-500 text-xs">Chart goes here</p>
                    </div>
                    <div className="space-y-1 text-xs">
                      <p className="text-gray-400">● Ingress Traffic</p>
                      <p className="text-gray-400">● Egress Traffic</p>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  )
}

export default TopologyPage