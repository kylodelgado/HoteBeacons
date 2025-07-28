import React, { useState } from 'react';
import { 
  Plus, 
  Search, 
  Edit, 
  Trash2, 
  Copy, 
  MapPin,
  Battery,
  Signal,
  Clock,
  Zap
} from 'lucide-react';
import { Beacon } from '../types';
import { 
  formatBattery, 
  formatRSSI, 
  formatDistance,
  formatTimeAgo,
  getBatteryStatusColor,
  getRSSIStatusColor,
  copyToClipboard,
  generateMockMacAddress
} from '../utils';

interface BeaconManagementProps {
  beacons: Beacon[];
  onAddBeacon: (beacon: Omit<Beacon, 'id' | 'createdAt' | 'isActive'>) => void;
  onUpdateBeacon: (id: string, updates: Partial<Beacon>) => void;
  onDeleteBeacon: (id: string) => void;
  onRefresh: () => void;
  isLoading: boolean;
}

const BeaconManagement: React.FC<BeaconManagementProps> = ({
  beacons,
  onAddBeacon,
  onUpdateBeacon,
  onDeleteBeacon,
  onRefresh: _onRefresh,
  isLoading: _isLoading,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingBeacon, setEditingBeacon] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    macAddress: '',
    roomNumber: '',
    description: '',
  });

  const filteredBeacons = beacons.filter(beacon =>
    beacon.roomNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
    beacon.macAddress.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (beacon.description && beacon.description.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const handleAddBeacon = () => {
    if (!formData.macAddress || !formData.roomNumber) return;

    onAddBeacon({
      macAddress: formData.macAddress,
      roomNumber: formData.roomNumber,
      description: formData.description,
      lastSeen: new Date(),
      rssi: -Math.floor(Math.random() * 50 + 30),
      batteryLevel: Math.floor(Math.random() * 100),
      deviceMode: 'Normal',
      auxiliaryOperation: 'None',
      estimatedDistance: Math.random() * 20,
      isCharging: false,
    });

    setFormData({ macAddress: '', roomNumber: '', description: '' });
    setShowAddForm(false);
  };

  const handleUpdateBeacon = (beacon: Beacon) => {
    if (!formData.roomNumber) return;

    onUpdateBeacon(beacon.id, {
      roomNumber: formData.roomNumber,
      description: formData.description,
    });

    setEditingBeacon(null);
    setFormData({ macAddress: '', roomNumber: '', description: '' });
  };

  const startEdit = (beacon: Beacon) => {
    setEditingBeacon(beacon.id);
    setFormData({
      macAddress: beacon.macAddress,
      roomNumber: beacon.roomNumber,
      description: beacon.description || '',
    });
  };

  const handleCopyMac = async (macAddress: string) => {
    const success = await copyToClipboard(macAddress);
    if (success) {
      // You could add a toast notification here
      console.log('MAC address copied to clipboard');
    }
  };

  const generateRandomMac = () => {
    setFormData(prev => ({
      ...prev,
      macAddress: generateMockMacAddress()
    }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Beacon Management</h2>
          <p className="text-sm text-gray-500 mt-1">
            Manage and monitor all registered beacons
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="btn btn-primary flex items-center mt-4 sm:mt-0"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Beacon
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by room number, MAC address, or description..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="input pl-10"
        />
      </div>

      {/* Add/Edit Form Modal */}
      {(showAddForm || editingBeacon) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              {showAddForm ? 'Add New Beacon' : 'Edit Beacon'}
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  MAC Address
                </label>
                <div className="flex space-x-2">
                  <input
                    type="text"
                    placeholder="XX:XX:XX:XX:XX:XX"
                    value={formData.macAddress}
                    onChange={(e) => setFormData(prev => ({ ...prev, macAddress: e.target.value }))}
                    disabled={!!editingBeacon}
                    className="input flex-1"
                  />
                  {showAddForm && (
                    <button
                      onClick={generateRandomMac}
                      className="btn btn-secondary"
                      title="Generate random MAC"
                    >
                      <Zap className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Room Number
                </label>
                <input
                  type="text"
                  placeholder="e.g., 101, 2A, Suite 5"
                  value={formData.roomNumber}
                  onChange={(e) => setFormData(prev => ({ ...prev, roomNumber: e.target.value }))}
                  className="input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g., Presidential Suite, Corner Room"
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  className="input"
                />
              </div>
            </div>

            <div className="flex space-x-3 mt-6">
              <button
                onClick={() => {
                  if (showAddForm) {
                    handleAddBeacon();
                  } else if (editingBeacon) {
                    const beacon = beacons.find(b => b.id === editingBeacon);
                    if (beacon) handleUpdateBeacon(beacon);
                  }
                }}
                disabled={!formData.macAddress || !formData.roomNumber}
                className="btn btn-primary flex-1"
              >
                {showAddForm ? 'Add Beacon' : 'Update Beacon'}
              </button>
              <button
                onClick={() => {
                  setShowAddForm(false);
                  setEditingBeacon(null);
                  setFormData({ macAddress: '', roomNumber: '', description: '' });
                }}
                className="btn btn-secondary flex-1"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Beacons Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Location
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  MAC Address
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Signal
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Battery
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Last Seen
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredBeacons.map((beacon) => (
                <tr key={beacon.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className={`w-3 h-3 rounded-full mr-2 ${
                        beacon.isActive ? 'bg-green-400' : 'bg-red-400'
                      }`}></div>
                      <span className={`text-sm font-medium ${
                        beacon.isActive ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {beacon.isActive ? 'Active' : 'Offline'}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <MapPin className="h-4 w-4 text-gray-400 mr-2" />
                      <div>
                        <div className="text-sm font-medium text-gray-900">
                          Room {beacon.roomNumber}
                        </div>
                        {beacon.description && (
                          <div className="text-sm text-gray-500">
                            {beacon.description}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <code className="text-sm font-mono text-gray-900">
                        {beacon.macAddress}
                      </code>
                      <button
                        onClick={() => handleCopyMac(beacon.macAddress)}
                        className="text-gray-400 hover:text-gray-600"
                        title="Copy MAC address"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <Signal className="h-4 w-4 text-gray-400" />
                      <span className={`text-sm ${getRSSIStatusColor(beacon.rssi)}`}>
                        {formatRSSI(beacon.rssi)}
                      </span>
                      {beacon.estimatedDistance && (
                        <span className="text-xs text-gray-500">
                          ({formatDistance(beacon.estimatedDistance)})
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <Battery className="h-4 w-4 text-gray-400" />
                      <span className={`text-sm ${getBatteryStatusColor(beacon.batteryLevel)}`}>
                        {formatBattery(beacon.batteryLevel, beacon.isCharging)}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <Clock className="h-4 w-4 text-gray-400" />
                      <span className="text-sm text-gray-500">
                        {beacon.lastSeen ? formatTimeAgo(beacon.lastSeen) : 'Unknown'}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => startEdit(beacon)}
                        className="text-primary-600 hover:text-primary-900"
                        title="Edit beacon"
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => onDeleteBeacon(beacon.id)}
                        className="text-red-600 hover:text-red-900"
                        title="Delete beacon"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {filteredBeacons.length === 0 && (
          <div className="text-center py-12">
            <div className="text-gray-400 mb-4">
              {searchTerm ? (
                <>
                  <Search className="h-12 w-12 mx-auto mb-4" />
                  <p>No beacons found matching "{searchTerm}"</p>
                </>
              ) : (
                <>
                  <MapPin className="h-12 w-12 mx-auto mb-4" />
                  <p>No beacons registered yet</p>
                  <p className="text-sm mt-2">Click "Add Beacon" to get started</p>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="text-2xl font-bold text-gray-900">{beacons.length}</div>
          <div className="text-sm text-gray-500">Total Beacons</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-green-600">
            {beacons.filter(b => b.isActive).length}
          </div>
          <div className="text-sm text-gray-500">Active Beacons</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-yellow-600">
            {beacons.filter(b => b.batteryLevel && b.batteryLevel <= 30).length}
          </div>
          <div className="text-sm text-gray-500">Low Battery</div>
        </div>
      </div>
    </div>
  );
};

export default BeaconManagement;