import React, { useState } from 'react';
import { 
  Database, 
  Search, 
  Trash2, 
  Download,
  Filter,
  Clock,
  MapPin
} from 'lucide-react';
import { ActivityLog } from '../types';
import { 
  formatFullDate, 
  formatTimestamp,
  formatTimeAgo,
  getEventTypeColor
} from '../utils';

interface ActivityLogsProps {
  logs: ActivityLog[];
  onClear: () => void;
  onRefresh: () => void;
  isLoading: boolean;
}

const ActivityLogs: React.FC<ActivityLogsProps> = ({
  logs,
  onClear,
  onRefresh: _onRefresh,
  isLoading: _isLoading,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterEventType, setFilterEventType] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'compact' | 'detailed'>('compact');

  const filteredLogs = logs.filter(log => {
    const matchesSearch = 
      log.details.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (log.roomNumber && log.roomNumber.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (log.macAddress && log.macAddress.toLowerCase().includes(searchTerm.toLowerCase()));
    
    const matchesEventType = filterEventType === 'all' || log.eventType === filterEventType;

    return matchesSearch && matchesEventType;
  });

  const exportLogs = () => {
    const csvContent = [
      ['Timestamp', 'Event Type', 'Room', 'MAC Address', 'Details'].join(','),
      ...filteredLogs.map(log => [
        formatFullDate(log.timestamp),
        log.eventType,
        log.roomNumber || '',
        log.macAddress || '',
        `"${log.details.replace(/"/g, '""')}"`
      ].join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `activity_logs_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getEventTypeIcon = (eventType: string) => {
    switch (eventType) {
      case 'ALERT':
        return <span className="text-red-600">🚨</span>;
      case 'MQTT_MSG':
        return <span className="text-blue-600">📡</span>;
      case 'SYSTEM':
        return <span className="text-green-600">⚙️</span>;
      case 'REGISTRATION':
        return <span className="text-purple-600">➕</span>;
      case 'BEACON_UPDATE':
        return <span className="text-yellow-600">🔄</span>;
      default:
        return <span className="text-gray-600">ℹ️</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Activity Logs</h2>
          <p className="text-sm text-gray-500 mt-1">
            System events, beacon updates, and operational logs
          </p>
        </div>
        <div className="flex space-x-2 mt-4 sm:mt-0">
          <button
            onClick={exportLogs}
            disabled={filteredLogs.length === 0}
            className="btn btn-secondary flex items-center"
          >
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </button>
          <button
            onClick={onClear}
            disabled={logs.length === 0}
            className="btn btn-danger flex items-center"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Clear All
          </button>
        </div>
      </div>

      {/* Filters and View Controls */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input pl-10"
          />
        </div>
        
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <select
            value={filterEventType}
            onChange={(e) => setFilterEventType(e.target.value)}
            className="input pl-10"
          >
            <option value="all">All Event Types</option>
            <option value="SYSTEM">System</option>
            <option value="MQTT_MSG">MQTT Messages</option>
            <option value="ALERT">Alerts</option>
            <option value="REGISTRATION">Registration</option>
            <option value="BEACON_UPDATE">Beacon Updates</option>
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-600">View:</span>
          <div className="flex rounded-lg border border-gray-300 overflow-hidden">
            <button
              onClick={() => setViewMode('compact')}
              className={`px-3 py-2 text-sm font-medium ${
                viewMode === 'compact' 
                  ? 'bg-primary-600 text-white' 
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Compact
            </button>
            <button
              onClick={() => setViewMode('detailed')}
              className={`px-3 py-2 text-sm font-medium ${
                viewMode === 'detailed' 
                  ? 'bg-primary-600 text-white' 
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Detailed
            </button>
          </div>
        </div>
      </div>

      {/* Logs Display */}
      <div className="card">
        {filteredLogs.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            {searchTerm || filterEventType !== 'all' ? (
              <>
                <Search className="h-12 w-12 mx-auto mb-4" />
                <p>No logs found matching your filters</p>
                <p className="text-sm mt-2">Try adjusting your search criteria</p>
              </>
            ) : (
              <>
                <Database className="h-12 w-12 mx-auto mb-4" />
                <p>No activity logs recorded</p>
                <p className="text-sm mt-2">System activity will appear here</p>
              </>
            )}
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {filteredLogs.map((log, index) => (
              <div key={log.id} className={`p-4 ${viewMode === 'detailed' ? 'p-6' : ''}`}>
                {viewMode === 'compact' ? (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      <div className="flex-shrink-0">
                        {getEventTypeIcon(log.eventType)}
                      </div>
                      <div className="flex-shrink-0">
                        <span className={`
                          inline-flex items-center px-2 py-1 rounded-full text-xs font-medium
                          ${getEventTypeColor(log.eventType)}
                        `}>
                          {log.eventType}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 truncate">{log.details}</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-4 text-sm text-gray-500">
                      {log.roomNumber && (
                        <div className="flex items-center space-x-1">
                          <MapPin className="h-3 w-3" />
                          <span>{log.roomNumber}</span>
                        </div>
                      )}
                      <div className="flex items-center space-x-1">
                        <Clock className="h-3 w-3" />
                        <span>{formatTimestamp(log.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="flex-shrink-0">
                          {getEventTypeIcon(log.eventType)}
                        </div>
                        <span className={`
                          inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
                          ${getEventTypeColor(log.eventType)}
                        `}>
                          {log.eventType}
                        </span>
                        <span className="text-sm text-gray-500">
                          {formatTimeAgo(log.timestamp)}
                        </span>
                      </div>
                      <span className="text-xs text-gray-400">
                        #{index + 1}
                      </span>
                    </div>

                    <div className="bg-gray-50 rounded-lg p-3">
                      <p className="text-gray-900 font-medium">{log.details}</p>
                    </div>

                    <div className="flex items-center space-x-6 text-xs text-gray-500">
                      <div>
                        <span className="font-medium">Timestamp:</span>{' '}
                        {formatFullDate(log.timestamp)}
                      </div>
                      {log.roomNumber && (
                        <div>
                          <span className="font-medium">Room:</span>{' '}
                          {log.roomNumber}
                        </div>
                      )}
                      {log.macAddress && (
                        <div>
                          <span className="font-medium">MAC:</span>{' '}
                          <code className="font-mono">{log.macAddress}</code>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
        <div className="card p-4">
          <div className="text-2xl font-bold text-gray-900">{logs.length}</div>
          <div className="text-sm text-gray-500">Total Logs</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-blue-600">
            {logs.filter(l => l.eventType === 'MQTT_MSG').length}
          </div>
          <div className="text-sm text-gray-500">MQTT Messages</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-red-600">
            {logs.filter(l => l.eventType === 'ALERT').length}
          </div>
          <div className="text-sm text-gray-500">Alerts</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-green-600">
            {logs.filter(l => l.eventType === 'SYSTEM').length}
          </div>
          <div className="text-sm text-gray-500">System Events</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-purple-600">
            {logs.filter(l => l.eventType === 'REGISTRATION').length}
          </div>
          <div className="text-sm text-gray-500">Registrations</div>
        </div>
      </div>
    </div>
  );
};

export default ActivityLogs;