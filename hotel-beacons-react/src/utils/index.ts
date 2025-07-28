import { format, formatDistanceToNow } from 'date-fns';

export const formatTimestamp = (date: Date): string => {
  return format(date, 'HH:mm:ss');
};

export const formatFullDate = (date: Date): string => {
  return format(date, 'yyyy-MM-dd HH:mm:ss');
};

export const formatTimeAgo = (date: Date): string => {
  return formatDistanceToNow(date, { addSuffix: true });
};

export const formatRSSI = (rssi?: number): string => {
  if (rssi === undefined) return 'N/A';
  return `${rssi} dBm`;
};

export const formatBattery = (batteryLevel?: number, isCharging?: boolean): string => {
  if (batteryLevel === undefined) return 'N/A';
  const suffix = isCharging ? ' ⚡' : '';
  return `${batteryLevel}%${suffix}`;
};

export const formatDistance = (distance?: number): string => {
  if (distance === undefined) return 'N/A';
  return `${distance.toFixed(1)} m`;
};

export const getBatteryStatusColor = (batteryLevel?: number): string => {
  if (batteryLevel === undefined) return 'text-gray-500';
  if (batteryLevel <= 15) return 'text-red-600';
  if (batteryLevel <= 30) return 'text-yellow-600';
  return 'text-green-600';
};

export const getRSSIStatusColor = (rssi?: number): string => {
  if (rssi === undefined) return 'text-gray-500';
  if (rssi >= -50) return 'text-green-600';
  if (rssi >= -70) return 'text-yellow-600';
  return 'text-red-600';
};

export const getConnectionStatusColor = (status: string): string => {
  switch (status) {
    case 'Connected':
      return 'text-green-600';
    case 'Connecting...':
      return 'text-yellow-600';
    case 'Disconnected':
      return 'text-red-600';
    default:
      return 'text-gray-500';
  }
};

export const getSeverityColor = (severity: string): string => {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-800 border-red-200';
    case 'high':
      return 'bg-orange-100 text-orange-800 border-orange-200';
    case 'medium':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'low':
      return 'bg-blue-100 text-blue-800 border-blue-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
  }
};

export const getEventTypeColor = (eventType: string): string => {
  switch (eventType) {
    case 'ALERT':
      return 'bg-red-100 text-red-800';
    case 'MQTT_MSG':
      return 'bg-blue-100 text-blue-800';
    case 'SYSTEM':
      return 'bg-green-100 text-green-800';
    case 'REGISTRATION':
      return 'bg-purple-100 text-purple-800';
    case 'BEACON_UPDATE':
      return 'bg-yellow-100 text-yellow-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
};

export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback for browsers that don't support clipboard API
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      document.body.removeChild(textArea);
      return true;
    } catch (err) {
      document.body.removeChild(textArea);
      return false;
    }
  }
};

export const generateMockMacAddress = (): string => {
  const chars = '0123456789ABCDEF';
  const parts = [];
  for (let i = 0; i < 6; i++) {
    const part = chars[Math.floor(Math.random() * 16)] + chars[Math.floor(Math.random() * 16)];
    parts.push(part);
  }
  return parts.join(':');
};

export const isBeaconActive = (lastSeen?: Date): boolean => {
  if (!lastSeen) return false;
  const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
  return lastSeen > fiveMinutesAgo;
};