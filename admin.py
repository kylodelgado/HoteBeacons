#!/usr/bin/env python3
import json
import base64
import time
import argparse
import threading
import os
import sys
from datetime import datetime, timezone # Added timezone for python 3.11+ compatibility
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
    print("Warning: AWS IoT SDK not found. Install with 'pip install awsiotsdk' for IoT connectivity.")

# --- Constants ---
APP_TITLE = "Beacon Alert and Management System"
APP_VERSION = "2.0" # Combined version
DB_NAME = "hotel_beacons.db"
LOG_DIR = "logs"
DEFAULT_ADMIN_PASSWORD = "0000" # Default password as requested

# Default AWS IoT Core settings (Consider moving to SettingsManager)
DEFAULT_ENDPOINT = "a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com"
DEFAULT_CERT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "MikeTheMexican 2") # Example path
DEFAULT_CLIENT_ID = "hotel-beacon-client"
DEFAULT_TOPIC = "#"
DEFAULT_ALERT_TOPIC = "beacon/alerts" # From client.py

# Config directories and files (Consolidated)
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "beacon_system_config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json") # Using admin.py's settings file
ALARM_HISTORY_FILE = os.path.join(CONFIG_DIR, "alarm_history.json") # Using client.py's history file

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Default settings structure (incorporating admin.py's)
DEFAULT_SETTINGS = {
    "aws_endpoint": DEFAULT_ENDPOINT,
    "cert_file": os.path.join(DEFAULT_CERT_DIR, "certificate.pem.crt"),
    "key_file": os.path.join(DEFAULT_CERT_DIR, "private.pem.key"),
    "root_ca": os.path.join(DEFAULT_CERT_DIR, "AmazonRootCA1.pem"),
    "client_id": DEFAULT_CLIENT_ID,
    "topic": DEFAULT_TOPIC,
    "alert_topic": DEFAULT_ALERT_TOPIC, # Added alert topic
    "alert_interval": 15,
    "port": 8883,
    "scan_interval": 5,
    "room_mapping_file": "", # Added placeholder for room mapping file path if needed from config
}

# --- Beacon Database Class (from admin.py) ---
class BeaconDatabase:
    """Database manager for storing beacon information"""

    def __init__(self, db_path=DB_NAME):
        """Initialize the database connection"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.init_db()

    def init_db(self):
        """Initialize the database with required tables"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()

            self.cursor.execute("""
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index on mac_address for faster lookups
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_beacons_mac
                ON beacons (mac_address)
            """)

            # Check if columns exist and add them if they don't
            columns_to_check = [
                ('battery_level', 'TEXT'),
                ('device_mode', 'TEXT'),
                ('auxiliary_operation', 'TEXT'),
                ('estimated_distance', 'REAL'),
                ('is_charging', 'BOOLEAN')
            ]

            for column, dtype in columns_to_check:
                try:
                    self.cursor.execute(f"ALTER TABLE beacons ADD COLUMN {column} {dtype}")
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' in str(e).lower():
                        continue  # Column already exists, skip
                    else:
                        raise e

            # Add Activity Log table if it doesn't exist
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    beacon_id INTEGER,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id) ON DELETE SET NULL
                )
            """)
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_activity_log_timestamp
                ON activity_log (timestamp)
            """)


            self.conn.commit()
            print("Database initialized at", self.db_path)
        except sqlite3.Error as e:
            print(f"Error initializing database: {e}")

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
            updates = []
            params = []
            if room_number is not None:
                updates.append("room_number = ?")
                params.append(room_number)
            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if not updates:
                return False # Nothing to update

            params.append(beacon_id)
            query = f"UPDATE beacons SET {', '.join(updates)} WHERE id = ?"
            self.cursor.execute(query, params)
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
                params.append(str(battery_level)) # Ensure string for DB

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
            print(f"Error updating beacon signal for {mac_address}: {e}")
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
                "version": "1.0", # Consider updating version scheme if needed
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
                mac_address = beacon.get("mac_address") or beacon.get("mac") # Handle both keys
                room_number = beacon.get("room_number")
                description = beacon.get("description", "")

                if not mac_address or not room_number:
                    print(f"Skipping invalid beacon entry: {beacon}")
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
        except Exception as e:
            # Catch other potential errors during import
            self.conn.rollback()
            print(f"Unexpected error during import: {e}")
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

# --- Settings Manager Class (from admin.py) ---
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
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    # Update settings with loaded values, maintaining defaults for missing keys
                    temp_settings = DEFAULT_SETTINGS.copy()
                    temp_settings.update(loaded_settings)
                    self.settings = temp_settings
            except json.JSONDecodeError:
                print("Error: Settings file is corrupted. Using defaults and attempting to save.")
                self.save_settings() # Try to save defaults if file is corrupt
            except Exception as e:
                print(f"Error loading settings: {e}. Using defaults.")
                self.settings = DEFAULT_SETTINGS.copy() # Fallback to defaults
        else:
            # Save default settings if file doesn't exist
            print("Settings file not found. Creating with default settings.")
            self.save_settings()

    def save_settings(self):
        """Save settings to file"""
        try:
            # Ensure the config directory exists before saving
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get(self, key, default=None):
        """Get a setting value"""
        # Provide a default if the key is missing from the loaded settings
        return self.settings.get(key, DEFAULT_SETTINGS.get(key, default))


    def set(self, key, value):
        """Set a setting value"""
        self.settings[key] = value
        self.save_settings() # Auto-save on set

# --- LoRa/AWS Client Class (Based on admin.py's LoRaClient, enhanced) ---
class LoRaClient:
    """Handles communication with AWS IoT Core for LoRaWAN"""

    def __init__(self, settings_manager, message_callback=None):
        """Initialize the LoRa client using SettingsManager"""
        self.settings_manager = settings_manager
        self.message_callback = message_callback
        self.mqtt_connection = None
        self.connected = False
        self.is_connecting = False # Flag to prevent multiple connect attempts

    def connect(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            print("AWS IoT SDK not available. Cannot connect.")
            return False
        if self.connected or self.is_connecting:
            print("Already connected or connection in progress.")
            return self.connected

        # Check required settings from SettingsManager
        endpoint = self.settings_manager.get("aws_endpoint")
        cert_file = self.settings_manager.get("cert_file")
        key_file = self.settings_manager.get("key_file")
        root_ca = self.settings_manager.get("root_ca")
        client_id = self.settings_manager.get("client_id")

        if not all([endpoint, cert_file, key_file, root_ca, client_id]):
            print("Error: Incomplete AWS IoT connection settings.")
            messagebox.showerror("Connection Error", "AWS IoT settings are incomplete. Please configure them via Admin Settings.")
            return False

        if not os.path.exists(cert_file):
            print(f"Error: Certificate file not found: {cert_file}")
            messagebox.showerror("Connection Error", f"Certificate file not found:\n{cert_file}\nPlease check Admin Settings.")
            return False
        if not os.path.exists(key_file):
            print(f"Error: Key file not found: {key_file}")
            messagebox.showerror("Connection Error", f"Key file not found:\n{key_file}\nPlease check Admin Settings.")
            return False
        if not os.path.exists(root_ca):
             print(f"Error: Root CA file not found: {root_ca}")
             messagebox.showerror("Connection Error", f"Root CA file not found:\n{root_ca}\nPlease check Admin Settings.")
             return False

        self.is_connecting = True
        try:
            # Set up connection to AWS IoT Core
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
            print("Successfully connected to AWS IoT Core.")
            return True
        except Exception as e:
            print(f"Error connecting to AWS IoT: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect to AWS IoT:\n{e}")
            self.connected = False
            return False
        finally:
             self.is_connecting = False

    def disconnect(self):
        """Disconnect from AWS IoT Core"""
        if self.mqtt_connection and self.connected:
            try:
                print("Disconnecting from AWS IoT Core...")
                disconnect_future = self.mqtt_connection.disconnect()
                disconnect_future.result() # Wait for disconnect to complete
                self.connected = False
                self.mqtt_connection = None # Clear the connection object
                print("Disconnected from AWS IoT Core")
                return True
            except Exception as e:
                print(f"Error disconnecting: {e}")
                # Force state update even if disconnect fails
                self.connected = False
                self.mqtt_connection = None
                return False
        self.connected = False # Ensure disconnected state if no connection existed
        self.mqtt_connection = None
        return True

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """Handle connection interruption"""
        print(f"Connection interrupted. Error: {error}")
        self.connected = False
        # Optional: Trigger a UI update or reconnection attempt here if needed

    def _on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """Handle connection resumption"""
        print(f"Connection resumed. Return code: {return_code} Session present: {session_present}")
        self.connected = True
        # Re-subscribe if session is not present
        if not session_present:
            print("Session not present. Re-subscribing...")
            self._subscribe_to_topics(connection)
        # Optional: Trigger a UI update here

    def _on_connection_success(self, connection, callback_data):
        """Handle successful connection"""
        print("AWS IoT Core connection established!")
        self._subscribe_to_topics(connection)

    def _subscribe_to_topics(self, connection):
        """Subscribe to configured topics"""
        topic = self.settings_manager.get('topic', DEFAULT_TOPIC)
        alert_topic = self.settings_manager.get('alert_topic', DEFAULT_ALERT_TOPIC)

        topics_to_subscribe = set([topic, alert_topic]) # Use a set to avoid duplicate subscriptions

        for sub_topic in topics_to_subscribe:
            if not sub_topic: # Skip empty topics
                continue
            print(f"Subscribing to topic: {sub_topic}")
            try:
                subscribe_future, packet_id = connection.subscribe(
                    topic=sub_topic,
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                    callback=self._on_message_received
                )
                subscribe_result = subscribe_future.result()
                print(f"Subscribed to '{sub_topic}' with {str(subscribe_result['qos'])}")
            except Exception as e:
                 print(f"Error subscribing to topic '{sub_topic}': {e}")


    def _on_message_received(self, topic, payload, dup, qos, retain, **kwargs):
        """Handle message received from AWS IoT Core"""
        print(f"Received message on topic '{topic}'")
        try:
            # Parse JSON message
            message = json.loads(payload.decode('utf-8'))

            # Get FPort for filtering
            fport = None
            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                fport = message["WirelessMetadata"]["LoRaWAN"].get("FPort")

            # Process payload if available
            decoded_payload = {}
            if "PayloadData" in message:
                payload_data = message["PayloadData"]
                decoded_payload = self._decode_lw004_pb_payload(payload_data, fport)
                print(f"Decoded payload: {json.dumps(decoded_payload, indent=2)}")
            else:
                print("No PayloadData found in message.")

            # Call the message callback with the topic, full message, and decoded data
            if self.message_callback:
                # Run callback in the main thread using root.after to avoid Tkinter thread issues
                 if hasattr(self.message_callback.__self__, 'root'): # Check if callback belongs to a Tkinter object
                     self.message_callback.__self__.root.after(0, self.message_callback, topic, message, decoded_payload)
                 else:
                     # If not a Tkinter callback, run directly (or adapt as needed)
                     self.message_callback(topic, message, decoded_payload)

        except json.JSONDecodeError:
            print(f"Error decoding JSON payload: {payload.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"Error processing message on topic '{topic}': {str(e)}")


    def _decode_lw004_pb_payload(self, payload_data, fport):
        """Enhanced decoder for LW004-PB payload"""
        try:
            binary_data = base64.b64decode(payload_data)
        except Exception as e:
            return {"error": f"Invalid Base64 payload: {e}", "raw_payload": payload_data}

        result = {"raw_hex": binary_data.hex()}
        data_len = len(binary_data)

        if data_len < 4:
            result["error"] = "Payload too short for standard header"
            return result

        # --- Standard Header (Bytes 0-3) ---
        try:
            # Byte 0: Battery Level and Charging Status
            result["battery_level"] = binary_data[0] & 0x7F
            result["is_charging"] = (binary_data[0] & 0x80) > 0
            result["battery"] = f"{result['battery_level']}%" + (" (Charging)" if result["is_charging"] else "")

            # Byte 1: Device Mode and Auxiliary Operation
            device_status = binary_data[1]
            device_mode_code = (device_status >> 4) & 0x0F
            auxiliary_op_code = device_status & 0x0F

            device_modes = {1: "Standby", 2: "Timing", 3: "Periodic", 4: "Motion Stationary",
                            5: "Motion Start", 6: "In Motion", 7: "Motion End"}
            aux_operations = {0: "None", 1: "Downlink Request", 2: "Man Down",
                              3: "Alert Alarm", 4: "SOS Alarm"}

            result["device_mode_code"] = device_mode_code
            result["auxiliary_operation_code"] = auxiliary_op_code
            result["device_mode"] = device_modes.get(device_mode_code, f"Unknown ({device_mode_code})")
            result["auxiliary_operation"] = aux_operations.get(auxiliary_op_code, f"Unknown ({auxiliary_op_code})")

            # Bytes 2-3: Age (seconds)
            result["age"] = int.from_bytes(binary_data[2:4], byteorder='big')

        except IndexError:
            result["error"] = "Payload too short for standard header fields."
            return result
        except Exception as e:
            result["error"] = f"Error parsing standard header: {e}"
            return result


        # --- FPort Specific Payloads ---
        try:
            # FPort 8 or 12: Bluetooth Location Fixed Payload
            if fport in [8, 12] and data_len >= 4:
                beacons = []
                offset = 4
                while offset + 7 <= data_len: # 6 bytes MAC + 1 byte RSSI
                    mac_bytes = binary_data[offset:offset + 6]
                    mac_address = ':'.join(f'{b:02X}' for b in mac_bytes)
                    rssi_byte = binary_data[offset + 6]
                    rssi = rssi_byte - 256 if rssi_byte > 127 else rssi_byte
                    est_distance = self.estimate_distance(rssi)

                    beacons.append({
                        "mac": mac_address,
                        "rssi": rssi,
                        "rssi_str": f"{rssi} dBm",
                        "estimated_distance": est_distance
                    })
                    offset += 7
                result["beacons"] = beacons
                result["beacon_count"] = len(beacons)

            # FPort 9 or 13: Bluetooth Location Failure Payload
            elif fport in [9, 13] and data_len >= 5:
                failure_code = binary_data[4]
                failure_reasons = {1: "Hardware Error", 2: "Downlink Interrupt", 3: "Man Down Interrupt",
                                   4: "Alarm Interrupt", 5: "Positioning Timeout", 6: "Broadcasting Busy",
                                   7: "End Motion Interrupt", 8: "Start Motion Interrupt",
                                   9: "GPS PDOP Limit", 10: "Other"}
                result["failure_reason_code"] = failure_code
                result["failure_reason"] = failure_reasons.get(failure_code, f"Unknown ({failure_code})")

            # FPort 1: Event Message Payload (including timestamp)
            elif fport == 1 and data_len >= 7:
                # Bytes 3-6: Timestamp (Unix epoch)
                timestamp_unix = int.from_bytes(binary_data[3:7], byteorder='big')
                result["timestamp_unix"] = timestamp_unix
                try:
                    # Use timezone-aware datetime objects (Python 3.3+)
                    # Replace utcfromtimestamp with fromtimestamp using UTC timezone
                    result["timestamp_utc"] = datetime.fromtimestamp(timestamp_unix, timezone.utc).isoformat().replace('+00:00', 'Z')
                except ValueError:
                    result["timestamp_utc"] = "Invalid Timestamp"

                # Byte 2: Time Zone (Offset from UTC in 30-min increments)
                # Handle potential signed byte interpretation carefully
                time_zone_byte = binary_data[2]
                time_zone_offset_half_hours = time_zone_byte if time_zone_byte < 128 else time_zone_byte - 256
                time_zone_offset_hours = time_zone_offset_half_hours / 2.0
                result["timezone_offset_hours"] = time_zone_offset_hours
                result["timezone"] = f"UTC{time_zone_offset_hours:+.1f}"

                # Byte 7: Event Type Code (if present)
                if data_len >= 8:
                    event_code = binary_data[7]
                    event_types = {0: "Start Movement", 1: "In Movement", 2: "End Movement",
                                 3: "SOS Alarm Start", 4: "SOS Alarm End", 5: "Alert Alarm Start",
                                 6: "Alert Alarm End", 7: "Man Down Start", 8: "Man Down End"}
                    result["event_type_code"] = event_code
                    result["event_type"] = event_types.get(event_code, f"Unknown ({event_code})")

        except IndexError:
             result["warning"] = "Payload ended unexpectedly during FPort-specific parsing."
        except Exception as e:
             result["warning"] = f"Error parsing FPort-specific data: {e}"


        return result


    def estimate_distance(self, rssi, measured_power=-65, n=2.5):
        """Estimate distance based on RSSI"""
        if rssi is None or not isinstance(rssi, (int, float)):
            return None
        try:
            # Path Loss Model: distance = 10 ** ((measured_power - rssi) / (10 * n))
            # Prevent division by zero or log of non-positive if rssi == measured_power
            if rssi == measured_power:
                return 1.0 # Assume 1 meter if RSSI matches measured power at 1m
            ratio = (measured_power - rssi) / (10 * n)
            distance = pow(10, ratio)
            return round(distance, 2)
        except Exception:
            # Catch potential math errors
            return None

# --- Main Application Class (Combined) ---
class CombinedApp:
    """Combined Beacon Alert and Management System Application"""

    def __init__(self, root):
        """Initialize the application"""
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("950x700") # Adjusted size
        self.root.minsize(800, 600)

        # --- Core Components ---
        self.settings = SettingsManager()
        self.db = BeaconDatabase() # Use the more featured DB from admin.py
        self.alarm_history = self.load_alarm_history()
        self.beacons_mapping = {}
        self.load_beacons_mapping() # Load mapping on init

        self.aws_client = None
        self.aws_connection_status = tk.StringVar(value="Disconnected")
        self.clipboard_mac = "" # For clipboard operations

        # --- Admin State ---
        self.admin_logged_in = False
        self.current_admin_password = DEFAULT_ADMIN_PASSWORD # Store password in memory

        # --- UI Setup ---
        self.setup_styles()
        self.create_menu() # Create menu first
        self.create_main_ui() # Create the client-focused main UI
        self.admin_dashboard_window = None # Placeholders for admin windows
        self.admin_beacons_window = None
        self.admin_logs_window = None
        self.admin_settings_window = None

        # --- Auto-Connect & Reconnect ---
        self.connect_to_aws()
        # Consider starting auto-reconnect thread later or making it optional
        # threading.Thread(target=self.auto_reconnect, daemon=True).start()

        # --- Initial Status ---
        self.update_status_bar(f"{APP_TITLE} v{APP_VERSION} - Ready")
        self.update_aws_connection_display() # Update display based on initial connection attempt


    def setup_styles(self):
        """Setup custom styles for the application"""
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        else:
             style.theme_use(style.theme_names()[0]) # Use default if clam not available


        # Configure colors (example, adjust as needed)
        bg_color = "#f0f0f0"
        accent_color = "#1e88e5"
        button_bg = "#e0e0e0"
        header_bg = "#34495e" # Darker header
        header_fg = "white"
        alert_color = "#e74c3c" # Red for alerts

        # Configure specific styles
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, font=("Segoe UI", 10))
        style.configure("TButton", background=button_bg, font=("Segoe UI", 10), padding=5)
        style.map("TButton", background=[('active', accent_color), ('!disabled', button_bg)])
        style.configure("TEntry", font=("Segoe UI", 10), padding=5)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[10, 5])
        style.configure("TLabelframe", background=bg_color, font=("Segoe UI", 11, "bold"))
        style.configure("TLabelframe.Label", background=bg_color, foreground="#333")


        # Header style
        style.configure("Header.TFrame", background=header_bg)
        style.configure("Header.TLabel", background=header_bg, foreground=header_fg, font=("Segoe UI", 12, "bold"))

        # Action buttons
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))

        # Treeview style
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=25)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[('selected', accent_color)])

        # Status indicators
        style.configure("Connected.TLabel", foreground="#2ecc71", font=("Segoe UI", 9, "bold")) # Green
        style.configure("Disconnected.TLabel", foreground=alert_color, font=("Segoe UI", 9, "bold")) # Red
        style.configure("Connecting.TLabel", foreground="#f39c12", font=("Segoe UI", 9, "bold")) # Orange

    def create_menu(self):
        """Create application menu"""
        self.menu = tk.Menu(self.root)
        self.root.config(menu=self.menu)

        # --- File Menu ---
        file_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Admin Login", command=self.prompt_admin_login)
        # Admin-specific items will be added later if login is successful
        self.admin_menu_separator = file_menu.add_separator() # Store separator index if needed
        self.admin_settings_menu_index = file_menu.index("end") # Placeholder index

        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit)

        # --- History Menu ---
        history_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="History", menu=history_menu)
        history_menu.add_command(label="Refresh", command=self.refresh_history_display)
        history_menu.add_command(label="Export", command=self.export_history)
        history_menu.add_command(label="Clear", command=self.clear_history)

        # --- Help Menu ---
        help_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def enable_admin_features(self):
        """Add admin-specific menu items after successful login"""
        file_menu = self.menu.winfo_children()[0] # Assuming File menu is the first

        # Check if already added to prevent duplicates
        if file_menu.index("end") > self.admin_settings_menu_index + 3: # Check if items were added
            return
        
        # Insert admin items before the last separator
        file_menu.insert_command(self.admin_settings_menu_index + 1, label="Admin Dashboard", command=self.show_admin_dashboard)
        file_menu.insert_command(self.admin_settings_menu_index + 2, label="Beacon Management", command=self.show_beacon_management)
        file_menu.insert_command(self.admin_settings_menu_index + 3, label="Activity Logs", command=self.show_activity_logs)
        file_menu.insert_command(self.admin_settings_menu_index + 4, label="Admin Settings", command=self.show_admin_settings_window)
        # Add logout option
        file_menu.insert_command(self.admin_settings_menu_index + 5, label="Admin Logout", command=self.admin_logout)


    def disable_admin_features(self):
        """Remove admin-specific menu items on logout"""
        file_menu = self.menu.winfo_children()[0] # Assuming File menu is the first
        try:
             # Remove items in reverse order of addition
             file_menu.delete("Admin Logout")
             file_menu.delete("Admin Settings")
             file_menu.delete("Activity Logs")
             file_menu.delete("Beacon Management")
             file_menu.delete("Admin Dashboard")
        except tk.TclError as e:
             print(f"Error removing admin menu items (might be already removed): {e}")

        # Close any open admin windows
        if self.admin_dashboard_window and self.admin_dashboard_window.winfo_exists():
            self.admin_dashboard_window.destroy()
        if self.admin_beacons_window and self.admin_beacons_window.winfo_exists():
            self.admin_beacons_window.destroy()
        if self.admin_logs_window and self.admin_logs_window.winfo_exists():
            self.admin_logs_window.destroy()
        if self.admin_settings_window and self.admin_settings_window.winfo_exists():
            self.admin_settings_window.destroy()


    def prompt_admin_login(self):
        """Prompt for admin password"""
        if self.admin_logged_in:
             messagebox.showinfo("Admin Login", "Already logged in as Admin.")
             return

        password = simpledialog.askstring("Admin Login", "Enter Admin Password:", show='*', parent=self.root)
        if password == self.current_admin_password:
            self.admin_logged_in = True
            messagebox.showinfo("Login Success", "Admin login successful.", parent=self.root)
            self.enable_admin_features()
            self.update_status_bar("Admin logged in.")
        elif password is not None: # Avoid error message if cancelled
            messagebox.showerror("Login Failed", "Incorrect password.", parent=self.root)
            self.update_status_bar("Admin login failed.")

    def admin_logout(self):
        """Log out the admin user"""
        self.admin_logged_in = False
        self.disable_admin_features()
        messagebox.showinfo("Logout", "Admin logout successful.", parent=self.root)
        self.update_status_bar("Admin logged out.")

    def change_admin_password_dialog(self, parent_window):
         """Dialog to change the admin password (called from admin settings)"""
         if not self.admin_logged_in:
              messagebox.showerror("Error", "Admin access required.", parent=parent_window)
              return

         new_password = simpledialog.askstring("Change Admin Password", "Enter new password:", show='*', parent=parent_window)
         if not new_password:
              return # Cancelled

         confirm_password = simpledialog.askstring("Change Admin Password", "Confirm new password:", show='*', parent=parent_window)
         if not confirm_password:
             return # Cancelled

         if new_password == confirm_password:
             self.current_admin_password = new_password
             messagebox.showinfo("Success", "Admin password updated successfully.\n(Note: Password resets when application closes)", parent=parent_window)
         else:
             messagebox.showerror("Error", "Passwords do not match.", parent=parent_window)


    def create_main_ui(self):
        """Create the main client UI (History View)"""
        # Header frame
        header_frame = ttk.Frame(self.root, style="Header.TFrame")
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text=APP_TITLE, style="Header.TLabel").pack(side=tk.LEFT, padx=15, pady=10)
        self.aws_status_label = ttk.Label(header_frame, textvariable=self.aws_connection_status) # Style set in update method
        self.aws_status_label.pack(side=tk.RIGHT, padx=15, pady=10)

        # Main content area
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # History label frame
        history_frame = ttk.LabelFrame(main_frame, text="Alarm History", padding=10)
        history_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar for history actions
        toolbar_frame = ttk.Frame(history_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))

        # Action buttons
        actions_frame = ttk.Frame(toolbar_frame)
        actions_frame.pack(side=tk.LEFT)
        ttk.Button(actions_frame, text="Refresh", style="Action.TButton", command=self.refresh_history_display, width=10).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(actions_frame, text="Export", style="Action.TButton", command=self.export_history, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Clear", style="Action.TButton", command=self.clear_history, width=10).pack(side=tk.LEFT, padx=5)

        # Search box
        search_frame = ttk.Frame(toolbar_frame)
        search_frame.pack(side=tk.RIGHT)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=25)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind("<KeyRelease>", lambda event: self.refresh_history_display())

        # History display area
        self.history_text = scrolledtext.ScrolledText(
            history_frame, wrap=tk.WORD, font=("Segoe UI", 10), background="white", relief="flat", borderwidth=1
        )
        self.history_text.pack(fill=tk.BOTH, expand=True)
        self.history_text.config(state=tk.DISABLED) # Start disabled

        # Status bar
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(10, 3))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Display initial history
        self.refresh_history_display()


    # --- AWS Connection Handling ---
    def connect_to_aws(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE:
            self.update_status_bar("AWS IoT SDK not installed. Cannot connect.")
            messagebox.showwarning("AWS SDK Missing", "AWS IoT SDK not found. Please install it using 'pip install awsiotsdk' to enable AWS features.", parent=self.root)
            return

        if self.aws_client and self.aws_client.connected:
            self.update_status_bar("Already connected to AWS IoT Core.")
            # messagebox.showinfo("AWS Connection", "Already connected.", parent=self.root)
            return

        if self.aws_client and self.aws_client.is_connecting:
             self.update_status_bar("AWS connection already in progress...")
             return

        self.aws_connection_status.set("Connecting...")
        self.update_aws_connection_display()
        self.update_status_bar("Attempting to connect to AWS IoT Core...")

        # Ensure LoRaClient is instantiated
        if not self.aws_client:
            self.aws_client = LoRaClient(self.settings, message_callback=self.handle_aws_message)

        # Run connection in a separate thread to avoid blocking UI
        threading.Thread(target=self._aws_connect_thread, daemon=True).start()

    def _aws_connect_thread(self):
        """Background thread for AWS connection"""
        if not self.aws_client:
             print("Error: AWS client not initialized.") # Should not happen
             self.root.after(0, lambda: self.aws_connection_status.set("Disconnected"))
             self.root.after(0, self.update_aws_connection_display)
             self.root.after(0, lambda: self.update_status_bar("Error: AWS client not ready."))
             return

        if self.aws_client.connect():
            self.root.after(0, lambda: self.aws_connection_status.set("Connected"))
            self.root.after(0, lambda: self.update_status_bar(f"Connected to AWS: {self.settings.get('aws_endpoint')}"))
        else:
            self.root.after(0, lambda: self.aws_connection_status.set("Disconnected"))
            self.root.after(0, lambda: self.update_status_bar("Failed to connect to AWS IoT Core. Check settings."))
            # No automatic messagebox here, rely on LoRaClient's messages for specifics

        # Update display regardless of outcome
        self.root.after(0, self.update_aws_connection_display)

    def disconnect_from_aws(self):
        """Disconnect from AWS IoT Core"""
        if not self.aws_client or not self.aws_client.connected:
            self.update_status_bar("Not currently connected to AWS IoT Core.")
            # messagebox.showinfo("AWS Connection", "Not currently connected.", parent=self.root)
            return

        self.update_status_bar("Disconnecting from AWS IoT Core...")
        # Run disconnect in thread
        threading.Thread(target=self._aws_disconnect_thread, daemon=True).start()

    def _aws_disconnect_thread(self):
         if self.aws_client.disconnect():
              self.root.after(0, lambda: self.aws_connection_status.set("Disconnected"))
              self.root.after(0, lambda: self.update_status_bar("Disconnected from AWS IoT Core."))
         else:
              self.root.after(0, lambda: self.update_status_bar("Error during AWS disconnection."))
              # Still update status to disconnected as the attempt was made
              self.root.after(0, lambda: self.aws_connection_status.set("Disconnected"))
         self.root.after(0, self.update_aws_connection_display)


    def check_aws_connection(self):
        """Check and display AWS connection status"""
        if self.aws_client and self.aws_client.connected:
             messagebox.showinfo("AWS Connection Status",
                                f"Status: Connected\n"
                                f"Endpoint: {self.settings.get('aws_endpoint')}\n"
                                f"Client ID: {self.settings.get('client_id')}\n"
                                f"Subscribed Topic: {self.settings.get('topic')}\n"
                                f"Alert Topic: {self.settings.get('alert_topic')}",
                                parent=self.root)
        else:
             status = "Disconnected"
             if self.aws_client and self.aws_client.is_connecting:
                  status = "Connecting..."
             messagebox.showinfo("AWS Connection Status", f"Status: {status}", parent=self.root)


    def update_aws_connection_display(self):
         """Update the visual style of the connection status label"""
         status = self.aws_connection_status.get()
         if status == "Connected":
              self.aws_status_label.configure(style="Connected.TLabel")
         elif status == "Connecting...":
              self.aws_status_label.configure(style="Connecting.TLabel")
         else: # Disconnected or error
              self.aws_status_label.configure(style="Disconnected.TLabel")


    # ==============================================================
    # --- Modified handle_aws_message Function ---
    # ==============================================================
    def handle_aws_message(self, topic, message, decoded_payload):
        """Handle messages from AWS IoT Core, identifying closest beacon for alerts"""
        print(f"Callback: Message received on topic '{topic}'")
        try:
            timestamp = datetime.now().isoformat()
            alert_topic = self.settings.get('alert_topic', DEFAULT_ALERT_TOPIC)

            # Determine if this message indicates an alert condition
            is_alert = False
            if decoded_payload:
                aux_op = decoded_payload.get("auxiliary_operation", "")
                if "Alert Alarm" in aux_op or "SOS Alarm" in aux_op:
                    is_alert = True
            if not is_alert and alert_topic and topic.startswith(alert_topic.replace('#', '').replace('+', '')):
                 is_alert = True

            # --- Initialize Alert Data ---
            # Default to using the button's device ID and gateway RSSI
            alert_mac = message.get("WirelessDeviceId") # Button/Device ID from message metadata
            alert_room = "Unknown Source"
            alert_desc = ""
            alert_rssi = None # Use gateway RSSI as fallback

            # Try to get gateway RSSI if available
            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                lorawan = message["WirelessMetadata"]["LoRaWAN"]
                if lorawan.get("Gateways") and isinstance(lorawan["Gateways"], list) and len(lorawan["Gateways"]) > 0:
                    alert_rssi = lorawan["Gateways"][0].get("Rssi") # Gateway RSSI


            # --- Find Closest Beacon from Payload (if available) ---
            closest_beacon = None
            min_distance = float('inf')

            if decoded_payload and "beacons" in decoded_payload and decoded_payload["beacons"]:
                detected_beacons = decoded_payload["beacons"]
                print(f"Detected {len(detected_beacons)} beacons in payload.") # Debug print

                # Loop through detected beacons to find the closest one
                for beacon in detected_beacons:
                    mac = beacon.get("mac")
                    dist = beacon.get("estimated_distance")
                    rssi = beacon.get("rssi")

                    # Update the signal info for this specific beacon in the database
                    self.db.update_beacon_signal(
                        mac, rssi,
                        battery_level=decoded_payload.get("battery_level"), # Use main device battery for now
                        is_charging=decoded_payload.get("is_charging"),     # Use main device charging status
                        device_mode=decoded_payload.get("device_mode"),       # Use main device mode
                        auxiliary_operation=decoded_payload.get("auxiliary_operation"), # Use main device aux op
                        estimated_distance=dist
                    )

                    # Check if this beacon is closer than the current minimum
                    if mac and dist is not None and dist < min_distance:
                        # Check if this closer beacon is actually mapped
                        mapping_info = self.beacons_mapping.get(mac)
                        if mapping_info: # Only consider mapped beacons as the 'closest known'
                             min_distance = dist
                             closest_beacon = beacon
                             print(f"New closest mapped beacon found: {mac} at {dist}m") # Debug print


                # If a closest mapped beacon was found, use its details for the alert
                if closest_beacon:
                    alert_mac = closest_beacon.get("mac")
                    alert_rssi = closest_beacon.get("rssi") # Use the closest beacon's RSSI
                    mapping_info = self.beacons_mapping.get(alert_mac)
                    if mapping_info:
                        alert_room = mapping_info.get("room_number", "Mapping Error")
                        alert_desc = mapping_info.get("description", "")
                    else:
                        # This case should technically not happen due to the check above,
                        # but handle defensively
                        alert_room = "Unknown Beacon (Closest)"
                else:
                    print("No *mapped* beacons found in payload or distances invalid.")
                    # Keep fallback to device ID if no mapped beacons detected or closest

            else: # No beacons array in payload, update signal for the main device ID
                print("No 'beacons' array in decoded payload. Using WirelessDeviceId.")
                # Update signal info for the primary device (button) if possible
                if alert_mac:
                    self.db.update_beacon_signal(
                        alert_mac, alert_rssi, # Use gateway RSSI
                        battery_level=decoded_payload.get("battery_level"),
                        is_charging=decoded_payload.get("is_charging"),
                        device_mode=decoded_payload.get("device_mode"),
                        auxiliary_operation=decoded_payload.get("auxiliary_operation")
                        # No estimated distance here
                    )

            # --- Look up room for the determined alert_mac (closest mapped or fallback device ID) ---
            if alert_mac: # Ensure we have a MAC to look up
                mapping_info = self.beacons_mapping.get(alert_mac)
                if mapping_info:
                    # Only override if we didn't already set it from the closest beacon loop
                    if closest_beacon is None:
                         alert_room = mapping_info.get("room_number", "Mapping Error")
                         alert_desc = mapping_info.get("description", "")
                else:
                     # Only set to unknown if we didn't find a closest beacon and the device ID isn't mapped
                    if closest_beacon is None:
                         alert_room = "Unknown Beacon (Not Mapped)"


            # --- Log Activity ---
            log_details = f"Topic: {topic}, ClosestMAC: {alert_mac}, Room: {alert_room}, RSSI: {alert_rssi}, Decoded: {json.dumps(decoded_payload)}"
            beacon_db_id = None
            if alert_mac:
                 beacon_record = self.db.get_beacon_by_mac(alert_mac)
                 if beacon_record:
                      beacon_db_id = beacon_record[0] # Get the ID for the closest/alerting beacon

            self.db.log_activity("MQTT_MSG", log_details, beacon_id=beacon_db_id)


            # --- If Alert, Store Data and Notify ---
            if is_alert:
                alert_data = {
                    "timestamp": timestamp,
                    "topic": topic,
                    "room_number": alert_room, # Use the determined room
                    "beacon_mac": alert_mac,   # Use the determined MAC (closest or fallback)
                    "description": alert_desc, # Use the determined description
                    "rssi": alert_rssi,        # Use the determined RSSI (closest or fallback)
                    "message_details": message, # Store the raw message too if needed
                    "decoded_payload": decoded_payload
                }

                # Add to alarm history list
                self.alarm_history.append(alert_data)
                self.save_alarm_history() # Save immediately
                self.refresh_history_display() # Update the UI
                self.show_alert_notification(alert_data) # Show popup

            # Refresh admin dashboard if open and auto-refresh is on
            if self.admin_dashboard_window and self.admin_dashboard_window.winfo_exists():
                if hasattr(self, 'admin_dashboard_auto_refresh_var') and self.admin_dashboard_auto_refresh_var.get():
                     # Use after() to schedule the update on the main thread
                     self.root.after(100, self.refresh_admin_dashboard_data) # Delay slightly


        except Exception as e:
            # Use sys module to get detailed traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            error_message = f"Error handling AWS message processing: {str(e)}\n{traceback_details}"
            print(error_message)
            # Optionally log this error to DB or file
            self.db.log_activity("ERROR", f"Failed processing message on {topic}: {e}")
    # ==============================================================
    # --- End of Modified handle_aws_message Function ---
    # ==============================================================


    # --- History Handling (from client.py) ---
    def load_alarm_history(self):
        """Load alarm history from file"""
        if os.path.exists(ALARM_HISTORY_FILE):
            try:
                with open(ALARM_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    # Handle empty file case
                    content = f.read()
                    if not content:
                        return []
                    return json.loads(content)
            except json.JSONDecodeError:
                 print(f"Error: Alarm history file ({ALARM_HISTORY_FILE}) is corrupted. Creating a new one.")
                 # Optionally backup the corrupted file
                 # os.rename(ALARM_HISTORY_FILE, ALARM_HISTORY_FILE + ".corrupted")
                 return [] # Return empty list
            except Exception as e:
                print(f"Error loading alarm history: {e}")
                return [] # Return empty list on other errors
        return []


    def save_alarm_history(self):
        """Save alarm history to file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(ALARM_HISTORY_FILE), exist_ok=True)
            with open(ALARM_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.alarm_history, f, indent=4)
        except Exception as e:
            print(f"Error saving alarm history: {e}")
            messagebox.showerror("Save Error", f"Could not save alarm history:\n{e}", parent=self.root)

    def refresh_history_display(self):
        """Refresh the alarm history display"""
        if not hasattr(self, 'history_text') or not self.history_text.winfo_exists():
             return # Avoid error if UI not ready

        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete(1.0, tk.END)

        # Configure tags for better display
        self.history_text.tag_configure('heading', font=("Segoe UI", 14, "bold"), foreground="#e74c3c") # Red heading for alerts
        self.history_text.tag_configure('date', font=("Segoe UI", 10), foreground="#555")
        self.history_text.tag_configure('room', font=("Segoe UI", 12, "bold"), foreground="#555") # Blue for room
        self.history_text.tag_configure('mac', font=("Consolas", 10), foreground="#3f51b5")
        self.history_text.tag_configure('desc', font=("Segoe UI", 10, "italic"), foreground="#555") # Grey italic for desc
        self.history_text.tag_configure('label', font=("Segoe UI", 10, "bold"), foreground="black")
        self.history_text.tag_configure('value', font=("Segoe UI", 10), foreground="black") 
        self.history_text.tag_configure("empty", justify="center", font=("Segoe UI", 12, "italic"), foreground="#9e9e9e")

        if not self.alarm_history:
            self.history_text.insert(tk.END, "Alarm history is empty.", "empty")
            self.history_text.config(state=tk.DISABLED)
            self.update_status_bar("Alarm history is empty.")
            return

        # Get search filter
        search_text = self.search_var.get().lower()

        # Sort history by timestamp (newest first)
        try:
             sorted_history = sorted(
                 [alarm for alarm in self.alarm_history if isinstance(alarm, dict) and 'timestamp' in alarm], # Filter out invalid entries
                 key=lambda x: x.get('timestamp', '0'), # Default to oldest if timestamp missing
                 reverse=True
             )
        except Exception as e:
             print(f"Error sorting history: {e}")
             messagebox.showerror("History Error", "Could not sort alarm history.", parent=self.root)
             sorted_history = self.alarm_history # Show unsorted if error

        displayed_count = 0
        total_alarms = len(sorted_history) # Get total before filtering

        for i, alarm in enumerate(sorted_history):
             # Basic check if alarm is a dict
             if not isinstance(alarm, dict):
                  print(f"Skipping invalid history entry: {alarm}")
                  continue

             # Format entry text for searching
             try:
                 alarm_str = f"{alarm.get('timestamp','')} {alarm.get('room_number','')} {alarm.get('beacon_mac','')} {alarm.get('description','')}"
                 alarm_str = alarm_str.lower()
             except Exception:
                 alarm_str = "" # Handle potential errors in getting values

             # Skip if doesn't match search criteria
             if search_text and search_text not in alarm_str:
                continue

            # Format timestamp
             try:
                 dt_str = alarm.get('timestamp', '')
                 if dt_str:
                      # Handle potential timezone info if present (e.g., 'Z' or '+HH:MM')
                      if dt_str.endswith('Z'):
                          dt_str = dt_str[:-1] + '+00:00'
                      # Ensure dt is timezone-aware if it has offset, otherwise assume local
                      if '+' in dt_str or '-' in dt_str[10:]: # Check for offset info
                           dt = datetime.fromisoformat(dt_str)
                      else: # Assume naive timestamp is local
                           dt_naive = datetime.fromisoformat(dt_str)
                           dt = dt_naive.astimezone() # Convert to local timezone-aware

                      timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S %Z") # Display timezone
                 else:
                      timestamp_str = "Unknown Time"
             except ValueError:
                 timestamp_str = alarm.get('timestamp', 'Invalid Time Format')
             except Exception as e:
                 timestamp_str = f"Time Error: {e}"


             room = alarm.get('room_number', 'Unknown')
             beacon_mac = alarm.get('beacon_mac', 'N/A')
             description = alarm.get('description', '') # Get description from alert data

             # Format entry
             self.history_text.insert(tk.END, f"🚨 ALARM #{total_alarms - i}\n", 'heading') # Number newest as #1 based on total alarms
             self.history_text.insert(tk.END, f"{timestamp_str}\n", 'date')
             self.history_text.insert(tk.END, f"Room: ", 'label')
             self.history_text.insert(tk.END, f"{room}\n", 'room')
             if description:
                  self.history_text.insert(tk.END, f"Desc: ", 'label')
                  self.history_text.insert(tk.END, f"{description}\n", 'desc')
             self.history_text.insert(tk.END, f"Beacon: ", 'label')
             self.history_text.insert(tk.END, f"{beacon_mac}\n", 'mac')
             self.history_text.insert(tk.END, f"RSSI: ", 'label')
             self.history_text.insert(tk.END, f"{alarm.get('rssi', 'N/A')}\n", 'value')

             # Optionally add more decoded details if needed
             # decoded = alarm.get('decoded_payload', {})
             # if decoded:
             #     self.history_text.insert(tk.END, f"Mode: {decoded.get('device_mode', 'N/A')}\n", 'value')
             #     self.history_text.insert(tk.END, f"Battery: {decoded.get('battery', 'N/A')}\n", 'value')


             self.history_text.insert(tk.END, "-" * 60 + "\n\n")
             displayed_count += 1

        # If nothing to display after filtering or initially
        if displayed_count == 0:
             if search_text:
                  self.history_text.insert(tk.END, f"No alarms found matching '{search_text}'.", "empty")
             elif not self.alarm_history: # Check again if the list itself is empty
                  self.history_text.insert(tk.END, "Alarm history is empty.", "empty")


        # Update status bar
        status_msg = f"Displayed {displayed_count} of {total_alarms} alarms."
        if search_text:
            status_msg += f" (Filter: '{search_text}')"
        self.update_status_bar(status_msg)

        self.history_text.config(state=tk.DISABLED)
        self.history_text.yview(tk.END) # Scroll to the bottom (most recent)


    def export_history(self):
        """Export alarm history to a JSON file"""
        if not self.alarm_history:
            messagebox.showinfo("Export History", "No history to export.", parent=self.root)
            return

        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Alarm History",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"alarm_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if not filename:
            return # User cancelled

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.alarm_history, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Export Complete", f"Alarm history successfully exported to:\n{filename}", parent=self.root)
            self.update_status_bar(f"History exported to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export alarm history:\n{e}", parent=self.root)
            self.update_status_bar("History export failed.")

    def clear_history(self):
        """Clear alarm history after confirmation"""
        if not self.alarm_history:
            messagebox.showinfo("Clear History", "No history to clear.", parent=self.root)
            return

        if messagebox.askyesno("Confirm Clear", "Are you sure you want to permanently delete all alarm history entries?", parent=self.root):
            self.alarm_history = []
            self.save_alarm_history() # Save the empty list
            self.refresh_history_display()
            messagebox.showinfo("Clear History", "Alarm history has been cleared.", parent=self.root)
            self.update_status_bar("Alarm history cleared.")

    # --- Alert Notification (from client.py, enhanced) ---
    def show_alert_notification(self, alert_data):
        """Show a fullscreen notification for a new alert"""
        # Create a new top-level window
        alert_window = tk.Toplevel(self.root)
        alert_window.title("🚨 ALARM! 🚨")
        alert_window.attributes("-topmost", True)
        alert_window.attributes("-fullscreen", True) # Make it fullscreen
        alert_window.configure(background="red") # Start with red background

        # --- Blinking Effect ---
        self.blink_on = True
        def blink():
            if not alert_window.winfo_exists(): # Stop if window closed
                 return
            current_color = "red" if self.blink_on else "black"
            alert_window.configure(background=current_color)
            # Also configure child frames/labels if needed
            for widget in alert_window.winfo_children():
                try: # Set background for ttk widgets differently
                    if isinstance(widget, ttk.Frame) or isinstance(widget, ttk.Label):
                         style_name = f"Blink.{widget.winfo_class()}"
                         style = ttk.Style()
                         style.configure(style_name, background=current_color)
                         widget.configure(style=style_name)
                    else:
                         widget.configure(background=current_color)
                except: pass # Ignore widgets that don't support background
            self.blink_on = not self.blink_on
            alert_window.after(500, blink) # Blink interval

        # --- Content Frame ---
        content_frame = ttk.Frame(alert_window, padding=50)
        content_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER) # Center content

        # Style for content frame needs to be dynamic for blinking
        style_name = f"Blink.{content_frame.winfo_class()}"
        style = ttk.Style()
        style.configure(style_name, background="red") # Initial background
        content_frame.configure(style=style_name)


        # --- Alert Details ---
        room = alert_data.get("room_number", "Unknown")
        beacon_mac = alert_data.get("beacon_mac", "N/A")
        description = alert_data.get("description", "")
        timestamp_str = alert_data.get("timestamp", "")
        try:
            if timestamp_str:
                # Handle timezone 'Z' and offsets for display
                dt_str = timestamp_str
                if dt_str.endswith('Z'):
                     dt_str = dt_str[:-1] + '+00:00'
                if '+' in dt_str or '-' in dt_str[10:]:
                     dt = datetime.fromisoformat(dt_str)
                else:
                     dt = datetime.fromisoformat(dt_str).astimezone() # Assume local if naive

                time_display = dt.strftime("%Y-%m-%d %H:%M:%S %Z") # Display timezone
            else:
                time_display = "No Timestamp"
        except Exception as e:
            print(f"Error formatting time for alert popup: {e}")
            time_display = "Invalid Time"


        # Configure label styles for blinking background
        label_style_name = f"Blink.TLabel"
        style.configure(label_style_name, background="red", foreground="white", anchor="center")

        ttk.Label(content_frame, text="🚨 ATTENTION: ALARM! 🚨", font=("Arial", 48, "bold"), style=label_style_name).pack(pady=20)
        ttk.Label(content_frame, text=f"ROOM: {room}", font=("Arial", 72, "bold"), style=label_style_name).pack(pady=10)
        if description:
             ttk.Label(content_frame, text=description, font=("Arial", 36), style=label_style_name).pack(pady=10)
        ttk.Label(content_frame, text=f"Beacon: {beacon_mac}", font=("Arial", 24), style=label_style_name).pack(pady=5)
        ttk.Label(content_frame, text=f"Time: {time_display}", font=("Arial", 18), style=label_style_name).pack(pady=5)

        # --- Close Button ---
        close_button = tk.Button(
            content_frame,
            text="CLOSE ALARM (ESC)",
            command=alert_window.destroy,
            font=("Arial", 20, "bold"),
            bg="white", fg="red",
            padx=30, pady=15, relief=tk.RAISED, bd=5
        )
        close_button.pack(pady=40)

        # Bind Escape key to close
        alert_window.bind("<Escape>", lambda e: alert_window.destroy())

        # Start blinking
        blink()

        # Optional: Auto-close after a timeout (e.g., 60 seconds)
        # alert_window.after(60000, lambda: alert_window.destroy() if alert_window.winfo_exists() else None)

        alert_window.focus_force() # Bring window to front


    # --- Beacon Mapping Handling (Loads from DB) ---
    def load_beacons_mapping(self):
        """Load beacon room mapping from the DATABASE for consistency"""
        self.beacons_mapping = {}
        try:
             all_db_beacons = self.db.get_all_beacons()
             for beacon_row in all_db_beacons:
                  # DB columns: id, mac_address, room_number, description, ...
                  mac = beacon_row[1]
                  room = beacon_row[2]
                  desc = beacon_row[3]
                  if mac:
                       self.beacons_mapping[mac.upper()] = {"room_number": room, "description": desc or ""} # Store MACs uppercase
             count = len(self.beacons_mapping)
             print(f"Loaded {count} beacons mapping from database.")
             self.update_status_bar(f"Loaded mapping for {count} beacons from DB.")
             return True

        except Exception as e:
             print(f"Error loading beacons mapping from database: {e}")
             self.update_status_bar("Error loading beacon mapping from DB.")
             return False


    # --- Admin Window Show Methods ---
    def show_admin_dashboard(self):
         if not self.admin_logged_in: return
         if self.admin_dashboard_window and self.admin_dashboard_window.winfo_exists():
              self.admin_dashboard_window.lift()
              return
         self.admin_dashboard_window = tk.Toplevel(self.root)
         self.admin_dashboard_window.title("Admin Dashboard")
         self.admin_dashboard_window.geometry("1000x700")
         self.setup_admin_dashboard(self.admin_dashboard_window) # Pass the new window

    def show_beacon_management(self):
         if not self.admin_logged_in: return
         if self.admin_beacons_window and self.admin_beacons_window.winfo_exists():
              self.admin_beacons_window.lift()
              return
         self.admin_beacons_window = tk.Toplevel(self.root)
         self.admin_beacons_window.title("Beacon Management")
         self.admin_beacons_window.geometry("1000x700")
         self.setup_beacons_tab(self.admin_beacons_window) # Pass the new window

    def show_activity_logs(self):
         if not self.admin_logged_in: return
         if self.admin_logs_window and self.admin_logs_window.winfo_exists():
              self.admin_logs_window.lift()
              return
         self.admin_logs_window = tk.Toplevel(self.root)
         self.admin_logs_window.title("Activity Logs")
         self.admin_logs_window.geometry("900x600")
         self.setup_logs_tab(self.admin_logs_window) # Pass the new window

    def show_admin_settings_window(self):
         if not self.admin_logged_in: return
         if self.admin_settings_window and self.admin_settings_window.winfo_exists():
             self.admin_settings_window.lift()
             return
         self.admin_settings_window = tk.Toplevel(self.root)
         self.admin_settings_window.title("Admin Settings")
         self.admin_settings_window.geometry("700x650") # Increased height for password change
         self.admin_settings_window.transient(self.root)
         self.admin_settings_window.grab_set()
         self.setup_settings_tab(self.admin_settings_window) # Pass the new window


    # --- Admin UI Setup Methods (Adapted from admin.py's BeaconApp) ---

    def setup_admin_dashboard(self, parent_window):
        """Setup enhanced dashboard tab (now in its own window)"""
        dashboard_frame = ttk.Frame(parent_window, padding=10)
        dashboard_frame.pack(fill=tk.BOTH, expand=True)

        # Paned window for layout
        dashboard_pane = ttk.PanedWindow(dashboard_frame, orient=tk.VERTICAL)
        dashboard_pane.pack(fill=tk.BOTH, expand=True)

        # Top frame: Connection & Stats
        top_frame = ttk.Frame(dashboard_pane)
        dashboard_pane.add(top_frame, weight=1)

        # --- Connection Frame ---
        conn_frame = ttk.LabelFrame(top_frame, text="Connection Status")
        conn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5, ipadx=5, ipady=5)

        # Use the main app's status variable
        ttk.Label(conn_frame, text="AWS IoT:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        conn_status_label = ttk.Label(conn_frame, textvariable=self.aws_connection_status)
        conn_status_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        # Apply style dynamically based on main app status
        def update_conn_label_style(*args):
            status = self.aws_connection_status.get()
            style = "Disconnected.TLabel"
            if status == "Connected": style = "Connected.TLabel"
            elif status == "Connecting...": style = "Connecting.TLabel"
            conn_status_label.configure(style=style)
        self.aws_connection_status.trace_add("write", update_conn_label_style)
        update_conn_label_style() # Initial setup

        ttk.Button(conn_frame, text="Connect", command=self.connect_to_aws).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(conn_frame, text="Disconnect", command=self.disconnect_from_aws).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Auto-refresh checkbutton
        self.admin_dashboard_auto_refresh_var = tk.BooleanVar(value=True) # Separate var for admin dashboard
        ttk.Checkbutton(conn_frame, text="Auto-refresh display", variable=self.admin_dashboard_auto_refresh_var).grid(
            row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)


        # --- Stats Frame ---
        stats_frame = ttk.LabelFrame(top_frame, text="Statistics")
        stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5, ipadx=5, ipady=5)

        self.admin_beacon_count_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Registered Beacons:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(stats_frame, textvariable=self.admin_beacon_count_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        self.admin_active_beacons_var = tk.StringVar(value="0")
        ttk.Label(stats_frame, text="Active Beacons (5 min):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(stats_frame, textvariable=self.admin_active_beacons_var).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        # Live Data section - split horizontally
        live_data_pane = ttk.PanedWindow(dashboard_pane, orient=tk.HORIZONTAL)
        dashboard_pane.add(live_data_pane, weight=4)

        # --- Active Beacons Panel ---
        active_frame = ttk.LabelFrame(live_data_pane, text="Active Beacons (Seen in last 5 mins)")
        live_data_pane.add(active_frame, weight=3) # Give more weight

        active_columns = ('mac', 'room', 'rssi', 'battery', 'distance', 'mode', 'last_seen')
        self.admin_active_tree = ttk.Treeview(active_frame, columns=active_columns, show='headings')

        col_widths = {'mac': 130, 'room': 70, 'rssi': 70, 'battery': 80, 'distance': 90, 'mode': 120, 'last_seen': 130}
        for col in active_columns:
             self.admin_active_tree.heading(col, text=col.replace('_', ' ').title())
             self.admin_active_tree.column(col, width=col_widths[col], anchor=tk.CENTER if col != 'mac' and col != 'mode' else tk.W)

        active_vsb = ttk.Scrollbar(active_frame, orient=tk.VERTICAL, command=self.admin_active_tree.yview)
        active_hsb = ttk.Scrollbar(active_frame, orient=tk.HORIZONTAL, command=self.admin_active_tree.xview)
        self.admin_active_tree.configure(yscrollcommand=active_vsb.set, xscrollcommand=active_hsb.set)

        active_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        active_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.admin_active_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Context menu for active tree
        self.admin_active_tree_menu = tk.Menu(self.admin_active_tree, tearoff=0)
        self.admin_active_tree_menu.add_command(label="Copy MAC Address", command=self.copy_mac_from_active_admin)
        self.admin_active_tree_menu.add_command(label="Register This Beacon", command=self.register_from_active_admin)
        self.admin_active_tree.bind("<Button-3>", self.show_active_tree_menu_admin)


        # --- Recent Events Panel ---
        events_frame = ttk.LabelFrame(live_data_pane, text="Recent Raw Events (MQTT)")
        live_data_pane.add(events_frame, weight=2)

        self.admin_recent_events = scrolledtext.ScrolledText(events_frame, height=10, wrap=tk.WORD, font=("Consolas", 9))
        self.admin_recent_events.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.admin_recent_events.configure(state=tk.DISABLED)

        # Context menu for events
        self.admin_recent_events_menu = tk.Menu(self.admin_recent_events, tearoff=0)
        self.admin_recent_events_menu.add_command(label="Copy Selected MAC", command=self.copy_mac_from_events_admin)
        self.admin_recent_events_menu.add_command(label="Register Selected MAC", command=self.register_from_events_admin)
        self.admin_recent_events.bind("<Button-3>", self.show_events_menu_admin)


        # Beacon details panel (bottom)
        details_frame = ttk.LabelFrame(dashboard_pane, text="Selected Beacon Details")
        dashboard_pane.add(details_frame, weight=2)

        self.admin_details_text = scrolledtext.ScrolledText(details_frame, height=8, wrap=tk.WORD, font=("Consolas", 10))
        self.admin_details_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.admin_details_text.configure(state=tk.DISABLED)
        self.admin_active_tree.bind('<<TreeviewSelect>>', self.show_beacon_details_admin)


        # Set pane positions
        dashboard_pane.sashpos(0, 120) # Position between top frame and live data
        live_data_pane.sashpos(0, 600) # Position between active beacons and events

        # Setup automatic refresh loop specific to this admin window
        self.setup_admin_dashboard_auto_refresh()

        # Initial data load
        self.refresh_admin_dashboard_data()


    def setup_admin_dashboard_auto_refresh(self):
        """Setup automatic refresh for the admin dashboard window"""
        def refresh_loop():
            # Only refresh if the window still exists and checkbox is checked
            if self.admin_dashboard_window and self.admin_dashboard_window.winfo_exists():
                if self.admin_dashboard_auto_refresh_var.get():
                    self.refresh_admin_dashboard_data()
                # Schedule next refresh regardless of checkbox state if window exists
                self.admin_dashboard_window.after(3000, refresh_loop) # Refresh every 3 seconds
            else:
                print("Admin dashboard refresh loop stopping.") # Window closed

        # Start the loop
        if self.admin_dashboard_window and self.admin_dashboard_window.winfo_exists():
             self.admin_dashboard_window.after(3000, refresh_loop)


    def refresh_admin_dashboard_data(self):
         """Update all data displayed on the admin dashboard"""
         if not self.admin_dashboard_window or not self.admin_dashboard_window.winfo_exists():
              return # Don't update if window is closed

         # --- Update Active Beacons Tree ---
         # Clear existing items
         for item in self.admin_active_tree.get_children():
              self.admin_active_tree.delete(item)

         beacons = self.db.get_all_beacons()
         active_count = 0
         current_time = datetime.now() # Naive time for comparison

         for beacon in beacons:
             # DB columns: id, mac, room, desc, last_seen, rssi, battery, mode, aux_op, dist, charging, created
             beacon_id, mac, room, desc, last_seen_iso, rssi_val, battery_lvl, mode, aux_op, dist, charging, created = beacon

             if last_seen_iso:
                 try:
                     # Convert ISO string to naive datetime for comparison
                     last_seen_dt_naive = datetime.fromisoformat(last_seen_iso.split('.')[0]) # Remove potential microseconds
                     time_diff_secs = (current_time - last_seen_dt_naive).total_seconds()

                     if time_diff_secs <= 300: # Active within 5 minutes
                         active_count += 1
                         # Format for display
                         last_seen_dt_aware = last_seen_dt_naive.astimezone() # Convert to local timezone for display
                         last_seen_str = last_seen_dt_aware.strftime("%H:%M:%S %Z")
                         rssi_str = f"{rssi_val} dBm" if rssi_val is not None else "N/A"
                         battery_str = f"{battery_lvl}%" if battery_lvl is not None else "N/A"
                         if charging: battery_str += " ⚡"
                         dist_str = f"{dist} m" if dist is not None else "N/A"
                         mode_str = mode or "N/A"

                         self.admin_active_tree.insert('', tk.END, iid=mac, values=( # Use MAC as item ID
                             mac, room, rssi_str, battery_str, dist_str, mode_str, last_seen_str
                         ))
                 except (ValueError, TypeError) as e:
                     print(f"Skipping beacon {mac} due to invalid last_seen format '{last_seen_iso}': {e}")
                     pass # Skip beacons with invalid timestamps

         # --- Update Stats ---
         self.admin_beacon_count_var.set(str(len(beacons)))
         self.admin_active_beacons_var.set(str(active_count))

         # --- Update Recent Events (Example: last 10 MQTT messages from DB log) ---
         self.admin_recent_events.configure(state=tk.NORMAL)
         self.admin_recent_events.delete(1.0, tk.END)
         recent_raw_logs = self.db.get_recent_logs(limit=20) # Get more logs

         event_count = 0
         for log_entry in recent_raw_logs:
              # DB log columns: timestamp, room, mac, event_type, details
              ts_iso, log_room, log_mac, ev_type, details = log_entry

              # Only show MQTT messages here for brevity
              if ev_type == "MQTT_MSG":
                   event_count += 1
                   try:
                       # Convert timestamp to local time for display
                       ts_dt_naive = datetime.fromisoformat(ts_iso.split('.')[0])
                       ts_dt_aware = ts_dt_naive.astimezone()
                       ts_str = ts_dt_aware.strftime("%H:%M:%S %Z")
                   except:
                       ts_str = ts_iso

                   # Try to parse details for better readability
                   log_line = f"[{ts_str}] "
                   if log_mac: log_line += f"MAC: {log_mac} "
                   if log_room: log_line += f"(Room: {log_room}) "

                   # Extract key info from details if possible
                   try:
                       details_parts = details.split("Decoded: ")
                       topic_part = details_parts[0].split("RSSI:")[0].replace("Topic: ", "").strip(', ') # Extract topic cleanly
                       decoded_part = details_parts[1] if len(details_parts) > 1 else "{}"
                       decoded_json = json.loads(decoded_part)

                       log_line += f"Topic: {topic_part} | "
                       if 'beacons' in decoded_json and decoded_json['beacons']:
                           log_line += f"Detected: {len(decoded_json['beacons'])} "
                           # Show closest detected beacon's MAC/RSSI for context
                           closest_dist = float('inf')
                           closest_info = "N/A"
                           for b in decoded_json['beacons']:
                               if b.get('estimated_distance') is not None and b['estimated_distance'] < closest_dist:
                                   closest_dist = b['estimated_distance']
                                   closest_info = f"({b.get('mac')} @ {b.get('rssi')}dBm)"
                           log_line += closest_info

                       else:
                           log_line += f"Batt: {decoded_json.get('battery','N/A')} | Mode: {decoded_json.get('device_mode','N/A')} | Aux: {decoded_json.get('auxiliary_operation','N/A')}"

                   except Exception as parse_err:
                       log_line += f"Raw: {details}" # Fallback to raw details
                       print(f"Could not parse log details: {parse_err}")


                   self.admin_recent_events.insert(tk.END, log_line + "\n")

              if event_count >= 10: # Limit display to 10 MQTT events
                   break

         self.admin_recent_events.yview(tk.END) # Scroll to bottom
         self.admin_recent_events.configure(state=tk.DISABLED)



    def show_beacon_details_admin(self, event):
        """Show detailed information about the selected beacon in the admin dashboard"""
        if not self.admin_dashboard_window or not self.admin_dashboard_window.winfo_exists(): return
        selected_items = self.admin_active_tree.selection()
        if not selected_items: return

        # selected_mac = self.admin_active_tree.item(selected_items[0], 'values')[0] # Get MAC from active tree
        # Use the IID which should be the MAC address
        selected_mac = selected_items[0]

        beacon_data = self.db.get_beacon_by_mac(selected_mac)

        self.admin_details_text.configure(state=tk.NORMAL)
        self.admin_details_text.delete(1.0, tk.END)

        if beacon_data:
            # DB columns: id, mac, room, desc, last_seen, rssi, battery, mode, aux_op, dist, charging, created
            field_names = ["ID", "MAC Address", "Room", "Description", "Last Seen", "RSSI", "Battery", "Mode", "Aux Op", "Est. Distance", "Charging", "Created"]
            self.admin_details_text.insert(tk.END, f"--- Beacon Details ({selected_mac}) ---\n", ('heading',))
            for i, field in enumerate(field_names):
                 value = beacon_data[i]
                 display_value = value
                 if field in ["Last Seen", "Created"] and value:
                      try:
                          dt_naive = datetime.fromisoformat(value.split('.')[0])
                          dt_aware = dt_naive.astimezone()
                          display_value = dt_aware.strftime("%Y-%m-%d %H:%M:%S %Z")
                      except: pass # Keep original string if parsing fails
                 elif field == "Charging": display_value = "Yes" if value else "No"
                 elif field == "RSSI" and value is not None: display_value = f"{value} dBm"
                 elif field == "Battery" and value is not None: display_value = f"{value}%"
                 elif field == "Est. Distance" and value is not None: display_value = f"{value} m"

                 self.admin_details_text.insert(tk.END, f"{field}: ", ('label',))
                 self.admin_details_text.insert(tk.END, f"{display_value if display_value not in [None, ''] else 'N/A'}\n", ('value',))

             # Configure tags
            self.admin_details_text.tag_configure('heading', font=("Consolas", 11, "bold"), underline=True)
            self.admin_details_text.tag_configure('label', font=("Consolas", 10, "bold"))
            self.admin_details_text.tag_configure('value', font=("Consolas", 10))
        else:
            self.admin_details_text.insert(tk.END, f"Could not retrieve details for beacon MAC: {selected_mac}")

        self.admin_details_text.configure(state=tk.DISABLED)


    def setup_beacons_tab(self, parent_window):
        """Setup beacons management tab (now in its own window)"""
        beacons_frame = ttk.Frame(parent_window, padding=10)
        beacons_frame.pack(fill=tk.BOTH, expand=True)

        # --- Control Buttons ---
        control_frame = ttk.Frame(beacons_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(control_frame, text="Add Beacon", command=self.add_beacon_dialog_admin).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Remove Beacon", command=self.remove_beacon_admin).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Edit Beacon", command=self.edit_beacon_admin).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Refresh List", command=self.refresh_beacons_admin).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Register Unknown", command=self.register_unknown_beacon_admin).pack(side=tk.LEFT, padx=2)

        # --- Data Export/Import Buttons ---
        io_frame = ttk.Frame(beacons_frame)
        io_frame.pack(fill=tk.X, padx=5, pady=5)
        # TRANSLATED from admin.py
        ttk.Button(io_frame, text="Export Room Map", command=self.export_room_mapping_admin).pack(side=tk.LEFT, padx=2)
        ttk.Button(io_frame, text="Import Room Map", command=self.import_room_mapping_admin).pack(side=tk.LEFT, padx=2)

        # --- Beacon List Treeview ---
        list_frame = ttk.Frame(beacons_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('id', 'mac_address', 'room_number', 'description', 'last_seen', 'last_rssi', 'battery', 'mode', 'created_at')
        self.admin_beacon_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        col_widths = {'id': 40, 'mac_address': 130, 'room_number': 70, 'description': 180, 'last_seen': 140, 'last_rssi': 60, 'battery': 70, 'mode': 110, 'created_at': 140}
        for col in columns:
             self.admin_beacon_tree.heading(col, text=col.replace('_', ' ').title(), command=lambda c=col: self.sort_beacon_column(c, False)) # Add sort command
             anchor = tk.CENTER if col in ['id', 'room_number', 'last_rssi', 'battery'] else tk.W
             self.admin_beacon_tree.column(col, width=col_widths[col], anchor=anchor, stretch=tk.YES if col == 'description' else tk.NO)


        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.admin_beacon_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.admin_beacon_tree.xview)
        self.admin_beacon_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.admin_beacon_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Context menu for beacon list
        self.admin_beacon_tree_menu = tk.Menu(self.admin_beacon_tree, tearoff=0)
        self.admin_beacon_tree_menu.add_command(label="Copy MAC Address", command=self.copy_mac_from_beacons_list_admin)
        self.admin_beacon_tree_menu.add_separator()
        self.admin_beacon_tree_menu.add_command(label="Edit Beacon", command=self.edit_beacon_admin)
        self.admin_beacon_tree_menu.add_command(label="Remove Beacon", command=self.remove_beacon_admin)
        self.admin_beacon_tree.bind("<Button-3>", self.show_beacon_tree_menu_admin)
        self.admin_beacon_tree.bind("<Double-1>", lambda e: self.edit_beacon_admin())

        # Load initial data
        self.refresh_beacons_admin()


    def sort_beacon_column(self, col, reverse):
         """Sort the beacon treeview by a column"""
         if not hasattr(self, 'admin_beacon_tree'): return

         # Get data with original index to fetch full row later if needed
         data = [(self.admin_beacon_tree.set(item, col), item) for item in self.admin_beacon_tree.get_children('')]

         # Define sort key logic
         def sort_key(item_tuple):
             value_str, item_id = item_tuple
             if value_str is None or value_str == 'N/A' or value_str == 'Never':
                 # Handle None/NA values consistently (e.g., place at end)
                 return (float('inf'), item_id) if not reverse else (float('-inf'), item_id)

             try:
                 # Attempt numeric/specific type sort
                 if col in ['id', 'last_rssi']:
                     # Extract number before ' dBm' if present
                     num_part = value_str.split(' ')[0]
                     return (int(num_part), item_id)
                 elif col == 'battery':
                     # Extract number before '%' or ' ⚡'
                     num_part = value_str.split('%')[0].split(' ')[0]
                     return (int(num_part), item_id)
                 elif col in ['last_seen', 'created_at']:
                     # Get full data from DB using ID for reliable date sorting
                     values = self.admin_beacon_tree.item(item_id, 'values')
                     db_id = values[0]
                     db_row = self.db.get_beacon_by_id(db_id)
                     if not db_row: return (datetime.min, item_id) # Fallback

                     iso_str = db_row[4] if col == 'last_seen' else db_row[11]
                     if not iso_str: return (datetime.min, item_id)

                     # Parse ISO string, making it timezone-naive for comparison
                     dt_naive = datetime.fromisoformat(iso_str.split('.')[0])
                     return (dt_naive, item_id)

                 else: # Default string sort
                     return (value_str.lower(), item_id)
             except (ValueError, TypeError, IndexError) as e:
                 # Fallback for any conversion errors
                 print(f"Sort warning for column {col}, value '{value_str}': {e}")
                 return (value_str.lower(), item_id)

         # Sort the data
         data.sort(key=sort_key, reverse=reverse)

         # Reorder items in the treeview
         for index, (val, item) in enumerate(data):
              self.admin_beacon_tree.move(item, '', index)

         # Toggle sort direction for next click
         self.admin_beacon_tree.heading(col, command=lambda: self.sort_beacon_column(col, not reverse))


    def setup_logs_tab(self, parent_window):
        """Setup logs tab (now in its own window)"""
        logs_frame = ttk.Frame(parent_window, padding=10)
        logs_frame.pack(fill=tk.BOTH, expand=True)

        # Control frame
        control_frame = ttk.Frame(logs_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(control_frame, text="Refresh Logs", command=self.refresh_logs_admin).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Export Logs", command=self.export_logs_admin).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Clear Display", command=self.clear_logs_display_admin).pack(side=tk.LEFT, padx=5)

        # Log viewer treeview
        list_frame = ttk.Frame(logs_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('timestamp', 'room', 'mac', 'event', 'details')
        self.admin_log_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        col_widths = {'timestamp': 150, 'room': 80, 'mac': 130, 'event': 100, 'details': 350}
        for col in columns:
             anchor = tk.W
             if col == 'room': anchor = tk.CENTER
             self.admin_log_tree.heading(col, text=col.replace('_', ' ').title())
             self.admin_log_tree.column(col, width=col_widths[col], anchor=anchor, stretch=tk.YES if col=='details' else tk.NO)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.admin_log_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.admin_log_tree.xview)
        self.admin_log_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.admin_log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Load initial logs
        self.refresh_logs_admin()

    def setup_settings_tab(self, parent_window):
        """Setup settings tab (now in its own window)"""
        settings_frame = ttk.Frame(parent_window, padding=15)
        settings_frame.pack(fill=tk.BOTH, expand=True)

        # Use a notebook for better organization
        notebook = ttk.Notebook(settings_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)

        # --- AWS Settings Tab ---
        aws_tab_frame = ttk.Frame(notebook, padding=10)
        notebook.add(aws_tab_frame, text="AWS IoT Configuration")

        aws_form_frame = ttk.Frame(aws_tab_frame)
        aws_form_frame.pack(fill=tk.BOTH, expand=True)

        # Create variables linked to the main settings manager instance
        self.admin_endpoint_var = tk.StringVar(value=self.settings.get("aws_endpoint"))
        self.admin_cert_var = tk.StringVar(value=self.settings.get("cert_file"))
        self.admin_key_var = tk.StringVar(value=self.settings.get("key_file"))
        self.admin_root_ca_var = tk.StringVar(value=self.settings.get("root_ca"))
        self.admin_client_id_var = tk.StringVar(value=self.settings.get("client_id"))
        self.admin_topic_var = tk.StringVar(value=self.settings.get("topic"))
        self.admin_alert_topic_var = tk.StringVar(value=self.settings.get("alert_topic"))

        fields = [
             ("Endpoint:", self.admin_endpoint_var, None),
             ("Certificate File:", self.admin_cert_var, lambda: self.browse_file_admin("cert_file", self.admin_cert_var)),
             ("Key File:", self.admin_key_var, lambda: self.browse_file_admin("key_file", self.admin_key_var)),
             ("Root CA File:", self.admin_root_ca_var, lambda: self.browse_file_admin("root_ca", self.admin_root_ca_var)),
             ("Client ID:", self.admin_client_id_var, None),
             ("Subscribe Topic:", self.admin_topic_var, None),
             ("Alert Topic:", self.admin_alert_topic_var, None),
        ]

        for i, (label_text, var, browse_cmd) in enumerate(fields):
             ttk.Label(aws_form_frame, text=label_text).grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)
             entry = ttk.Entry(aws_form_frame, textvariable=var, width=50)
             entry.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=5)
             if browse_cmd:
                  ttk.Button(aws_form_frame, text="Browse...", command=browse_cmd).grid(row=i, column=2, padx=5, pady=5)

        aws_form_frame.columnconfigure(1, weight=1) # Make entry fields expand

        # --- Application Settings Tab ---
        app_tab_frame = ttk.Frame(notebook, padding=10)
        notebook.add(app_tab_frame, text="Application Settings")

        app_form_frame = ttk.Frame(app_tab_frame)
        app_form_frame.pack(fill=tk.BOTH, expand=True)

        # Create variables
        self.admin_alert_interval_var = tk.StringVar(value=str(self.settings.get("alert_interval")))
        self.admin_scan_interval_var = tk.StringVar(value=str(self.settings.get("scan_interval")))

        ttk.Label(app_form_frame, text="Alert Interval (sec):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(app_form_frame, textvariable=self.admin_alert_interval_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(app_form_frame, text="DB Scan Interval (sec):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(app_form_frame, textvariable=self.admin_scan_interval_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        # --- Password Change ---
        ttk.Button(app_form_frame, text="Change Admin Password", command=lambda: self.change_admin_password_dialog(parent_window)).grid(row=2, column=0, columnspan=2, pady=20)


        # --- Save Button ---
        ttk.Separator(settings_frame).pack(fill=tk.X, pady=15)
        button_frame = ttk.Frame(settings_frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="Cancel", command=parent_window.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Save Settings", command=lambda: self.save_settings_admin(parent_window), style="Action.TButton").pack(side=tk.RIGHT, padx=5)


    # --- Admin Action Methods (Need to be adapted) ---
    # These methods now operate on the specific admin treeviews/widgets
    # and potentially interact with the main app's core components (db, settings).

    def refresh_beacons_admin(self):
        """Refresh the beacon list display in the admin window"""
        if not hasattr(self, 'admin_beacon_tree') or not self.admin_beacon_tree.winfo_exists(): return
        for item in self.admin_beacon_tree.get_children():
             self.admin_beacon_tree.delete(item)
        beacons = self.db.get_all_beacons()
        for beacon in beacons:
             # DB columns: id, mac, room, desc, last_seen, rssi, battery, mode, aux_op, dist, charging, created
             last_seen_str = "Never"
             if beacon[4]:
                 try:
                     dt_naive = datetime.fromisoformat(beacon[4].split('.')[0])
                     dt_aware = dt_naive.astimezone()
                     last_seen_str = dt_aware.strftime("%Y-%m-%d %H:%M:%S %Z")
                 except: last_seen_str = beacon[4] # Show raw if format error

             created_str = "N/A"
             if beacon[11]:
                 try:
                     dt_naive = datetime.fromisoformat(beacon[11].split('.')[0])
                     dt_aware = dt_naive.astimezone()
                     created_str = dt_aware.strftime("%Y-%m-%d %H:%M:%S %Z")
                 except: created_str = beacon[11]

             rssi_str = f"{beacon[5]} dBm" if beacon[5] is not None else "N/A"
             battery_str = f"{beacon[6]}%" if beacon[6] is not None else "N/A"
             if beacon[10]: battery_str += " ⚡" # Charging indicator

             self.admin_beacon_tree.insert('', tk.END, values=(
                 beacon[0], beacon[1], beacon[2], beacon[3] or "", last_seen_str,
                 rssi_str, battery_str, beacon[7] or "N/A", created_str
             ))
        self.update_status_bar(f"Refreshed beacon list ({len(beacons)} entries).")


    def refresh_logs_admin(self):
        """Refresh the logs display in the admin window"""
        if not hasattr(self, 'admin_log_tree') or not self.admin_log_tree.winfo_exists(): return
        for item in self.admin_log_tree.get_children():
             self.admin_log_tree.delete(item)
        logs = self.db.get_recent_logs(limit=200) # Get more logs for admin view
        for log in logs:
             # DB log columns: timestamp, room, mac, event_type, details
             ts_iso, room, mac, ev_type, details = log
             try:
                 dt_naive = datetime.fromisoformat(ts_iso.split('.')[0])
                 dt_aware = dt_naive.astimezone()
                 ts_str = dt_aware.strftime("%Y-%m-%d %H:%M:%S %Z")
             except:
                 ts_str = ts_iso
             self.admin_log_tree.insert('', tk.END, values=(
                 ts_str, room or "N/A", mac or "N/A", ev_type, details
             ))
        self.update_status_bar(f"Refreshed activity logs ({len(logs)} entries).")


    def add_beacon_dialog_admin(self, initial_mac=""):
        """Show dialog to add a new beacon (Admin context)"""
        parent = self.admin_beacons_window if self.admin_beacons_window and self.admin_beacons_window.winfo_exists() else self.root

        dialog = tk.Toplevel(parent)
        dialog.title("Add Beacon")
        dialog.geometry("400x250") # Slightly taller
        dialog.transient(parent)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        mac_var = tk.StringVar(value=initial_mac)
        mac_entry = ttk.Entry(frame, textvariable=mac_var, width=30)
        mac_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(frame, text="Room Number:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        room_var = tk.StringVar()
        room_entry = ttk.Entry(frame, textvariable=room_var, width=30)
        room_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(frame, text="Description:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(frame, textvariable=desc_var, width=30)
        desc_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        # Paste button
        def paste_mac():
             try:
                 # Clean up potential extra chars from clipboard
                 clip_text = dialog.clipboard_get().strip()
                 # Basic MAC format check (optional but helpful)
                 import re
                 if re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', clip_text):
                     mac_var.set(clip_text.upper())
                 else:
                     mac_var.set(clip_text) # Set anyway, let validation handle it
             except tk.TclError: pass # Ignore clipboard errors

        ttk.Button(frame, text="Paste MAC", command=paste_mac).grid(row=0, column=3, padx=5, pady=5)

        # Add button action
        def add_beacon():
            mac = mac_var.get().strip().upper() # Standardize MAC format
            room = room_var.get().strip()
            desc = desc_var.get().strip()

            # Basic MAC validation
            import re
            if not re.match(r'^([0-9A-F]{2}[:-]){5}([0-9A-F]{2})$', mac):
                 messagebox.showerror("Input Error", "Invalid MAC Address format. Use XX:XX:XX:XX:XX:XX", parent=dialog)
                 return

            if not room:
                messagebox.showerror("Input Error", "Room Number is required.", parent=dialog)
                return

            if self.db.add_beacon(mac, room, desc):
                self.db.log_activity("ADMIN", f"Added beacon {mac} for room {room}", None) # Log as Admin action
                self.refresh_beacons_admin() # Refresh admin list
                self.load_beacons_mapping() # Reload main app mapping
                self.update_status_bar(f"Added beacon {mac}")
                dialog.destroy()
            else:
                messagebox.showerror("Database Error", f"Failed to add beacon.\nMAC Address '{mac}' may already exist.", parent=dialog)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=15)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Add Beacon", command=add_beacon, style="Action.TButton").pack(side=tk.RIGHT, padx=5)

        # Set initial focus
        (room_entry if initial_mac else mac_entry).focus_set()

    def remove_beacon_admin(self):
        """Remove selected beacon (Admin context)"""
        if not hasattr(self, 'admin_beacon_tree') or not self.admin_beacon_tree.winfo_exists(): return
        selected = self.admin_beacon_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a beacon to remove.", parent=self.admin_beacons_window)
            return

        values = self.admin_beacon_tree.item(selected[0], 'values')
        beacon_id = values[0]
        mac = values[1]

        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to remove beacon:\nID: {beacon_id}\nMAC: {mac}?", parent=self.admin_beacons_window):
            if self.db.delete_beacon(beacon_id):
                self.db.log_activity("ADMIN", f"Removed beacon ID {beacon_id} ({mac})", None)
                self.refresh_beacons_admin()
                self.load_beacons_mapping() # Reload main app mapping
                self.update_status_bar(f"Removed beacon {mac}")
            else:
                messagebox.showerror("Database Error", "Failed to remove beacon.", parent=self.admin_beacons_window)


    def edit_beacon_admin(self):
        """Edit selected beacon (Admin context)"""
        if not hasattr(self, 'admin_beacon_tree') or not self.admin_beacon_tree.winfo_exists(): return
        selected = self.admin_beacon_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a beacon to edit.", parent=self.admin_beacons_window)
            return

        values = self.admin_beacon_tree.item(selected[0], 'values')
        beacon_id = values[0]
        mac = values[1]
        current_room = values[2]
        current_desc = values[3]

        parent = self.admin_beacons_window if self.admin_beacons_window and self.admin_beacons_window.winfo_exists() else self.root
        dialog = tk.Toplevel(parent)
        dialog.title("Edit Beacon")
        dialog.geometry("400x200")
        dialog.transient(parent)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="MAC Address:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        mac_var = tk.StringVar(value=mac)
        ttk.Entry(frame, textvariable=mac_var, width=30, state=tk.DISABLED).grid(row=0, column=1, padx=5, pady=5, sticky="ew") # MAC not editable

        ttk.Label(frame, text="Room Number:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        room_var = tk.StringVar(value=current_room)
        room_entry = ttk.Entry(frame, textvariable=room_var, width=30)
        room_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(frame, text="Description:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        desc_var = tk.StringVar(value=current_desc)
        desc_entry = ttk.Entry(frame, textvariable=desc_var, width=30)
        desc_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        def update_beacon():
            new_room = room_var.get().strip()
            new_desc = desc_var.get().strip()

            if not new_room:
                messagebox.showerror("Input Error", "Room Number is required.", parent=dialog)
                return

            if self.db.update_beacon(beacon_id, new_room, new_desc):
                self.db.log_activity("ADMIN", f"Updated beacon ID {beacon_id} ({mac})", None)
                self.refresh_beacons_admin()
                self.load_beacons_mapping() # Reload main app mapping
                self.update_status_bar(f"Updated beacon {mac}")
                dialog.destroy()
            else:
                messagebox.showerror("Database Error", "Failed to update beacon.", parent=dialog)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Update Beacon", command=update_beacon, style="Action.TButton").pack(side=tk.RIGHT, padx=5)

        room_entry.focus_set()
        room_entry.select_range(0, tk.END)


    def export_room_mapping_admin(self):
        """Export room mapping to JSON (Admin context)"""
        parent = self.admin_beacons_window if self.admin_beacons_window and self.admin_beacons_window.winfo_exists() else self.root
        mapping_data = self.db.export_room_mapping_data()

        if not mapping_data:
            # TRANSLATED
            messagebox.showerror("Export Error", "Failed to export room map data.", parent=parent)
            return

        default_filename = f"room_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filename = filedialog.asksaveasfilename(
            parent=parent,
            title="Export Room Map As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_filename
        )

        if not filename: return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=4, ensure_ascii=False)

            beacon_count = len(mapping_data.get("beacons", []))
            self.db.log_activity("ADMIN", f"Exported {beacon_count} beacons to {filename}")
            # TRANSLATED
            messagebox.showinfo("Export Complete", f"Successfully exported {beacon_count} beacons to:\n{filename}", parent=parent)
            self.update_status_bar(f"Exported room map to {os.path.basename(filename)}")
        except Exception as e:
            # TRANSLATED
            messagebox.showerror("Export Error", f"Error exporting room map: {str(e)}", parent=parent)


    def import_room_mapping_admin(self):
        """Import room mapping from JSON (Admin context)"""
        parent = self.admin_beacons_window if self.admin_beacons_window and self.admin_beacons_window.winfo_exists() else self.root
        filename = filedialog.askopenfilename(
            parent=parent,
            title="Import Room Map From",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not filename: return

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)

            if "beacons" not in mapping_data or not isinstance(mapping_data["beacons"], list):
                # TRANSLATED
                messagebox.showerror("Import Error", "Invalid room map file format. Missing 'beacons' list.", parent=parent)
                return

            # TRANSLATED Confirmation Dialog
            replace = messagebox.askyesno(
                "Confirm Import Type",
                "Do you want to replace all existing beacon mappings?\n\n"
                "Click 'Yes' to clear current mappings before import.\n"
                "Click 'No' to merge with existing mappings (updates existing, adds new).",
                parent=parent
            )

            if replace:
                 if self.db.clear_all_beacons():
                      self.db.log_activity("ADMIN", "Cleared all beacons before import")
                 else:
                      messagebox.showerror("Database Error", "Failed to clear existing beacons before import.", parent=parent)
                      return # Stop import if clearing failed


            result = self.db.import_room_mapping_data(mapping_data)

            if result:
                # TRANSLATED
                import_msg = f"Imported {result['imported']} new, updated {result['updated']} existing beacons."
                self.db.log_activity("ADMIN", f"{import_msg} from {filename}")
                # TRANSLATED
                messagebox.showinfo("Import Complete", import_msg, parent=parent)
                self.refresh_beacons_admin() # Refresh admin list
                self.load_beacons_mapping() # Reload main app mapping
                self.update_status_bar(f"Imported room map from {os.path.basename(filename)}")
            else:
                # TRANSLATED
                messagebox.showerror("Import Error", "Failed to import room map data. Check logs.", parent=parent)

        except json.JSONDecodeError:
            # TRANSLATED
            messagebox.showerror("Import Error", "Invalid JSON file format.", parent=parent)
        except Exception as e:
            # TRANSLATED
            messagebox.showerror("Import Error", f"Error importing room map: {str(e)}", parent=parent)


    def export_logs_admin(self):
        """Export logs to CSV (Admin context)"""
        parent = self.admin_logs_window if self.admin_logs_window and self.admin_logs_window.winfo_exists() else self.root
        filename = filedialog.asksaveasfilename(
            parent=parent,
            title="Export Activity Logs As",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"activity_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not filename: return

        try:
            # Get more logs for export
            logs = self.db.get_recent_logs(limit=10000) # Export up to 10000 logs
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                import csv
                writer = csv.writer(csvfile)
                # Header row matching treeview columns
                writer.writerow(["Timestamp", "Room", "MAC Address", "Event Type", "Details"])
                # Write data rows
                for log in logs:
                     writer.writerow(log)
            messagebox.showinfo("Export Complete", f"Successfully exported {len(logs)} log entries to:\n{filename}", parent=parent)
            self.update_status_bar(f"Exported logs to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting logs: {str(e)}", parent=parent)
            self.update_status_bar("Log export failed.")


    def clear_logs_display_admin(self):
        """Clear the logs display in the admin window"""
        if hasattr(self, 'admin_log_tree') and self.admin_log_tree.winfo_exists():
             for item in self.admin_log_tree.get_children():
                  self.admin_log_tree.delete(item)
             self.update_status_bar("Log display cleared.")


    def save_settings_admin(self, parent_window):
        """Save settings from the admin settings form"""
        try:
            # Update settings from admin form variables
            self.settings.set("aws_endpoint", self.admin_endpoint_var.get())
            self.settings.set("cert_file", self.admin_cert_var.get())
            self.settings.set("key_file", self.admin_key_var.get())
            self.settings.set("root_ca", self.admin_root_ca_var.get())
            self.settings.set("client_id", self.admin_client_id_var.get())
            self.settings.set("topic", self.admin_topic_var.get())
            self.settings.set("alert_topic", self.admin_alert_topic_var.get())

            # Save numeric values with validation
            try:
                self.settings.set("alert_interval", int(self.admin_alert_interval_var.get()))
            except ValueError:
                 messagebox.showwarning("Input Error", "Invalid Alert Interval. Please enter a number.", parent=parent_window)
                 # Keep old value or default? Let's keep old.
                 self.admin_alert_interval_var.set(str(self.settings.get("alert_interval"))) # Revert display

            try:
                 self.settings.set("scan_interval", int(self.admin_scan_interval_var.get()))
            except ValueError:
                 messagebox.showwarning("Input Error", "Invalid Scan Interval. Please enter a number.", parent=parent_window)
                 self.admin_scan_interval_var.set(str(self.settings.get("scan_interval"))) # Revert display


            # SettingsManager saves automatically on set, but call save again to be sure
            if self.settings.save_settings():
                messagebox.showinfo("Success", "Settings saved successfully.", parent=parent_window)
                self.db.log_activity("ADMIN", "Settings updated")
                self.update_status_bar("Settings saved.")

                 # Ask to reconnect if connected and AWS settings might have changed
                if self.aws_client and self.aws_client.connected:
                    # Check if relevant AWS settings changed (simple check)
                    aws_keys = ["aws_endpoint", "cert_file", "key_file", "root_ca", "client_id", "topic", "alert_topic"]
                    # NOTE: This comparison won't work directly as save_settings modifies self.settings
                    # A better approach would be to compare with previous values before setting.
                    # For now, just ask if any setting was saved.
                    if messagebox.askyesno("Reconnect AWS", "AWS settings have been modified. Reconnect now to apply changes?", parent=parent_window):
                          self.disconnect_from_aws()
                          # Use 'after' to allow disconnect to finish before reconnecting
                          self.root.after(1000, self.connect_to_aws)

                parent_window.destroy() # Close settings window on successful save
            else:
                messagebox.showerror("Error", "Failed to save settings file.", parent=parent_window)

        except Exception as e:
            messagebox.showerror("Save Error", f"An error occurred while saving settings: {str(e)}", parent=parent_window)


    def browse_file_admin(self, setting_key, target_var):
        """Browse for a file and update the corresponding setting var (Admin context)"""
        parent = self.admin_settings_window if self.admin_settings_window and self.admin_settings_window.winfo_exists() else self.root
        filename = filedialog.askopenfilename(parent=parent, title=f"Select {setting_key.replace('_',' ').title()}")
        if filename:
            target_var.set(filename) # Update the linked String Variable


    # --- Admin Helper/Context Menu Functions ---
    def show_active_tree_menu_admin(self, event):
        """Show context menu for admin active beacons tree"""
        if hasattr(self, 'admin_active_tree') and self.admin_active_tree.winfo_exists():
            item = self.admin_active_tree.identify_row(event.y)
            if item:
                self.admin_active_tree.selection_set(item) # Select the item under cursor
                self.admin_active_tree_menu.post(event.x_root, event.y_root)

    def show_beacon_tree_menu_admin(self, event):
        """Show context menu for admin beacons list tree"""
        if hasattr(self, 'admin_beacon_tree') and self.admin_beacon_tree.winfo_exists():
            item = self.admin_beacon_tree.identify_row(event.y)
            if item:
                self.admin_beacon_tree.selection_set(item)
                self.admin_beacon_tree_menu.post(event.x_root, event.y_root)

    def show_events_menu_admin(self, event):
        """Show context menu for admin recent events"""
        if hasattr(self, 'admin_recent_events_menu') and self.admin_recent_events.winfo_exists():
            self.admin_recent_events_menu.post(event.x_root, event.y_root)


    def copy_mac_from_active_admin(self, event=None):
        """Copy MAC from admin active beacons tree"""
        if not hasattr(self, 'admin_active_tree'): return None
        selected = self.admin_active_tree.selection()
        if selected:
            # values = self.admin_active_tree.item(selected[0], 'values')
            # mac = values[0] if values else None
            mac = selected[0] # IID is the MAC
            if mac:
                self.root.clipboard_clear()
                self.root.clipboard_append(mac)
                self.clipboard_mac = mac # Update shared clipboard variable
                self.update_status_bar(f"Copied MAC: {mac}")
                return mac
        return None

    def register_from_active_admin(self):
         """Register beacon from admin active beacons list"""
         mac = self.copy_mac_from_active_admin()
         if mac:
              # Check if already registered before opening dialog
              if self.db.get_beacon_by_mac(mac):
                   messagebox.showinfo("Already Registered", f"Beacon {mac} is already registered.", parent=self.admin_dashboard_window)
              else:
                   self.add_beacon_dialog_admin(mac) # Pass MAC to admin add dialog

    def copy_mac_from_beacons_list_admin(self):
        """Copy MAC from admin beacons list tree"""
        if not hasattr(self, 'admin_beacon_tree'): return None
        selected = self.admin_beacon_tree.selection()
        if selected:
            mac = self.admin_beacon_tree.item(selected[0], 'values')[1]
            self.root.clipboard_clear()
            self.root.clipboard_append(mac)
            self.clipboard_mac = mac
            self.update_status_bar(f"Copied MAC: {mac}")
            return mac
        return None

    def copy_mac_from_events_admin(self):
        """Copy MAC from selected text in admin recent events"""
        if not hasattr(self, 'admin_recent_events'): return None
        try:
            selected_text = self.admin_recent_events.get(tk.SEL_FIRST, tk.SEL_LAST)
            import re
            # Updated regex to handle various MAC formats potentially in the log
            mac_pattern = re.compile(r'([0-9A-F]{2}[:.-]){5}[0-9A-F]{2}', re.IGNORECASE)
            matches = mac_pattern.findall(selected_text)
            if matches:
                # Normalize MAC to use colons and uppercase
                mac_raw = matches[0].replace('.', ':').replace('-', ':').upper()
                self.root.clipboard_clear()
                self.root.clipboard_append(mac_raw)
                self.clipboard_mac = mac_raw
                self.update_status_bar(f"Copied MAC: {mac_raw}")
                return mac_raw
        except tk.TclError:
            pass # No selection
        except Exception as e:
             print(f"Error copying MAC from events: {e}")
        return None

    def register_from_events_admin(self):
         """Register beacon from selected text in admin recent events"""
         mac = self.copy_mac_from_events_admin()
         if mac:
              if self.db.get_beacon_by_mac(mac):
                   messagebox.showinfo("Already Registered", f"Beacon {mac} is already registered.", parent=self.admin_dashboard_window)
              else:
                   self.add_beacon_dialog_admin(mac)


    def register_unknown_beacon_admin(self):
        """Dialog to register unknown beacons seen in admin event logs"""
        parent = self.admin_beacons_window if self.admin_beacons_window and self.admin_beacons_window.winfo_exists() else self.root
        # Scan DB logs for unknown MACs (more reliable than UI text)
        recent_logs = self.db.get_recent_logs(limit=500) # Scan more logs
        unknown_macs = set()
        import re
        # Regex to find MAC addresses (standard formats)
        mac_pattern = re.compile(r'([0-9A-F]{2}[:.-]){5}[0-9A-F]{2}', re.IGNORECASE)

        registered_macs = {b[1] for b in self.db.get_all_beacons()}

        for log in recent_logs:
            # Extract MACs from details string
            details = log[4]
            matches = mac_pattern.findall(details)
            for match in matches:
                 # Reconstruct the full MAC from the matched groups if necessary
                 # (This regex actually captures the full MAC, so reconstruction isn't needed here)
                 mac_raw = match.replace('.', ':').replace('-', ':').upper() # Normalize format
                 if mac_raw not in registered_macs:
                      unknown_macs.add(mac_raw)

            # Check MAC from log entry itself if present
            log_mac = log[2]
            if log_mac:
                log_mac_upper = log_mac.upper()
                if log_mac_upper not in registered_macs:
                     unknown_macs.add(log_mac_upper)


        if not unknown_macs:
            messagebox.showinfo("Info", "No unknown beacons found in recent activity logs.", parent=parent)
            return

        # --- Dialog Setup ---
        dialog = tk.Toplevel(parent)
        dialog.title("Register Unknown Beacon")
        dialog.geometry("500x300")
        dialog.transient(parent)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # MAC Selection
        select_frame = ttk.LabelFrame(frame, text="Select Detected Unknown MAC")
        select_frame.pack(fill=tk.X, pady=10)
        ttk.Label(select_frame, text="MAC Address:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        mac_var = tk.StringVar()
        mac_combo = ttk.Combobox(select_frame, textvariable=mac_var, values=sorted(list(unknown_macs)), width=25, state="readonly")
        mac_combo.grid(row=0, column=1, padx=5, pady=5)
        if unknown_macs: mac_combo.current(0) # Select first one

        # Details Frame
        details_frame = ttk.LabelFrame(frame, text="Assign Details")
        details_frame.pack(fill=tk.X, pady=10)
        ttk.Label(details_frame, text="Room Number:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        room_var = tk.StringVar()
        room_entry = ttk.Entry(details_frame, textvariable=room_var, width=20)
        room_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(details_frame, text="Description:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(details_frame, textvariable=desc_var, width=30)
        desc_entry.grid(row=1, column=1, padx=5, pady=5)

        # Register Button Action
        def register_beacon():
            mac = mac_var.get()
            room = room_var.get().strip()
            desc = desc_var.get().strip()
            if not mac or not room:
                messagebox.showerror("Input Error", "MAC Address and Room Number are required.", parent=dialog)
                return

            if self.db.add_beacon(mac, room, desc):
                self.db.log_activity("ADMIN", f"Registered unknown beacon {mac} for room {room}", None)
                self.refresh_beacons_admin()
                self.load_beacons_mapping() # Update main app mapping
                self.update_status_bar(f"Registered beacon {mac}")
                dialog.destroy()
            else:
                messagebox.showerror("Database Error", f"Failed to register beacon {mac}. It might already exist.", parent=dialog)

        # Buttons Frame
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=15)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Register Beacon", command=register_beacon, style="Action.TButton").pack(side=tk.RIGHT, padx=5)

        room_entry.focus_set()

    # --- General App Methods ---
    def update_status_bar(self, message):
        """Update the main status bar text"""
        if hasattr(self, 'status_var'):
            try:
                self.status_var.set(message)
                print(f"Status: {message}") # Also print to console
            except RuntimeError as e:
                 # Handle case where Tkinter objects might be destroyed during shutdown
                 if "application has been destroyed" in str(e):
                      print(f"Status (suppressed TclError): {message}")
                 else:
                      raise e


    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About Beacon System",
            f"{APP_TITLE} - Version {APP_VERSION}\n\n"
            "Combined application for managing LoRa beacons via AWS IoT and viewing alerts.\n\n"
            "Features:\n"
            "- Real-time alert display (based on closest mapped beacon)\n"
            "- Alarm history view, search, and export\n"
            "- Admin section (requires login):\n"
            "  - Live dashboard with active beacons\n"
            "  - Beacon registration and management\n"
            "  - Room map import/export (using database)\n"
            "  - Detailed activity logs\n"
            "  - AWS & Application settings\n"
            "  - Admin password management (resets on close)\n\n"
            f"(c) {datetime.now().year}",
            parent=self.root
        )

    def on_exit(self):
        """Handle application exit gracefully"""
        print("Exiting application...")
        self.update_status_bar("Exiting...")
        # Ensure disconnection from AWS
        if self.aws_client and self.aws_client.connected:
             print("Disconnecting from AWS IoT...")
             # Run disconnect synchronously on exit? Might hang if network issue.
             # Or give it a short timeout. Let's try synchronous for now.
             try:
                  if self.aws_client.disconnect():
                       print("Disconnected successfully.")
                  else:
                       print("Disconnection error occurred.")
             except Exception as e:
                  print(f"Exception during disconnect: {e}")

        # Close database connection
        if self.db:
            print("Closing database connection...")
            self.db.close()
            print("Database closed.")

        # Destroy the main window
        self.root.destroy()
        print("Application closed.")

# --- Main Execution ---
# Add necessary imports for traceback
import traceback

def main():
    """Main entry point for the application"""
    root = tk.Tk()
    # Set application icon (optional, requires icon file)
    # try:
    #     # Needs a 'beacon_app.ico' or similar in the same directory
    #     # icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beacon_app.ico")
    #     # if os.path.exists(icon_path): root.iconbitmap(icon_path)
    #     pass
    # except Exception as e:
    #     print(f"Could not set window icon: {e}")

    app = CombinedApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_exit) # Ensure clean exit on window close

    # Show warning if SDK is missing
    if not AWS_IOT_AVAILABLE:
         messagebox.showwarning(
             "AWS SDK Missing",
             "AWS IoT SDK (awsiotsdk) is not installed.\nAWS connectivity features will be unavailable.\n\n"
             "Please install it using: pip install awsiotsdk",
             parent=root # Attach to root window
         )

    root.mainloop()

if __name__ == "__main__":
    main()