"""
UNIFIED BEACON MANAGEMENT AND ALERT SYSTEM

This application combines the Beacon Alert Manager (from new.py) and the 
Enhanced Hotel LoRa Beacon Management System (from admin.py) into a single
application that can operate in both client and admin modes.

Features:
1. Client mode:
   - Alert monitoring
   - History display
   - AWS IoT connectivity
   
2. Admin mode:
   - Beacon database management
   - Room mapping
   - System logs
   - AWS IoT configuration
"""

import json
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from datetime import datetime
import threading
import base64
import time
import sqlite3
import argparse

# Import AWS IoT SDK
try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder

    AWS_IOT_AVAILABLE = True
except ImportError:
    AWS_IOT_AVAILABLE = False
    print("Warning: AWS IoT SDK not found. Install with 'pip install awsiotsdk' for IoT connectivity.")

# Application constants
APP_TITLE = "Unified Beacon Management System"
APP_VERSION = "1.0"
DB_NAME = "hotel_beacons.db"
ADMIN_PASSWORD = "admin123"  # Password for admin mode
CLIENT_PASSWORD = "3456"     # Password for client mode

# Configuration directories and files
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "beacon_management_system")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ALARM_HISTORY_FILE = os.path.join(CONFIG_DIR, "alarm_history.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# Default settings
DEFAULT_SETTINGS = {
    "aws": {
        "endpoint": "a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com",
        "client_id": "beacon-client",
        "topic": "#",
        "alert_topic": "beacon/alerts"
    },
    "cert_file": "",
    "key_file": "",
    "root_ca": "",
    "alert_interval": 15,  # seconds between alerts
    "port": 8883,
    "scan_interval": 5,  # seconds between scans
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

    def __init__(self, settings_file=SETTINGS_FILE):
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
                    # Use deep update for nested dictionaries
                    self._update_dict(self.settings, loaded_settings)
            except json.JSONDecodeError:
                print("Error: Settings file is corrupted. Using defaults.")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            # Save default settings
            self.save_settings()
    
    def _update_dict(self, d, u):
        """Deep update dictionary"""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._update_dict(d[k], v)
            else:
                d[k] = v

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
        path = key.split('.')
        current = self.settings
        
        try:
            for p in path:
                current = current[p]
            return current
        except (KeyError, TypeError):
            return default

    def set(self, key, value):
        """Set a setting value"""
        path = key.split('.')
        current = self.settings
        
        # Navigate to the right level
        for p in path[:-1]:
            if p not in current:
                current[p] = {}
            elif not isinstance(current[p], dict):
                current[p] = {}
            current = current[p]
                
        # Set the value at the final level
        current[path[-1]] = value
        self.save_settings()


class AWSIoTClient:
    """Handles communication with AWS IoT Core"""

    def __init__(self, settings, message_callback=None):
        """Initialize the IoT client"""
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

            # Get AWS settings
            endpoint = self.settings.get("aws.endpoint", "")
            cert_file = self.settings.get("cert_file", "")
            key_file = self.settings.get("key_file", "")
            root_ca = self.settings.get("root_ca", "")
            client_id = self.settings.get("aws.client_id", "beacon-client")
            
            if not endpoint or not cert_file or not key_file or not root_ca:
                print("AWS IoT Core settings are incomplete")
                return False

            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=endpoint,
                cert_filepath=cert_file,
                pri_key_filepath=key_file,
                client_bootstrap=client_bootstrap,
                ca_filepath=root_ca,
                client_id=client_id,
                on_connection_interrupted=self._on_connection_interrupted,
                on_connection_resumed=self._on_connection_resumed,
                clean_session=False,
                keep_alive_secs=30
            )

            print(f"Connecting to {endpoint} with client ID '{client_id}'...")
            connect_future = self.mqtt_connection.connect()

            # Wait for connection to complete
            connect_future.result()
            self._on_connection_success(self.mqtt_connection, None)
            self.connected = True
            return True
        except Exception as e:
            print(f"Error connecting to AWS IoT: {e}")
            self.connected = False
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
        topic = self.settings.get("aws.topic", "#")
        print(f"Subscribing to topic: {topic}")
        connection.subscribe(
            topic=topic,
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
                lorawan = message["WirelessMetadata"]["LoRaWAN"]
                fport = lorawan.get("FPort")

            # Process payload if available
            if "PayloadData" in message:
                payload_data = message["PayloadData"]
                # Decode the payload
                decoded_payload = self._decode_lw004_pb_payload(payload_data, fport)
                
                # Call the message callback with the message and decoded data
                if self.message_callback:
                    self.message_callback(topic, message, decoded_payload)
            else:
                # If there's no payload data, just call the callback with the message
                if self.message_callback:
                    self.message_callback(topic, message, {})
                    
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

class Application(tk.Tk):
    """Base Application class with shared functionality"""
    
    def __init__(self, mode="client"):
        """Initialize the base application"""
        super().__init__()
        
        # Set application mode (client or admin)
        self.mode = mode
        
        # Initialize managers
        self.settings = SettingsManager()
        self.db = BeaconDatabase()
        
        # Setup UI
        self.title(f"{APP_TITLE} v{APP_VERSION} - {mode.capitalize()} Mode")
        self.geometry("1200x800")
        self.minsize(800, 600)
        
        # Create menu
        self.create_menu()
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(10, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Setup styles
        self.setup_styles()
        
        # Setup main frame
        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log application start
        self.db.log_activity("SYSTEM", f"Application started in {mode} mode")
        
    def setup_styles(self):
        """Setup custom styles for the application"""
        style = ttk.Style()

        # Configure the main theme
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Configure colors
        bg_color = "#f0f0f0"
        accent_color = "#1e88e5"
        button_bg = "#e3f2fd"
        header_bg = "#2c3e50"
        header_fg = "white"

        # Configure specific styles
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, font=("Segoe UI", 10))
        style.configure("TButton", background=button_bg, font=("Segoe UI", 10))
        style.configure("TEntry", font=("Segoe UI", 10))

        # Header style
        style.configure("Header.TFrame", background=header_bg)
        style.configure("Header.TLabel", background=header_bg, foreground=header_fg, font=("Segoe UI", 12, "bold"))

        # Action buttons
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))

        # List view
        style.configure("History.TFrame", background="white", relief="sunken", borderwidth=1)

        # Status indicators
        style.configure("Connected.TLabel", foreground="green", font=("Segoe UI", 9, "bold"))
        style.configure("Disconnected.TLabel", foreground="red", font=("Segoe UI", 9, "bold"))
        
    def create_menu(self):
        """Create application menu"""
        self.menu = tk.Menu(self)
        self.config(menu=self.menu)
        
        # File menu
        file_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        # Mode menu
        mode_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Mode", menu=mode_menu)
        mode_menu.add_command(label="Client Mode", command=lambda: self.switch_mode("client"))
        mode_menu.add_command(label="Admin Mode", command=lambda: self.switch_mode("admin"))
        
        # Help menu
        help_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
    def switch_mode(self, new_mode):
        """Switch between client and admin modes"""
        if new_mode == self.mode:
            return
            
        if new_mode == "admin":
            # Require password for admin mode
            password = simpledialog.askstring("Password Required", 
                                             "Enter admin password:", 
                                             show='*')
            if password != ADMIN_PASSWORD:
                messagebox.showerror("Error", "Incorrect password")
                return
        elif new_mode == "client":
            # No password required to go to client mode from admin
            if self.mode != "admin":
                # But require password if coming from somewhere else
                password = simpledialog.askstring("Password Required", 
                                                "Enter client password:", 
                                                show='*')
                if password != CLIENT_PASSWORD:
                    messagebox.showerror("Error", "Incorrect password")
                    return
                
        # Save any current state
        self.save_state()
        
        # Destroy current window
        self.destroy()
        
        # Start new application in the desired mode
        if new_mode == "admin":
            app = AdminApp()
        else:
            app = ClientApp()
        
        app.mainloop()
        
    def open_settings(self):
        """Open settings dialog - to be overridden by subclasses"""
        pass
        
    def save_state(self):
        """Save current application state - to be overridden by subclasses"""
        pass
        
    def show_about(self):
        """Show about dialog"""
        about_text = f"{APP_TITLE} v{APP_VERSION}\n\n"
        about_text += "A unified application for managing beacon alerts and room mapping.\n\n"
        about_text += "© 2024 Beacon Systems"
        
        messagebox.showinfo("About", about_text) 

class ClientApp(Application):
    """Client application for beacon alerts and history"""
    
    def __init__(self):
        """Initialize the client application"""
        super().__init__(mode="client")
        
        # Initialize additional components
        self.aws_client = None
        self.aws_connection_status = tk.StringVar(value="Disconnected")
        self.beacons_mapping = {}
        
        # Load alarm history
        self.alarm_history = self.load_alarm_history()
        
        # Load beacon mapping
        self.load_beacons_mapping()
        
        # Create main UI
        self.create_main_ui()
        
        # Auto-connect to AWS IoT if config is available
        self.connect_to_aws()
        
        # Start background thread for automatic reconnection
        threading.Thread(target=self.auto_reconnect, daemon=True).start()
        
    def load_alarm_history(self):
        """Load alarm history from file"""
        if os.path.exists(ALARM_HISTORY_FILE):
            try:
                with open(ALARM_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading alarm history: {e}")
        return []
        
    def save_alarm_history(self):
        """Save alarm history to file"""
        try:
            with open(ALARM_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.alarm_history, f, indent=4)
        except Exception as e:
            print(f"Error saving alarm history: {e}")
            
    def load_beacons_mapping(self):
        """Load beacon room mapping from database"""
        beacons = self.db.get_all_beacons()
        self.beacons_mapping = {}
        
        for beacon in beacons:
            mac_address = beacon[1]
            room_number = beacon[2]
            description = beacon[3] or ""
            
            self.beacons_mapping[mac_address] = {
                "room_number": room_number,
                "description": description
            }
            
        print(f"Loaded {len(self.beacons_mapping)} beacons from database")
        return True

    def create_main_ui(self):
        """Create the main application UI with history view"""
        # Create header frame
        header_frame = ttk.Frame(self.main_frame, style="Header.TFrame")
        header_frame.pack(fill=tk.X)

        # Application title in header
        ttk.Label(
            header_frame,
            text=f"{APP_TITLE} - Client Mode",
            style="Header.TLabel"
        ).pack(side=tk.LEFT, padx=15, pady=10)

        # AWS connection status in header
        self.aws_status_label = ttk.Label(
            header_frame,
            textvariable=self.aws_connection_status,
            style="Disconnected.TLabel"
        )
        self.aws_status_label.pack(side=tk.RIGHT, padx=15, pady=10)

        # Create history label frame with a subtle border
        history_frame = ttk.LabelFrame(
            self.main_frame,
            text="Alert History",
            padding=10
        )
        history_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Create toolbar for history actions
        toolbar_frame = ttk.Frame(history_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))

        # Left side - action buttons
        actions_frame = ttk.Frame(toolbar_frame)
        actions_frame.pack(side=tk.LEFT)

        # Action buttons with improved styling
        refresh_btn = ttk.Button(
            actions_frame,
            text="Refresh",
            style="Action.TButton",
            command=self.refresh_history,
            width=10
        )
        refresh_btn.pack(side=tk.LEFT, padx=(0, 5))

        export_btn = ttk.Button(
            actions_frame,
            text="Export",
            style="Action.TButton",
            command=self.export_history,
            width=10
        )
        export_btn.pack(side=tk.LEFT, padx=5)

        clear_btn = ttk.Button(
            actions_frame,
            text="Clear",
            style="Action.TButton",
            command=self.clear_history,
            width=10
        )
        clear_btn.pack(side=tk.LEFT, padx=5)

        # Right side - search box
        search_frame = ttk.Frame(toolbar_frame)
        search_frame.pack(side=tk.RIGHT)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=25)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind("<KeyRelease>", lambda event: self.refresh_history())

        # History display area with improved styling
        self.history_text = scrolledtext.ScrolledText(
            history_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            background="white"
        )
        self.history_text.pack(fill=tk.BOTH, expand=True)
        
        # Display initial history
        self.refresh_history()
        
    def connect_to_aws(self):
        """Connect to AWS IoT Core with improved handling"""
        if not AWS_IOT_AVAILABLE:
            self.status_var.set("AWS IoT SDK not installed. Install with 'pip install awsiotsdk'")
            return False

        # Check if already connected
        if self.aws_client and self.aws_client.connected:
            self.status_var.set("Already connected to AWS IoT Core")
            return True

        # Create AWS IoT client and connect in a separate thread to avoid freezing UI
        def connect_thread():
            self.status_var.set("Connecting to AWS IoT Core...")
            self.aws_connection_status.set("Connecting...")
            self.aws_status_label.configure(style="Disconnected.TLabel")
            
            # Use our AWSIoTClient with improved message handling
            self.aws_client = AWSIoTClient(self.settings, message_callback=self.handle_aws_message)

            if self.aws_client.connect():
                # Update UI from main thread
                self.after(0, self.update_aws_connected_status)
                return True
            else:
                # Update UI from main thread
                self.after(0, lambda: self.status_var.set("Failed to connect to AWS IoT Core"))
                self.after(0, lambda: self.aws_connection_status.set("Disconnected"))
                self.after(0, lambda: self.aws_status_label.configure(style="Disconnected.TLabel"))
                return False

        # Start connection thread
        threading.Thread(target=connect_thread, daemon=True).start()
        return True
        
    def update_aws_connected_status(self):
        """Update UI elements to show AWS connected status"""
        self.aws_connection_status.set("Connected")
        self.aws_status_label.configure(style="Connected.TLabel")
        self.status_var.set(f"Connected to AWS IoT Core endpoint: {self.settings.get('aws.endpoint')}")

    def update_aws_disconnected_status(self):
        """Update UI elements to show AWS disconnected status"""
        self.aws_connection_status.set("Disconnected")
        self.aws_status_label.configure(style="Disconnected.TLabel")
        self.status_var.set("Disconnected from AWS IoT Core")

    def disconnect_from_aws(self):
        """Disconnect from AWS IoT Core"""
        if self.aws_client:
            # Disconnect in a thread to avoid freezing UI
            def disconnect_thread():
                if self.aws_client.disconnect():
                    # Update UI from main thread
                    self.after(0, self.update_aws_disconnected_status)
                    return True
                else:
                    self.after(0, lambda: self.status_var.set("Error disconnecting from AWS IoT Core"))
                    return False

            threading.Thread(target=disconnect_thread, daemon=True).start()
            return True
        else:
            self.update_aws_disconnected_status()
            return True
            
    def auto_reconnect(self):
        """Background thread for automatic reconnection to AWS IoT"""
        # Wait a bit before starting reconnection attempts to allow initial connection to complete
        time.sleep(5)
        
        while True:
            if self.aws_client is None or not self.aws_client.connected:
                print("AWS IoT connection lost or not established. Attempting to connect...")
                self.connect_to_aws()
            time.sleep(10)
    
    def handle_aws_message(self, topic, message, decoded_payload=None):
        """Handle messages from AWS IoT Core with enhanced decoding"""
        try:
            # Check if this is an alert message
            alert_topic = self.settings.get("aws.alert_topic", "beacon/alerts")
            is_alert = alert_topic in topic

            # Extract relevant data
            timestamp = datetime.now().isoformat()

            # Try to get room number and beacon mac from topic or payload
            room_number = None
            beacon_mac = None
            rssi = None

            # Parse topic parts to extract room/device info
            topic_parts = topic.split('/')
            if len(topic_parts) >= 3:
                if topic_parts[1] == "room":
                    room_number = topic_parts[2]
                elif topic_parts[1] == "device":
                    beacon_mac = topic_parts[2]

            # Look in the message for additional data
            if "WirelessDeviceId" in message:
                beacon_mac = message.get("WirelessDeviceId")

            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                lorawan = message["WirelessMetadata"]["LoRaWAN"]
                if "Gateways" in lorawan and lorawan["Gateways"] and "Rssi" in lorawan["Gateways"][0]:
                    rssi = lorawan["Gateways"][0]["Rssi"]

            # If decoded payload has beacons, use the first one's information
            if decoded_payload and "beacons" in decoded_payload and decoded_payload["beacons"]:
                beacon_info = decoded_payload["beacons"][0]
                beacon_mac = beacon_info.get("mac", beacon_mac)
                rssi = beacon_info.get("rssi_value", rssi)

            # Look up room number from mapping if beacon_mac is available
            if beacon_mac and not room_number and beacon_mac in self.beacons_mapping:
                room_number = self.beacons_mapping[beacon_mac].get("room_number", "Unknown")

            # For alert messages, add to history
            if is_alert or (decoded_payload and "auxiliary_operation" in decoded_payload and 
                           ("Alert Alarm" in decoded_payload["auxiliary_operation"] or 
                            "SOS Alarm" in decoded_payload["auxiliary_operation"])):
                
                alert_data = {
                    "timestamp": timestamp,
                    "topic": topic,
                    "room_number": room_number or "Unknown",
                    "beacon_mac": beacon_mac or "Unknown",
                    "rssi": rssi
                }

                # Add additional data from message
                if isinstance(message, dict):
                    for key, value in message.items():
                        if key not in ["WirelessMetadata", "PayloadData"] and not key.startswith("__"):
                            alert_data[key] = value

                # Add any decoded payload data
                if decoded_payload:
                    for key, value in decoded_payload.items():
                        if key not in ["beacons", "raw_hex"]:
                            alert_data[f"decoded_{key}"] = value

                # Add to alarm history
                self.alarm_history.append(alert_data)
                self.save_alarm_history()

                # Update display if this tab is active
                self.refresh_history()

                # Show notification
                self.show_alert_notification(alert_data)
                
        except Exception as e:
            print(f"Error handling AWS message: {str(e)}")
            
    def show_alert_notification(self, alert_data):
        """Show a notification for a new alert"""
        room = alert_data.get("room_number", "Unknown")
        beacon_mac = alert_data.get("beacon_mac", "Unknown")
        
        # Find description if available
        description = ""
        if beacon_mac in self.beacons_mapping:
            description = self.beacons_mapping[beacon_mac].get("description", "")
            
        # Show a messagebox with the alert info
        messagebox.showwarning(
            "ALERT!",
            f"Alert from Room: {room}\n" +
            (f"Description: {description}\n" if description else "") +
            f"Beacon: {beacon_mac}\n" +
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
    def refresh_history(self):
        """Refresh the alarm history display"""
        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete(1.0, tk.END)

        # Configure tags for better display
        self.history_text.tag_configure('heading', font=("Segoe UI", 14, "bold"), foreground="#1e88e5")
        self.history_text.tag_configure('date', font=("Segoe UI", 12, "bold"), foreground="#2c3e50")
        self.history_text.tag_configure('room', font=("Segoe UI", 12, "bold"), foreground="#e91e63")
        self.history_text.tag_configure('mac', font=("Segoe UI", 10), foreground="#3f51b5")
        self.history_text.tag_configure('label', font=("Segoe UI", 10, "bold"))
        self.history_text.tag_configure('value', font=("Segoe UI", 10))
        self.history_text.tag_configure("empty", justify="center", font=("Segoe UI", 12, "italic"), foreground="#9e9e9e")

        if not self.alarm_history:
            self.history_text.insert(tk.END, "No alert history available.", "empty")
            self.history_text.config(state=tk.DISABLED)
            return

        # Get search filter
        search_text = self.search_var.get().lower()

        # Sort history by timestamp (newest first)
        sorted_history = sorted(
            self.alarm_history,
            key=lambda x: x.get('timestamp', ''),
            reverse=True
        )

        displayed_count = 0

        for i, alarm in enumerate(sorted_history):
            # Skip if doesn't match search criteria
            alarm_text = str(alarm).lower()
            if search_text and search_text not in alarm_text:
                continue

            # Format timestamp
            try:
                dt = datetime.fromisoformat(alarm.get('timestamp', ''))
                timestamp = dt.strftime("%d.%m.%Y %H:%M:%S")
            except:
                timestamp = alarm.get('timestamp', 'Unknown date')

            # Get room and beacon information
            room = alarm.get('room_number', 'Unknown')
            beacon_mac = alarm.get('beacon_mac', 'N/A')

            # Format entry with simplified styling
            self.history_text.insert(tk.END, f"ALERT #{i + 1}\n", 'heading')
            self.history_text.insert(tk.END, f"{timestamp}\n", 'date')
            self.history_text.insert(tk.END, f"Room: ", 'label')
            self.history_text.insert(tk.END, f"{room}\n", 'room')
            self.history_text.insert(tk.END, f"MAC: ", 'label')
            self.history_text.insert(tk.END, f"{beacon_mac}\n", 'mac')

            # Add separator line
            self.history_text.insert(tk.END, "\n" + "-" * 60 + "\n\n")
            displayed_count += 1

        # If nothing to display after filtering
        if displayed_count == 0 and search_text:
            self.history_text.insert(tk.END, f"No alerts found matching '{search_text}'.", "empty")

        # Update status
        if search_text:
            self.status_var.set(f"Showing {displayed_count} of {len(sorted_history)} alerts matching '{search_text}'")
        else:
            self.status_var.set(f"Showing {displayed_count} alerts")

        self.history_text.config(state=tk.DISABLED)
        
    def export_history(self):
        """Export alarm history to a file"""
        if not self.alarm_history:
            messagebox.showinfo("Export History", "No history to export.")
            return

        # Ask for export location
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"alarm_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.alarm_history, f, indent=4)

            messagebox.showinfo("Export Complete", f"Alert history exported to {filename}")
            self.status_var.set(f"History exported to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export alert history: {e}")

    def clear_history(self):
        """Clear alarm history after confirmation"""
        if not self.alarm_history:
            messagebox.showinfo("Clear History", "No history to clear.")
            return

        if messagebox.askyesno("Clear History", "Are you sure you want to clear all alert history?"):
            self.alarm_history = []
            self.save_alarm_history()
            self.refresh_history()
            messagebox.showinfo("Clear History", "Alert history cleared.")
            self.status_var.set("History cleared")
            
    def open_settings(self):
        """Open settings dialog"""
        # Ask for password
        password = simpledialog.askstring("Password Required", 
                                        "Enter password to access settings:", 
                                        show='*')
        if password != CLIENT_PASSWORD:
            messagebox.showerror("Error", "Incorrect password")
            return
            
        # Create settings dialog
        settings_dialog = tk.Toplevel(self)
        settings_dialog.title("Settings")
        settings_dialog.geometry("600x500")
        settings_dialog.transient(self)
        settings_dialog.grab_set()
        settings_dialog.focus_set()
        
        # Center on parent
        settings_dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - settings_dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - settings_dialog.winfo_height()) // 2
        settings_dialog.geometry(f"+{x}+{y}")
        
        # Create notebook for settings tabs
        notebook = ttk.Notebook(settings_dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # AWS tab
        aws_frame = ttk.Frame(notebook, padding=10)
        notebook.add(aws_frame, text="AWS Settings")
        
        # AWS Settings
        ttk.Label(aws_frame, text="AWS IoT Endpoint:").grid(row=0, column=0, sticky=tk.W, pady=5)
        endpoint_var = tk.StringVar(value=self.settings.get("aws.endpoint", ""))
        ttk.Entry(aws_frame, textvariable=endpoint_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(aws_frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        client_id_var = tk.StringVar(value=self.settings.get("aws.client_id", ""))
        ttk.Entry(aws_frame, textvariable=client_id_var, width=40).grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(aws_frame, text="Topic:").grid(row=2, column=0, sticky=tk.W, pady=5)
        topic_var = tk.StringVar(value=self.settings.get("aws.topic", ""))
        ttk.Entry(aws_frame, textvariable=topic_var, width=40).grid(row=2, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(aws_frame, text="Alert Topic:").grid(row=3, column=0, sticky=tk.W, pady=5)
        alert_topic_var = tk.StringVar(value=self.settings.get("aws.alert_topic", ""))
        ttk.Entry(aws_frame, textvariable=alert_topic_var, width=40).grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Certificate files
        ttk.Label(aws_frame, text="Certificate File:").grid(row=4, column=0, sticky=tk.W, pady=5)
        cert_file_var = tk.StringVar(value=self.settings.get("cert_file", ""))
        cert_entry = ttk.Entry(aws_frame, textvariable=cert_file_var, width=40)
        cert_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(aws_frame, text="Browse", 
                  command=lambda: cert_file_var.set(filedialog.askopenfilename())).grid(row=4, column=2, pady=5)
        
        ttk.Label(aws_frame, text="Key File:").grid(row=5, column=0, sticky=tk.W, pady=5)
        key_file_var = tk.StringVar(value=self.settings.get("key_file", ""))
        key_entry = ttk.Entry(aws_frame, textvariable=key_file_var, width=40)
        key_entry.grid(row=5, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(aws_frame, text="Browse", 
                  command=lambda: key_file_var.set(filedialog.askopenfilename())).grid(row=5, column=2, pady=5)
        
        ttk.Label(aws_frame, text="Root CA File:").grid(row=6, column=0, sticky=tk.W, pady=5)
        root_ca_var = tk.StringVar(value=self.settings.get("root_ca", ""))
        root_ca_entry = ttk.Entry(aws_frame, textvariable=root_ca_var, width=40)
        root_ca_entry.grid(row=6, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(aws_frame, text="Browse", 
                  command=lambda: root_ca_var.set(filedialog.askopenfilename())).grid(row=6, column=2, pady=5)
        
        # Make columns expandable
        aws_frame.columnconfigure(1, weight=1)
        
        # Setup buttons
        button_frame = ttk.Frame(settings_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_settings():
            # Save AWS settings
            self.settings.set("aws.endpoint", endpoint_var.get())
            self.settings.set("aws.client_id", client_id_var.get())
            self.settings.set("aws.topic", topic_var.get())
            self.settings.set("aws.alert_topic", alert_topic_var.get())
            
            # Save certificate files
            self.settings.set("cert_file", cert_file_var.get())
            self.settings.set("key_file", key_file_var.get())
            self.settings.set("root_ca", root_ca_var.get())
            
            # Save settings
            self.settings.save_settings()
            
            # Close dialog
            settings_dialog.destroy()
            
            # Ask to reconnect if AWS settings changed
            if self.aws_client and self.aws_client.connected:
                if messagebox.askyesno("Reconnect", "AWS settings changed. Reconnect now?"):
                    self.disconnect_from_aws()
                    self.after(1000, self.connect_to_aws)
            
        ttk.Button(button_frame, text="Cancel", command=settings_dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=5)

class AdminApp(Application):
    """Admin application for beacon management"""
    
    def __init__(self):
        """Initialize the admin application"""
        super().__init__(mode="admin")
        
        # Initialize additional variables
        self.aws_client = None
        self.aws_connection_status = tk.StringVar(value="Disconnected")
        self.selected_beacon = None
        
        # Setup UI components
        self.setup_ui()
        
        # Connect to AWS IoT if settings are available
        self.connect_to_aws()
        
    def setup_ui(self):
        """Setup admin UI with tabs"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Setup tabs
        self.setup_dashboard()
        self.setup_beacons_tab()
        self.setup_logs_tab()
        
    def setup_dashboard(self):
        """Set up dashboard tab"""
        dashboard_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(dashboard_frame, text="Dashboard")
        
        # Header with status information
        header_frame = ttk.Frame(dashboard_frame, style="Header.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            header_frame, 
            text="Beacon Management System Dashboard",
            style="Header.TLabel"
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        # AWS Connection status
        self.aws_status_label = ttk.Label(
            header_frame,
            textvariable=self.aws_connection_status,
            style="Disconnected.TLabel"
        )
        self.aws_status_label.pack(side=tk.RIGHT, padx=15, pady=10)
        
        # Stats frame
        stats_frame = ttk.LabelFrame(dashboard_frame, text="System Statistics")
        stats_frame.pack(fill=tk.X, pady=10)
        
        # Beacon count
        self.beacon_count_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Total Beacons:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(stats_frame, textvariable=self.beacon_count_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky=tk.W, pady=5)
        
        # Recent logs count
        self.log_count_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Recent Logs:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(stats_frame, textvariable=self.log_count_var, font=("Segoe UI", 10, "bold")).grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Action buttons
        actions_frame = ttk.LabelFrame(dashboard_frame, text="Actions")
        actions_frame.pack(fill=tk.X, pady=10)
        
        # Connect to AWS button
        aws_frame = ttk.Frame(actions_frame)
        aws_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            aws_frame,
            text="Connect to AWS IoT",
            command=self.connect_to_aws,
            width=20
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(
            aws_frame,
            text="Disconnect",
            command=self.disconnect_from_aws,
            width=20
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Beacon management buttons
        beacon_frame = ttk.Frame(actions_frame)
        beacon_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            beacon_frame,
            text="Add Beacon",
            command=self.add_beacon_dialog,
            width=20
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(
            beacon_frame,
            text="Export Room Mapping",
            command=self.export_room_mapping,
            width=20
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(
            beacon_frame,
            text="Import Room Mapping",
            command=self.import_room_mapping_dialog,
            width=20
        ).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Recent activity
        activity_frame = ttk.LabelFrame(dashboard_frame, text="Recent Activity")
        activity_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Recent activity list
        self.activity_text = scrolledtext.ScrolledText(
            activity_frame,
            wrap=tk.WORD,
            height=10,
            font=("Segoe UI", 9)
        )
        self.activity_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Refresh button for activity
        ttk.Button(
            activity_frame,
            text="Refresh",
            command=self.refresh_activity,
            width=15
        ).pack(anchor=tk.E, padx=5, pady=5)
        
        # Update statistics
        self.update_stats()
        
    def setup_beacons_tab(self):
        """Set up beacons management tab"""
        beacons_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(beacons_frame, text="Beacons")
        
        # Create a frame for the treeview
        tree_frame = ttk.Frame(beacons_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create treeview with scrollbars
        columns = ("ID", "MAC Address", "Room", "Description", "Last Seen")
        self.beacon_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        
        # Define headings
        for col in columns:
            self.beacon_tree.heading(col, text=col)
            
        # Define column widths
        self.beacon_tree.column("ID", width=50, anchor=tk.CENTER)
        self.beacon_tree.column("MAC Address", width=150)
        self.beacon_tree.column("Room", width=80)
        self.beacon_tree.column("Description", width=200)
        self.beacon_tree.column("Last Seen", width=150)
        
        # Add scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.beacon_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.beacon_tree.xview)
        self.beacon_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid the treeview and scrollbars
        self.beacon_tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        # Configure grid weights
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Add selection event
        self.beacon_tree.bind("<ButtonRelease-1>", self.select_beacon)
        
        # Add right-click menu
        self.beacon_tree.bind("<Button-3>", self.show_beacon_context_menu)
        
        # Button frame for beacon actions
        button_frame = ttk.Frame(beacons_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            button_frame,
            text="Add Beacon",
            command=self.add_beacon_dialog,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Edit Beacon",
            command=self.edit_beacon,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Remove Beacon",
            command=self.remove_beacon,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Refresh",
            command=self.refresh_beacons,
            width=15
        ).pack(side=tk.RIGHT, padx=5)
        
        # Load initial data
        self.refresh_beacons()
        
    def setup_logs_tab(self):
        """Set up system logs tab"""
        logs_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(logs_frame, text="System Logs")
        
        # Create a frame for the treeview
        tree_frame = ttk.Frame(logs_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create treeview with scrollbars
        columns = ("Timestamp", "Room", "MAC Address", "Event Type", "Details")
        self.log_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        
        # Define headings
        for col in columns:
            self.log_tree.heading(col, text=col)
            
        # Define column widths
        self.log_tree.column("Timestamp", width=150)
        self.log_tree.column("Room", width=80)
        self.log_tree.column("MAC Address", width=150)
        self.log_tree.column("Event Type", width=100)
        self.log_tree.column("Details", width=250)
        
        # Add scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.log_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid the treeview and scrollbars
        self.log_tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        # Configure grid weights
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Button frame for log actions
        button_frame = ttk.Frame(logs_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            button_frame,
            text="Refresh",
            command=self.refresh_logs,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Export Logs",
            command=self.export_logs,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        # Load initial data
        self.refresh_logs()

    def connect_to_aws(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            self.status_var.set("AWS IoT SDK not installed. Install with 'pip install awsiotsdk'")
            return False

        # Check if already connected
        if self.aws_client and self.aws_client.connected:
            self.status_var.set("Already connected to AWS IoT Core")
            return True

        # Create AWS IoT client and connect in a separate thread to avoid freezing UI
        def connect_thread():
            self.status_var.set("Connecting to AWS IoT Core...")
            self.aws_connection_status.set("Connecting...")
            self.aws_status_label.configure(style="Disconnected.TLabel")
            
            # Use our AWSIoTClient with improved message handling
            self.aws_client = AWSIoTClient(self.settings, message_callback=self.handle_aws_message)

            if self.aws_client.connect():
                # Update UI from main thread
                self.after(0, self.update_aws_connected_status)
                return True
            else:
                # Update UI from main thread
                self.after(0, lambda: self.status_var.set("Failed to connect to AWS IoT Core"))
                self.after(0, lambda: self.aws_connection_status.set("Disconnected"))
                self.after(0, lambda: self.aws_status_label.configure(style="Disconnected.TLabel"))
                return False

        # Start connection thread
        threading.Thread(target=connect_thread, daemon=True).start()
        return True
        
    def update_aws_connected_status(self):
        """Update UI elements to show AWS connected status"""
        self.aws_connection_status.set("Connected")
        self.aws_status_label.configure(style="Connected.TLabel")
        self.status_var.set(f"Connected to AWS IoT Core endpoint: {self.settings.get('aws.endpoint')}")

    def update_aws_disconnected_status(self):
        """Update UI elements to show AWS disconnected status"""
        self.aws_connection_status.set("Disconnected")
        self.aws_status_label.configure(style="Disconnected.TLabel")
        self.status_var.set("Disconnected from AWS IoT Core")

    def disconnect_from_aws(self):
        """Disconnect from AWS IoT Core"""
        if self.aws_client:
            # Disconnect in a thread to avoid freezing UI
            def disconnect_thread():
                if self.aws_client.disconnect():
                    # Update UI from main thread
                    self.after(0, self.update_aws_disconnected_status)
                    return True
                else:
                    self.after(0, lambda: self.status_var.set("Error disconnecting from AWS IoT Core"))
                    return False

            threading.Thread(target=disconnect_thread, daemon=True).start()
            return True
        else:
            self.update_aws_disconnected_status()
            return True
            
    def handle_aws_message(self, topic, message, decoded_payload=None):
        """Handle messages from AWS IoT Core"""
        try:
            # Extract beacon information from the message
            beacon_mac = None
            room_number = None
            rssi = None
            
            # Try to extract MAC address
            if "WirelessDeviceId" in message:
                beacon_mac = message.get("WirelessDeviceId")
                
            # Try to extract room number
            topic_parts = topic.split('/')
            if len(topic_parts) >= 3 and topic_parts[1] == "room":
                room_number = topic_parts[2]
                
            # Try to extract RSSI
            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                lorawan = message["WirelessMetadata"]["LoRaWAN"]
                if "Gateways" in lorawan and lorawan["Gateways"] and "Rssi" in lorawan["Gateways"][0]:
                    rssi = lorawan["Gateways"][0]["Rssi"]
                    
            # If decoded payload has beacons, use the first one's information
            if decoded_payload and "beacons" in decoded_payload and decoded_payload["beacons"]:
                beacon_info = decoded_payload["beacons"][0]
                beacon_mac = beacon_info.get("mac", beacon_mac)
                rssi = beacon_info.get("rssi_value", rssi)
                
            # Look up the beacon in the database
            if beacon_mac:
                beacon = self.db.get_beacon_by_mac(beacon_mac)
                
                # If beacon exists, update its signal information
                if beacon:
                    # Extract additional information
                    battery_level = None
                    is_charging = None
                    device_mode = None
                    auxiliary_operation = None
                    estimated_distance = None
                    
                    if decoded_payload:
                        battery_level = decoded_payload.get("battery", None)
                        is_charging = decoded_payload.get("is_charging", None)
                        device_mode = decoded_payload.get("device_mode", None)
                        auxiliary_operation = decoded_payload.get("auxiliary_operation", None)
                        
                        # Check if beacons info is available for distance estimation
                        if "beacons" in decoded_payload and decoded_payload["beacons"]:
                            beacon_info = decoded_payload["beacons"][0]
                            estimated_distance = beacon_info.get("estimated_distance", None)
                    
                    # Update beacon signal in database
                    self.db.update_beacon_signal(
                        beacon_mac, 
                        rssi, 
                        battery_level, 
                        is_charging,
                        device_mode, 
                        auxiliary_operation, 
                        estimated_distance
                    )
                    
                    # Log the activity
                    self.db.log_activity(
                        "SIGNAL", 
                        f"Updated signal for {beacon_mac} - RSSI: {rssi} dBm", 
                        beacon[0]
                    )
                    
                    # Add to recent activity
                    self.add_activity(f"Updated signal for {beacon_mac}")
                    
                    # Refresh UI if needed
                    if self.notebook.index(self.notebook.select()) == 0:  # Dashboard selected
                        self.after(0, self.update_stats)
                    elif self.notebook.index(self.notebook.select()) == 1:  # Beacons selected
                        self.after(0, self.refresh_beacons)
                        
        except Exception as e:
            print(f"Error handling AWS message: {str(e)}")
    
    def refresh_beacons(self):
        """Refresh beacon treeview"""
        # Clear treeview
        for item in self.beacon_tree.get_children():
            self.beacon_tree.delete(item)
            
        # Add beacons from database
        beacons = self.db.get_all_beacons()
        for beacon in beacons:
            beacon_id = beacon[0]
            mac = beacon[1]
            room = beacon[2]
            description = beacon[3]
            last_seen = beacon[4] or ""
            
            # Convert ISO format to readable date if possible
            if last_seen:
                try:
                    dt = datetime.fromisoformat(last_seen)
                    last_seen = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
                    
            self.beacon_tree.insert("", tk.END, values=(beacon_id, mac, room, description, last_seen))
            
        # Update statistics
        self.update_stats()
            
    def refresh_logs(self):
        """Refresh logs treeview"""
        # Clear treeview
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
            
        # Add logs from database
        logs = self.db.get_recent_logs()
        for log in logs:
            timestamp = log[0]
            room = log[1] or ""
            mac = log[2] or ""
            event = log[3]
            details = log[4]
            
            # Convert ISO format to readable date if possible
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
                    
            self.log_tree.insert("", tk.END, values=(timestamp, room, mac, event, details))
            
        # Update statistics
        self.update_stats()
    
    def refresh_activity(self):
        """Refresh recent activity"""
        self.activity_text.config(state=tk.NORMAL)
        self.activity_text.delete(1.0, tk.END)
        
        # Get recent logs
        logs = self.db.get_recent_logs(20)
        for log in logs:
            timestamp = log[0]
            room = log[1] or ""
            mac = log[2] or ""
            event = log[3]
            details = log[4]
            
            # Convert ISO format to readable date if possible
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
                    
            # Format log entry
            log_text = f"[{timestamp}] {event}: {details}\n"
            self.activity_text.insert(tk.END, log_text)
            
        self.activity_text.config(state=tk.DISABLED)
    
    def update_stats(self):
        """Update dashboard statistics"""
        # Count beacons
        beacons = self.db.get_all_beacons()
        self.beacon_count_var.set(str(len(beacons)))
        
        # Count recent logs
        logs = self.db.get_recent_logs(100)
        self.log_count_var.set(str(len(logs)))
        
    def add_activity(self, message):
        """Add message to activity log"""
        self.activity_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.activity_text.insert(1.0, f"[{timestamp}] {message}\n")
        self.activity_text.config(state=tk.DISABLED)
        
    def select_beacon(self, event):
        """Handle beacon selection in treeview"""
        selected = self.beacon_tree.selection()
        if selected:
            # Get beacon ID from the selected item
            beacon_id = self.beacon_tree.item(selected[0], 'values')[0]
            self.selected_beacon = self.db.get_beacon_by_id(beacon_id)
            
    def show_beacon_context_menu(self, event):
        """Show context menu for beacon treeview"""
        # Select row under mouse
        iid = self.beacon_tree.identify_row(event.y)
        if iid:
            # Select this item
            self.beacon_tree.selection_set(iid)
            self.select_beacon(None)
            
            # Create popup menu
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Edit Beacon", command=self.edit_beacon)
            menu.add_command(label="Remove Beacon", command=self.remove_beacon)
            menu.add_separator()
            menu.add_command(label="Copy MAC Address", command=self.copy_beacon_mac)
            
            # Display the menu
            menu.post(event.x_root, event.y_root)
            
    def copy_beacon_mac(self):
        """Copy selected beacon MAC address to clipboard"""
        if self.selected_beacon:
            mac = self.selected_beacon[1]
            self.clipboard_clear()
            self.clipboard_append(mac)
            self.status_var.set(f"Copied MAC address: {mac}")
            
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

    def open_settings(self):
        """Open settings dialog"""
        # For admin mode, just redirect to AWS settings
        self.show_aws_settings()

    def show_aws_settings(self):
        """Show AWS IoT settings dialog"""
        settings_dialog = tk.Toplevel(self)
        settings_dialog.title("AWS IoT Settings")
        settings_dialog.transient(self)
        settings_dialog.grab_set()
        settings_dialog.geometry("600x400")
        
        # Center on parent
        settings_dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - settings_dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - settings_dialog.winfo_height()) // 2
        settings_dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(settings_dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # AWS Settings
        ttk.Label(main_frame, text="AWS IoT Endpoint:").grid(row=0, column=0, sticky=tk.W, pady=5)
        endpoint_var = tk.StringVar(value=self.settings.get("aws.endpoint", ""))
        ttk.Entry(main_frame, textvariable=endpoint_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(main_frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        client_id_var = tk.StringVar(value=self.settings.get("aws.client_id", ""))
        ttk.Entry(main_frame, textvariable=client_id_var, width=40).grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(main_frame, text="Topic:").grid(row=2, column=0, sticky=tk.W, pady=5)
        topic_var = tk.StringVar(value=self.settings.get("aws.topic", ""))
        ttk.Entry(main_frame, textvariable=topic_var, width=40).grid(row=2, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(main_frame, text="Alert Topic:").grid(row=3, column=0, sticky=tk.W, pady=5)
        alert_topic_var = tk.StringVar(value=self.settings.get("aws.alert_topic", ""))
        ttk.Entry(main_frame, textvariable=alert_topic_var, width=40).grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Certificate files
        ttk.Label(main_frame, text="Certificate File:").grid(row=4, column=0, sticky=tk.W, pady=5)
        cert_file_var = tk.StringVar(value=self.settings.get("cert_file", ""))
        cert_entry = ttk.Entry(main_frame, textvariable=cert_file_var, width=40)
        cert_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(main_frame, text="Browse", 
                  command=lambda: cert_file_var.set(filedialog.askopenfilename())).grid(row=4, column=2, pady=5)
        
        ttk.Label(main_frame, text="Key File:").grid(row=5, column=0, sticky=tk.W, pady=5)
        key_file_var = tk.StringVar(value=self.settings.get("key_file", ""))
        key_entry = ttk.Entry(main_frame, textvariable=key_file_var, width=40)
        key_entry.grid(row=5, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(main_frame, text="Browse", 
                  command=lambda: key_file_var.set(filedialog.askopenfilename())).grid(row=5, column=2, pady=5)
        
        ttk.Label(main_frame, text="Root CA File:").grid(row=6, column=0, sticky=tk.W, pady=5)
        root_ca_var = tk.StringVar(value=self.settings.get("root_ca", ""))
        root_ca_entry = ttk.Entry(main_frame, textvariable=root_ca_var, width=40)
        root_ca_entry.grid(row=6, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(main_frame, text="Browse", 
                  command=lambda: root_ca_var.set(filedialog.askopenfilename())).grid(row=6, column=2, pady=5)
        
        # Make columns expandable
        main_frame.columnconfigure(1, weight=1)
        
        # Setup buttons
        button_frame = ttk.Frame(settings_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_settings():
            # Save AWS settings
            self.settings.set("aws.endpoint", endpoint_var.get())
            self.settings.set("aws.client_id", client_id_var.get())
            self.settings.set("aws.topic", topic_var.get())
            self.settings.set("aws.alert_topic", alert_topic_var.get())
            
            # Save certificate files
            self.settings.set("cert_file", cert_file_var.get())
            self.settings.set("key_file", key_file_var.get())
            self.settings.set("root_ca", root_ca_var.get())
            
            # Save settings
            self.settings.save_settings()
            
            # Log the activity
            self.db.log_activity("SYSTEM", "Updated AWS IoT settings")
            self.add_activity("Updated AWS IoT settings")
            
            # Close dialog
            settings_dialog.destroy()
            
            # Ask to reconnect if AWS settings changed
            if self.aws_client and self.aws_client.connected:
                if messagebox.askyesno("Reconnect", "AWS settings changed. Reconnect now?"):
                    self.disconnect_from_aws()
                    self.after(1000, self.connect_to_aws)
            
        ttk.Button(button_frame, text="Cancel", command=settings_dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=5)
        
    def add_beacon_dialog(self):
        """Show dialog to add a new beacon"""
        dialog = tk.Toplevel(self)
        dialog.title("Add New Beacon")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("400x250")
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # MAC Address field
        ttk.Label(main_frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        mac_var = tk.StringVar()
        mac_entry = ttk.Entry(main_frame, textvariable=mac_var, width=30)
        mac_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        mac_entry.focus()
        
        # Room Number field
        ttk.Label(main_frame, text="Room Number:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        room_var = tk.StringVar()
        room_entry = ttk.Entry(main_frame, textvariable=room_var, width=30)
        room_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        
        # Description field
        ttk.Label(main_frame, text="Description:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(main_frame, textvariable=desc_var, width=30)
        desc_entry.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        
        # Make columns expandable
        main_frame.columnconfigure(1, weight=1)
        
        # Setup buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=10)
        
        def add_beacon():
            mac = mac_var.get().strip()
            room = room_var.get().strip()
            description = desc_var.get().strip()
            
            # Validate MAC address and room number
            if not mac:
                messagebox.showerror("Error", "MAC address is required")
                return
                
            if not room:
                messagebox.showerror("Error", "Room number is required")
                return
                
            # Add the beacon to the database
            if self.db.add_beacon(mac, room, description):
                # Log the activity
                beacon = self.db.get_beacon_by_mac(mac)
                if beacon:
                    self.db.log_activity("CREATE", f"Added new beacon for room {room}", beacon[0])
                self.add_activity(f"Added new beacon for room {room}")
                
                # Refresh beacon list
                self.refresh_beacons()
                
                # Close dialog
                dialog.destroy()
                
                messagebox.showinfo("Success", "Beacon added successfully")
            else:
                messagebox.showerror("Error", "Failed to add beacon. MAC address may already exist.")
            
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Add Beacon", command=add_beacon).pack(side=tk.RIGHT, padx=5)
        
    def edit_beacon(self):
        """Edit selected beacon"""
        if not self.selected_beacon:
            messagebox.showinfo("Info", "Please select a beacon to edit.")
            return
            
        beacon_id = self.selected_beacon[0]
        mac = self.selected_beacon[1]
        current_room = self.selected_beacon[2]
        current_desc = self.selected_beacon[3] or ""
        
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Beacon - {mac}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("400x200")
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # MAC Address - read only
        ttk.Label(main_frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text=mac).grid(row=0, column=1, sticky=tk.W, pady=5)
        
        # Room Number field
        ttk.Label(main_frame, text="Room Number:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        room_var = tk.StringVar(value=current_room)
        room_entry = ttk.Entry(main_frame, textvariable=room_var, width=30)
        room_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        room_entry.focus()
        
        # Description field
        ttk.Label(main_frame, text="Description:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        desc_var = tk.StringVar(value=current_desc)
        desc_entry = ttk.Entry(main_frame, textvariable=desc_var, width=30)
        desc_entry.grid(row=2, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Make columns expandable
        main_frame.columnconfigure(1, weight=1)
        
        # Setup buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        def update_beacon():
            room = room_var.get().strip()
            description = desc_var.get().strip()
            
            # Validate room number
            if not room:
                messagebox.showerror("Error", "Room number is required")
                return
                
            # Update the beacon in the database
            if self.db.update_beacon(beacon_id, room, description):
                # Log the activity
                self.db.log_activity("UPDATE", f"Updated beacon for room {room}", beacon_id)
                self.add_activity(f"Updated beacon {mac} for room {room}")
                
                # Refresh beacon list
                self.refresh_beacons()
                
                # Close dialog
                dialog.destroy()
                
                messagebox.showinfo("Success", "Beacon updated successfully")
            else:
                messagebox.showerror("Error", "Failed to update beacon")
            
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Update Beacon", command=update_beacon).pack(side=tk.RIGHT, padx=5)
        
    def remove_beacon(self):
        """Remove selected beacon"""
        if not self.selected_beacon:
            messagebox.showinfo("Info", "Please select a beacon to remove.")
            return
            
        beacon_id = self.selected_beacon[0]
        mac = self.selected_beacon[1]
        room = self.selected_beacon[2]
        
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove beacon {mac} from room {room}?"):
            if self.db.delete_beacon(beacon_id):
                # Log the activity
                self.db.log_activity("DELETE", f"Removed beacon {mac} from room {room}")
                self.add_activity(f"Removed beacon {mac} from room {room}")
                
                # Refresh beacon list
                self.refresh_beacons()
                
                messagebox.showinfo("Success", "Beacon removed successfully")
            else:
                messagebox.showerror("Error", "Failed to remove beacon")
                
    def export_room_mapping(self):
        """Export room mapping to JSON file"""
        # Get filename for export
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"room_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if not filename:
            return

        try:
            # Get mapping data from database
            mapping_data = self.db.export_room_mapping_data()
            
            if not mapping_data:
                messagebox.showerror("Error", "Failed to export room mapping data")
                return
                
            # Save to file
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=4)
                
            # Log the activity
            self.db.log_activity("SYSTEM", f"Exported room mapping data to {os.path.basename(filename)}")
            self.add_activity(f"Exported room mapping to {os.path.basename(filename)}")
            
            beacon_count = len(mapping_data.get("beacons", []))
            messagebox.showinfo("Export Complete", f"Successfully exported {beacon_count} beacons to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting room mapping: {str(e)}")
            
    def import_room_mapping_dialog(self):
        """Show dialog to import room mapping"""
        dialog = tk.Toplevel(self)
        dialog.title("Import Room Mapping")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("500x300")
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # File selection
        ttk.Label(main_frame, text="Select JSON file:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        file_var = tk.StringVar()
        file_entry = ttk.Entry(main_frame, textvariable=file_var, width=40)
        file_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        
        browse_button = ttk.Button(
            main_frame, 
            text="Browse",
            command=lambda: file_var.set(filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            ))
        )
        browse_button.grid(row=0, column=2, pady=5, padx=5)
        
        # Replacement options
        ttk.Label(main_frame, text="Import options:").grid(row=1, column=0, sticky=tk.W, pady=10)
        
        replace_var = tk.BooleanVar(value=False)
        replace_check = ttk.Checkbutton(
            main_frame, 
            text="Replace all existing beacons (clear database before import)",
            variable=replace_var
        )
        replace_check.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=10)
        
        # Preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="File Preview")
        preview_frame.grid(row=2, column=0, columnspan=3, sticky=tk.NSEW, pady=10)
        
        preview_text = scrolledtext.ScrolledText(preview_frame, height=8, width=50, wrap=tk.WORD)
        preview_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Make columns and rows expandable
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Preview function
        def preview_file():
            filename = file_var.get()
            if not filename or not os.path.exists(filename):
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, "Please select a valid file to preview.")
                return
                
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Count beacons
                beacons = data.get("beacons", [])
                beacon_count = len(beacons)
                
                # Show preview
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, f"Version: {data.get('version', 'N/A')}\n")
                preview_text.insert(tk.END, f"Export Date: {data.get('export_date', 'N/A')}\n")
                preview_text.insert(tk.END, f"Number of Beacons: {beacon_count}\n\n")
                
                # Show first few beacons
                if beacon_count > 0:
                    preview_text.insert(tk.END, "Sample Beacons:\n")
                    for i, beacon in enumerate(beacons[:5]):
                        preview_text.insert(tk.END, f"{i+1}. {beacon.get('mac_address', 'N/A')} - ")
                        preview_text.insert(tk.END, f"Room: {beacon.get('room_number', 'N/A')}\n")
                        
                    if beacon_count > 5:
                        preview_text.insert(tk.END, f"\n... and {beacon_count - 5} more beacons")
                    
            except Exception as e:
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, f"Error previewing file: {str(e)}")
                
        # Add preview button
        ttk.Button(main_frame, text="Preview", command=preview_file).grid(row=3, column=0, sticky=tk.W, pady=10)
        
        # Setup buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=1, columnspan=2, sticky=tk.E, pady=10)
        
        def import_mapping():
            filename = file_var.get()
            if not filename or not os.path.exists(filename):
                messagebox.showerror("Error", "Please select a valid file to import")
                return
                
            try:
                # Read the file
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Check if we should replace all beacons
                if replace_var.get():
                    if messagebox.askyesno("Confirm", "This will delete ALL existing beacons. Are you sure?"):
                        self.db.clear_all_beacons()
                    else:
                        return
                        
                # Import the data
                result = self.db.import_room_mapping_data(data)
                
                if result:
                    # Log the activity
                    self.db.log_activity("SYSTEM", f"Imported room mapping from {os.path.basename(filename)} - " +
                                       f"Added: {result['imported']}, Updated: {result['updated']}")
                    self.add_activity(f"Imported room mapping - Added: {result['imported']}, Updated: {result['updated']}")
                    
                    # Refresh beacon list
                    self.refresh_beacons()
                    
                    # Close dialog
                    dialog.destroy()
                    
                    messagebox.showinfo("Import Complete", 
                                      f"Successfully imported room mapping data\n" +
                                      f"Added: {result['imported']}\n" +
                                      f"Updated: {result['updated']}")
                else:
                    messagebox.showerror("Import Error", "Failed to import room mapping data")
                    
            except Exception as e:
                messagebox.showerror("Import Error", f"Error importing room mapping: {str(e)}")
            
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Import", command=import_mapping).pack(side=tk.RIGHT, padx=5)
        
        # Automatically preview when a file is selected
        file_var.trace_add("write", lambda *args: preview_file())

def main():
    """Main entry point for the application"""
    parser = argparse.ArgumentParser(description=f"{APP_TITLE} v{APP_VERSION}")
    parser.add_argument('--mode', choices=['client', 'admin'], default='client',
                      help='Application mode (client or admin)')
    parser.add_argument('--password', help='Password for the specified mode')
    args = parser.parse_args()
    
    # Check password if provided
    if args.password:
        if args.mode == 'admin' and args.password != ADMIN_PASSWORD:
            print("Error: Incorrect admin password")
            return
        elif args.mode == 'client' and args.password != CLIENT_PASSWORD:
            print("Error: Incorrect client password")
            return
    
    # Start the application in the specified mode
    if args.mode == 'admin':
        app = AdminApp()
    else:
        app = ClientApp()
    
    app.mainloop()

if __name__ == "__main__":
    main()