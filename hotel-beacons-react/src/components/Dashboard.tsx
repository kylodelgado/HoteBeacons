import React from 'react';
import { 
  Radio, 
  Battery, 
  Signal, 
  AlertTriangle,
  Activity,
  Clock,
  MapPin
} from 'lucide-react';
import { Beacon, ActivityLog, ConnectionStatus, BeaconStatistics } from '../types';
import { 
  formatTimestamp, 
  formatBattery, 
  formatRSSI, 
  formatDistance,
  formatTimeAgo,
  getBatteryStatusColor,
  getRSSIStatusColor,
  getEventTypeColor
} from '../utils';

interface DashboardProps {
  beacons: Beacon[];
  statistics: BeaconStatistics;
  connectionStatus: ConnectionStatus;
  recentLogs: ActivityLog[];
  onRefresh: () => void;
  isLoading: boolean;
}

const Dashboard: React.FC<DashboardProps> = ({
  beacons,
  statistics,
  connectionStatus,
  recentLogs,
  onRefresh: _onRefresh,
  isLoading: _isLoading,
}) => {
  const activeBeacons = beacons.filter(beacon => beacon.isActive);

  const StatCard: React.FC<{
    title: string;
    value: number;
    icon: React.ComponentType<any>;
    color: string;
    description?: string;
  }> = ({ title, value, icon: Icon, color, description }) => (
    <div className="card p-6">
      <div className="flex items-center">
        <div className={`${color} p-3 rounded-lg`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div className="ml-4">
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {description && (
            <p className="text-xs text-gray-500 mt-1">{description}</p>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Beacons"
          value={statistics.totalBeacons}
          icon={Radio}
          color="bg-blue-500"
          description="Registered in system"
        />
        <StatCard
          title="Active Beacons"
          value={statistics.activeBeacons}
          icon={Activity}
          color="bg-green-500"
          description="Seen in last 5 minutes"
        />
        <StatCard
          title="Low Battery"
          value={statistics.lowBatteryBeacons}
          icon={Battery}
          color="bg-yellow-500"
          description="Below 30% charge"
        />
        <StatCard
          title="Offline"
          value={statistics.offlineBeacons}
          icon={AlertTriangle}
          color="bg-red-500"
          description="Not responding"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Beacons */}
        <div className="card">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Active Beacons</h3>
            <p className="text-sm text-gray-500">
              Beacons seen in the last 5 minutes
            </p>
          </div>
          <div className="p-6">
            {activeBeacons.length === 0 ? (
              <div className="text-center py-8">
                <Radio className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">No active beacons</p>
              </div>
            ) : (
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {activeBeacons.map((beacon) => (
                  <div
                    key={beacon.id}
                    className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0">
                        <div className="w-3 h-3 bg-green-400 rounded-full"></div>
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <MapPin className="h-4 w-4 text-gray-400" />
                          <span className="font-medium text-gray-900">
                            Room {beacon.roomNumber}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 font-mono">
                          {beacon.macAddress}
                        </p>
                        {beacon.description && (
                          <p className="text-xs text-gray-600">
                            {beacon.description}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="text-right space-y-1">
                      <div className="flex items-center space-x-2 text-sm">
                        <Signal className="h-4 w-4 text-gray-400" />
                        <span className={getRSSIStatusColor(beacon.rssi)}>
                          {formatRSSI(beacon.rssi)}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2 text-sm">
                        <Battery className="h-4 w-4 text-gray-400" />
                        <span className={getBatteryStatusColor(beacon.batteryLevel)}>
                          {formatBattery(beacon.batteryLevel, beacon.isCharging)}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-gray-500">
                        <Clock className="h-3 w-3" />
                        <span>
                          {beacon.lastSeen ? formatTimeAgo(beacon.lastSeen) : 'Unknown'}
                        </span>
                      </div>
                      {beacon.estimatedDistance && (
                        <div className="text-xs text-gray-500">
                          Distance: {formatDistance(beacon.estimatedDistance)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="card">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Recent Activity</h3>
            <p className="text-sm text-gray-500">
              Latest system events and beacon updates
            </p>
          </div>
          <div className="p-6">
            {recentLogs.length === 0 ? (
              <div className="text-center py-8">
                <Activity className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">No recent activity</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {recentLogs.map((log) => (
                  <div key={log.id} className="flex items-start space-x-3">
                    <div className="flex-shrink-0 mt-1">
                      <span className={`
                        inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                        ${getEventTypeColor(log.eventType)}
                      `}>
                        {log.eventType}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900">
                        {log.details}
                      </p>
                      <div className="flex items-center space-x-2 mt-1">
                        <span className="text-xs text-gray-500">
                          {formatTimestamp(log.timestamp)}
                        </span>
                        {log.roomNumber && (
                          <>
                            <span className="text-xs text-gray-400">•</span>
                            <span className="text-xs text-gray-500">
                              Room {log.roomNumber}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Connection Status */}
      <div className="card p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-medium text-gray-900">System Status</h3>
            <p className="text-sm text-gray-500">
              AWS IoT connection and system health
            </p>
          </div>
          <div className="text-right">
            <div className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${
                connectionStatus.isConnected ? 'bg-green-400' : 'bg-red-400'
              }`}></div>
              <span className={`font-medium ${
                connectionStatus.isConnected ? 'text-green-600' : 'text-red-600'
              }`}>
                {connectionStatus.status}
              </span>
            </div>
            {connectionStatus.lastConnected && (
              <p className="text-xs text-gray-500 mt-1">
                Last connected: {formatTimeAgo(connectionStatus.lastConnected)}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;