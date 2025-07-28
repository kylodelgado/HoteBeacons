import React, { useState } from 'react';
import { 
  Settings as SettingsIcon, 
  Wifi, 
  WifiOff,
  Save,
  RotateCcw,
  Cloud,
  Zap,
  Clock,
  Shield
} from 'lucide-react';
import { Settings as SettingsType, ConnectionStatus } from '../types';

interface SettingsProps {
  settings: SettingsType;
  connectionStatus: ConnectionStatus;
  onUpdateSettings: (settings: Partial<SettingsType>) => void;
  onToggleConnection: () => void;
}

const Settings: React.FC<SettingsProps> = ({
  settings,
  connectionStatus,
  onUpdateSettings,
  onToggleConnection,
}) => {
  const [formData, setFormData] = useState(settings);
  const [hasChanges, setHasChanges] = useState(false);

  const handleInputChange = (field: keyof SettingsType, value: string | number | boolean) => {
    const newData = { ...formData, [field]: value };
    setFormData(newData);
    setHasChanges(JSON.stringify(newData) !== JSON.stringify(settings));
  };

  const handleSave = () => {
    onUpdateSettings(formData);
    setHasChanges(false);
  };

  const handleReset = () => {
    setFormData(settings);
    setHasChanges(false);
  };

  const testConnection = () => {
    // Simulate connection test
    alert('Connection test started. Check the connection status in the header.');
    onToggleConnection();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">
          Configure AWS IoT connection and application preferences
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AWS IoT Configuration */}
        <div className="lg:col-span-2 space-y-6">
          <div className="card p-6">
            <div className="flex items-center space-x-2 mb-4">
              <Cloud className="h-5 w-5 text-blue-600" />
              <h3 className="text-lg font-medium text-gray-900">AWS IoT Configuration</h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  AWS IoT Endpoint
                </label>
                <input
                  type="text"
                  value={formData.awsEndpoint}
                  onChange={(e) => handleInputChange('awsEndpoint', e.target.value)}
                  placeholder="your-endpoint.iot.region.amazonaws.com"
                  className="input"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Your AWS IoT Core endpoint URL
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Client ID
                </label>
                <input
                  type="text"
                  value={formData.clientId}
                  onChange={(e) => handleInputChange('clientId', e.target.value)}
                  placeholder="hotel-beacon-client"
                  className="input"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Unique identifier for this client connection
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Alert Interval (minutes)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={formData.alertInterval}
                    onChange={(e) => handleInputChange('alertInterval', parseInt(e.target.value))}
                    className="input"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Refresh Interval (seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={formData.refreshInterval}
                    onChange={(e) => handleInputChange('refreshInterval', parseInt(e.target.value))}
                    className="input"
                  />
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="autoRefresh"
                  checked={formData.autoRefresh}
                  onChange={(e) => handleInputChange('autoRefresh', e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <label htmlFor="autoRefresh" className="text-sm text-gray-700">
                  Enable automatic data refresh
                </label>
              </div>
            </div>

            {hasChanges && (
              <div className="flex items-center space-x-3 mt-6 pt-4 border-t border-gray-200">
                <button
                  onClick={handleSave}
                  className="btn btn-primary flex items-center"
                >
                  <Save className="h-4 w-4 mr-2" />
                  Save Changes
                </button>
                <button
                  onClick={handleReset}
                  className="btn btn-secondary flex items-center"
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Reset
                </button>
              </div>
            )}
          </div>

          {/* Application Preferences */}
          <div className="card p-6">
            <div className="flex items-center space-x-2 mb-4">
              <SettingsIcon className="h-5 w-5 text-gray-600" />
              <h3 className="text-lg font-medium text-gray-900">Application Preferences</h3>
            </div>

            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 mb-2">Demo Mode Settings</h4>
                <p className="text-sm text-gray-600 mb-3">
                  This is a demo version with simulated data. In a production environment, 
                  these settings would connect to real AWS IoT services and manage actual 
                  Bluetooth beacons.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="font-medium text-gray-700">Data Source:</span>
                    <span className="ml-2 text-gray-600">Mock/Simulated</span>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">Real-time Updates:</span>
                    <span className="ml-2 text-gray-600">Simulated</span>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">AWS Connection:</span>
                    <span className="ml-2 text-gray-600">Simulated</span>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">MQTT Messages:</span>
                    <span className="ml-2 text-gray-600">Generated</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">
                      Auto-refresh Data
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={formData.autoRefresh}
                    onChange={(e) => handleInputChange('autoRefresh', e.target.checked)}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                </div>

                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">
                      Fast Updates
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={formData.refreshInterval <= 5}
                    onChange={(e) => handleInputChange('refreshInterval', e.target.checked ? 3 : 10)}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Connection Status and Actions */}
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-center space-x-2 mb-4">
              <Shield className="h-5 w-5 text-green-600" />
              <h3 className="text-lg font-medium text-gray-900">Connection Status</h3>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center space-x-3">
                  {connectionStatus.isConnected ? (
                    <Wifi className="h-5 w-5 text-green-600" />
                  ) : (
                    <WifiOff className="h-5 w-5 text-red-600" />
                  )}
                  <div>
                    <div className={`font-medium ${
                      connectionStatus.isConnected ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {connectionStatus.status}
                    </div>
                    {connectionStatus.lastConnected && (
                      <div className="text-xs text-gray-500">
                        Last connected: {connectionStatus.lastConnected.toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
                <div className={`w-3 h-3 rounded-full ${
                  connectionStatus.isConnected ? 'bg-green-400' : 'bg-red-400'
                }`}></div>
              </div>

              <div className="space-y-2">
                <button
                  onClick={onToggleConnection}
                  className={`w-full btn ${
                    connectionStatus.isConnected ? 'btn-danger' : 'btn-success'
                  } flex items-center justify-center`}
                >
                  {connectionStatus.isConnected ? (
                    <>
                      <WifiOff className="h-4 w-4 mr-2" />
                      Disconnect
                    </>
                  ) : (
                    <>
                      <Wifi className="h-4 w-4 mr-2" />
                      Connect
                    </>
                  )}
                </button>

                <button
                  onClick={testConnection}
                  className="w-full btn btn-secondary flex items-center justify-center"
                >
                  <Zap className="h-4 w-4 mr-2" />
                  Test Connection
                </button>
              </div>
            </div>
          </div>

          {/* System Information */}
          <div className="card p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">System Information</h3>
            
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Version:</span>
                <span className="font-mono text-gray-900">2.0 (React Demo)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Environment:</span>
                <span className="font-mono text-gray-900">Development</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Client ID:</span>
                <span className="font-mono text-gray-900">{formData.clientId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Endpoint:</span>
                <span className="font-mono text-gray-900 text-xs break-all">
                  {formData.awsEndpoint}
                </span>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="card p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Quick Actions</h3>
            
            <div className="space-y-2">
              <button
                onClick={() => window.location.reload()}
                className="w-full btn btn-secondary text-left"
              >
                <RotateCcw className="h-4 w-4 mr-2 inline" />
                Restart Application
              </button>
              
              <button
                onClick={() => {
                  if (confirm('Reset all settings to default values?')) {
                    const defaults: SettingsType = {
                      awsEndpoint: 'a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com',
                      clientId: 'hotel-beacon-client',
                      alertInterval: 15,
                      autoRefresh: true,
                      refreshInterval: 5,
                    };
                    setFormData(defaults);
                    onUpdateSettings(defaults);
                    setHasChanges(false);
                  }
                }}
                className="w-full btn btn-warning text-left"
              >
                <SettingsIcon className="h-4 w-4 mr-2 inline" />
                Reset to Defaults
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;