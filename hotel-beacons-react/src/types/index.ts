export interface Beacon {
  id: string;
  macAddress: string;
  roomNumber: string;
  description?: string;
  lastSeen?: Date;
  rssi?: number;
  batteryLevel?: number;
  deviceMode?: string;
  auxiliaryOperation?: string;
  estimatedDistance?: number;
  isCharging?: boolean;
  createdAt: Date;
  isActive: boolean;
}

export interface ActivityLog {
  id: string;
  timestamp: Date;
  beaconId?: string;
  eventType: 'SYSTEM' | 'MQTT_MSG' | 'ALERT' | 'BEACON_UPDATE' | 'REGISTRATION';
  details: string;
  roomNumber?: string;
  macAddress?: string;
}

export interface AlarmHistory {
  id: string;
  timestamp: Date;
  beaconId: string;
  macAddress: string;
  roomNumber: string;
  alertType: 'LOW_BATTERY' | 'DISCONNECTED' | 'SIGNAL_WEAK' | 'MAINTENANCE';
  message: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  acknowledged: boolean;
}

export interface ConnectionStatus {
  isConnected: boolean;
  status: 'Connected' | 'Disconnected' | 'Connecting...';
  lastConnected?: Date;
}

export interface BeaconStatistics {
  totalBeacons: number;
  activeBeacons: number;
  lowBatteryBeacons: number;
  offlineBeacons: number;
}

export type TabType = 'dashboard' | 'beacons' | 'alerts' | 'logs' | 'settings';

export interface Settings {
  awsEndpoint: string;
  clientId: string;
  alertInterval: number;
  autoRefresh: boolean;
  refreshInterval: number;
}