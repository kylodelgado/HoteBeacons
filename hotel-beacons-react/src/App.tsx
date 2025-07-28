import { useState } from 'react';
import { 
  Activity, 
  Radio, 
  AlertTriangle, 
  Database, 
  Settings as SettingsIcon,
  RefreshCw,
  Wifi,
  WifiOff
} from 'lucide-react';
import { TabType } from './types';
import { useBeaconData } from './hooks/useBeaconData';
import { getConnectionStatusColor } from './utils';

// Import components (we'll create these next)
import Dashboard from './components/Dashboard';
import BeaconManagement from './components/BeaconManagement';
import AlarmHistory from './components/AlarmHistory';
import ActivityLogs from './components/ActivityLogs';
import Settings from './components/Settings';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const {
    beacons,
    activityLogs,
    alarmHistory,
    connectionStatus,
    statistics,
    settings,
    isLoading,
    addBeacon,
    updateBeacon,
    deleteBeacon,
    acknowledgeAlarm,
    clearAlarmHistory,
    clearActivityLogs,
    toggleConnection,
    updateSettings,
    refreshData,
  } = useBeaconData();

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'beacons', label: 'Beacon Management', icon: Radio },
    { id: 'alerts', label: 'Alarm History', icon: AlertTriangle },
    { id: 'logs', label: 'Activity Logs', icon: Database },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ] as const;

  const renderTabContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <Dashboard
            beacons={beacons}
            statistics={statistics}
            connectionStatus={connectionStatus}
            recentLogs={activityLogs.slice(0, 10)}
            onRefresh={refreshData}
            isLoading={isLoading}
          />
        );
      case 'beacons':
        return (
          <BeaconManagement
            beacons={beacons}
            onAddBeacon={addBeacon}
            onUpdateBeacon={updateBeacon}
            onDeleteBeacon={deleteBeacon}
            onRefresh={refreshData}
            isLoading={isLoading}
          />
        );
      case 'alerts':
        return (
          <AlarmHistory
            alarms={alarmHistory}
            onAcknowledge={acknowledgeAlarm}
            onClear={clearAlarmHistory}
            onRefresh={refreshData}
            isLoading={isLoading}
          />
        );
      case 'logs':
        return (
          <ActivityLogs
            logs={activityLogs}
            onClear={clearActivityLogs}
            onRefresh={refreshData}
            isLoading={isLoading}
          />
        );
      case 'settings':
        return (
          <Settings
            settings={settings}
            connectionStatus={connectionStatus}
            onUpdateSettings={updateSettings}
            onToggleConnection={toggleConnection}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Radio className="h-8 w-8 text-primary-600 mr-3" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">
                  Hotel Beacon Management System
                </h1>
                <p className="text-sm text-gray-500">v2.0 - React Demo</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              <button
                onClick={refreshData}
                disabled={isLoading}
                className="btn btn-secondary flex items-center"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              
              <div className="flex items-center space-x-2">
                {connectionStatus.isConnected ? (
                  <Wifi className="h-5 w-5 text-green-600" />
                ) : (
                  <WifiOff className="h-5 w-5 text-red-600" />
                )}
                <span className={`text-sm font-medium ${getConnectionStatusColor(connectionStatus.status)}`}>
                  {connectionStatus.status}
                </span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    flex items-center px-3 py-4 text-sm font-medium border-b-2 transition-colors
                    ${isActive
                      ? 'border-primary-500 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }
                  `}
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.label}
                  {/* Badge for alerts */}
                  {tab.id === 'alerts' && alarmHistory.filter(a => !a.acknowledged).length > 0 && (
                    <span className="ml-2 bg-red-100 text-red-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                      {alarmHistory.filter(a => !a.acknowledged).length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {renderTabContent()}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center text-sm text-gray-500">
            <div>
              <p>Hotel Beacon Management System - React Demo Component</p>
              <p>Simulating real-time beacon monitoring and management</p>
            </div>
            <div className="text-right">
              <p>Statistics: {statistics.totalBeacons} beacons, {statistics.activeBeacons} active</p>
              <p>Last updated: {new Date().toLocaleTimeString()}</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;