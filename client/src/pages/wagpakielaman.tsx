import { useState, useCallback } from 'react'
import { ReactFlow, Background, Controls, Handle, Position, useNodesState, useEdgesState, type Node, type Edge, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Server, Router, Monitor } from 'lucide-react'

function CustomNode({ data }: NodeProps) {
  const Icon = data.icon as typeof Server
  return (
    <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-[#1a1f26] px-3 py-2 text-white text-xs">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <Icon className="h-4 w-4 shrink-0" />
      <span>{data.label as string}</span>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  )
}

const nodeTypes = { custom: CustomNode }

type SelectedItem =
  | { type: 'device'; id: string }
  | { type: 'link'; source: string; target: string }
  | null

const initialNodes: Node[] = [
  { id: 'core-sw', type: 'custom', position: { x: 400, y: 50 }, data: { label: 'Core Switch', icon: Server } },
  { id: 'router-1', type: 'custom', position: { x: 200, y: 200 }, data: { label: 'Router 1', icon: Router } },
  { id: 'router-2', type: 'custom', position: { x: 600, y: 200 }, data: { label: 'Router 2', icon: Router } },
  { id: 'sw-01', type: 'custom', position: { x: 100, y: 350 }, data: { label: 'SW-01', icon: Server } },
  { id: 'sw-02', type: 'custom', position: { x: 300, y: 350 }, data: { label: 'SW-02', icon: Server } },
  { id: 'sw-03', type: 'custom', position: { x: 500, y: 350 }, data: { label: 'SW-03', icon: Server } },
  { id: 'sw-04', type: 'custom', position: { x: 700, y: 350 }, data: { label: 'SW-04', icon: Server } },
  { id: 'pc-01', type: 'custom', position: { x: 50, y: 500 }, data: { label: 'PC-001', icon: Monitor } },
  { id: 'pc-02', type: 'custom', position: { x: 150, y: 500 }, data: { label: 'PC-002', icon: Monitor } },
  { id: 'pc-03', type: 'custom', position: { x: 250, y: 500 }, data: { label: 'PC-003', icon: Monitor } },
  { id: 'pc-04', type: 'custom', position: { x: 350, y: 500 }, data: { label: 'PC-004', icon: Monitor } },
  { id: 'pc-05', type: 'custom', position: { x: 450, y: 500 }, data: { label: 'PC-005', icon: Monitor } },
  { id: 'pc-06', type: 'custom', position: { x: 550, y: 500 }, data: { label: 'PC-006', icon: Monitor } },
  { id: 'pc-07', type: 'custom', position: { x: 650, y: 500 }, data: { label: 'PC-007', icon: Monitor } },
  { id: 'pc-08', type: 'custom', position: { x: 750, y: 500 }, data: { label: 'PC-008', icon: Monitor } },
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

const interfaceInfo: Record<string, { interfaceId: string; hostName: string; ipAddress: string; subnetMask: string; macAddress: string; duplexMode: string; speed: string; status: string; connectedTo: string }> = {
  'core-sw': { interfaceId: 'INT-001', hostName: 'Core-SW', ipAddress: '192.168.200.1', subnetMask: '255.255.255.0', macAddress: '00:1A:2B:4C:6D:7E', duplexMode: 'Full-Duplex', speed: '1 Gbps', status: 'Up', connectedTo: 'INT-002' },
  'router-1': { interfaceId: 'INT-002', hostName: 'R1', ipAddress: '192.168.200.2', subnetMask: '255.255.255.0', macAddress: '00:1A:2B:4C:6D:7F', duplexMode: 'Full-Duplex', speed: '1 Gbps', status: 'Up', connectedTo: 'INT-001' },
  'router-2': { interfaceId: 'INT-003', hostName: 'R2', ipAddress: '192.168.200.3', subnetMask: '255.255.255.0', macAddress: '00:1A:2B:4C:6D:80', duplexMode: 'Full-Duplex', speed: '1 Gbps', status: 'Up', connectedTo: 'INT-001' },
  'sw-01': { interfaceId: 'INT-004', hostName: 'SW-01', ipAddress: '192.168.201.1', subnetMask: '255.255.255.0', macAddress: '00:1A:2B:4C:6D:81', duplexMode: 'Half-Duplex', speed: '100 Mbps', status: 'Up', connectedTo: 'INT-002' },
  'sw-02': { interfaceId: 'INT-005', hostName: 'SW-02', ipAddress: '192.168.201.2', subnetMask: '255.255.255.0', macAddress: '00:1A:2B:4C:6D:82', duplexMode: 'Half-Duplex', speed: '100 Mbps', status: 'Down', connectedTo: 'INT-002' },
}

export function TopologyPage() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const [selected, setSelected] = useState<SelectedItem>(null)
  const [showInterface, setShowInterface] = useState(false)

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelected({ type: 'device', id: node.id })
    setShowInterface(false)
  }, [])

  const onEdgeClick = useCallback((_: unknown, edge: Edge) => {
    setSelected({ type: 'link', source: edge.source, target: edge.target })
    setShowInterface(false)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelected(null)
    setShowInterface(false)
  }, [])

  const device = selected?.type === 'device' ? deviceInfo[selected.id] : null
  const iface = selected?.type === 'device' ? interfaceInfo[selected.id] : null

  return (
    <main className="ml-[220px] flex-1">
      <div className="rounded-3xl bg-[#1a1f26] p-8 shadow-lg">
        <h1 className="text-2xl font-semibold text-white">Service Status</h1>
        <p className="mt-2 text-gray-400">Visual representation of the network's structure and architecture.</p>

        <div className="mt-6 flex gap-4">
          {/* Network Map */}
          <div className="rounded-2xl overflow-hidden bg-[#0d1117]" style={{ height: '600px', width: '0', flexGrow: 1 }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
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
              {selected.type === 'device' && device && !showInterface && (
                <>
                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <h2 className="text-white font-semibold text-sm">Device Information</h2>
                      <button
                        onClick={() => setShowInterface(true)}
                        className="text-xs text-blue-400 hover:text-blue-300 underline"
                      >
                        View Interface
                      </button>
                    </div>
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

              {selected.type === 'device' && iface && showInterface && (
                <>
                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <h2 className="text-white font-semibold text-sm">Interface Information</h2>
                      <button
                        onClick={() => setShowInterface(false)}
                        className="text-xs text-blue-400 hover:text-blue-300 underline"
                      >
                        ← Back
                      </button>
                    </div>
                    <div className="space-y-1 text-sm">
                      <p className="text-gray-400">Interface ID: <span className="text-white">{iface.interfaceId}</span></p>
                      <p className="text-gray-400">Host Name: <span className="text-white">{iface.hostName}</span></p>
                      <p className="text-gray-400">IP Address: <span className="text-white">{iface.ipAddress}</span></p>
                      <p className="text-gray-400">Subnet Mask: <span className="text-white">{iface.subnetMask}</span></p>
                      <p className="text-gray-400">Mac Address: <span className="text-white">{iface.macAddress}</span></p>
                      <p className="text-gray-400">Duplex Mode: <span className="text-white">{iface.duplexMode}</span></p>
                      <p className="text-gray-400">Speed: <span className="text-white">{iface.speed}</span></p>
                      <p className="text-gray-400">Status: <span className={iface.status === 'Up' ? 'text-green-400' : 'text-red-400'}>{iface.status}</span></p>
                      <p className="text-gray-400">Connected to: <span className="text-white">{iface.connectedTo}</span></p>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-[#0d1117] p-4 space-y-2">
                    <h2 className="text-white font-semibold text-sm">Interface Health</h2>
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