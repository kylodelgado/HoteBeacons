import React from 'react';
import { 
  Radio, 
  Battery, 
  Signal, 
  AlertTriangle,
  Activity,
  Clock,
  MapPin,
  Wifi,
  WifiOff
} from 'lucide-react';
import { Beacon, ActivityLog, ConnectionStatus, BeaconStatistics } from '../types';
import { 
  formatTimestamp, 
  formatBattery, 
  formatRSSI, 
  formatDistance,
  formatTimeAgo,
  getBatteryStatusColor,
  getRSSIStatusColor
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
    colorClass: string;
    description?: string;
  }> = ({ title, value, icon: Icon, colorClass, description }) => (
    <div className={`stat-card ${colorClass} group hover:scale-105 transition-transform duration-200`}>
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-600 mb-1">{title}</p>
          <p className="text-3xl font-bold text-gray-900 mb-1">{value}</p>
          {description && (
            <p className="text-xs text-gray-500">{description}</p>
          )}
        </div>
        <div className="ml-4">
          <div className="bg-gradient-to-br from-white to-gray-50 p-4 rounded-2xl shadow-lg group-hover:shadow-xl transition-shadow duration-200">
            <Icon className="h-8 w-8 text-gray-700" />
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-8">
      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        <StatCard
          title="Total Beacons"
          value={statistics.totalBeacons}
          icon={Radio}
          colorClass="stat-card-blue"
          description="Registered in system"
        />
        <StatCard
          title="Active Beacons"
          value={statistics.activeBeacons}
          icon={Activity}
          colorClass="stat-card-green"
          description="Seen in last 5 minutes"
        />
        <StatCard
          title="Low Battery"
          value={statistics.lowBatteryBeacons}
          icon={Battery}
          colorClass="stat-card-amber"
          description="Below 30% charge"
        />
        <StatCard
          title="Offline"
          value={statistics.offlineBeacons}
          icon={AlertTriangle}
          colorClass="stat-card-red"
          description="Not responding"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Active Beacons */}
        <div className="card-premium">
          <div className="p-8 border-b border-gray-100">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-r from-emerald-500 to-green-600 p-2 rounded-xl">
                <Radio className="h-6 w-6 text-white" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Active Beacons</h3>
                <p className="text-sm text-gray-600">
                  Beacons seen in the last 5 minutes
                </p>
              </div>
            </div>
          </div>
          <div className="p-8">
            {activeBeacons.length === 0 ? (
              <div className="text-center py-12">
                <div className="bg-gray-100 p-4 rounded-2xl w-fit mx-auto mb-4">
                  <Radio className="h-12 w-12 text-gray-400" />
                </div>
                <p className="text-gray-500 font-medium">No active beacons</p>
              </div>
            ) : (
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {activeBeacons.map((beacon) => (
                  <div
                    key={beacon.id}
                    className={`beacon-card ${beacon.isActive ? 'beacon-card-active' : 'beacon-card-inactive'}`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        <div className="flex-shrink-0">
                          <div className={`status-dot ${beacon.isActive ? 'status-dot-active' : 'status-dot-inactive'}`}></div>
                        </div>
                        <div>
                          <div className="flex items-center space-x-2 mb-1">
                            <MapPin className="h-4 w-4 text-gray-500" />
                            <span className="font-semibold text-gray-900">
                              Room {beacon.roomNumber}
                            </span>
                          </div>
                          <p className="text-xs text-gray-500 font-mono mb-1">
                            {beacon.macAddress}
                          </p>
                          {beacon.description && (
                            <p className="text-xs text-gray-600">
                              {beacon.description}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="text-right space-y-2">
                        <div className="flex items-center justify-end space-x-2">
                          <Signal className="h-4 w-4 text-gray-400" />
                          <span className={`text-sm font-medium ${getRSSIStatusColor(beacon.rssi)}`}>
                            {formatRSSI(beacon.rssi)}
                          </span>
                        </div>
                        <div className="flex items-center justify-end space-x-2">
                          <Battery className="h-4 w-4 text-gray-400" />
                          <span className={`text-sm font-medium ${getBatteryStatusColor(beacon.batteryLevel)}`}>
                            {formatBattery(beacon.batteryLevel, beacon.isCharging)}
                          </span>
                        </div>
                        <div className="flex items-center justify-end space-x-2 text-xs text-gray-500">
                          <Clock className="h-3 w-3" />
                          <span>
                            {beacon.lastSeen ? formatTimeAgo(beacon.lastSeen) : 'Unknown'}
                          </span>
                        </div>
                        {beacon.estimatedDistance && (
                          <div className="text-xs text-gray-500 text-right">
                            Distance: {formatDistance(beacon.estimatedDistance)}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="card-premium">
          <div className="p-8 border-b border-gray-100">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-r from-blue-500 to-indigo-600 p-2 rounded-xl">
                <Activity className="h-6 w-6 text-white" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Recent Activity</h3>
                <p className="text-sm text-gray-600">
                  Latest system events and beacon updates
                </p>
              </div>
            </div>
          </div>
          <div className="p-8">
            {recentLogs.length === 0 ? (
              <div className="text-center py-12">
                <div className="bg-gray-100 p-4 rounded-2xl w-fit mx-auto mb-4">
                  <Activity className="h-12 w-12 text-gray-400" />
                </div>
                <p className="text-gray-500 font-medium">No recent activity</p>
              </div>
            ) : (
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {recentLogs.map((log) => (
                  <div key={log.id} className="bg-gradient-to-r from-white to-gray-50/50 rounded-xl p-4 border border-gray-100 hover:border-gray-200 transition-all duration-200">
                    <div className="flex items-start space-x-4">
                      <div className="flex-shrink-0 mt-1">
                        <span className={`badge ${
                          log.eventType === 'ALERT' ? 'badge-red' :
                          log.eventType === 'MQTT_MSG' ? 'badge-blue' :
                          log.eventType === 'SYSTEM' ? 'badge-green' :
                          log.eventType === 'REGISTRATION' ? 'badge-purple' :
                          log.eventType === 'BEACON_UPDATE' ? 'badge-amber' :
                          'badge-gray'
                        }`}>
                          {log.eventType}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 mb-1">
                          {log.details}
                        </p>
                        <div className="flex items-center space-x-3 text-xs text-gray-500">
                          <div className="flex items-center space-x-1">
                            <Clock className="h-3 w-3" />
                            <span>{formatTimestamp(log.timestamp)}</span>
                          </div>
                          {log.roomNumber && (
                            <div className="flex items-center space-x-1">
                              <MapPin className="h-3 w-3" />
                              <span>Room {log.roomNumber}</span>
                            </div>
                          )}
                        </div>
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
      <div className="card-premium p-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className={`p-3 rounded-2xl ${
              connectionStatus.isConnected 
                ? 'bg-gradient-to-r from-emerald-500 to-green-600' 
                : 'bg-gradient-to-r from-red-500 to-rose-600'
            }`}>
              {connectionStatus.isConnected ? (
                <Wifi className="h-6 w-6 text-white" />
              ) : (
                <WifiOff className="h-6 w-6 text-white" />
              )}
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900">System Status</h3>
              <p className="text-sm text-gray-600">
                AWS IoT connection and system health
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className={`connection-indicator ${
              connectionStatus.isConnected 
                ? 'connection-connected' 
                : connectionStatus.status === 'Connecting...'
                ? 'connection-connecting'
                : 'connection-disconnected'
            } text-base font-semibold`}>
              <div className={`status-dot ${
                connectionStatus.isConnected ? 'status-dot-active' : 'status-dot-inactive'
              } ${connectionStatus.isConnected ? 'pulse-dot' : ''}`}></div>
              <span>{connectionStatus.status}</span>
            </div>
            {connectionStatus.lastConnected && (
              <p className="text-sm text-gray-500 mt-2">
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