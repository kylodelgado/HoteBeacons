#!/usr/bin/env python3
import json
import base64
import time
import argparse
import threading
import os
import sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog
import sqlite3

# Import AWS IoT SDK
try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder

    AWS_IOT_AVAILABLE = True
except ImportError:
    AWS_IOT_AVAILABLE = False
    print("Warning: AWS IoT SDK not found. Install with 'pip install awsiotsdk' for LoRa connectivity.")

# Application constants
APP_TITLE = "Enhanced Hotel LoRa Beacon Management System"
DB_NAME = "hotel_beacons.db"
LOG_DIR = "logs"
ADMIN_PASSWORD = "admin123"  # Simple password for demo purposes

# Default AWS IoT Core settings
DEFAULT_ENDPOINT = "a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com"
DEFAULT_CERT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "MikeTheMexican 2")
DEFAULT_CLIENT_ID = "hotel-beacon-client"
DEFAULT_TOPIC = "#"

# Room mapping and history files
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "hotel_beacon_config")
room_mapping_file = os.path.join(CONFIG_DIR, "room_mapping.json")
alarm_history_file = os.path.join(CONFIG_DIR, "alarm_history.json")
settings_file = os.path.join(CONFIG_DIR, "settings.json")

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# Default settings
DEFAULT_SETTINGS = {
    "aws_endpoint": DEFAULT_ENDPOINT,
    "cert_file": os.path.join(DEFAULT_CERT_DIR, "certificate.pem.crt"),
    "key_file": os.path.join(DEFAULT_CERT_DIR, "private.pem.key"),
    "root_ca": os.path.join(DEFAULT_CERT_DIR, "AmazonRootCA1.pem"),
    "client_id": DEFAULT_CLIENT_ID,
    "topic": DEFAULT_TOPIC,
    "alert_interval": 15,  # seconds between alerts
    "port": 8883,
    "scan_interval": 5  # seconds between scans
}


class BeaconDatabase:
    """Database manager for storing beacon information"""

    def __init__(self, db_path=DB_NAME):
        """Initialize the database connection"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.init_db()

    def init_db(self):
        """Create database and tables if they don't exist"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()

            # Create beacons table with expanded fields
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS beacons (
                id INTEGER PRIMARY KEY,
                mac_address TEXT NOT NULL UNIQUE,
                room_number TEXT NOT NULL,
                description TEXT,
                last_seen TEXT,
                last_rssi INTEGER,
                battery_level TEXT,
                device_mode TEXT,
                auxiliary_operation TEXT,
                estimated_distance REAL,
                is_charging BOOLEAN,
                created_at TEXT
            )
            ''')

            # Create activity log table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                beacon_id INTEGER,
                event_type TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (beacon_id) REFERENCES beacons (id)
            )
            ''')

            self.conn.commit()
            print("Database initialized successfully")
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def add_beacon(self, mac_address, room_number, description=""):
        """Add a new beacon to the database"""
        try:
            current_time = datetime.now().isoformat()
            self.cursor.execute(
                "INSERT INTO beacons (mac_address, room_number, description, created_at) VALUES (?, ?, ?, ?)",
                (mac_address, room_number, description, current_time)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # MAC address already exists
            return False
        except sqlite3.Error as e:
            print(f"Error adding beacon: {e}")
            return False

    def update_beacon(self, beacon_id, room_number=None, description=None):
        """Update beacon information"""
        try:
            if room_number and description:
                self.cursor.execute(
                    "UPDATE beacons SET room_number = ?, description = ? WHERE id = ?",
                    (room_number, description, beacon_id)
                )
            elif room_number:
                self.cursor.execute(
                    "UPDATE beacons SET room_number = ? WHERE id = ?",
                    (room_number, beacon_id)
                )
            elif description:
                self.cursor.execute(
                    "UPDATE beacons SET description = ? WHERE id = ?",
                    (description, beacon_id)
                )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error updating beacon: {e}")
            return False

    def delete_beacon(self, beacon_id):
        """Delete a beacon from the database"""
        try:
            self.cursor.execute("DELETE FROM beacons WHERE id = ?", (beacon_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error deleting beacon: {e}")
            return False

    def get_all_beacons(self):
        """Get all beacons from the database"""
        try:
            self.cursor.execute("SELECT * FROM beacons ORDER BY room_number")
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting beacons: {e}")
            return []

    def get_beacon_by_mac(self, mac_address):
        """Get a beacon by MAC address"""
        try:
            self.cursor.execute("SELECT * FROM beacons WHERE mac_address = ?", (mac_address,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error getting beacon: {e}")
            return None

    def get_beacon_by_id(self, beacon_id):
        """Get a beacon by ID"""
        try:
            self.cursor.execute("SELECT * FROM beacons WHERE id = ?", (beacon_id,))
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error getting beacon: {e}")
            return None

    def update_beacon_signal(self, mac_address, rssi, battery_level=None, is_charging=None,
                             device_mode=None, auxiliary_operation=None, estimated_distance=None):
        """Update beacon's last seen time and all signal information"""
        try:
            current_time = datetime.now().isoformat()

            # Start with basic update fields
            update_fields = ["last_seen = ?", "last_rssi = ?"]
            params = [current_time, rssi]

            # Add optional fields if provided
            if battery_level is not None:
                update_fields.append("battery_level = ?")
                params.append(battery_level)

            if is_charging is not None:
                update_fields.append("is_charging = ?")
                params.append(is_charging)

            if device_mode is not None:
                update_fields.append("device_mode = ?")
                params.append(device_mode)

            if auxiliary_operation is not None:
                update_fields.append("auxiliary_operation = ?")
                params.append(auxiliary_operation)

            if estimated_distance is not None:
                update_fields.append("estimated_distance = ?")
                params.append(estimated_distance)

            # Add MAC address as the last parameter
            params.append(mac_address)

            # Build and execute query
            query = f"UPDATE beacons SET {', '.join(update_fields)} WHERE mac_address = ?"
            self.cursor.execute(query, params)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error updating beacon signal: {e}")
            return False

    def log_activity(self, event_type, details, beacon_id=None):
        """Log beacon-related activity"""
        try:
            current_time = datetime.now().isoformat()
            self.cursor.execute(
                "INSERT INTO activity_log (timestamp, beacon_id, event_type, details) VALUES (?, ?, ?, ?)",
                (current_time, beacon_id, event_type, details)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error logging activity: {e}")
            return False

    def get_recent_logs(self, limit=100):
        """Get recent activity logs"""
        try:
            self.cursor.execute("""
                SELECT l.timestamp, b.room_number, b.mac_address, l.event_type, l.details 
                FROM activity_log l 
                LEFT JOIN beacons b ON l.beacon_id = b.id 
                ORDER BY l.timestamp DESC 
                LIMIT ?
            """, (limit,))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting logs: {e}")
            return []

    def export_room_mapping_data(self):
        """Export room mapping data to a dictionary"""
        try:
            # We'll export only essential fields for room mapping
            self.cursor.execute("""
                SELECT mac_address, room_number, description 
                FROM beacons
                ORDER BY room_number
            """)
            rows = self.cursor.fetchall()

            # Create a list of beacon mappings
            beacons = []
            for row in rows:
                beacon = {
                    "mac_address": row[0],
                    "room_number": row[1],
                    "description": row[2] or ""
                }
                beacons.append(beacon)

            # Create the export dictionary
            export_data = {
                "version": "1.0",
                "export_date": datetime.now().isoformat(),
                "beacons": beacons
            }

            return export_data
        except sqlite3.Error as e:
            print(f"Error exporting room mapping: {e}")
            return None

    def import_room_mapping_data(self, mapping_data):
        """Import room mapping data from a dictionary"""
        try:
            # Start a transaction
            self.conn.execute("BEGIN TRANSACTION")

            # Process each beacon in the import data
            import_count = 0
            update_count = 0

            for beacon in mapping_data.get("beacons", []):
                mac_address = beacon.get("mac_address")
                room_number = beacon.get("room_number")
                description = beacon.get("description", "")

                if not mac_address or not room_number:
                    continue

                # Check if beacon already exists
                existing = self.get_beacon_by_mac(mac_address)

                if existing:
                    # Update existing beacon
                    self.cursor.execute(
                        "UPDATE beacons SET room_number = ?, description = ? WHERE mac_address = ?",
                        (room_number, description, mac_address)
                    )
                    update_count += 1
                else:
                    # Add new beacon
                    current_time = datetime.now().isoformat()
                    self.cursor.execute(
                        "INSERT INTO beacons (mac_address, room_number, description, created_at) VALUES (?, ?, ?, ?)",
                        (mac_address, room_number, description, current_time)
                    )
                    import_count += 1

            # Commit the transaction
            self.conn.commit()

            return {
                "imported": import_count,
                "updated": update_count
            }
        except sqlite3.Error as e:
            # Rollback in case of error
            self.conn.rollback()
            print(f"Error importing room mapping: {e}")
            return None

    def clear_all_beacons(self):
        """Clear all beacons from the database - use with caution!"""
        try:
            self.cursor.execute("DELETE FROM beacons")
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error clearing beacons: {e}")
            return False

    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()


class SettingsManager:
    """Manages application settings"""

    def __init__(self, settings_file=settings_file):
        """Initialize settings manager"""
        self.settings_file = settings_file
        self.settings = DEFAULT_SETTINGS.copy()
        self.load_settings()

    def load_settings(self):
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    # Update settings with loaded values
                    self.settings.update(loaded_settings)
            except json.JSONDecodeError:
                print("Error: Settings file is corrupted. Using defaults.")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Save default settings
            self.save_settings()

    def save_settings(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """Set a setting value"""
        self.settings[key] = value
        self.save_settings()


class LoRaClient:
    """Handles communication with AWS IoT Core for LoRaWAN"""

    def __init__(self, settings, message_callback=None):
        """Initialize the LoRa client"""
        self.settings = settings
        self.message_callback = message_callback
        self.mqtt_connection = None
        self.connected = False
        self.beacons = {}  # Store detected beacons

    def connect(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            print("AWS IoT SDK not available. Cannot connect.")
            return False

        try:
            # Set up connection to AWS IoT Core
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.settings.get("aws_endpoint"),
                cert_filepath=self.settings.get("cert_file"),
                pri_key_filepath=self.settings.get("key_file"),
                client_bootstrap=client_bootstrap,
                ca_filepath=self.settings.get("root_ca"),
                client_id=self.settings.get("client_id"),
                on_connection_interrupted=self._on_connection_interrupted,
                on_connection_resumed=self._on_connection_resumed,
                clean_session=False,
                keep_alive_secs=30
            )

            print(
                f"Connecting to {self.settings.get('aws_endpoint')} with client ID '{self.settings.get('client_id')}'...")
            connect_future = self.mqtt_connection.connect()

            # Wait for connection to complete
            connect_future.result()
            self._on_connection_success(self.mqtt_connection, None)
            self.connected = True
            return True
        except Exception as e:
            print(f"Error connecting to AWS IoT: {e}")
            return False

    def disconnect(self):
        """Disconnect from AWS IoT Core"""
        if self.mqtt_connection and self.connected:
            try:
                disconnect_future = self.mqtt_connection.disconnect()
                disconnect_future.result()
                self.connected = False
                print("Disconnected from AWS IoT Core")
                return True
            except Exception as e:
                print(f"Error disconnecting: {e}")
                return False
        return True

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """Handle connection interruption"""
        print(f"Connection interrupted. error: {error}")
        self.connected = False

    def _on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """Handle connection resumption"""
        print(f"Connection resumed. return_code: {return_code} session_present: {session_present}")
        self.connected = True

    def _on_connection_success(self, connection, callback_data):
        """Handle successful connection"""
        print("Connection established!")
        print(f"Subscribing to topic: {self.settings.get('topic')}")
        connection.subscribe(
            topic=self.settings.get('topic'),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=self._on_message_received
        )

    def _on_message_received(self, topic, payload, dup, qos, retain, **kwargs):
        """Handle message received from AWS IoT Core"""
        try:
            # Parse JSON message
            message = json.loads(payload.decode())

            # Get FPort for filtering
            fport = None
            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                fport = message["WirelessMetadata"]["LoRaWAN"].get("FPort")

            # Process payload if available
            if "PayloadData" in message:
                payload_data = message["PayloadData"]

                # Call the message callback with the decoded data
                if self.message_callback:
                    self.message_callback(topic, message, self._decode_lw004_pb_payload(payload_data, fport))
        except Exception as e:
            print(f"Error processing message: {str(e)}")

    def _decode_lw004_pb_payload(self, payload_data, fport):
        """
        Enhanced decoder for LW004-PB payload from Base64 encoded string
        """
        # Decode Base64 payload
        try:
            binary_data = base64.b64decode(payload_data)
        except:
            return {"error": "Invalid Base64 payload"}

        # Create result dictionary
        result = {
            "raw_hex": binary_data.hex()
        }

        # Check if we have enough data to parse
        if len(binary_data) < 4:
            return {"error": "Payload too short", "raw_hex": binary_data.hex()}

        # Extract battery level from first byte (7 bits, ignore MSB which is charging flag)
        battery_level = binary_data[0] & 0x7F
        is_charging = (binary_data[0] & 0x80) > 0
        result["battery"] = f"{battery_level}%"
        result["battery_level"] = battery_level
        result["is_charging"] = is_charging

        # Extract device status from second byte
        device_status = binary_data[1]
        device_mode = (device_status >> 4) & 0x0F
        auxiliary_op = device_status & 0x0F

        # Map to human-readable values
        device_modes = {
            1: "Standby Mode",
            2: "Timing Mode",
            3: "Periodic Mode",
            4: "Stationary in Motion Mode",
            5: "Start of Movement",
            6: "In Movement",
            7: "End of Movement"
        }
        aux_operations = {
            0: "None",
            1: "Downlink for Position",
            2: "Man Down Status",
            3: "Alert Alarm",
            4: "SOS Alarm"
        }

        result["device_mode"] = device_modes.get(device_mode, f"Unknown ({device_mode})")
        result["auxiliary_operation"] = aux_operations.get(auxiliary_op, f"Unknown ({auxiliary_op})")

        # Extract age from bytes 2-3
        age = int.from_bytes(binary_data[2:4], byteorder='big')
        result["age"] = f"{age} seconds"

        # Port-specific processing
        if fport in [8, 12]:  # Bluetooth Location Fixed Payload
            # Create a list to store beacon information
            beacons = []

            # Process each beacon (7 bytes each: 6 for MAC + 1 for RSSI)
            offset = 4  # Start at byte 4 (after header)

            # Loop to extract up to 3 beacons or until we reach the end of the payload
            beacon_count = 0
            while offset + 7 <= len(binary_data) and beacon_count < 3:
                # Extract MAC address (6 bytes)
                mac_bytes = binary_data[offset:offset + 6]
                mac_address = ':'.join(f'{b:02X}' for b in mac_bytes)

                # Extract RSSI (1 byte)
                rssi_byte = binary_data[offset + 6]
                rssi = rssi_byte - 256 if rssi_byte > 127 else rssi_byte

                # Calculate distance using path loss model
                est_distance = self.estimate_distance(rssi)

                # Add beacon info to the list
                beacons.append({
                    "mac": mac_address,
                    "rssi": f"{rssi} dBm",
                    "rssi_value": rssi,  # Raw value for distance calculation
                    "estimated_distance": est_distance
                })

                # Move to next beacon
                offset += 7
                beacon_count += 1

            # Add beacons to result
            result["beacons"] = beacons
            result["beacon_count"] = len(beacons)

        elif fport in [9, 13]:  # Bluetooth Location Failure Payload
            if len(binary_data) >= 5:
                failure_code = binary_data[4]
                failure_reasons = {
                    1: "Hardware Error",
                    2: "Interrupted by Downlink for Position",
                    3: "Interrupted by Man Down Detection",
                    4: "Interrupted by Alarm function",
                    5: "Bluetooth positioning timeout",
                    6: "Bluetooth broadcasting in progress",
                    7: "Interrupted positioning at end of movement",
                    8: "Interrupted positioning at start of movement",
                    9: "GPS PDOP Limit",
                    10: "Other reason"
                }
                result["failure_reason"] = failure_reasons.get(failure_code, f"Unknown ({failure_code})")

        elif fport == 1:  # Event Message Payload
            if len(binary_data) >= 7:
                # Extract time zone and timestamp
                time_zone = binary_data[2]
                time_zone_value = time_zone / 2 if time_zone <= 127 else (time_zone - 256) / 2
                result["time_zone"] = f"UTC{'+' if time_zone_value >= 0 else ''}{time_zone_value}"

                timestamp = int.from_bytes(binary_data[3:7], byteorder='big')
                result["timestamp"] = timestamp

                # Extract event type if present
                if len(binary_data) >= 8:
                    event_code = binary_data[7]
                    event_types = {
                        0: "Start of movement",
                        1: "In movement",
                        2: "End of movement",
                        3: "Start SOS alarm",
                        4: "SOS alarm exit",
                        5: "Start Alert alarm",
                        6: "Alert alarm exit",
                        7: "Man Down start",
                        8: "Man Down end"
                    }
                    result["event_type"] = event_types.get(event_code, f"Unknown ({event_code})")

        return result

    def estimate_distance(self, rssi, measured_power=-65, n=2.5):
        """
        Estimate distance based on RSSI value using path loss model
        rssi: Received signal strength in dBm
        measured_power: RSSI at 1 meter distance (calibration value)
        n: Environmental factor (2 for free space, 2.5-4 for indoor)
        """
        try:
            # Extract RSSI numeric value if it's in string format
            if isinstance(rssi, str) and "dBm" in rssi:
                rssi = int(rssi.split()[0])

            # Calculate distance using path loss formula
            ratio = (measured_power - rssi) / (10 * n)
            distance = pow(10, ratio)
            return round(distance, 2)
        except Exception as e:
            return None


class BeaconApp:
    """Enhanced Hotel LoRa Beacon Management System GUI Application"""

    def __init__(self, root):
        """Initialize the application"""
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1000x700")

        # Initialize components
        self.settings = SettingsManager()
        self.db = BeaconDatabase()
        self.client = None
        self.connected = False
        self.current_beacons = {}  # Store active beacons for quick reference

        # Create UI
        self.create_ui()

        # Log application start
        self.db.log_activity("SYSTEM", "Application started")

    def create_ui(self):
        """Create the user interface"""
        # Set up clipboard operations
        self.clipboard_mac = ""

        # Create main notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs
        self.dashboard_frame = ttk.Frame(self.notebook)
        self.beacons_frame = ttk.Frame(self.notebook)
        self.logs_frame = ttk.Frame(self.notebook)
        self.settings_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_frame, text="Dashboard")
        self.notebook.add(self.beacons_frame, text="Beacons")
        self.notebook.add(self.logs_frame, text="Logs")
        self.notebook.add(self.settings_frame, text="Settings")

        # Setup each tab
        self.setup_dashboard()
        self.setup_beacons_tab()
        self.setup_logs_tab()
        self.setup_settings_tab()

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Not Connected")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Add keyboard shortcuts globally
        self.root.bind("<Control-n>", lambda e: self.add_beacon_dialog(self.clipboard_mac))
        self.root.bind("<Control-r>", lambda e: self.register_unknown_beacon())

    def setup_dashboard(self):
        """Setup enhanced dashboard tab with live beacon data"""
        # Create a paned window to divide the dashboard
        self.dashboard_pane = ttk.PanedWindow(self.dashboard_frame, orient=tk.VERTICAL)
        self.dashboard_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Top frame for connection and stats
        top_frame = ttk.Frame(self.dashboard_pane)
        self.dashboard_pane.add(top_frame, weight=1)

        # Connection frame
        conn_frame = ttk.LabelFrame(top_frame, text="Connection")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)

        self.conn_status_var = tk.StringVar(value="Not Connected")
        ttk.Label(conn_frame, text="Status:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(conn_frame, textvariable=self.conn_status_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.connect_to_aws)
        self.connect_btn.grid(row=0, column=2, padx=5, pady=5)

        # Auto-refresh checkbutton
        self.auto_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(conn_frame, text="Auto-refresh display", variable=self.auto_refresh_var).grid(
            row=0, column=3, padx=5, pady=5, sticky=tk.W)

        # Stats frame
        stats_frame = ttk.LabelFrame(top_frame, text="Statistics")
        stats_frame.pack(fill=tk.X, padx=5, pady=5)

        self.beacon_count_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Registered Beacons:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(stats_frame, textvariable=self.beacon_count_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        self.active_beacons_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Active Beacons:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Label(stats_frame, textvariable=self.active_beacons_var).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        # Live Data section - split into two panels
        self.live_data_pane = ttk.PanedWindow(self.dashboard_pane, orient=tk.HORIZONTAL)
        self.dashboard_pane.add(self.live_data_pane, weight=4)

        # Active beacons panel
        active_frame = ttk.LabelFrame(self.live_data_pane, text="Active Beacons")
        self.live_data_pane.add(active_frame, weight=2)

        # Create Treeview for active beacons
        active_columns = ('mac', 'room', 'rssi', 'battery', 'distance', 'mode', 'last_seen')
        self.active_tree = ttk.Treeview(active_frame, columns=active_columns, show='headings')

        # Define column headings
        self.active_tree.heading('mac', text='MAC Address')
        self.active_tree.heading('room', text='Room')
        self.active_tree.heading('rssi', text='RSSI')
        self.active_tree.heading('battery', text='Battery')
        self.active_tree.heading('distance', text='Est. Distance')
        self.active_tree.heading('mode', text='Mode')
        self.active_tree.heading('last_seen', text='Last Seen')

        # Set column widths
        self.active_tree.column('mac', width=120)
        self.active_tree.column('room', width=60, anchor=tk.CENTER)
        self.active_tree.column('rssi', width=60, anchor=tk.CENTER)
        self.active_tree.column('battery', width=70, anchor=tk.CENTER)
        self.active_tree.column('distance', width=80, anchor=tk.CENTER)
        self.active_tree.column('mode', width=100)
        self.active_tree.column('last_seen', width=120)

        # Add a scrollbar
        active_scrollbar = ttk.Scrollbar(active_frame, orient=tk.VERTICAL, command=self.active_tree.yview)
        self.active_tree.configure(yscrollcommand=active_scrollbar.set)

        # Pack the components
        self.active_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        active_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Add right-click context menu for copying MAC addresses
        self.active_tree_menu = tk.Menu(self.active_tree, tearoff=0)
        self.active_tree_menu.add_command(label="Copy MAC Address", command=self.copy_mac_from_active)
        self.active_tree_menu.add_command(label="Register Beacon", command=self.register_from_active)

        # Bind right-click to show context menu
        self.active_tree.bind("<Button-3>", self.show_active_tree_menu)
        # Bind double-click to copy MAC address
        self.active_tree.bind("<Double-1>", self.copy_mac_from_active)

        # Recent events panel
        events_frame = ttk.LabelFrame(self.live_data_pane, text="Recent Events")
        self.live_data_pane.add(events_frame, weight=1)

        # Create scrolled text widget for events
        self.recent_events = scrolledtext.ScrolledText(events_frame, height=10)
        self.recent_events.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.recent_events.configure(state=tk.DISABLED)

        # Add right-click menu for recent events text widget
        self.recent_events_menu = tk.Menu(self.recent_events, tearoff=0)
        self.recent_events_menu.add_command(label="Copy Selected MAC Address", command=self.copy_mac_from_events)
        self.recent_events_menu.add_command(label="Register Selected MAC Address", command=self.register_from_events)

        # Bind right-click to show context menu
        self.recent_events.bind("<Button-3>", self.show_events_menu)

        # Set the divider position
        self.live_data_pane.sashpos(0, 650)

        # Beacon details panel
        details_frame = ttk.LabelFrame(self.dashboard_pane, text="Beacon Details")
        self.dashboard_pane.add(details_frame, weight=2)

        # Create a Text widget for beacon details
        self.details_text = scrolledtext.ScrolledText(details_frame, height=10)
        self.details_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.details_text.configure(state=tk.DISABLED)

        # Bind selection event on active tree to show details
        self.active_tree.bind('<<TreeviewSelect>>', self.show_beacon_details)

        # Set pane positions
        self.dashboard_pane.sashpos(0, 100)
        self.dashboard_pane.sashpos(1, 400)

        # Setup automatic refresh
        self.setup_auto_refresh()

        # Update stats
        self.update_stats()

    def setup_auto_refresh(self):
        """Setup automatic refresh of dashboard"""

        def refresh_loop():
            if self.auto_refresh_var.get():
                self.update_active_beacons()

            # Schedule next refresh
            self.root.after(2000, refresh_loop)  # Refresh every 2 seconds

        # Start the refresh loop
        self.root.after(2000, refresh_loop)

    def update_active_beacons(self):
        """Update the active beacons display"""
        # Clear the treeview
        for item in self.active_tree.get_children():
            self.active_tree.delete(item)

        # Get all beacons from the database
        beacons = self.db.get_all_beacons()

        active_count = 0
        # Add them to the treeview if they have been seen recently (last 5 minutes)
        current_time = datetime.now()
        for beacon in beacons:
            # Check if beacon has been seen
            if beacon[4]:  # last_seen field
                try:
                    last_seen_time = datetime.fromisoformat(beacon[4])
                    time_diff = (current_time - last_seen_time).total_seconds()

                    # Only show recently active beacons (last 5 minutes)
                    if time_diff <= 300:
                        active_count += 1

                        # Format last seen time
                        last_seen_str = last_seen_time.strftime("%H:%M:%S")

                        # Battery level with charging indicator
                        battery = beacon[6] or "N/A"
                        if battery != "N/A" and beacon[10]:  # is_charging
                            battery = f"{battery} ⚡"

                        # Distance
                        distance = f"{beacon[9]} m" if beacon[9] else "N/A"

                        # RSSI
                        rssi = f"{beacon[5]} dBm" if beacon[5] else "N/A"

                        # Add to treeview
                        self.active_tree.insert('', tk.END, values=(
                            beacon[1],  # MAC address
                            beacon[2],  # Room number
                            rssi,  # RSSI
                            battery,  # Battery
                            distance,  # Estimated distance
                            beacon[7] or "N/A",  # Device mode
                            last_seen_str  # Last seen
                        ))
                except (ValueError, TypeError):
                    # Skip beacons with invalid timestamps
                    pass

        # Update the active beacons count
        self.active_beacons_var.set(str(active_count))

    def show_beacon_details(self, event):
        """Show detailed information about the selected beacon"""
        selected = self.active_tree.selection()
        if not selected:
            return

        # Get the MAC address from the selected item
        mac = self.active_tree.item(selected[0], 'values')[0]

        # Get detailed beacon information from database
        beacon = self.db.get_beacon_by_mac(mac)
        if not beacon:
            return

        # Update the details text
        self.details_text.configure(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)

        # Format the beacon details
        self.details_text.insert(tk.END, f"BEACON DETAILS\n", 'heading')
        self.details_text.insert(tk.END, f"{'-' * 50}\n\n")

        self.details_text.insert(tk.END, f"MAC Address: {beacon[1]}\n")
        self.details_text.insert(tk.END, f"Room Number: {beacon[2]}\n")
        self.details_text.insert(tk.END, f"Description: {beacon[3] or 'N/A'}\n\n")

        self.details_text.insert(tk.END, f"Battery Level: {beacon[6] or 'N/A'}\n")
        self.details_text.insert(tk.END, f"Charging Status: {'Charging' if beacon[10] else 'Not Charging'}\n")
        self.details_text.insert(tk.END, f"RSSI: {beacon[5]} dBm\n")
        self.details_text.insert(tk.END, f"Estimated Distance: {beacon[9]} meters\n\n")

        self.details_text.insert(tk.END, f"Device Mode: {beacon[7] or 'N/A'}\n")
        self.details_text.insert(tk.END, f"Auxiliary Operation: {beacon[8] or 'N/A'}\n\n")

        # Format last seen time
        last_seen = "Never"
        if beacon[4]:
            try:
                dt = datetime.fromisoformat(beacon[4])
                last_seen = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                last_seen = beacon[4]

        self.details_text.insert(tk.END, f"Last Seen: {last_seen}\n")
        self.details_text.insert(tk.END, f"Created: {beacon[11] or 'N/A'}\n")

        # Apply some basic styling
        self.details_text.tag_configure('heading', font=('Helvetica', 12, 'bold'))

        self.details_text.configure(state=tk.DISABLED)

    def setup_beacons_tab(self):
        """Setup beacons management tab"""
        # Control buttons
        control_frame = ttk.Frame(self.beacons_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="Add Beacon (Ctrl+N)",
                   command=lambda: self.add_beacon_dialog(self.clipboard_mac)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Remove Beacon", command=self.remove_beacon).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Edit Beacon", command=self.edit_beacon).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Refresh", command=self.refresh_beacons).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Register Unknown (Ctrl+R)", command=self.register_unknown_beacon).pack(
            side=tk.LEFT, padx=5)

        # Data export/import buttons
        export_frame = ttk.Frame(self.beacons_frame)
        export_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(export_frame, text="Экспорт карты комнат", command=self.export_room_mapping).pack(side=tk.LEFT,
                                                                                                     padx=5)
        ttk.Button(export_frame, text="Импорт карты комнат", command=self.import_room_mapping).pack(side=tk.LEFT,
                                                                                                    padx=5)

        # Beacon list
        list_frame = ttk.Frame(self.beacons_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('id', 'mac_address', 'room_number', 'description', 'last_seen', 'last_rssi', 'battery', 'mode')
        self.beacon_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        # Define column headings
        self.beacon_tree.heading('id', text='ID')
        self.beacon_tree.heading('mac_address', text='MAC Address')
        self.beacon_tree.heading('room_number', text='Room')
        self.beacon_tree.heading('description', text='Description')
        self.beacon_tree.heading('last_seen', text='Last Seen')
        self.beacon_tree.heading('last_rssi', text='RSSI')
        self.beacon_tree.heading('battery', text='Battery')
        self.beacon_tree.heading('mode', text='Mode')

        # Set column widths
        self.beacon_tree.column('id', width=50, anchor=tk.CENTER)
        self.beacon_tree.column('mac_address', width=150)
        self.beacon_tree.column('room_number', width=80, anchor=tk.CENTER)
        self.beacon_tree.column('description', width=200)
        self.beacon_tree.column('last_seen', width=150)
        self.beacon_tree.column('last_rssi', width=80, anchor=tk.CENTER)
        self.beacon_tree.column('battery', width=80, anchor=tk.CENTER)
        self.beacon_tree.column('mode', width=120)

        # Add a scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.beacon_tree.yview)
        self.beacon_tree.configure(yscrollcommand=scrollbar.set)

        # Pack the treeview and scrollbar
        self.beacon_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Add right-click context menu for beacon list
        self.beacon_tree_menu = tk.Menu(self.beacon_tree, tearoff=0)
        self.beacon_tree_menu.add_command(label="Copy MAC Address", command=self.copy_mac_from_beacons_list)
        self.beacon_tree_menu.add_separator()
        self.beacon_tree_menu.add_command(label="Edit Beacon", command=self.edit_beacon)
        self.beacon_tree_menu.add_command(label="Remove Beacon", command=self.remove_beacon)

        # Bind right-click to show context menu
        self.beacon_tree.bind("<Button-3>", self.show_beacon_tree_menu)
        # Bind double-click to edit beacon
        self.beacon_tree.bind("<Double-1>", lambda e: self.edit_beacon())
        # Bind Ctrl+C to copy MAC address
        self.beacon_tree.bind("<Control-c>", lambda e: self.copy_mac_from_beacons_list())

        # Load beacons
        self.refresh_beacons()

    def setup_logs_tab(self):
        """Setup logs tab"""
        # Control frame
        control_frame = ttk.Frame(self.logs_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="Refresh Logs", command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Export Logs", command=self.export_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Clear Display", command=self.clear_logs_display).pack(side=tk.LEFT, padx=5)

        # Log viewer
        list_frame = ttk.Frame(self.logs_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('timestamp', 'room', 'mac', 'event', 'details')
        self.log_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        # Define column headings
        self.log_tree.heading('timestamp', text='Timestamp')
        self.log_tree.heading('room', text='Room')
        self.log_tree.heading('mac', text='MAC Address')
        self.log_tree.heading('event', text='Event')
        self.log_tree.heading('details', text='Details')

        # Set column widths
        self.log_tree.column('timestamp', width=150)
        self.log_tree.column('room', width=80, anchor=tk.CENTER)
        self.log_tree.column('mac', width=150)
        self.log_tree.column('event', width=100)
        self.log_tree.column('details', width=250)

        # Add a scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scrollbar.set)

        # Pack the treeview and scrollbar
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load logs
        self.refresh_logs()

    def setup_settings_tab(self):
        """Setup settings tab"""
        # Create a form for settings
        form_frame = ttk.Frame(self.settings_frame)
        form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # AWS IoT settings
        aws_frame = ttk.LabelFrame(form_frame, text="AWS IoT Core Settings")
        aws_frame.pack(fill=tk.X, padx=10, pady=5)

        # Endpoint
        ttk.Label(aws_frame, text="Endpoint:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.endpoint_var = tk.StringVar(value=self.settings.get("aws_endpoint"))
        ttk.Entry(aws_frame, textvariable=self.endpoint_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=5,
                                                                            pady=5)

        # Certificate file
        ttk.Label(aws_frame, text="Certificate File:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.cert_var = tk.StringVar(value=self.settings.get("cert_file"))
        cert_entry = ttk.Entry(aws_frame, textvariable=self.cert_var, width=40)
        cert_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file("cert_file")).grid(row=1, column=2,
                                                                                                 padx=5, pady=5)

        # Key file
        ttk.Label(aws_frame, text="Key File:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.key_var = tk.StringVar(value=self.settings.get("key_file"))
        key_entry = ttk.Entry(aws_frame, textvariable=self.key_var, width=40)
        key_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file("key_file")).grid(row=2, column=2, padx=5,
                                                                                                pady=5)

        # Root CA file
        ttk.Label(aws_frame, text="Root CA File:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.root_ca_var = tk.StringVar(value=self.settings.get("root_ca"))
        root_ca_entry = ttk.Entry(aws_frame, textvariable=self.root_ca_var, width=40)
        root_ca_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file("root_ca")).grid(row=3, column=2, padx=5,
                                                                                               pady=5)

        # Client ID and topic
        ttk.Label(aws_frame, text="Client ID:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.client_id_var = tk.StringVar(value=self.settings.get("client_id"))
        ttk.Entry(aws_frame, textvariable=self.client_id_var, width=40).grid(row=4, column=1, sticky=tk.W, padx=5,
                                                                             pady=5)

        ttk.Label(aws_frame, text="Topic:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.topic_var = tk.StringVar(value=self.settings.get("topic"))
        ttk.Entry(aws_frame, textvariable=self.topic_var, width=40).grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)

        # Alert settings
        alert_frame = ttk.LabelFrame(form_frame, text="Alert Settings")
        alert_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(alert_frame, text="Alert Interval (seconds):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.alert_interval_var = tk.StringVar(value=str(self.settings.get("alert_interval")))
        ttk.Entry(alert_frame, textvariable=self.alert_interval_var, width=10).grid(row=0, column=1, sticky=tk.W,
                                                                                    padx=5, pady=5)

        ttk.Label(alert_frame, text="Scan Interval (seconds):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.scan_interval_var = tk.StringVar(value=str(self.settings.get("scan_interval")))
        ttk.Entry(alert_frame, textvariable=self.scan_interval_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5,
                                                                                   pady=5)

        # Save button
        ttk.Button(form_frame, text="Save Settings", command=self.save_settings).pack(pady=10)

    def connect_to_aws(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            messagebox.showerror("Error", "AWS IoT SDK not installed. Please install it with 'pip install awsiotsdk'")
            return

        if self.connected:
            # Disconnect if already connected
            if self.client:
                self.client.disconnect()
                self.client = None
                self.connected = False
                self.conn_status_var.set("Not Connected")
                self.connect_btn.config(text="Connect")
                self.status_var.set("Disconnected from AWS IoT Core")
                return

        # Check if certificate files exist
        cert_file = self.settings.get("cert_file")
        key_file = self.settings.get("key_file")
        root_ca = self.settings.get("root_ca")

        if not os.path.exists(cert_file):
            messagebox.showerror("Error", f"Certificate file not found: {cert_file}")
            return

        if not os.path.exists(key_file):
            messagebox.showerror("Error", f"Key file not found: {key_file}")
            return

        if not os.path.exists(root_ca):
            messagebox.showerror("Error", f"Root CA file not found: {root_ca}")
            return

        # Create client and connect
        self.client = LoRaClient(self.settings, message_callback=self.message_callback)

        if self.client.connect():
            self.connected = True
            self.conn_status_var.set("Connected")
            self.connect_btn.config(text="Disconnect")
            self.status_var.set(f"Connected to AWS IoT Core endpoint: {self.settings.get('aws_endpoint')}")
            self.db.log_activity("SYSTEM", f"Connected to AWS IoT Core")
        else:
            messagebox.showerror("Connection Error", "Failed to connect to AWS IoT Core. Check settings and try again.")

    def message_callback(self, topic, message, decoded_payload):
        """Handle messages from AWS IoT Core with enhanced decoding"""
        # Log the message
        self.db.log_activity("MQTT", f"Message received on topic: {topic}")

        # Process the beacon data based on payload format
        if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
            lorawan = message["WirelessMetadata"]["LoRaWAN"]

            # Get device ID
            device_id = message.get("WirelessDeviceId", "Unknown")

            # Get RSSI from first gateway if available
            rssi = None
            if "Gateways" in lorawan and lorawan["Gateways"] and "Rssi" in lorawan["Gateways"][0]:
                rssi = lorawan["Gateways"][0]["Rssi"]

            # Check if this is a registered beacon
            beacon = self.db.get_beacon_by_mac(device_id)

            if "beacons" in decoded_payload and decoded_payload["beacons"]:
                # This is a message containing detected beacons
                for detected_beacon in decoded_payload["beacons"]:
                    beacon_mac = detected_beacon["mac"]
                    beacon_rssi = detected_beacon["rssi_value"]
                    est_distance = detected_beacon["estimated_distance"]

                    # Check if this is a registered beacon
                    reg_beacon = self.db.get_beacon_by_mac(beacon_mac)

                    if reg_beacon:
                        # Update the registered beacon's last seen time and signal data
                        self.db.update_beacon_signal(
                            beacon_mac,
                            beacon_rssi,
                            decoded_payload.get("battery_level"),
                            decoded_payload.get("is_charging"),
                            decoded_payload.get("device_mode"),
                            decoded_payload.get("auxiliary_operation"),
                            est_distance
                        )

                        # Add to recent events
                        self.add_event_log(f"Beacon {beacon_mac} in room {reg_beacon[2]} detected | "
                                           f"RSSI: {beacon_rssi} dBm | Distance: {est_distance} m | "
                                           f"Battery: {decoded_payload.get('battery', 'N/A')}")

                        # Store in current beacons for quick reference
                        self.current_beacons[beacon_mac] = {
                            "mac": beacon_mac,
                            "room": reg_beacon[2],
                            "rssi": beacon_rssi,
                            "battery": decoded_payload.get("battery", "N/A"),
                            "distance": est_distance,
                            "mode": decoded_payload.get("device_mode", "N/A"),
                            "last_seen": datetime.now().isoformat()
                        }
                    else:
                        # Unknown beacon
                        self.add_event_log(f"Unknown beacon {beacon_mac} detected | RSSI: {beacon_rssi} dBm | "
                                           f"Distance: {est_distance} m")

                # Refresh displays if auto-refresh is on
                if self.auto_refresh_var.get():
                    self.refresh_beacons()
                    self.update_active_beacons()
            elif beacon:
                # This is a direct message from a registered beacon
                # Update the beacon's last seen time and RSSI
                self.db.update_beacon_signal(
                    device_id,
                    rssi,
                    decoded_payload.get("battery_level"),
                    decoded_payload.get("is_charging"),
                    decoded_payload.get("device_mode"),
                    decoded_payload.get("auxiliary_operation"),
                    None  # We don't have distance for direct messages
                )

                # Add to recent events
                battery_str = decoded_payload.get("battery", "N/A")
                mode_str = decoded_payload.get("device_mode", "N/A")
                aux_str = decoded_payload.get("auxiliary_operation", "N/A")

                self.add_event_log(f"Direct message from beacon {device_id} in room {beacon[2]} | "
                                   f"RSSI: {rssi} dBm | Battery: {battery_str} | "
                                   f"Mode: {mode_str} | Operation: {aux_str}")

                # Refresh displays if auto-refresh is on
                if self.auto_refresh_var.get():
                    self.refresh_beacons()
                    self.update_active_beacons()
            else:
                # Unknown beacon
                self.add_event_log(f"Unknown beacon {device_id} sent direct message | "
                                   f"RSSI: {rssi} dBm | Battery: {decoded_payload.get('battery', 'N/A')}")

    def add_event_log(self, message):
        """Add a message to the dashboard event log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        self.recent_events.configure(state=tk.NORMAL)
        self.recent_events.insert(tk.END, log_message)
        self.recent_events.see(tk.END)
        self.recent_events.configure(state=tk.DISABLED)

    def update_stats(self):
        """Update dashboard statistics"""
        # Count registered beacons
        beacons = self.db.get_all_beacons()
        self.beacon_count_var.set(str(len(beacons)))

        # Count active beacons (seen in last 5 minutes)
        active_count = 0
        current_time = datetime.now()
        for beacon in beacons:
            if beacon[4]:  # last_seen field
                try:
                    last_seen_time = datetime.fromisoformat(beacon[4])
                    time_diff = (current_time - last_seen_time).total_seconds()
                    if time_diff <= 300:  # 5 minutes
                        active_count += 1
                except:
                    pass

        self.active_beacons_var.set(str(active_count))

    # MAC address copying functions
    def show_active_tree_menu(self, event):
        """Show the context menu for active beacons tree"""
        item = self.active_tree.identify_row(event.y)
        if item:
            self.active_tree.selection_set(item)
            self.active_tree_menu.post(event.x_root, event.y_root)

    def show_beacon_tree_menu(self, event):
        """Show the context menu for beacons list tree"""
        item = self.beacon_tree.identify_row(event.y)
        if item:
            self.beacon_tree.selection_set(item)
            self.beacon_tree_menu.post(event.x_root, event.y_root)

    def show_events_menu(self, event):
        """Show the context menu for recent events text widget"""
        self.recent_events_menu.post(event.x_root, event.y_root)

    def copy_mac_from_active(self, event=None):
        """Copy MAC address from selected active beacon"""
        selected = self.active_tree.selection()
        if selected:
            mac = self.active_tree.item(selected[0], 'values')[0]
            self.root.clipboard_clear()
            self.root.clipboard_append(mac)
            self.clipboard_mac = mac
            self.status_var.set(f"Copied MAC address: {mac}")
            self.add_event_log(f"Copied MAC address {mac} to clipboard")
            return mac
        return None

    def register_from_active(self):
        """Register beacon from active beacons list"""
        mac = self.copy_mac_from_active()
        if mac:
            self.add_beacon_dialog(mac)

    def copy_mac_from_beacons_list(self):
        """Copy MAC address from selected beacon in the beacons list"""
        selected = self.beacon_tree.selection()
        if selected:
            mac = self.beacon_tree.item(selected[0], 'values')[1]  # MAC is the second column
            self.root.clipboard_clear()
            self.root.clipboard_append(mac)
            self.clipboard_mac = mac
            self.status_var.set(f"Copied MAC address: {mac}")
            self.add_event_log(f"Copied MAC address {mac} to clipboard")

    def copy_mac_from_events(self):
        """Copy MAC address from selected text in recent events"""
        try:
            # Get selected text
            selected_text = self.recent_events.get("sel.first", "sel.last")

            # Find MAC address pattern in selected text
            import re
            mac_pattern = re.compile(r'([0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2})')
            matches = mac_pattern.findall(selected_text)

            if matches:
                mac = matches[0]
                self.root.clipboard_clear()
                self.root.clipboard_append(mac)
                self.clipboard_mac = mac
                self.status_var.set(f"Copied MAC address: {mac}")
                self.add_event_log(f"Copied MAC address {mac} to clipboard")
                return mac
        except tk.TclError:
            # No selection
            pass

        return None

    def register_from_events(self):
        """Register beacon from selected text in recent events"""
        mac = self.copy_mac_from_events()
        if mac:
            self.add_beacon_dialog(mac)

    def refresh_beacons(self):
        """Refresh the beacon list display"""
        # Clear the treeview
        for item in self.beacon_tree.get_children():
            self.beacon_tree.delete(item)

        # Get all beacons from the database
        beacons = self.db.get_all_beacons()

        # Add them to the treeview
        for beacon in beacons:
            # Format last seen time if available
            last_seen = beacon[4] or "Never"
            if last_seen != "Never":
                try:
                    # Convert ISO format to readable format
                    dt = datetime.fromisoformat(last_seen)
                    last_seen = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass

            # Format RSSI
            rssi = beacon[5] or "N/A"

            # Battery level with charging indicator
            battery = beacon[6] or "N/A"
            if battery != "N/A" and beacon[10]:  # is_charging
                battery = f"{battery} ⚡"

            self.beacon_tree.insert('', tk.END, values=(
                beacon[0],  # ID
                beacon[1],  # MAC address
                beacon[2],  # Room number
                beacon[3],  # Description
                last_seen,  # Last seen
                rssi,  # RSSI
                battery,  # Battery
                beacon[7] or "N/A"  # Device mode
            ))

        # Update stats
        self.update_stats()

    def refresh_logs(self):
        """Refresh the logs display"""
        # Clear the treeview
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        # Get recent logs
        logs = self.db.get_recent_logs(100)

        # Add them to the treeview
        for log in logs:
            timestamp, room, mac, event_type, details = log

            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

            self.log_tree.insert('', tk.END, values=(
                timestamp,
                room or "N/A",
                mac or "N/A",
                event_type,
                details
            ))

    def clear_logs_display(self):
        """Clear the logs display (but not the database)"""
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

    def add_beacon_dialog(self, initial_mac=""):
        """Show dialog to add a new beacon"""
        # Create a dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Beacon")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Form elements
        ttk.Label(dialog, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        mac_var = tk.StringVar(value=initial_mac)
        mac_entry = ttk.Entry(dialog, textvariable=mac_var, width=30)
        mac_entry.grid(row=0, column=1, padx=10, pady=5)

        # Focus on Room Number if MAC is provided, otherwise focus on MAC
        if initial_mac:
            focus_field = 1
        else:
            focus_field = 0

        ttk.Label(dialog, text="Room Number:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        room_var = tk.StringVar()
        room_entry = ttk.Entry(dialog, textvariable=room_var, width=30)
        room_entry.grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(dialog, text="Description:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(dialog, textvariable=desc_var, width=30)
        desc_entry.grid(row=2, column=1, padx=10, pady=5)

        # Create a frame for buttons
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)

        # Add "Paste MAC" button
        def paste_mac():
            try:
                clipboard_text = dialog.clipboard_get()
                mac_var.set(clipboard_text)
            except:
                pass

        paste_btn = ttk.Button(button_frame, text="Paste MAC", command=paste_mac)
        paste_btn.pack(side=tk.LEFT, padx=5)

        # Add beacon button
        def add_beacon():
            mac = mac_var.get().strip()
            room = room_var.get().strip()
            desc = desc_var.get().strip()

            if not mac or not room:
                messagebox.showerror("Error", "MAC Address and Room Number are required.")
                return

            if self.db.add_beacon(mac, room, desc):
                self.db.log_activity("SYSTEM", f"Added beacon for room {room}", None)
                self.refresh_beacons()
                dialog.destroy()
                self.add_event_log(f"Added new beacon for room {room}")
            else:
                messagebox.showerror("Error", "Failed to add beacon. MAC Address may already exist.")

        add_btn = ttk.Button(button_frame, text="Add Beacon", command=add_beacon)
        add_btn.pack(side=tk.LEFT, padx=5)

        # Set focus to the appropriate field
        if focus_field == 0:
            mac_entry.focus_set()
        else:
            room_entry.focus_set()

    def register_unknown_beacon(self):
        """Register an unknown beacon that has been detected"""
        # Get list of MAC addresses from recent events log
        macs = set()
        log_text = self.recent_events.get(1.0, tk.END)

        # Simple regex to find MAC-like patterns
        import re
        mac_pattern = re.compile(r'([0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2})')

        for line in log_text.split('\n'):
            if "Unknown beacon" in line:
                matches = mac_pattern.findall(line)
                for mac in matches:
                    # Check if this MAC is already registered
                    if not self.db.get_beacon_by_mac(mac):
                        macs.add(mac)

        if not macs:
            messagebox.showinfo("Info", "No unknown beacons detected recently.")
            return

        # Create a dialog to choose MAC address
        dialog = tk.Toplevel(self.root)
        dialog.title("Register Unknown Beacon")
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Frame for MAC selection
        select_frame = ttk.LabelFrame(dialog, text="Select MAC Address")
        select_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(select_frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        mac_var = tk.StringVar()
        mac_combo = ttk.Combobox(select_frame, textvariable=mac_var, width=30)
        mac_combo.grid(row=0, column=1, padx=5, pady=5)
        mac_combo['values'] = sorted(list(macs))
        if macs:
            mac_combo.current(0)

        # Add "Paste MAC" button
        def paste_mac():
            try:
                clipboard_text = dialog.clipboard_get()
                mac_var.set(clipboard_text)
            except:
                pass

        ttk.Button(select_frame, text="Paste MAC", command=paste_mac).grid(row=0, column=2, padx=5, pady=5)

        # Frame for beacon details
        details_frame = ttk.LabelFrame(dialog, text="Beacon Details")
        details_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(details_frame, text="Room Number:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        room_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=room_var, width=15).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(details_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        desc_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=desc_var, width=30).grid(row=1, column=1, padx=5, pady=5)

        # Register button
        def register_beacon():
            mac = mac_var.get().strip()
            room = room_var.get().strip()
            desc = desc_var.get().strip()

            if not mac or not room:
                messagebox.showerror("Error", "MAC Address and Room Number are required.")
                return

            if self.db.add_beacon(mac, room, desc):
                self.db.log_activity("SYSTEM", f"Registered unknown beacon {mac} for room {room}", None)
                self.refresh_beacons()
                dialog.destroy()
                self.add_event_log(f"Registered previously unknown beacon {mac} for room {room}")
            else:
                messagebox.showerror("Error", "Failed to register beacon. MAC Address may already exist.")

        # Add Copy MAC button
        def copy_mac():
            mac = mac_var.get().strip()
            if mac:
                self.root.clipboard_clear()
                self.root.clipboard_append(mac)
                self.add_event_log(f"Copied MAC address {mac} to clipboard")

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(button_frame, text="Copy MAC", command=copy_mac).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Register Beacon", command=register_beacon).pack(side=tk.LEFT, padx=5)

    def export_room_mapping(self):
        """Export room mapping to a JSON file"""
        # Get room mapping data from database
        mapping_data = self.db.export_room_mapping_data()

        if not mapping_data:
            messagebox.showerror("Ошибка экспорта", "Не удалось экспортировать данные карты комнат.")
            return

        # Ask user for save location
        default_filename = f"room_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_filename
        )

        if not filename:
            return

        try:
            # Save the data to file
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=4, ensure_ascii=False)

            # Log success and show message
            beacon_count = len(mapping_data["beacons"])
            self.db.log_activity("SYSTEM", f"Экспортировано {beacon_count} маяков в {filename}")
            self.add_event_log(f"Экспортировано {beacon_count} маяков в {filename}")
            messagebox.showinfo("Экспорт завершен", f"Успешно экспортировано {beacon_count} маяков в {filename}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", f"Ошибка экспорта карты комнат: {str(e)}")

    def import_room_mapping(self):
        """Import room mapping from a JSON file"""
        # Ask user for file location
        filename = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            # Read data from file
            with open(filename, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)

            # Validate the data format
            if "beacons" not in mapping_data or not isinstance(mapping_data["beacons"], list):
                messagebox.showerror("Ошибка импорта", "Неверный формат файла карты комнат.")
                return

            # Ask if user wants to replace or merge
            if messagebox.askyesno("Импорт", "Вы хотите заменить все существующие привязки маяков?\n\n"
                                             "Нажмите 'Да' для замены всех существующих привязок.\n"
                                             "Нажмите 'Нет' для объединения с существующими привязками."):
                # Clear existing beacons if replace mode
                self.db.clear_all_beacons()

            # Import the data
            result = self.db.import_room_mapping_data(mapping_data)

            if result:
                # Log success and show message
                import_msg = f"Импортировано {result['imported']} новых маяков, обновлено {result['updated']} существующих маяков"
                self.db.log_activity("SYSTEM", f"{import_msg} из {filename}")
                self.add_event_log(f"{import_msg} из {filename}")
                messagebox.showinfo("Импорт завершен", import_msg)

                # Refresh beacon list
                self.refresh_beacons()
            else:
                messagebox.showerror("Ошибка импорта", "Не удалось импортировать данные карты комнат.")
        except json.JSONDecodeError:
            messagebox.showerror("Ошибка импорта", "Неверный формат JSON файла.")
        except Exception as e:
            messagebox.showerror("Ошибка импорта", f"Ошибка импорта карты комнат: {str(e)}")

    def remove_beacon(self):
        """Remove selected beacon"""
        selected = self.beacon_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select a beacon to remove.")
            return

        # Get the beacon ID from the selected item
        beacon_id = self.beacon_tree.item(selected[0], 'values')[0]

        # Confirm deletion
        if messagebox.askyesno("Confirm", "Are you sure you want to remove this beacon?"):
            if self.db.delete_beacon(beacon_id):
                self.db.log_activity("SYSTEM", f"Removed beacon ID {beacon_id}", None)
                self.refresh_beacons()
                self.add_event_log(f"Removed beacon ID {beacon_id}")
            else:
                messagebox.showerror("Error", "Failed to remove beacon.")

    def edit_beacon(self):
        """Edit selected beacon"""
        selected = self.beacon_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select a beacon to edit.")
            return

        # Get the beacon ID from the selected item
        values = self.beacon_tree.item(selected[0], 'values')
        beacon_id = values[0]
        mac = values[1]
        room = values[2]
        desc = values[3]

        # Create a dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Beacon")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Form elements
        ttk.Label(dialog, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        mac_var = tk.StringVar(value=mac)
        ttk.Entry(dialog, textvariable=mac_var, width=30, state=tk.DISABLED).grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(dialog, text="Room Number:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        room_var = tk.StringVar(value=room)
        ttk.Entry(dialog, textvariable=room_var, width=30).grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(dialog, text="Description:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        desc_var = tk.StringVar(value=desc)
        ttk.Entry(dialog, textvariable=desc_var, width=30).grid(row=2, column=1, padx=10, pady=5)

        # Update button
        def update_beacon():
            new_room = room_var.get().strip()
            new_desc = desc_var.get().strip()

            if not new_room:
                messagebox.showerror("Error", "Room Number is required.")
                return

            if self.db.update_beacon(beacon_id, new_room, new_desc):
                self.db.log_activity("SYSTEM", f"Updated beacon ID {beacon_id}", None)
                self.refresh_beacons()
                dialog.destroy()
                self.add_event_log(f"Updated beacon ID {beacon_id}")
            else:
                messagebox.showerror("Error", "Failed to update beacon.")

        ttk.Button(dialog, text="Update Beacon", command=update_beacon).grid(row=3, column=0, columnspan=2, pady=10)

    def export_logs(self):
        """Export logs to CSV file"""
        # Get filename for export
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            # Get all logs
            logs = self.db.get_recent_logs(1000)  # Get up to 1000 most recent logs

            with open(filename, 'w', newline='') as csvfile:
                import csv
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(["Timestamp", "Room", "MAC Address", "Event Type", "Details"])

                # Write data
                for log in logs:
                    writer.writerow(log)

            messagebox.showinfo("Export Complete", f"Successfully exported {len(logs)} log entries to {filename}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting logs: {str(e)}")

    def browse_file(self, setting_key):
        """Browse for a file and update the corresponding setting"""
        filename = filedialog.askopenfilename()
        if filename:
            if setting_key == "cert_file":
                self.cert_var.set(filename)
            elif setting_key == "key_file":
                self.key_var.set(filename)
            elif setting_key == "root_ca":
                self.root_ca_var.set(filename)

    def save_settings(self):
        """Save settings from the form"""
        try:
            # Update settings from form variables
            self.settings.set("aws_endpoint", self.endpoint_var.get())
            self.settings.set("cert_file", self.cert_var.get())
            self.settings.set("key_file", self.key_var.get())
            self.settings.set("root_ca", self.root_ca_var.get())
            self.settings.set("client_id", self.client_id_var.get())
            self.settings.set("topic", self.topic_var.get())

            # Convert numeric values
            try:
                alert_interval = int(self.alert_interval_var.get())
                self.settings.set("alert_interval", alert_interval)
            except ValueError:
                pass

            try:
                scan_interval = int(self.scan_interval_var.get())
                self.settings.set("scan_interval", scan_interval)
            except ValueError:
                pass

            # Save settings
            if self.settings.save_settings():
                messagebox.showinfo("Success", "Settings saved successfully.")
                self.db.log_activity("SYSTEM", "Settings updated")
            else:
                messagebox.showerror("Error", "Failed to save settings.")

        except Exception as e:
            messagebox.showerror("Error", f"Error saving settings: {str(e)}")


def main():
    """Main entry point with GUI"""
    root = tk.Tk()
    app = BeaconApp(root)
    root.mainloop()


if __name__ == "__main__":
    # Check if command line arguments are provided
    if len(sys.argv) > 1:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Hotel LoRa Beacon Management System")
        parser.add_argument('--cert', help="Path to the certificate file")
        parser.add_argument('--key', help="Path to the private key file")
        parser.add_argument('--root-ca', help="Path to the root CA file")
        parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT, help="AWS IoT endpoint")
        parser.add_argument('--client-id', default=DEFAULT_CLIENT_ID, help="MQTT client ID")
        parser.add_argument('--topic', default=DEFAULT_TOPIC, help="MQTT topic to subscribe to")
        parser.add_argument('--verbose', action='store_true', help="Enable verbose output")
        parser.add_argument('--gui', action='store_true', help="Start with GUI")
        args = parser.parse_args()

        # Initialize settings
        settings = SettingsManager()

        # Update settings from command line if provided
        if args.cert:
            settings.set("cert_file", args.cert)
        if args.key:
            settings.set("key_file", args.key)
        if args.root_ca:
            settings.set("root_ca", args.root_ca)
        if args.endpoint:
            settings.set("aws_endpoint", args.endpoint)
        if args.client_id:
            settings.set("client_id", args.client_id)
        if args.topic:
            settings.set("topic", args.topic)

        # Check if we should start GUI
        if args.gui:
            main()
        else:
            # Initialize database
            db = BeaconDatabase()


            # Define message callback
            def message_callback(topic, message, decoded_payload):
                if args.verbose:
                    print(f"Topic: {topic}")
                    print(f"Message: {json.dumps(message, indent=2)}")
                    print(f"Decoded payload: {json.dumps(decoded_payload, indent=2)}")
                    print("-" * 80)


            # Initialize and connect LoRa client
            client = LoRaClient(settings, message_callback=message_callback)
            if client.connect():
                try:
                    # Keep the main thread alive
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nDisconnecting...")
                    client.disconnect()
                    db.close()
                    print("Goodbye!")
            else:
                print("Failed to connect to AWS IoT Core. Please check your credentials and try again.")
    else:
        # No command line arguments, start GUI
        main()