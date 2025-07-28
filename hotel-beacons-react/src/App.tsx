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
    <div className="min-h-screen">
      {/* Header */}
      <header className="header-glass sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-20">
            <div className="flex items-center space-x-4">
              <div className="glow-effect">
                <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-3 rounded-2xl shadow-lg">
                  <Radio className="h-8 w-8 text-white" />
                </div>
              </div>
              <div>
                <h1 className="text-2xl font-bold gradient-text">
                  Hotel Beacon Management System
                </h1>
                <p className="text-sm text-gray-600 font-medium">v2.0 - Professional Demo</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-6">
              <button
                onClick={refreshData}
                disabled={isLoading}
                className="btn btn-secondary flex items-center group"
              >
                <RefreshCw className={`h-4 w-4 mr-2 transition-transform duration-200 ${isLoading ? 'animate-spin' : 'group-hover:rotate-180'}`} />
                Refresh
              </button>
              
              <div className={`connection-indicator ${
                connectionStatus.isConnected 
                  ? 'connection-connected' 
                  : connectionStatus.status === 'Connecting...'
                  ? 'connection-connecting'
                  : 'connection-disconnected'
              }`}>
                {connectionStatus.isConnected ? (
                  <Wifi className="h-4 w-4" />
                ) : (
                  <WifiOff className="h-4 w-4" />
                )}
                <span className="font-semibold">
                  {connectionStatus.status}
                </span>
                {connectionStatus.isConnected && (
                  <div className="status-dot-active pulse-dot"></div>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white/60 backdrop-blur-md border-b border-white/20 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`nav-tab ${isActive ? 'nav-tab-active' : 'nav-tab-inactive'} relative z-10`}
                >
                  <Icon className="h-5 w-5 mr-3" />
                  <span>{tab.label}</span>
                  {/* Enhanced badge for alerts */}
                  {tab.id === 'alerts' && alarmHistory.filter(a => !a.acknowledged).length > 0 && (
                    <span className="ml-3 bg-gradient-to-r from-red-500 to-rose-600 text-white text-xs font-bold px-2.5 py-1 rounded-full shadow-lg animate-pulse">
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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="relative">
          {renderTabContent()}
        </div>
      </main>

      {/* Enhanced Footer */}
      <footer className="bg-gradient-to-r from-gray-50 to-blue-50/50 border-t border-white/20 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold gradient-text mb-2">
                Hotel Beacon Management System
              </h3>
              <p className="text-gray-600 mb-2">Professional React Demo Component</p>
              <p className="text-sm text-gray-500">
                Simulating real-time beacon monitoring and management with modern web technologies
              </p>
            </div>
            <div className="text-right">
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="card p-4">
                  <div className="text-2xl font-bold gradient-text">{statistics.totalBeacons}</div>
                  <div className="text-sm text-gray-600">Total Beacons</div>
                </div>
                <div className="card p-4">
                  <div className="text-2xl font-bold text-emerald-600">{statistics.activeBeacons}</div>
                  <div className="text-sm text-gray-600">Active Now</div>
                </div>
              </div>
              <p className="text-sm text-gray-500">
                Last updated: {new Date().toLocaleTimeString()}
              </p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;