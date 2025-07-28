import { useState, useEffect, useCallback } from 'react';
import { 
  Beacon, 
  ActivityLog, 
  AlarmHistory, 
  ConnectionStatus, 
  BeaconStatistics, 
  Settings 
} from '../types';
import {
  mockBeacons,
  mockActivityLogs,
  mockAlarmHistory,
  mockConnectionStatus,
  mockBeaconStatistics,
  mockSettings,
  updateMockData
} from '../data/mockData';
import { isBeaconActive } from '../utils';

export const useBeaconData = () => {
  const [beacons, setBeacons] = useState<Beacon[]>(mockBeacons);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>(mockActivityLogs);
  const [alarmHistory, setAlarmHistory] = useState<AlarmHistory[]>(mockAlarmHistory);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(mockConnectionStatus);
  const [statistics, setStatistics] = useState<BeaconStatistics>(mockBeaconStatistics);
  const [settings, setSettings] = useState<Settings>(mockSettings);
  const [isLoading, setIsLoading] = useState(false);

  // Calculate statistics based on current beacon data
  const calculateStatistics = useCallback((beaconList: Beacon[]): BeaconStatistics => {
    const totalBeacons = beaconList.length;
    const activeBeacons = beaconList.filter(beacon => isBeaconActive(beacon.lastSeen)).length;
    const lowBatteryBeacons = beaconList.filter(beacon => 
      beacon.batteryLevel !== undefined && beacon.batteryLevel <= 30
    ).length;
    const offlineBeacons = totalBeacons - activeBeacons;

    return {
      totalBeacons,
      activeBeacons,
      lowBatteryBeacons,
      offlineBeacons,
    };
  }, []);

  // Add a new beacon
  const addBeacon = useCallback((newBeacon: Omit<Beacon, 'id' | 'createdAt' | 'isActive'>) => {
    const beacon: Beacon = {
      ...newBeacon,
      id: Date.now().toString(),
      createdAt: new Date(),
      isActive: isBeaconActive(newBeacon.lastSeen),
    };

    setBeacons(prev => {
      const updated = [...prev, beacon];
      setStatistics(calculateStatistics(updated));
      return updated;
    });

    // Add activity log
    const logEntry: ActivityLog = {
      id: Date.now().toString(),
      timestamp: new Date(),
      beaconId: beacon.id,
      eventType: 'REGISTRATION',
      details: `New beacon registered: Room ${beacon.roomNumber}`,
      roomNumber: beacon.roomNumber,
      macAddress: beacon.macAddress,
    };
    
    setActivityLogs(prev => [logEntry, ...prev]);
  }, [calculateStatistics]);

  // Update a beacon
  const updateBeacon = useCallback((id: string, updates: Partial<Beacon>) => {
    setBeacons(prev => {
      const updated = prev.map(beacon => 
        beacon.id === id 
          ? { ...beacon, ...updates, isActive: isBeaconActive(updates.lastSeen || beacon.lastSeen) }
          : beacon
      );
      setStatistics(calculateStatistics(updated));
      return updated;
    });

    // Add activity log if significant update
    if (updates.lastSeen || updates.batteryLevel || updates.rssi) {
      const beacon = beacons.find(b => b.id === id);
      if (beacon) {
        const logEntry: ActivityLog = {
          id: Date.now().toString(),
          timestamp: new Date(),
          beaconId: id,
          eventType: 'BEACON_UPDATE',
          details: `Beacon updated: ${updates.rssi ? `RSSI ${updates.rssi} dBm` : ''} ${updates.batteryLevel ? `Battery ${updates.batteryLevel}%` : ''}`.trim(),
          roomNumber: beacon.roomNumber,
          macAddress: beacon.macAddress,
        };
        
        setActivityLogs(prev => [logEntry, ...prev]);
      }
    }
  }, [beacons, calculateStatistics]);

  // Delete a beacon
  const deleteBeacon = useCallback((id: string) => {
    setBeacons(prev => {
      const updated = prev.filter(beacon => beacon.id !== id);
      setStatistics(calculateStatistics(updated));
      return updated;
    });
  }, [calculateStatistics]);

  // Acknowledge an alarm
  const acknowledgeAlarm = useCallback((alarmId: string) => {
    setAlarmHistory(prev => 
      prev.map(alarm => 
        alarm.id === alarmId 
          ? { ...alarm, acknowledged: true }
          : alarm
      )
    );
  }, []);

  // Clear alarm history
  const clearAlarmHistory = useCallback(() => {
    setAlarmHistory([]);
  }, []);

  // Clear activity logs
  const clearActivityLogs = useCallback(() => {
    setActivityLogs([]);
  }, []);

  // Connect/disconnect from AWS
  const toggleConnection = useCallback(() => {
    setConnectionStatus(prev => ({
      ...prev,
      isConnected: !prev.isConnected,
      status: !prev.isConnected ? 'Connected' : 'Disconnected',
      lastConnected: !prev.isConnected ? new Date() : prev.lastConnected,
    }));

    const logEntry: ActivityLog = {
      id: Date.now().toString(),
      timestamp: new Date(),
      eventType: 'SYSTEM',
      details: connectionStatus.isConnected ? 'AWS IoT connection terminated' : 'AWS IoT connection established',
    };
    
    setActivityLogs(prev => [logEntry, ...prev]);
  }, [connectionStatus.isConnected]);

  // Update settings
  const updateSettings = useCallback((newSettings: Partial<Settings>) => {
    setSettings(prev => ({ ...prev, ...newSettings }));
  }, []);

  // Simulate real-time updates
  useEffect(() => {
    if (!settings.autoRefresh) return;

    const interval = setInterval(() => {
      updateMockData();
      
      // Update beacons with new data
      setBeacons(() => {
        const updated = [...mockBeacons];
        setStatistics(calculateStatistics(updated));
        return updated;
      });

      // Update activity logs
      setActivityLogs([...mockActivityLogs]);

      // Simulate connection status changes occasionally
      if (Math.random() > 0.95) { // 5% chance
        setConnectionStatus(prev => ({
          ...prev,
          status: prev.isConnected ? 'Connected' : 'Disconnected',
          lastConnected: prev.isConnected ? new Date() : prev.lastConnected,
        }));
      }
    }, settings.refreshInterval * 1000);

    return () => clearInterval(interval);
  }, [settings.autoRefresh, settings.refreshInterval, calculateStatistics]);

  // Manual refresh
  const refreshData = useCallback(() => {
    setIsLoading(true);
    
    // Simulate API call delay
    setTimeout(() => {
      updateMockData();
      setBeacons([...mockBeacons]);
      setActivityLogs([...mockActivityLogs]);
      setStatistics(calculateStatistics(mockBeacons));
      setIsLoading(false);
    }, 1000);
  }, [calculateStatistics]);

  return {
    // Data
    beacons,
    activityLogs,
    alarmHistory,
    connectionStatus,
    statistics,
    settings,
    isLoading,
    
    // Actions
    addBeacon,
    updateBeacon,
    deleteBeacon,
    acknowledgeAlarm,
    clearAlarmHistory,
    clearActivityLogs,
    toggleConnection,
    updateSettings,
    refreshData,
  };
};