# -*- coding: utf-8 -*-
"""
UNIFIED APPLICATION: BEACON ALERT MANAGER SYSTEM
Combines admin and client functionality:
- Admin features: Database management, beacon registration, log analytics
- Client features: Alert notifications, AWS connectivity, room mapping
"""

import json
import os
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from datetime import datetime
import threading
import base64
import time
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
APP_TITLE = "Unified Beacon Alert Manager System"
APP_VERSION = "2.0"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "beacon_alert_manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ALARM_HISTORY_FILE = os.path.join(CONFIG_DIR, "alarm_history.json")
DB_NAME = os.path.join(CONFIG_DIR, "hotel_beacons.db")
ADMIN_PASSWORD = "3456"  # Admin password
CLIENT_PASSWORD = "3456"  # Client password

# Default AWS IoT Core settings
DEFAULT_ENDPOINT = ""
DEFAULT_CLIENT_ID = "beacon-client"
DEFAULT_TOPIC = "#"

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# Default settings
DEFAULT_SETTINGS = {
    "settings_file": "",
    "cert_file": "",
    "key_file": "",
    "root_ca": "",
    "aws": {
        "endpoint": DEFAULT_ENDPOINT,
        "client_id": DEFAULT_CLIENT_ID,
        "topic": "#",
        "alert_topic": "beacon/alerts"
    },
    "alert_interval": 15,  # seconds between alerts
    "scan_interval": 5     # seconds between scans
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
                if not mac_address and "mac" in beacon:
                    mac_address = beacon.get("mac")
                    
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
    """Manages application settings and configuration"""

    def __init__(self, config_file=CONFIG_FILE):
        """Initialize the settings manager"""
        self.config_file = config_file
        self.settings = self.load_settings()
        self.beacons_mapping = {}
        
        # Ensure default values exist
        for key, value in DEFAULT_SETTINGS.items():
            if key not in self.settings:
                self.settings[key] = value
            elif isinstance(value, dict) and isinstance(self.settings[key], dict):
                # Ensure all nested dict keys exist
                for sub_key, sub_value in value.items():
                    if sub_key not in self.settings[key]:
                        self.settings[key][sub_key] = sub_value

    def load_settings(self):
        """Load settings from the config file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    settings = json.load(f)
                return settings
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading settings: {e}")
                return dict(DEFAULT_SETTINGS)
        else:
            # Create default settings if file doesn't exist
            self.save_settings(DEFAULT_SETTINGS)
            return dict(DEFAULT_SETTINGS)

    def save_settings(self, settings=None):
        """Save settings to the config file"""
        if settings:
            self.settings = settings
            
        try:
            # Ensure the config directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            return True
        except IOError as e:
            print(f"Error saving settings: {e}")
            return False

    def get_setting(self, key, default=None):
        """Get a setting value by key"""
        keys = key.split('.')
        settings = self.settings
        
        for k in keys:
            if k in settings:
                settings = settings[k]
            else:
                return default
        
        return settings

    def set_setting(self, key, value):
        """Set a setting value by key"""
        keys = key.split('.')
        settings = self.settings
        
        # Navigate to the correct nested dictionary
        for i, k in enumerate(keys[:-1]):
            if k not in settings:
                settings[k] = {}
            settings = settings[k]
        
        # Set the value
        settings[keys[-1]] = value
        
        # Save the updated settings
        self.save_settings()
        return True

    def load_beacon_mapping(self, file_path=None):
        """Load beacon mapping from a JSON file"""
        if not file_path:
            file_path = self.settings.get("settings_file", "")
            
        if not file_path or not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Check for different formats and extract beacons
            beacons = None
            if "beacons" in data:
                beacons = data["beacons"]
            elif isinstance(data, list):
                beacons = data
                
            if not beacons:
                return False
                
            # Clear and rebuild beacon mapping
            self.beacons_mapping = {}
            
            for beacon in beacons:
                # Handle different formats (mac vs mac_address)
                mac = beacon.get("mac_address", beacon.get("mac", ""))
                if mac:
                    self.beacons_mapping[mac] = beacon
                    
            # Save the settings file path
            self.set_setting("settings_file", file_path)
            return True
                
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading beacon mapping: {e}")
            return False

    def save_beacon_mapping(self, file_path=None):
        """Save beacon mapping to a JSON file"""
        if not file_path:
            file_path = self.settings.get("settings_file", "")
            
        if not file_path:
            return False
            
        try:
            # Convert mapping dictionary to list format for saving
            beacons_list = list(self.beacons_mapping.values())
            
            with open(file_path, 'w') as f:
                json.dump({"beacons": beacons_list}, f, indent=2)
                
            # Save the settings file path
            self.set_setting("settings_file", file_path)
            return True
                
        except IOError as e:
            print(f"Error saving beacon mapping: {e}")
            return False

    def update_beacon_mapping(self, mac, room_number=None, description=None):
        """Update a beacon in the mapping dictionary"""
        # Ensure mac is the mac_address format used in mapping
        if mac in self.beacons_mapping:
            if room_number:
                self.beacons_mapping[mac]["room_number"] = room_number
            if description is not None:
                self.beacons_mapping[mac]["description"] = description
            return True
        return False

    def get_room_number(self, mac):
        """Get room number for a given MAC address"""
        if mac in self.beacons_mapping:
            return self.beacons_mapping[mac].get("room_number", "Unknown")
        return "Unknown"

    def get_beacon_description(self, mac):
        """Get description for a given MAC address"""
        if mac in self.beacons_mapping:
            return self.beacons_mapping[mac].get("description", "")
        return ""

    def import_from_database(self, db):
        """Import beacon mapping from database"""
        export_data = db.export_room_mapping_data()
        if not export_data:
            return False
            
        # Update beacon mapping from database
        self.beacons_mapping = {}
        for beacon in export_data.get("beacons", []):
            mac = beacon.get("mac_address")
            if mac:
                self.beacons_mapping[mac] = beacon
                
        return True

    def export_to_database(self, db):
        """Export beacon mapping to database"""
        if not self.beacons_mapping:
            return False
            
        # Create import data structure
        import_data = {
            "version": "1.0",
            "export_date": datetime.now().isoformat(),
            "beacons": list(self.beacons_mapping.values())
        }
        
        # Import to database
        result = db.import_room_mapping_data(import_data)
        return result is not None

class LoRaClient:
    """Handles AWS IoT Core connectivity for LoRa beacon messages"""

    def __init__(self, settings_manager, callback=None):
        """Initialize the LoRa client with connection settings"""
        self.settings = settings_manager
        self.mqtt_connection = None
        self.connected = False
        self.message_callback = callback
        self.alarm_history = []  # Store alarm history
        self.alarm_log_file = ALARM_HISTORY_FILE
        
        # Load alarm history if exists
        self.load_alarm_history()

    def load_alarm_history(self):
        """Load alarm history from file"""
        if os.path.exists(self.alarm_log_file):
            try:
                with open(self.alarm_log_file, 'r') as f:
                    self.alarm_history = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading alarm history: {e}")
                self.alarm_history = []
        else:
            self.alarm_history = []

    def save_alarm_history(self):
        """Save alarm history to file"""
        try:
            # Ensure the config directory exists
            os.makedirs(os.path.dirname(self.alarm_log_file), exist_ok=True)
            
            with open(self.alarm_log_file, 'w') as f:
                json.dump(self.alarm_history, f, indent=2)
        except IOError as e:
            print(f"Error saving alarm history: {e}")

    def connect(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            return False
            
        try:
            # Get connection parameters from settings
            endpoint = self.settings.get_setting("aws.endpoint")
            client_id = self.settings.get_setting("aws.client_id")
            cert_file = self.settings.get_setting("cert_file")
            key_file = self.settings.get_setting("key_file")
            root_ca = self.settings.get_setting("root_ca")
            
            # Validate parameters
            if not all([endpoint, client_id, cert_file, key_file, root_ca]):
                print("Missing AWS IoT connection parameters")
                return False
                
            # Verify files exist
            for file_path in [cert_file, key_file, root_ca]:
                if not os.path.exists(file_path):
                    print(f"File not found: {file_path}")
                    return False
            
            # Create MQTT connection
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=endpoint,
                cert_filepath=cert_file,
                pri_key_filepath=key_file,
                client_bootstrap=client_bootstrap,
                ca_filepath=root_ca,
                client_id=client_id,
                clean_session=False,
                keep_alive_secs=30
            )
            
            # Connect to AWS IoT Core
            connect_future = self.mqtt_connection.connect()
            connect_future.result()
            
            # Subscribe to topic
            topic = self.settings.get_setting("aws.topic")
            subscribe_future, _ = self.mqtt_connection.subscribe(
                topic=topic,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_message_received
            )
            subscribe_future.result()
            
            self.connected = True
            print(f"Connected to AWS IoT Core: {endpoint}")
            print(f"Subscribed to topic: {topic}")
            return True
            
        except Exception as e:
            print(f"Error connecting to AWS IoT Core: {e}")
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
                print(f"Error disconnecting from AWS IoT Core: {e}")
                return False
        return True

    def _on_message_received(self, topic, payload, **kwargs):
        """Handle messages received from AWS IoT Core"""
        try:
            # Parse the payload
            payload_str = payload.decode('utf-8')
            payload_json = json.loads(payload_str)
            
            # Extract beacon information
            mac = payload_json.get("mac", "")
            rssi = payload_json.get("rssi", 0)
            
            # Additional beacon information if available
            battery = payload_json.get("battery", "")
            is_charging = payload_json.get("charging", False)
            device_mode = payload_json.get("device_mode", "")
            
            # Check if it's an alarm (button pressed)
            is_alarm = False
            if "button" in payload_json and payload_json["button"]:
                is_alarm = True
                
                # Get room number from beacon mapping
                room_number = self.settings.get_room_number(mac)
                
                # Add to alarm history
                alarm_entry = {
                    "mac": mac,
                    "room_number": room_number,
                    "timestamp": datetime.now().isoformat(),
                    "rssi": rssi,
                    "battery": battery
                }
                self.alarm_history.append(alarm_entry)
                self.save_alarm_history()
            
            # Invoke callback if provided
            if self.message_callback:
                self.message_callback(mac, rssi, is_alarm, payload_json)
                
        except Exception as e:
            print(f"Error processing message: {e}")

    def publish_message(self, topic, message):
        """Publish a message to AWS IoT Core"""
        if not self.mqtt_connection or not self.connected:
            return False
            
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
                
            publish_future, _ = self.mqtt_connection.publish(
                topic=topic,
                payload=message,
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            publish_future.result()
            return True
            
        except Exception as e:
            print(f"Error publishing message: {e}")
            return False

    def send_alert(self, alert_data):
        """Send an alert message to the alert topic"""
        alert_topic = self.settings.get_setting("aws.alert_topic")
        return self.publish_message(alert_topic, alert_data)

    def get_alarm_history(self, count=None):
        """Get alarm history, optionally limited to count entries"""
        if count is None:
            return self.alarm_history
        else:
            return self.alarm_history[-count:] if len(self.alarm_history) > 0 else []

    def clear_alarm_history(self):
        """Clear alarm history"""
        self.alarm_history = []
        self.save_alarm_history()

# -*- coding: utf-8 -*-

class Application(tk.Tk):
    """Base Application class with shared functionality"""
    
    def __init__(self, mode="client"):
        super().__init__()
        
        # Set application mode (client or admin)
        self.mode = mode
        
        # Initialize managers
        self.settings = SettingsManager()
        self.db = BeaconDatabase()
        
        # Setup UI
        self.title(f"{APP_TITLE} v{APP_VERSION} - {mode.capitalize()} Mode")
        self.geometry("1200x800")
        
        # Setup main frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create menu
        self.create_menu()
        
        # Setup application-specific UI
        self.setup_ui()
        
    def create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Mode menu
        mode_menu = tk.Menu(menubar, tearoff=0)
        mode_menu.add_command(label="Client Mode", command=lambda: self.switch_mode("client"))
        mode_menu.add_command(label="Admin Mode", command=lambda: self.switch_mode("admin"))
        menubar.add_cascade(label="Mode", menu=mode_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)
        
    def setup_ui(self):
        """Setup application-specific UI - to be overridden by subclasses"""
        pass
        
    def open_settings(self):
        """Open settings dialog"""
        settings_dialog = SettingsDialog(self, self.settings)
        if settings_dialog.result:
            # Apply settings changes
            self.apply_settings()
            
    def apply_settings(self):
        """Apply settings changes - to be overridden by subclasses"""
        pass
        
    def show_about(self):
        """Show about dialog"""
        about_text = f"{APP_TITLE} v{APP_VERSION}\n\n"
        about_text += "A unified application for managing beacon alerts and room mapping.\n\n"
        about_text += "© 2024 Beacon Systems"
        
        messagebox.showinfo("About", about_text)
        
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
            # Require password for client mode
            password = simpledialog.askstring("Password Required", 
                                             "Enter client password:", 
                                             show='*')
            if password != CLIENT_PASSWORD:
                messagebox.showerror("Error", "Incorrect password")
                return
                
        # Save current state if needed
        self.save_state()
        
        # Destroy current window
        self.destroy()
        
        # Start new application in the desired mode
        if new_mode == "admin":
            app = AdminApp()
        else:
            app = ClientApp()
            
        app.mainloop()
        
    def save_state(self):
        """Save application state before switching modes - to be overridden by subclasses"""
        pass


class SettingsDialog(tk.Toplevel):
    """Dialog for configuring application settings"""
    
    def __init__(self, parent, settings_manager):
        super().__init__(parent)
        self.title("Application Settings")
        self.settings = settings_manager
        self.result = False
        
        # Set dialog properties
        self.transient(parent)
        self.grab_set()
        self.geometry("600x500")
        
        # Create notebook for tabbed settings
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_aws_tab()
        self.create_app_tab()
        
        # Create buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self.save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        # Wait for dialog to close
        self.wait_window()
        
    def create_aws_tab(self):
        """Create AWS IoT Core settings tab"""
        aws_frame = ttk.Frame(self.notebook)
        self.notebook.add(aws_frame, text="AWS IoT Core")
        
        # AWS endpoint
        ttk.Label(aws_frame, text="IoT Core Endpoint:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.endpoint_var = tk.StringVar(value=self.settings.get_setting("aws.endpoint", ""))
        ttk.Entry(aws_frame, textvariable=self.endpoint_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # AWS client ID
        ttk.Label(aws_frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.client_id_var = tk.StringVar(value=self.settings.get_setting("aws.client_id", DEFAULT_CLIENT_ID))
        ttk.Entry(aws_frame, textvariable=self.client_id_var, width=40).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # AWS topic
        ttk.Label(aws_frame, text="Subscribe Topic:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.topic_var = tk.StringVar(value=self.settings.get_setting("aws.topic", DEFAULT_TOPIC))
        ttk.Entry(aws_frame, textvariable=self.topic_var, width=40).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # AWS alert topic
        ttk.Label(aws_frame, text="Alert Topic:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.alert_topic_var = tk.StringVar(value=self.settings.get_setting("aws.alert_topic", "beacon/alerts"))
        ttk.Entry(aws_frame, textvariable=self.alert_topic_var, width=40).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Certificate file
        ttk.Label(aws_frame, text="Certificate File:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.cert_file_var = tk.StringVar(value=self.settings.get_setting("cert_file", ""))
        cert_entry = ttk.Entry(aws_frame, textvariable=self.cert_file_var, width=40)
        cert_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file(self.cert_file_var)).grid(row=4, column=2)
        
        # Key file
        ttk.Label(aws_frame, text="Key File:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.key_file_var = tk.StringVar(value=self.settings.get_setting("key_file", ""))
        key_entry = ttk.Entry(aws_frame, textvariable=self.key_file_var, width=40)
        key_entry.grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file(self.key_file_var)).grid(row=5, column=2)
        
        # Root CA
        ttk.Label(aws_frame, text="Root CA File:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.root_ca_var = tk.StringVar(value=self.settings.get_setting("root_ca", ""))
        root_ca_entry = ttk.Entry(aws_frame, textvariable=self.root_ca_var, width=40)
        root_ca_entry.grid(row=6, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(aws_frame, text="Browse", command=lambda: self.browse_file(self.root_ca_var)).grid(row=6, column=2)
        
    def create_app_tab(self):
        """Create application settings tab"""
        app_frame = ttk.Frame(self.notebook)
        self.notebook.add(app_frame, text="Application")
        
        # Settings file
        ttk.Label(app_frame, text="Room Mapping File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.settings_file_var = tk.StringVar(value=self.settings.get_setting("settings_file", ""))
        settings_entry = ttk.Entry(app_frame, textvariable=self.settings_file_var, width=40)
        settings_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(app_frame, text="Browse", command=self.browse_settings_file).grid(row=0, column=2)
        
        # Alert interval
        ttk.Label(app_frame, text="Alert Interval (seconds):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.alert_interval_var = tk.IntVar(value=self.settings.get_setting("alert_interval", 15))
        ttk.Spinbox(app_frame, from_=5, to=60, textvariable=self.alert_interval_var, width=5).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Scan interval
        ttk.Label(app_frame, text="Scan Interval (seconds):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.scan_interval_var = tk.IntVar(value=self.settings.get_setting("scan_interval", 5))
        ttk.Spinbox(app_frame, from_=1, to=30, textvariable=self.scan_interval_var, width=5).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
    def browse_file(self, var):
        """Browse for a file and update the variable"""
        file_path = filedialog.askopenfilename()
        if file_path:
            var.set(file_path)
            
    def browse_settings_file(self):
        """Browse for a settings file and update the variable"""
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if file_path:
            self.settings_file_var.set(file_path)
            
            # Load beacon mapping from file
            self.settings.load_beacon_mapping(file_path)
            
    def save_settings(self):
        """Save settings and close dialog"""
        # Update AWS settings
        self.settings.set_setting("aws.endpoint", self.endpoint_var.get())
        self.settings.set_setting("aws.client_id", self.client_id_var.get())
        self.settings.set_setting("aws.topic", self.topic_var.get())
        self.settings.set_setting("aws.alert_topic", self.alert_topic_var.get())
        self.settings.set_setting("cert_file", self.cert_file_var.get())
        self.settings.set_setting("key_file", self.key_file_var.get())
        self.settings.set_setting("root_ca", self.root_ca_var.get())
        
        # Update application settings
        self.settings.set_setting("settings_file", self.settings_file_var.get())
        self.settings.set_setting("alert_interval", self.alert_interval_var.get())
        self.settings.set_setting("scan_interval", self.scan_interval_var.get())
        
        # Save settings
        self.settings.save_settings()
        
        # Close dialog
        self.result = True
        self.destroy()
        
    def cancel(self):
        """Cancel dialog"""
        self.destroy()


class MainApp:
    """Main entry point for the application"""
    
    @staticmethod
    def run():
        """Run the application"""
        # Parse command line arguments
        parser = argparse.ArgumentParser(description=APP_TITLE)
        parser.add_argument('--mode', choices=['client', 'admin'], default='client',
                          help='Application mode (client or admin)')
        args = parser.parse_args()
        
        # Start application in the specified mode
        if args.mode == "admin":
            app = AdminApp()
        else:
            app = ClientApp()
            
        app.mainloop()

class ClientApp(Application):
    """Client application for beacon alerts and monitoring"""
    
    def __init__(self):
        super().__init__(mode="client")
        
        # Initialize LoRa client
        self.lora = LoRaClient(self.settings, self.on_beacon_message)
        
        # Initialize UI components
        self.connection_status = None
        self.status_var = tk.StringVar(value="Disconnected")
        self.history_tree = None
        self.last_alarm_time = None
        
        # Auto-connect to AWS
        self.connect_aws()
        
    def setup_ui(self):
        """Setup client UI"""
        # Create left and right frames
        left_frame = ttk.Frame(self.main_frame, width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        right_frame = ttk.Frame(self.main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Setup connection panel
        self.setup_connection_panel(left_frame)
        
        # Setup status panel
        self.setup_status_panel(left_frame)
        
        # Setup beacon mapping panel
        self.setup_beacon_mapping_panel(right_frame)
        
        # Setup history panel
        self.setup_history_panel(right_frame)
        
        # Load beacon mapping from settings file
        self.settings.load_beacon_mapping()
        
    def setup_connection_panel(self, parent):
        """Setup connection panel"""
        connection_frame = ttk.LabelFrame(parent, text="AWS IoT Connection")
        connection_frame.pack(fill=tk.X, pady=5)
        
        # Status label
        status_frame = ttk.Frame(connection_frame)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=5)
        self.connection_status = ttk.Label(status_frame, textvariable=self.status_var, 
                                      foreground="red")
        self.connection_status.pack(side=tk.LEFT, padx=5)
        
        # Endpoint
        endpoint_frame = ttk.Frame(connection_frame)
        endpoint_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(endpoint_frame, text="Endpoint:").pack(side=tk.LEFT, padx=5)
        endpoint_label = ttk.Label(endpoint_frame, 
                                  text=self.settings.get_setting("aws.endpoint", "Not configured"))
        endpoint_label.pack(side=tk.LEFT, padx=5)
        
        # Topic
        topic_frame = ttk.Frame(connection_frame)
        topic_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(topic_frame, text="Topic:").pack(side=tk.LEFT, padx=5)
        topic_label = ttk.Label(topic_frame, 
                              text=self.settings.get_setting("aws.topic", "Not configured"))
        topic_label.pack(side=tk.LEFT, padx=5)
        
        # Connection button
        button_frame = ttk.Frame(connection_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        disconnect_button = ttk.Button(button_frame, text="Disconnect", command=self.disconnect_aws)
        disconnect_button.pack(side=tk.RIGHT, padx=5)
        
    def setup_status_panel(self, parent):
        """Setup status panel"""
        status_frame = ttk.LabelFrame(parent, text="System Status")
        status_frame.pack(fill=tk.X, pady=5)
        
        # Add status information
        ttk.Label(status_frame, text="Application Version:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(status_frame, text=APP_VERSION).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_frame, text="Database:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(status_frame, text=DB_NAME).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(status_frame, text="Room Mapping:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        settings_file = self.settings.get_setting("settings_file", "Not loaded")
        settings_file_label = ttk.Label(status_frame, text=os.path.basename(settings_file) if settings_file else "Not loaded")
        settings_file_label.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Button(status_frame, text="Load Room Mapping", command=self.load_room_mapping).grid(row=3, column=0, columnspan=2, pady=5)
        
    def setup_beacon_mapping_panel(self, parent):
        """Setup beacon mapping panel"""
        mapping_frame = ttk.LabelFrame(parent, text="Room Mapping")
        mapping_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        
        # Create treeview for beacon mapping
        columns = ("mac", "room", "description")
        self.mapping_tree = ttk.Treeview(mapping_frame, columns=columns, show="headings", height=10)
        
        # Configure columns
        self.mapping_tree.heading("mac", text="MAC Address")
        self.mapping_tree.heading("room", text="Room Number")
        self.mapping_tree.heading("description", text="Description")
        
        self.mapping_tree.column("mac", width=180)
        self.mapping_tree.column("room", width=100)
        self.mapping_tree.column("description", width=300)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(mapping_frame, orient="vertical", command=self.mapping_tree.yview)
        self.mapping_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        self.mapping_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Refresh mapping
        self.refresh_mapping()
        
    def setup_history_panel(self, parent):
        """Setup history panel"""
        history_frame = ttk.LabelFrame(parent, text="Alarm History")
        history_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create treeview for alarm history
        columns = ("timestamp", "mac", "room")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings")
        
        # Configure columns
        self.history_tree.heading("timestamp", text="Date/Time")
        self.history_tree.heading("mac", text="MAC Address")
        self.history_tree.heading("room", text="Room Number")
        
        self.history_tree.column("timestamp", width=180)
        self.history_tree.column("mac", width=180)
        self.history_tree.column("room", width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add buttons
        button_frame = ttk.Frame(history_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Refresh", command=self.refresh_history).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(button_frame, text="Clear History", command=self.clear_history).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Refresh history
        self.refresh_history()
        
    def connect_aws(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            self.status_var.set("AWS IoT SDK not installed")
            self.connection_status.configure(foreground="red")
            return
            
        # Start connection in a separate thread
        threading.Thread(target=self._connect_aws_thread).start()
        
    def _connect_aws_thread(self):
        """Connect to AWS IoT Core in a separate thread"""
        self.status_var.set("Connecting...")
        self.connection_status.configure(foreground="orange")
        
        if self.lora.connect():
            self.status_var.set("Connected")
            self.connection_status.configure(foreground="green")
        else:
            self.status_var.set("Connection failed")
            self.connection_status.configure(foreground="red")
            
    def disconnect_aws(self):
        """Disconnect from AWS IoT Core"""
        if self.lora.disconnect():
            self.status_var.set("Disconnected")
            self.connection_status.configure(foreground="red")
            
    def load_room_mapping(self):
        """Load room mapping from a file"""
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if file_path:
            if self.settings.load_beacon_mapping(file_path):
                self.refresh_mapping()
                messagebox.showinfo("Success", f"Room mapping loaded from {os.path.basename(file_path)}")
            else:
                messagebox.showerror("Error", "Failed to load room mapping")
                
    def refresh_mapping(self):
        """Refresh beacon mapping treeview"""
        # Clear treeview
        for item in self.mapping_tree.get_children():
            self.mapping_tree.delete(item)
            
        # Add beacon mapping
        for mac, beacon in self.settings.beacons_mapping.items():
            room_number = beacon.get("room_number", "")
            description = beacon.get("description", "")
            self.mapping_tree.insert("", tk.END, values=(mac, room_number, description))
            
    def refresh_history(self):
        """Refresh alarm history treeview"""
        # Clear treeview
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
            
        # Add alarm history
        alarm_history = self.lora.get_alarm_history()
        for alarm in reversed(alarm_history):
            # Convert ISO timestamp to datetime for formatting
            try:
                dt = datetime.fromisoformat(alarm["timestamp"])
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                timestamp = alarm["timestamp"]
                
            mac = alarm["mac"]
            room_number = alarm.get("room_number", self.settings.get_room_number(mac))
            
            self.history_tree.insert("", tk.END, values=(timestamp, mac, room_number))
            
    def clear_history(self):
        """Clear alarm history"""
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the alarm history?"):
            self.lora.clear_alarm_history()
            self.refresh_history()
            
    def on_beacon_message(self, mac, rssi, is_alarm, payload):
        """Handle beacon messages"""
        if is_alarm:
            # Get room number
            room_number = self.settings.get_room_number(mac)
            
            # Show alert if room number is known
            if room_number != "Unknown":
                # Show alert notification
                self.show_alert(mac, room_number)
                
            # Refresh history
            self.refresh_history()
            
    def show_alert(self, mac, room_number):
        """Show alert notification"""
        # Check if enough time has passed since last alert
        current_time = datetime.now()
        alert_interval = self.settings.get_setting("alert_interval", 15)
        
        if (self.last_alarm_time is None or 
            (current_time - self.last_alarm_time).total_seconds() > alert_interval):
            
            # Update last alarm time
            self.last_alarm_time = current_time
            
            # Create alert window
            alert_window = tk.Toplevel(self)
            alert_window.title("ALERT")
            alert_window.attributes('-fullscreen', True)
            alert_window.configure(background='red')
            
            # Make alert window appear on top
            alert_window.attributes('-topmost', True)
            
            # Display room number
            room_label = tk.Label(alert_window, text=f"ROOM {room_number}",
                                font=("Arial", 72, "bold"), bg="red", fg="white")
            room_label.pack(expand=True)
            
            # Display MAC address
            mac_label = tk.Label(alert_window, text=f"Device: {mac}",
                               font=("Arial", 24), bg="red", fg="white")
            mac_label.pack()
            
            # Display timestamp
            time_label = tk.Label(alert_window, text=f"Time: {current_time.strftime('%H:%M:%S')}",
                                font=("Arial", 18), bg="red", fg="white")
            time_label.pack()
            
            # Add close button
            close_button = tk.Button(alert_window, text="CLOSE", 
                                    font=("Arial", 24, "bold"),
                                    command=alert_window.destroy)
            close_button.pack(pady=20)
            
            # Play alert sound if available
            try:
                alert_window.bell()
            except:
                pass
                
            # Auto-close alert after 30 seconds
            alert_window.after(30000, alert_window.destroy)
            
    def apply_settings(self):
        """Apply settings changes"""
        # Refresh connection if connected
        if self.lora.connected:
            self.disconnect_aws()
            self.connect_aws()
            
        # Refresh mapping
        self.refresh_mapping()
        
    def save_state(self):
        """Save application state before switching modes"""
        # Disconnect from AWS
        self.disconnect_aws()
        
        # Close database connection
        self.db.close()
        
        # Destroy window
        self.destroy()


# -*- coding: utf-8 -*-

class AdminApp(Application):
    """Admin application for beacon management and database administration"""
    
    def __init__(self):
        super().__init__(mode="admin")
        
        # Initialize LoRa client for testing
        self.lora = LoRaClient(self.settings)
        
        # Initialize UI components
        self.beacon_tree = None
        self.log_tree = None
        self.selected_beacon = None
        
    def setup_ui(self):
        """Setup admin UI"""
        # Create notebook for tabbed interface
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.create_beacons_tab()
        self.create_logs_tab()
        self.create_export_tab()
        self.create_test_tab()
        
    def create_beacons_tab(self):
        """Create beacons tab for managing beacon database"""
        beacons_frame = ttk.Frame(self.notebook)
        self.notebook.add(beacons_frame, text="Beacons Database")
        
        # Split into left (tree) and right (details) panels
        left_frame = ttk.Frame(beacons_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        right_frame = ttk.Frame(beacons_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5, expand=False)
        
        # Create treeview for beacons
        columns = ("id", "mac", "room", "description", "last_seen")
        self.beacon_tree = ttk.Treeview(left_frame, columns=columns, show="headings")
        
        # Configure columns
        self.beacon_tree.heading("id", text="ID")
        self.beacon_tree.heading("mac", text="MAC Address")
        self.beacon_tree.heading("room", text="Room Number")
        self.beacon_tree.heading("description", text="Description")
        self.beacon_tree.heading("last_seen", text="Last Seen")
        
        self.beacon_tree.column("id", width=50, anchor=tk.CENTER)
        self.beacon_tree.column("mac", width=180)
        self.beacon_tree.column("room", width=100, anchor=tk.CENTER)
        self.beacon_tree.column("description", width=200)
        self.beacon_tree.column("last_seen", width=150)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.beacon_tree.yview)
        self.beacon_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        self.beacon_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add selection event
        self.beacon_tree.bind("<<TreeviewSelect>>", self.on_beacon_select)
        
        # Add toolbar
        toolbar = ttk.Frame(left_frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="Add Beacon", command=self.add_beacon).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_beacons).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Delete", command=self.delete_beacon).pack(side=tk.LEFT, padx=5)
        
        # Create details panel
        details_frame = ttk.LabelFrame(right_frame, text="Beacon Details")
        details_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # MAC address
        ttk.Label(details_frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.mac_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.mac_var, width=25).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Room number
        ttk.Label(details_frame, text="Room Number:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.room_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.room_var, width=25).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Description
        ttk.Label(details_frame, text="Description:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.description_var = tk.StringVar()
        ttk.Entry(details_frame, textvariable=self.description_var, width=25).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Last seen
        ttk.Label(details_frame, text="Last Seen:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.last_seen_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.last_seen_var).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # RSSI
        ttk.Label(details_frame, text="Last RSSI:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.rssi_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.rssi_var).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Battery
        ttk.Label(details_frame, text="Battery Level:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.battery_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.battery_var).grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(details_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Save Changes", command=self.save_beacon).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self.clear_details).pack(side=tk.LEFT, padx=5)
        
        # Refresh beacons
        self.refresh_beacons()
        
    def create_logs_tab(self):
        """Create logs tab for viewing activity logs"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="Activity Logs")
        
        # Create treeview for logs
        columns = ("timestamp", "room", "mac", "event", "details")
        self.log_tree = ttk.Treeview(logs_frame, columns=columns, show="headings")
        
        # Configure columns
        self.log_tree.heading("timestamp", text="Timestamp")
        self.log_tree.heading("room", text="Room")
        self.log_tree.heading("mac", text="MAC Address")
        self.log_tree.heading("event", text="Event")
        self.log_tree.heading("details", text="Details")
        
        self.log_tree.column("timestamp", width=150)
        self.log_tree.column("room", width=80, anchor=tk.CENTER)
        self.log_tree.column("mac", width=180)
        self.log_tree.column("event", width=100)
        self.log_tree.column("details", width=300)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(logs_frame, orient="vertical", command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add toolbar
        toolbar = ttk.Frame(logs_frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="Refresh", command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        
        # Refresh logs
        self.refresh_logs()
        
    def create_export_tab(self):
        """Create export/import tab for room mapping"""
        export_frame = ttk.Frame(self.notebook)
        self.notebook.add(export_frame, text="Import/Export")
        
        # Export section
        export_section = ttk.LabelFrame(export_frame, text="Export Room Mapping")
        export_section.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(export_section, text="Export room mapping to a JSON file for use in client applications.").pack(pady=5)
        
        export_button = ttk.Button(export_section, text="Export Room Mapping", command=self.export_room_mapping)
        export_button.pack(pady=10)
        
        # Import section
        import_section = ttk.LabelFrame(export_frame, text="Import Room Mapping")
        import_section.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(import_section, text="Import room mapping from a JSON file.").pack(pady=5)
        
        import_frame = ttk.Frame(import_section)
        import_frame.pack(fill=tk.X, pady=5)
        
        self.import_file_var = tk.StringVar()
        import_entry = ttk.Entry(import_frame, textvariable=self.import_file_var, width=40)
        import_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        browse_button = ttk.Button(import_frame, text="Browse", 
                                 command=lambda: self.import_file_var.set(
                                     filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])))
        browse_button.pack(side=tk.LEFT, padx=5)
        
        import_button = ttk.Button(import_section, text="Import Room Mapping", 
                                 command=self.import_room_mapping)
        import_button.pack(pady=10)
        
        # Database maintenance section
        maintenance_section = ttk.LabelFrame(export_frame, text="Database Maintenance")
        maintenance_section.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(maintenance_section, text="Warning: These actions cannot be undone!").pack(pady=5)
        
        button_frame = ttk.Frame(maintenance_section)
        button_frame.pack(pady=10)
        
        clear_button = ttk.Button(button_frame, text="Clear All Beacons", 
                                command=self.clear_database)
        clear_button.pack(side=tk.LEFT, padx=10)
        
    def create_test_tab(self):
        """Create test tab for sending test messages"""
        test_frame = ttk.Frame(self.notebook)
        self.notebook.add(test_frame, text="Test")
        
        # AWS connection section
        aws_section = ttk.LabelFrame(test_frame, text="AWS IoT Connection")
        aws_section.pack(fill=tk.X, pady=10, padx=10)
        
        self.aws_status_var = tk.StringVar(value="Disconnected")
        status_label = ttk.Label(aws_section, textvariable=self.aws_status_var, foreground="red")
        status_label.pack(pady=5)
        
        button_frame = ttk.Frame(aws_section)
        button_frame.pack(pady=5)
        
        connect_button = ttk.Button(button_frame, text="Connect", 
                                  command=self.connect_aws)
        connect_button.pack(side=tk.LEFT, padx=5)
        
        disconnect_button = ttk.Button(button_frame, text="Disconnect", 
                                     command=self.disconnect_aws)
        disconnect_button.pack(side=tk.LEFT, padx=5)
        
        # Test message section
        test_section = ttk.LabelFrame(test_frame, text="Send Test Message")
        test_section.pack(fill=tk.X, pady=10, padx=10)
        
        # MAC address
        mac_frame = ttk.Frame(test_section)
        mac_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mac_frame, text="MAC Address:").pack(side=tk.LEFT, padx=5)
        self.test_mac_var = tk.StringVar()
        ttk.Combobox(mac_frame, textvariable=self.test_mac_var, width=30).pack(side=tk.LEFT, padx=5)
        
        # Message type
        type_frame = ttk.Frame(test_section)
        type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(type_frame, text="Message Type:").pack(side=tk.LEFT, padx=5)
        self.test_type_var = tk.StringVar(value="Regular")
        type_combo = ttk.Combobox(type_frame, textvariable=self.test_type_var, width=20,
                                values=["Regular", "Button Press (Alarm)"])
        type_combo.pack(side=tk.LEFT, padx=5)
        
        # RSSI
        rssi_frame = ttk.Frame(test_section)
        rssi_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(rssi_frame, text="RSSI:").pack(side=tk.LEFT, padx=5)
        self.test_rssi_var = tk.IntVar(value=-70)
        ttk.Spinbox(rssi_frame, from_=-100, to=0, textvariable=self.test_rssi_var, width=5).pack(side=tk.LEFT, padx=5)
        
        # Battery
        battery_frame = ttk.Frame(test_section)
        battery_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(battery_frame, text="Battery Level:").pack(side=tk.LEFT, padx=5)
        self.test_battery_var = tk.StringVar(value="100%")
        ttk.Entry(battery_frame, textvariable=self.test_battery_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Send button
        send_button = ttk.Button(test_section, text="Send Test Message", 
                               command=self.send_test_message)
        send_button.pack(pady=10)
        
        # Update available MAC addresses when tab is selected
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
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
            
    def on_beacon_select(self, event):
        """Handle beacon selection"""
        # Get selected item
        selection = self.beacon_tree.selection()
        if not selection:
            return
            
        # Get beacon ID
        item = self.beacon_tree.item(selection[0])
        beacon_id = item["values"][0]
        
        # Get beacon details
        beacon = self.db.get_beacon_by_id(beacon_id)
        if not beacon:
            return
            
        # Save selected beacon
        self.selected_beacon = beacon
        
        # Update details panel
        self.mac_var.set(beacon[1])
        self.room_var.set(beacon[2])
        self.description_var.set(beacon[3] or "")
        
        # Format last seen date
        last_seen = beacon[4] or ""
        if last_seen:
            try:
                dt = datetime.fromisoformat(last_seen)
                last_seen = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
                
        self.last_seen_var.set(last_seen)
        self.rssi_var.set(str(beacon[5] or ""))
        self.battery_var.set(beacon[6] or "")
        
    def add_beacon(self):
        """Add a new beacon"""
        # Clear details panel
        self.clear_details()
        
        # Set focus to MAC address field
        self.mac_var.set("")
        self.room_var.set("")
        self.description_var.set("")
        
        # Deselect any selected beacon
        for item in self.beacon_tree.selection():
            self.beacon_tree.selection_remove(item)
            
        self.selected_beacon = None
        
    def save_beacon(self):
        """Save beacon details"""
        mac = self.mac_var.get().strip()
        room = self.room_var.get().strip()
        description = self.description_var.get().strip()
        
        if not mac:
            messagebox.showerror("Error", "MAC address is required")
            return
            
        if not room:
            messagebox.showerror("Error", "Room number is required")
            return
            
        if self.selected_beacon:
            # Update existing beacon
            beacon_id = self.selected_beacon[0]
            if self.db.update_beacon(beacon_id, room, description):
                messagebox.showinfo("Success", "Beacon updated successfully")
                self.refresh_beacons()
                
                # Log activity
                self.db.log_activity("update", f"Updated room to {room}", beacon_id)
            else:
                messagebox.showerror("Error", "Failed to update beacon")
        else:
            # Add new beacon
            if self.db.add_beacon(mac, room, description):
                messagebox.showinfo("Success", "Beacon added successfully")
                self.refresh_beacons()
                
                # Get new beacon ID for logging
                beacon = self.db.get_beacon_by_mac(mac)
                if beacon:
                    self.db.log_activity("create", f"Added new beacon for room {room}", beacon[0])
            else:
                messagebox.showerror("Error", "Failed to add beacon. MAC may already exist.")
                
    def delete_beacon(self):
        """Delete selected beacon"""
        selection = self.beacon_tree.selection()
        if not selection:
            messagebox.showerror("Error", "No beacon selected")
            return
            
        # Confirm deletion
        if not messagebox.askyesno("Confirm", "Are you sure you want to delete this beacon?"):
            return
            
        # Get beacon ID
        item = self.beacon_tree.item(selection[0])
        beacon_id = item["values"][0]
        
        # Delete beacon
        if self.db.delete_beacon(beacon_id):
            messagebox.showinfo("Success", "Beacon deleted successfully")
            self.refresh_beacons()
            self.clear_details()
            
            # Log activity
            self.db.log_activity("delete", f"Deleted beacon ID {beacon_id}")
        else:
            messagebox.showerror("Error", "Failed to delete beacon")
            
    def clear_details(self):
        """Clear details panel"""
        self.mac_var.set("")
        self.room_var.set("")
        self.description_var.set("")
        self.last_seen_var.set("")
        self.rssi_var.set("")
        self.battery_var.set("")
        
    def export_room_mapping(self):
        """Export room mapping to a JSON file"""
        # Get export data
        export_data = self.db.export_room_mapping_data()
        if not export_data:
            messagebox.showerror("Error", "Failed to export room mapping")
            return
            
        # Get file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"room_mapping_{timestamp}.json"
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
            
        # Save to file
        try:
            with open(file_path, 'w') as f:
                json.dump(export_data, f, indent=2)
                
            messagebox.showinfo("Success", f"Room mapping exported to {os.path.basename(file_path)}")
        except IOError as e:
            messagebox.showerror("Error", f"Failed to export room mapping: {e}")
            
    def import_room_mapping(self):
        """Import room mapping from a JSON file"""
        file_path = self.import_file_var.get()
        
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
            
        # Read file
        try:
            with open(file_path, 'r') as f:
                import_data = json.load(f)
                
            # Import to database
            result = self.db.import_room_mapping_data(import_data)
            
            if result:
                messagebox.showinfo("Success", 
                                  f"Room mapping imported successfully\n"
                                  f"Added: {result['imported']}\n"
                                  f"Updated: {result['updated']}")
                                  
                self.refresh_beacons()
                
                # Log activity
                self.db.log_activity("import", f"Imported room mapping from {os.path.basename(file_path)}")
            else:
                messagebox.showerror("Error", "Failed to import room mapping")
                
        except (json.JSONDecodeError, IOError) as e:
            messagebox.showerror("Error", f"Failed to import room mapping: {e}")
            
    def clear_database(self):
        """Clear all beacons from the database"""
        # Confirm deletion
        if not messagebox.askyesno("Confirm", 
                                 "Are you sure you want to delete ALL beacons?\n"
                                 "This action cannot be undone!"):
            return
            
        # Double-confirm deletion
        if not messagebox.askyesno("Confirm Again", 
                                 "ALL beacon data will be permanently deleted.\n"
                                 "Are you absolutely sure?"):
            return
            
        # Clear database
        if self.db.clear_all_beacons():
            messagebox.showinfo("Success", "All beacons have been deleted")
            self.refresh_beacons()
            self.clear_details()
            
            # Log activity
            self.db.log_activity("clear", "Cleared all beacons from database")
        else:
            messagebox.showerror("Error", "Failed to clear database")
            
    def connect_aws(self):
        """Connect to AWS IoT Core for testing"""
        if not AWS_IOT_AVAILABLE:
            self.aws_status_var.set("AWS IoT SDK not installed")
            return
            
        # Connect to AWS
        if self.lora.connect():
            self.aws_status_var.set("Connected")
        else:
            self.aws_status_var.set("Connection failed")
            
    def disconnect_aws(self):
        """Disconnect from AWS IoT Core"""
        if self.lora.disconnect():
            self.aws_status_var.set("Disconnected")
            
    def send_test_message(self):
        """Send a test message to AWS IoT Core"""
        if not self.lora.connected:
            messagebox.showerror("Error", "Not connected to AWS")
            return
            
        # Get message parameters
        mac = self.test_mac_var.get().strip()
        message_type = self.test_type_var.get()
        rssi = self.test_rssi_var.get()
        battery = self.test_battery_var.get()
        
        if not mac:
            messagebox.showerror("Error", "MAC address is required")
            return
            
        # Create message
        timestamp = datetime.now().isoformat()
        message = {
            "mac": mac,
            "rssi": rssi,
            "battery": battery,
            "timestamp": timestamp,
            "button": message_type == "Button Press (Alarm)"
        }
        
        # Send message
        topic = self.settings.get_setting("aws.topic", "#").replace("#", f"beacon/{mac}")
        if self.lora.publish_message(topic, message):
            messagebox.showinfo("Success", "Test message sent successfully")
            
            # Log activity
            beacon = self.db.get_beacon_by_mac(mac)
            if beacon:
                self.db.log_activity("test", f"Sent test {message_type} message", beacon[0])
            else:
                self.db.log_activity("test", f"Sent test {message_type} message for unregistered MAC {mac}")
                
            # Update beacon signal in database
            self.db.update_beacon_signal(mac, rssi, battery)
            
            # Refresh beacons
            self.refresh_beacons()
        else:
            messagebox.showerror("Error", "Failed to send test message")
            
    def on_tab_changed(self, event):
        """Handle tab changed event"""
        # Update MAC addresses in test tab
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 3:  # Test tab
            # Get MAC addresses from database
            beacons = self.db.get_all_beacons()
            mac_addresses = [beacon[1] for beacon in beacons]
            
            # Update combobox values
            test_mac_combo = self.notebook.winfo_children()[3].winfo_children()[1].winfo_children()[1].winfo_children()[2]
            test_mac_combo["values"] = mac_addresses
            
    def apply_settings(self):
        """Apply settings changes"""
        pass
        
    def save_state(self):
        """Save application state before switching modes"""
        # Disconnect from AWS if connected
        if hasattr(self, 'lora') and self.lora.connected:
            self.disconnect_aws()
        
    def on_closing(self):
        """Handle application closing"""
        # Close database connection
        self.db.close()
        
        # Destroy window
        self.destroy()


if __name__ == "__main__":
    MainApp.run()
