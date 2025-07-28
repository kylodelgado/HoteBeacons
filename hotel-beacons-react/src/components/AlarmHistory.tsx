import React, { useState } from 'react';
import { 
  AlertTriangle, 
  Search, 
  Check, 
  Trash2, 
  Clock, 
  MapPin,
  Filter
} from 'lucide-react';
import { AlarmHistory as AlarmType } from '../types';
import { 
  formatFullDate, 
  formatTimeAgo,
  getSeverityColor
} from '../utils';

interface AlarmHistoryProps {
  alarms: AlarmType[];
  onAcknowledge: (alarmId: string) => void;
  onClear: () => void;
  onRefresh: () => void;
  isLoading: boolean;
}

const AlarmHistory: React.FC<AlarmHistoryProps> = ({
  alarms,
  onAcknowledge,
  onClear,
  onRefresh: _onRefresh,
  isLoading: _isLoading,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const filteredAlarms = alarms.filter(alarm => {
    const matchesSearch = 
      alarm.roomNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alarm.macAddress.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alarm.message.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesSeverity = filterSeverity === 'all' || alarm.severity === filterSeverity;
    const matchesStatus = 
      filterStatus === 'all' || 
      (filterStatus === 'acknowledged' && alarm.acknowledged) ||
      (filterStatus === 'unacknowledged' && !alarm.acknowledged);

    return matchesSearch && matchesSeverity && matchesStatus;
  });

  const unacknowledgedCount = alarms.filter(alarm => !alarm.acknowledged).length;

  const getSeverityIcon = (severity: string) => {
    const iconClass = "h-4 w-4";
    switch (severity) {
      case 'critical':
        return <AlertTriangle className={`${iconClass} text-red-600`} />;
      case 'high':
        return <AlertTriangle className={`${iconClass} text-orange-600`} />;
      case 'medium':
        return <AlertTriangle className={`${iconClass} text-yellow-600`} />;
      case 'low':
        return <AlertTriangle className={`${iconClass} text-blue-600`} />;
      default:
        return <AlertTriangle className={`${iconClass} text-gray-600`} />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Alarm History</h2>
          <p className="text-sm text-gray-500 mt-1">
            View and manage system alerts and notifications
          </p>
          {unacknowledgedCount > 0 && (
            <div className="flex items-center mt-2">
              <AlertTriangle className="h-4 w-4 text-red-600 mr-1" />
              <span className="text-sm text-red-600 font-medium">
                {unacknowledgedCount} unacknowledged alert{unacknowledgedCount !== 1 ? 's' : ''}
              </span>
            </div>
          )}
        </div>
        <div className="flex space-x-2 mt-4 sm:mt-0">
          <button
            onClick={onClear}
            disabled={alarms.length === 0}
            className="btn btn-danger flex items-center"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Clear All
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search alarms..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input pl-10"
          />
        </div>
        
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <select
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
            className="input pl-10"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <div className="relative">
          <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="input pl-10"
          >
            <option value="all">All Status</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="unacknowledged">Unacknowledged</option>
          </select>
        </div>
      </div>

      {/* Alarms List */}
      <div className="space-y-4">
        {filteredAlarms.length === 0 ? (
          <div className="card p-12">
            <div className="text-center text-gray-400">
              {searchTerm || filterSeverity !== 'all' || filterStatus !== 'all' ? (
                <>
                  <Search className="h-12 w-12 mx-auto mb-4" />
                  <p>No alarms found matching your filters</p>
                  <p className="text-sm mt-2">Try adjusting your search criteria</p>
                </>
              ) : (
                <>
                  <AlertTriangle className="h-12 w-12 mx-auto mb-4" />
                  <p>No alarms recorded</p>
                  <p className="text-sm mt-2">System alerts will appear here</p>
                </>
              )}
            </div>
          </div>
        ) : (
          filteredAlarms.map((alarm) => (
            <div
              key={alarm.id}
              className={`card p-6 border-l-4 ${
                alarm.acknowledged ? 'opacity-75' : ''
              } ${
                alarm.severity === 'critical' ? 'border-l-red-500' :
                alarm.severity === 'high' ? 'border-l-orange-500' :
                alarm.severity === 'medium' ? 'border-l-yellow-500' :
                alarm.severity === 'low' ? 'border-l-blue-500' :
                'border-l-gray-500'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    {getSeverityIcon(alarm.severity)}
                    <span className={`
                      inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border
                      ${getSeverityColor(alarm.severity)}
                    `}>
                      {alarm.severity.toUpperCase()}
                    </span>
                    <span className={`
                      inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
                      ${alarm.acknowledged 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-gray-100 text-gray-800'
                      }
                    `}>
                      {alarm.acknowledged ? 'Acknowledged' : 'Pending'}
                    </span>
                    <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      {alarm.alertType.replace('_', ' ')}
                    </span>
                  </div>

                  <div className="flex items-center space-x-4 mb-3">
                    <div className="flex items-center space-x-1">
                      <MapPin className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">
                        Room {alarm.roomNumber}
                      </span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Clock className="h-4 w-4 text-gray-400" />
                      <span className="text-sm text-gray-500">
                        {formatTimeAgo(alarm.timestamp)}
                      </span>
                    </div>
                  </div>

                  <p className="text-gray-900 mb-2">{alarm.message}</p>
                  
                  <div className="text-xs text-gray-500 space-y-1">
                    <p>MAC: <code className="font-mono">{alarm.macAddress}</code></p>
                    <p>Time: {formatFullDate(alarm.timestamp)}</p>
                  </div>
                </div>

                <div className="flex items-center space-x-2 ml-4">
                  {!alarm.acknowledged && (
                    <button
                      onClick={() => onAcknowledge(alarm.id)}
                      className="btn btn-success flex items-center"
                      title="Acknowledge alarm"
                    >
                      <Check className="h-4 w-4 mr-1" />
                      Acknowledge
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-2xl font-bold text-gray-900">{alarms.length}</div>
          <div className="text-sm text-gray-500">Total Alarms</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-red-600">
            {alarms.filter(a => !a.acknowledged).length}
          </div>
          <div className="text-sm text-gray-500">Unacknowledged</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-orange-600">
            {alarms.filter(a => a.severity === 'critical' || a.severity === 'high').length}
          </div>
          <div className="text-sm text-gray-500">High Priority</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-bold text-green-600">
            {alarms.filter(a => a.acknowledged).length}
          </div>
          <div className="text-sm text-gray-500">Resolved</div>
        </div>
      </div>
    </div>
  );
};

export default AlarmHistory;