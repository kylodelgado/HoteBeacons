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
from tkinter import ttk, scrolledtext, messagebox, simpledialog
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
APP_TITLE = "Hotel LoRa Beacon Management System"
DB_NAME = "hotel_beacons.db"
LOG_DIR = "logs"
ADMIN_PASSWORD = "admin123"  # Simple password for demo purposes

# Default AWS IoT Core settings
DEFAULT_ENDPOINT = "a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com"
DEFAULT_CERT_PATH = os.path.expanduser("~/certificates")
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
    "cert_file": os.path.join(DEFAULT_CERT_PATH, "certificate.pem.crt"),
    "key_file": os.path.join(DEFAULT_CERT_PATH, "private.pem.key"),
    "root_ca": os.path.join(DEFAULT_CERT_PATH, "AmazonRootCA1.pem"),
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
            
            # Create beacons table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS beacons (
                id INTEGER PRIMARY KEY,
                mac_address TEXT NOT NULL UNIQUE,
                room_number TEXT NOT NULL,
                description TEXT,
                last_seen TEXT,
                last_rssi INTEGER,
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
    
    def update_beacon_signal(self, mac_address, rssi):
        """Update beacon's last seen time and RSSI"""
        try:
            current_time = datetime.now().isoformat()
            self.cursor.execute(
                "UPDATE beacons SET last_seen = ?, last_rssi = ? WHERE mac_address = ?",
                (current_time, rssi, mac_address)
            )
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
            
            print(f"Connecting to {self.settings.get('aws_endpoint')} with client ID '{self.settings.get('client_id')}'...")
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
        Decode LW004-PB payload from Base64 encoded string
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
        
        # Add battery level to result
        result["battery_level"] = battery_level
        
        return result

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Hotel LoRa Beacon Management System")
    parser.add_argument('--cert', required=True, help="Path to the certificate file")
    parser.add_argument('--key', required=True, help="Path to the private key file")
    parser.add_argument('--root-ca', required=True, help="Path to the root CA file")
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT, help="AWS IoT endpoint")
    parser.add_argument('--client-id', default=DEFAULT_CLIENT_ID, help="MQTT client ID")
    parser.add_argument('--topic', default=DEFAULT_TOPIC, help="MQTT topic to subscribe to")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose output")
    args = parser.parse_args()

    # Initialize settings
    settings = SettingsManager()
    settings.settings.update({
        "aws_endpoint": args.endpoint,
        "cert_file": args.cert,
        "key_file": args.key,
        "root_ca": args.root_ca,
        "client_id": args.client_id,
        "topic": args.topic
    })

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