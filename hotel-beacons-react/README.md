# Hotel Beacon Management System - React Demo Component

A modern React-based demo component that replicates the functionality of the Hotel Beacon Management System originally built in Python/Tkinter. This component provides a complete web-based interface for managing and monitoring Bluetooth beacons in a hotel environment.

## 🚀 Features

### Dashboard
- **Real-time Statistics**: Overview of total, active, low battery, and offline beacons
- **Active Beacon Monitoring**: Live view of beacons seen in the last 5 minutes
- **Recent Activity Feed**: Latest system events and beacon updates
- **Connection Status**: AWS IoT connectivity indicator

### Beacon Management
- **Add/Edit/Delete Beacons**: Complete CRUD operations for beacon registration
- **Room Mapping**: Associate beacons with hotel room numbers
- **Search and Filter**: Find beacons by room, MAC address, or description
- **Status Monitoring**: Real-time signal strength, battery level, and distance tracking

### Alarm History
- **Alert Management**: View and acknowledge system alerts
- **Severity Filtering**: Filter by critical, high, medium, or low priority
- **Status Tracking**: Acknowledged vs unacknowledged alerts
- **Detailed Information**: Full alert context and timestamps

### Activity Logs
- **System Events**: Complete log of all system activities
- **MQTT Messages**: Real-time message tracking
- **Export Functionality**: Download logs as CSV files
- **Multiple View Modes**: Compact and detailed log views

### Settings
- **AWS IoT Configuration**: Endpoint and client ID management
- **Refresh Settings**: Configurable auto-refresh intervals
- **Connection Testing**: Test and manage AWS connectivity
- **Demo Mode Indicators**: Clear indication of simulated data

## 🛠️ Technology Stack

- **React 18** with TypeScript
- **Tailwind CSS** for styling
- **Lucide React** for icons
- **Vite** for build tooling
- **date-fns** for date formatting

## 📦 Installation

```bash
# Clone or download the project
cd hotel-beacons-react

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## 🎯 Demo Data

The component uses comprehensive mock data to simulate real beacon activity:

- **5 Sample Beacons** with different statuses and battery levels
- **Real-time Updates** simulating actual beacon communication
- **Activity Logs** showing system events and MQTT messages
- **Alarm History** with various severity levels
- **Simulated AWS Connection** status changes

## 🔧 Configuration

The component is fully self-contained and doesn't require external services. All data is simulated and updates automatically to demonstrate real-time functionality.

### Mock Data Features:
- Battery level degradation over time
- Signal strength variations
- Random beacon activity simulation
- Automatic generation of activity logs
- Connection status changes

## 🎨 Design Features

### Modern UI/UX
- **Responsive Design**: Works on desktop and mobile devices
- **Clean Interface**: Professional hotel management aesthetic
- **Color-coded Status**: Intuitive visual indicators
- **Accessibility**: Proper contrast and keyboard navigation

### Real-time Updates
- **Live Data Refresh**: Configurable auto-refresh intervals
- **Status Indicators**: Real-time connection and beacon status
- **Activity Streaming**: Continuous activity log updates

## 📱 Responsive Design

The component is fully responsive and optimized for:
- **Desktop**: Full-featured admin interface
- **Tablet**: Optimized layout with collapsible panels
- **Mobile**: Touch-friendly interface with stacked navigation

## 🔌 Integration

This component is designed to be easily integrated into existing websites:

```tsx
import App from './hotel-beacons-react/src/App';

function MyWebsite() {
  return (
    <div>
      <h1>My Hotel Management System</h1>
      <App />
    </div>
  );
}
```

## 🎭 Demo vs Production

This is a **demonstration component** with simulated data. For production use:

1. Replace mock data with real API calls
2. Implement actual AWS IoT SDK integration
3. Add authentication and authorization
4. Connect to real beacon hardware
5. Implement data persistence
6. Add proper error handling and logging

## 📊 Simulated Features

The demo accurately simulates:
- **Beacon Signal Strength**: RSSI values and distance calculations
- **Battery Monitoring**: Degrading battery levels and charging status
- **Device Modes**: Normal, Low Power, High Performance, Critical
- **Alert Generation**: Low battery, disconnection, and maintenance alerts
- **Real-time Communication**: MQTT message simulation
- **System Events**: Connection status, registrations, updates

## 🚦 Status Indicators

- **Green**: Active beacons (seen in last 5 minutes)
- **Red**: Offline or critical status beacons
- **Yellow**: Low battery or maintenance required
- **Blue**: Information and normal operations

## 📈 Performance

- **Optimized Rendering**: Efficient React component updates
- **Minimal Bundle Size**: Tree-shaken dependencies
- **Fast Development**: Hot module replacement with Vite
- **TypeScript Safety**: Full type coverage for reliability

## 🤝 Contributing

This is a demo component, but suggestions for improvements are welcome:

1. UI/UX enhancements
2. Additional mock data scenarios
3. Performance optimizations
4. Accessibility improvements

## 📄 License

MIT License - Feel free to use this demo component in your projects.

## 🎯 Use Cases

Perfect for:
- **Sales Demonstrations**: Show potential clients the system capabilities
- **Development Planning**: Prototype interface before backend development
- **User Testing**: Gather feedback on interface design
- **Training**: Familiarize staff with the system interface
- **Portfolio**: Demonstrate React development skills

---

**Note**: This is a demonstration component with simulated data. All beacon activity, AWS connections, and MQTT messages are generated for demo purposes only.