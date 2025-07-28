# Hotel Beacon Management System - Demo Guide

## Quick Start

```bash
cd hotel-beacons-react
npm install
npm run dev
```

Then open http://localhost:3000 in your browser.

## What to Explore

### 1. Dashboard Tab
- **Statistics Cards**: See total beacons, active beacons, low battery alerts
- **Active Beacons Panel**: Real-time beacon status with signal strength and battery
- **Recent Activity**: Live feed of system events and MQTT messages
- **System Status**: AWS IoT connection indicator

### 2. Beacon Management Tab
- **Add New Beacon**: Click "Add Beacon" and use the random MAC generator
- **Search Function**: Try searching for room numbers like "87", "6h", or "101"
- **Edit Beacons**: Click the edit icon to modify room numbers or descriptions
- **Status Indicators**: Green dots for active beacons, red for offline

### 3. Alarm History Tab
- **Unacknowledged Alerts**: Notice the red badge in the navigation
- **Acknowledge Alerts**: Click "Acknowledge" on pending alerts
- **Filter by Severity**: Use dropdown to filter by critical, high, medium, low
- **Search Alerts**: Search by room number or alert message

### 4. Activity Logs Tab
- **Real-time Updates**: Watch new logs appear automatically
- **Event Type Filtering**: Filter by System, MQTT, Alerts, etc.
- **View Modes**: Switch between Compact and Detailed views
- **Export Function**: Download logs as CSV files

### 5. Settings Tab
- **Connection Toggle**: Connect/disconnect from AWS IoT (simulated)
- **Auto-refresh Settings**: Enable/disable real-time updates
- **Interval Configuration**: Change refresh rates
- **Demo Mode Info**: Clear indication this is simulated data

## Interactive Features to Try

1. **Watch Real-time Updates**: Leave the dashboard open and watch beacon data change
2. **Add Multiple Beacons**: Create several beacons with different room numbers
3. **Acknowledge All Alerts**: Clear the notification badge by acknowledging alerts
4. **Test Connection**: Use the settings to simulate connection changes
5. **Search Everything**: Try searching across different sections
6. **Export Data**: Download activity logs to see the CSV export function

## Responsive Design

- **Desktop**: Full interface with all features
- **Tablet**: Try resizing your browser window to see mobile layouts
- **Mobile**: All functionality works on small screens

## Simulated Behavior

The demo includes realistic simulations of:
- Battery levels decreasing over time
- Signal strength fluctuations
- New beacon discoveries
- Connection status changes
- Alert generation
- MQTT message traffic

## Integration Example

To use this component in your own website:

```tsx
import HotelBeacons from './hotel-beacons-react/src/App';

function MyApp() {
  return (
    <div>
      {/* Your existing content */}
      <section id="beacon-demo">
        <HotelBeacons />
      </section>
    </div>
  );
}
```

## Notes

- All data is simulated - no real beacons or AWS services required
- Perfect for demonstrations, prototyping, and user feedback
- Component is fully self-contained and production-ready for demo purposes
- Real-time updates happen automatically to showcase live functionality