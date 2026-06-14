export function TopologyPage() {
  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
        <h1 className="text-lg font-semibold text-white">Topology</h1>
        <p className="text-sm text-gray-400">Visual representation of the network's structure and architecture.</p>
      </div>

      {/* Main content */}
      <div className="flex gap-6">

        {/* Network Map */}
        <div className="flex-1 rounded-3xl bg-[#1a1f26] p-6 shadow-lg" style={{ height: '600px' }}>
          <p className="text-white">Network map will go here</p>
        </div>

        {/* Side Panel - Device Information */}
        <div className="w-72 rounded-3xl bg-[#1a1f26] p-6 shadow-lg space-y-4">
          <h2 className="text-white font-semibold">Device Information</h2>
          <div className="space-y-2 text-sm">
            <p className="text-gray-400">Device ID: <span className="text-white">D-001</span></p>
            <p className="text-gray-400">Host Name: <span className="text-white">R1</span></p>
            <p className="text-gray-400">Vendor: <span className="text-white">Cisco</span></p>
            <p className="text-gray-400">OS Version: <span className="text-white">IOS-XE 17.9</span></p>
          </div>

          <div className="rounded-xl bg-[#0f1318] p-4 space-y-2">
            <div className="flex justify-between">
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

          <div className="space-y-2 text-sm">
            <p className="text-gray-400">Power Status: <span className="text-green-400">Online</span></p>
            <p className="text-gray-400">Uptime (HH:mm:ss): <span className="text-white">17:40:22</span></p>
            <p className="text-gray-400">Last Scanned: <span className="text-white">2025-10-12 15:25:34</span></p>
          </div>
        </div>

      </div>
    </div>
  )
}

export default TopologyPage