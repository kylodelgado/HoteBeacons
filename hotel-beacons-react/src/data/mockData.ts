import { Beacon, ActivityLog, AlarmHistory, ConnectionStatus, BeaconStatistics, Settings } from '../types';

// Mock beacons data based on the original system
export const mockBeacons: Beacon[] = [
  {
    id: '1',
    macAddress: 'D3:8D:48:10:63:3C',
    roomNumber: '6h',
    description: 'Deluxe Suite 6H',
    lastSeen: new Date(Date.now() - 2 * 60 * 1000), // 2 minutes ago
    rssi: -45,
    batteryLevel: 85,
    deviceMode: 'Normal',
    auxiliaryOperation: 'None',
    estimatedDistance: 2.5,
    isCharging: false,
    createdAt: new Date('2025-04-08T16:35:41.860275'),
    isActive: true,
  },
  {
    id: '2',
    macAddress: 'D6:20:31:E8:D8:1D',
    roomNumber: '87',
    description: 'Standard Room 87',
    lastSeen: new Date(Date.now() - 5 * 60 * 1000), // 5 minutes ago
    rssi: -62,
    batteryLevel: 45,
    deviceMode: 'Low Power',
    auxiliaryOperation: 'Maintenance',
    estimatedDistance: 8.2,
    isCharging: true,
    createdAt: new Date('2025-04-08T16:35:41.860275'),
    isActive: true,
  },
  {
    id: '3',
    macAddress: 'ED:38:4C:1C:47:93',
    roomNumber: '8i',
    description: 'Presidential Suite 8I',
    lastSeen: new Date(Date.now() - 10 * 60 * 1000), // 10 minutes ago
    rssi: -78,
    batteryLevel: 92,
    deviceMode: 'High Performance',
    auxiliaryOperation: 'Security',
    estimatedDistance: 15.6,
    isCharging: false,
    createdAt: new Date('2025-04-08T16:35:41.860275'),
    isActive: false,
  },
  {
    id: '4',
    macAddress: 'A1:B2:C3:D4:E5:F6',
    roomNumber: '101',
    description: 'Guest Room 101',
    lastSeen: new Date(Date.now() - 1 * 60 * 1000), // 1 minute ago
    rssi: -35,
    batteryLevel: 15,
    deviceMode: 'Critical',
    auxiliaryOperation: 'Alert',
    estimatedDistance: 1.2,
    isCharging: false,
    createdAt: new Date('2025-04-07T10:20:15.123456'),
    isActive: true,
  },
  {
    id: '5',
    macAddress: 'F1:E2:D3:C4:B5:A6',
    roomNumber: '205',
    description: 'Business Suite 205',
    lastSeen: new Date(Date.now() - 3 * 60 * 1000), // 3 minutes ago
    rssi: -55,
    batteryLevel: 78,
    deviceMode: 'Normal',
    auxiliaryOperation: 'Monitoring',
    estimatedDistance: 5.8,
    isCharging: false,
    createdAt: new Date('2025-04-06T14:15:30.789012'),
    isActive: true,
  },
];

export const mockActivityLogs: ActivityLog[] = [
  {
    id: '1',
    timestamp: new Date(Date.now() - 5 * 60 * 1000),
    beaconId: '1',
    eventType: 'MQTT_MSG',
    details: 'Beacon signal received: RSSI -45 dBm, Battery 85%',
    roomNumber: '6h',
    macAddress: 'D3:8D:48:10:63:3C',
  },
  {
    id: '2',
    timestamp: new Date(Date.now() - 10 * 60 * 1000),
    beaconId: '2',
    eventType: 'ALERT',
    details: 'Low battery warning: 45% remaining',
    roomNumber: '87',
    macAddress: 'D6:20:31:E8:D8:1D',
  },
  {
    id: '3',
    timestamp: new Date(Date.now() - 15 * 60 * 1000),
    eventType: 'SYSTEM',
    details: 'AWS IoT connection established',
  },
  {
    id: '4',
    timestamp: new Date(Date.now() - 20 * 60 * 1000),
    beaconId: '4',
    eventType: 'REGISTRATION',
    details: 'New beacon registered: Room 101',
    roomNumber: '101',
    macAddress: 'A1:B2:C3:D4:E5:F6',
  },
  {
    id: '5',
    timestamp: new Date(Date.now() - 25 * 60 * 1000),
    beaconId: '3',
    eventType: 'BEACON_UPDATE',
    details: 'Beacon status updated: Device mode changed to High Performance',
    roomNumber: '8i',
    macAddress: 'ED:38:4C:1C:47:93',
  },
];

export const mockAlarmHistory: AlarmHistory[] = [
  {
    id: '1',
    timestamp: new Date(Date.now() - 30 * 60 * 1000),
    beaconId: '4',
    macAddress: 'A1:B2:C3:D4:E5:F6',
    roomNumber: '101',
    alertType: 'LOW_BATTERY',
    message: 'Critical battery level: 15% remaining. Please replace or charge immediately.',
    severity: 'critical',
    acknowledged: false,
  },
  {
    id: '2',
    timestamp: new Date(Date.now() - 45 * 60 * 1000),
    beaconId: '2',
    macAddress: 'D6:20:31:E8:D8:1D',
    roomNumber: '87',
    alertType: 'LOW_BATTERY',
    message: 'Low battery warning: 45% remaining. Consider charging soon.',
    severity: 'medium',
    acknowledged: true,
  },
  {
    id: '3',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000),
    beaconId: '3',
    macAddress: 'ED:38:4C:1C:47:93',
    roomNumber: '8i',
    alertType: 'SIGNAL_WEAK',
    message: 'Weak signal detected: RSSI -78 dBm. Check beacon placement.',
    severity: 'low',
    acknowledged: true,
  },
  {
    id: '4',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000),
    beaconId: '5',
    macAddress: 'F1:E2:D3:C4:B5:A6',
    roomNumber: '205',
    alertType: 'MAINTENANCE',
    message: 'Scheduled maintenance required for beacon in room 205.',
    severity: 'medium',
    acknowledged: false,
  },
];

export const mockConnectionStatus: ConnectionStatus = {
  isConnected: true,
  status: 'Connected',
  lastConnected: new Date(Date.now() - 30 * 60 * 1000),
};

export const mockBeaconStatistics: BeaconStatistics = {
  totalBeacons: 5,
  activeBeacons: 4,
  lowBatteryBeacons: 2,
  offlineBeacons: 1,
};

export const mockSettings: Settings = {
  awsEndpoint: 'a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com',
  clientId: 'hotel-beacon-client',
  alertInterval: 15,
  autoRefresh: true,
  refreshInterval: 5,
};

// Utility function to simulate real-time updates
export const updateMockData = () => {
  // Simulate some beacon updates
  const now = new Date();
  
  mockBeacons.forEach((beacon) => {
    if (Math.random() > 0.7) { // 30% chance of update
      beacon.lastSeen = new Date(now.getTime() - Math.random() * 5 * 60 * 1000);
      beacon.rssi = -30 - Math.random() * 50;
      beacon.batteryLevel = Math.max(0, beacon.batteryLevel! - Math.random() * 2);
      beacon.estimatedDistance = Math.random() * 20;
      beacon.isActive = (now.getTime() - beacon.lastSeen.getTime()) < 5 * 60 * 1000;
    }
  });
  
  // Add new activity log
  if (Math.random() > 0.8) { // 20% chance
    const randomBeacon = mockBeacons[Math.floor(Math.random() * mockBeacons.length)];
    mockActivityLogs.unshift({
      id: Date.now().toString(),
      timestamp: now,
      beaconId: randomBeacon.id,
      eventType: 'MQTT_MSG',
      details: `Beacon signal received: RSSI ${randomBeacon.rssi} dBm, Battery ${randomBeacon.batteryLevel}%`,
      roomNumber: randomBeacon.roomNumber,
      macAddress: randomBeacon.macAddress,
    });
    
    // Keep only last 50 logs
    if (mockActivityLogs.length > 50) {
      mockActivityLogs.splice(50);
    }
  }
};