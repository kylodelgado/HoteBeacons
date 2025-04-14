"""
FIXED VERSION OF THE BEACON ALERT MANAGER WITH IMPROVED AWS CONNECTIVITY

This file contains the enhanced AWS connectivity functionality from admin.py implemented in CL.py.
The main improvements include:

1. Enhanced AWSIoTClient class with:
   - Improved message handling
   - Advanced payload decoding capabilities
   - Beacon detection and distance estimation
   - Better error handling and connection management

2. Modified handle_aws_message method to:
   - Work with decoded payloads
   - Extract more accurate beacon information
   - Properly identify and process alert messages

3. Upgraded connect_to_aws method with:
   - Better connection handling
   - More reliable threading
   - Improved error reporting

These changes make the AWS IoT connectivity more reliable and provide better handling
of beacon data from LoRaWAN messages.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
import base64
import time

# Import AWS IoT SDK
try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder

    AWS_IOT_AVAILABLE = True
except ImportError:
    AWS_IOT_AVAILABLE = False
    print("Warning: AWS IoT SDK not found. Install with 'pip install awsiotsdk' for IoT connectivity.")

# Application constants
APP_TITLE = "Beacon Alert Manager"
APP_VERSION = "1.1"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "beacon_alert_manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ALARM_HISTORY_FILE = os.path.join(CONFIG_DIR, "alarm_history.json")
PASSWORD = "3456"  # Пароль для доступу до налаштувань

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)


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

            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.settings.get("aws", {}).get("endpoint", ""),
                cert_filepath=self.settings.get("cert_file", ""),
                pri_key_filepath=self.settings.get("key_file", ""),
                client_bootstrap=client_bootstrap,
                ca_filepath=self.settings.get("root_ca", ""),
                client_id=self.settings.get("aws", {}).get("client_id", "beacon-client"),
                on_connection_interrupted=self._on_connection_interrupted,
                on_connection_resumed=self._on_connection_resumed,
                clean_session=False,
                keep_alive_secs=30
            )

            print(f"Connecting to {self.settings.get('aws', {}).get('endpoint')} with client ID '{self.settings.get('aws', {}).get('client_id')}'...")
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
        print(f"Subscribing to topic: {self.settings.get('aws', {}).get('topic', '#')}")
        connection.subscribe(
            topic=self.settings.get('aws', {}).get('topic', '#'),
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


class BeaconApp:
    """Application for managing beacon configurations and viewing alert history"""

    def __init__(self, root):
        """Initialize the application"""
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(800, 600)

        # Set application style
        self.setup_styles()

        # Try to set window icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beacon_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Could not set icon: {e}")

        # Initialize data structures
        self.config = self.load_config()
        self.alarm_history = self.load_alarm_history()
        
        # Initialize beacons mapping dictionary
        self.beacons_mapping = {}
        
        # Load beacon mapping if settings file exists
        self.load_beacons_mapping()

        # Initialize AWS IoT client
        self.aws_client = None
        self.aws_connection_status = tk.StringVar(value="Disconnected")

        # Create main UI
        self.create_main_ui()

        # Auto-connect to AWS IoT if config is available
        self.connect_to_aws()

        # Start background thread for automatic reconnection
        threading.Thread(target=self.auto_reconnect, daemon=True).start()

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

    def load_config(self):
        """Load configuration from file or return default"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")

        # Return default config
        return {
            "settings_file": "",
            "cert_file": "",
            "key_file": "",
            "root_ca": "",
            "aws": {
                "endpoint": "",
                "client_id": "beacon-client",
                "topic": "#",
                "alert_topic": "beacon/alerts"
            }
        }

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти конфігурацію: {e}")
            return False

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

    def create_main_ui(self):
        """Create the main application UI with history view"""
        # Create menu (with settings in File menu)
        self.create_menu()

        # Create header frame
        header_frame = ttk.Frame(self.root, style="Header.TFrame")
        header_frame.pack(fill=tk.X)

        # Application title in header
        ttk.Label(
            header_frame,
            text=APP_TITLE,
            style="Header.TLabel"
        ).pack(side=tk.LEFT, padx=15, pady=10)

        # AWS connection status in header
        self.aws_status_label = ttk.Label(
            header_frame,
            textvariable=self.aws_connection_status,
            style="Disconnected.TLabel"
        )
        self.aws_status_label.pack(side=tk.RIGHT, padx=15, pady=10)

        # Main content area with padding
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create history label frame with a subtle border
        history_frame = ttk.LabelFrame(
            main_frame,
            text="Історія тривог",
            padding=10
        )
        history_frame.pack(fill=tk.BOTH, expand=True)

        # Create toolbar for history actions
        toolbar_frame = ttk.Frame(history_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))

        # Left side - action buttons
        actions_frame = ttk.Frame(toolbar_frame)
        actions_frame.pack(side=tk.LEFT)

        # Action buttons with improved styling
        refresh_btn = ttk.Button(
            actions_frame,
            text="Оновити",
            style="Action.TButton",
            command=self.refresh_history,
            width=10
        )
        refresh_btn.pack(side=tk.LEFT, padx=(0, 5))

        export_btn = ttk.Button(
            actions_frame,
            text="Експорт",
            style="Action.TButton",
            command=self.export_history,
            width=10
        )
        export_btn.pack(side=tk.LEFT, padx=5)

        clear_btn = ttk.Button(
            actions_frame,
            text="Очистити",
            style="Action.TButton",
            command=self.clear_history,
            width=10
        )
        clear_btn.pack(side=tk.LEFT, padx=5)

        # Right side - search box
        search_frame = ttk.Frame(toolbar_frame)
        search_frame.pack(side=tk.RIGHT)

        ttk.Label(search_frame, text="Пошук:").pack(side=tk.LEFT, padx=(0, 5))

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

        # Status bar with application info
        self.status_var = tk.StringVar(value=f"{APP_TITLE} v{APP_VERSION}")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(10, 2)
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Display initial history
        self.refresh_history()

    def create_menu(self):
        """Create application menu with settings in File menu"""
        self.menu = tk.Menu(self.root)
        self.root.config(menu=self.menu)

        # File menu (with settings)
        file_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Налаштування", command=self.show_password_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.root.destroy)

        # AWS menu
        aws_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="AWS", menu=aws_menu)
        aws_menu.add_command(label="Відключитися", command=self.disconnect_from_aws)
        aws_menu.add_command(label="Підключитися", command=self.connect_to_aws)
        aws_menu.add_separator()
        aws_menu.add_command(label="Перевірити з'єднання", command=self.check_aws_connection)

        # History menu
        history_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Історія", menu=history_menu)
        history_menu.add_command(label="Оновити", command=self.refresh_history)
        history_menu.add_command(label="Експорт", command=self.export_history)
        history_menu.add_command(label="Очистити", command=self.clear_history)

        # Help menu
        help_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Довідка", menu=help_menu)
        help_menu.add_command(label="Про програму", command=self.show_about)

    def connect_to_aws(self):
        """Connect to AWS IoT Core with improved handling"""
        if not AWS_IOT_AVAILABLE:
            self.status_var.set("AWS IoT SDK not installed. Install with 'pip install awsiotsdk'")
            return

        # Check if already connected
        if self.aws_client and self.aws_client.connected:
            self.status_var.set("Already connected to AWS IoT Core")
            return

        # Check for required configuration
        endpoint = self.config.get("aws", {}).get("endpoint")
        cert_file = self.config.get("cert_file")
        key_file = self.config.get("key_file")
        root_ca = self.config.get("root_ca")

        if not endpoint or not cert_file or not key_file or not root_ca:
            self.status_var.set("AWS IoT configuration is incomplete. Please check settings.")
            return

        # Check if certificate files exist
        if not os.path.exists(cert_file):
            self.status_var.set(f"Certificate file not found: {cert_file}")
            return

        if not os.path.exists(key_file):
            self.status_var.set(f"Key file not found: {key_file}")
            return

        if not os.path.exists(root_ca):
            self.status_var.set(f"Root CA file not found: {root_ca}")
            return

        # Create AWS IoT client and connect in a separate thread to avoid freezing UI
        def connect_thread():
            self.status_var.set("Connecting to AWS IoT Core...")
            self.aws_connection_status.set("Connecting...")
            self.aws_status_label.configure(style="Disconnected.TLabel")
            
            # Use our enhanced AWSIoTClient with improved message handling
            self.aws_client = AWSIoTClient(self.config, message_callback=self.handle_aws_message)

            if self.aws_client.connect():
                # Update UI from main thread
                self.root.after(0, self.update_aws_connected_status)
            else:
                # Update UI from main thread
                self.root.after(0, lambda: self.status_var.set("Failed to connect to AWS IoT Core"))
                self.root.after(0, lambda: self.aws_connection_status.set("Disconnected"))
                self.root.after(0, lambda: self.aws_status_label.configure(style="Disconnected.TLabel"))
                
                # Try reconnecting in the background via auto_reconnect thread
                print("Initial connection failed. Will try again in background...")

        # Start connection thread
        threading.Thread(target=connect_thread, daemon=True).start()

    def update_aws_connected_status(self):
        """Update UI elements to show AWS connected status"""
        self.aws_connection_status.set("Connected")
        self.aws_status_label.configure(style="Connected.TLabel")
        self.status_var.set(f"Connected to AWS IoT Core endpoint: {self.config.get('aws', {}).get('endpoint')}")

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
                    self.root.after(0, self.update_aws_disconnected_status)
                else:
                    self.root.after(0, lambda: self.status_var.set("Error disconnecting from AWS IoT Core"))

            threading.Thread(target=disconnect_thread, daemon=True).start()
        else:
            self.update_aws_disconnected_status()

    def check_aws_connection(self):
        """Check AWS IoT connection status"""
        if self.aws_client and self.aws_client.connected:
            messagebox.showinfo("AWS IoT Status",
                                f"Connected to AWS IoT Core\nEndpoint: {self.config.get('aws', {}).get('endpoint')}\nTopic: {self.config.get('aws', {}).get('topic')}")
        else:
            messagebox.showinfo("AWS IoT Status", "Not connected to AWS IoT Core")

    def handle_aws_message(self, topic, message, decoded_payload=None):
        """Handle messages from AWS IoT Core with enhanced decoding"""
        try:
            # Check if this is an alert message
            alert_topic = self.config.get("aws", {}).get("alert_topic", "beacon/alerts")
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

                # Show notification with custom Toplevel window
                self.show_alert_notification(alert_data)
        except Exception as e:
            print(f"Error handling AWS message: {str(e)}")

    def auto_reconnect(self):
        """Фоновий потік для автоматичного відновлення з'єднання з AWS IoT"""
        # Wait a bit before starting reconnection attempts to allow initial connection to complete
        time.sleep(5)
        
        while True:
            if self.aws_client is None or not self.aws_client.connected:
                print("AWS IoT connection lost or not established. Attempting to connect...")
                self.connect_to_aws()
            time.sleep(10)

    def show_alert_notification(self, alert_data):
        """Show a fullscreen notification for a new alert with blinking red-black background"""
        room = alert_data.get("room_number", "Unknown")
        beacon_mac = alert_data.get("beacon_mac", "Unknown")
        rssi = alert_data.get("rssi", "N/A")
        timestamp = alert_data.get("timestamp", "")
        
        # Find description if available
        description = ""
        if beacon_mac in self.beacons_mapping:
            description = self.beacons_mapping[beacon_mac].get("description", "")

        # Створюємо нове вікно на весь екран
        alert_window = tk.Toplevel(self.root)
        alert_window.title("ТРИВОГА!")
        alert_window.attributes("-topmost", True)
        
        # Make window fullscreen
        alert_window.attributes("-fullscreen", True)
        
        # Get screen width and height
        screen_width = alert_window.winfo_screenwidth()
        screen_height = alert_window.winfo_screenheight()
        
        # Variables for blinking effect
        blink_color = "red"
        is_blinking = True
        
        # Фрейм для вмісту на весь екран
        info_frame = ttk.Frame(alert_window, padding=20)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure background color and create a canvas for blinking effect
        canvas = tk.Canvas(info_frame, bg="red", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # Create text with white font - ALERT MESSAGE FIRST
        title_text = canvas.create_text(
            screen_width // 2, 
            screen_height // 4,
            text="УВАГА! ТРИВОГА!", 
            font=("Arial", 48, "bold"), 
            fill="white",
            justify=tk.CENTER
        )
        
        # ROOM NUMBER MORE PROMINENTLY
        room_text = canvas.create_text(
            screen_width // 2, 
            screen_height // 2,
            text=f"КІМНАТА: {room}", 
            font=("Arial", 72, "bold"), 
            fill="white",
            justify=tk.CENTER
        )
        
        # Add description if available
        if description:
            desc_text = canvas.create_text(
                screen_width // 2, 
                screen_height // 2 + 100,
                text=description, 
                font=("Arial", 36), 
                fill="white",
                justify=tk.CENTER
            )
        
        # Beacon info in smaller font
        beacon_text = canvas.create_text(
            screen_width // 2, 
            screen_height * 3 // 4 - 50,
            text=f"Бікон: {beacon_mac}", 
            font=("Arial", 18), 
            fill="white",
            justify=tk.CENTER
        )
        
        time_text = canvas.create_text(
            screen_width // 2, 
            screen_height * 3 // 4,
            text=f"Час: {timestamp}", 
            font=("Arial", 16), 
            fill="white",
            justify=tk.CENTER
        )
        
        # Create button to close the alert
        button_frame = tk.Frame(canvas, bg="red")
        button_frame.place(relx=0.5, rely=0.9, anchor=tk.CENTER)
        
        close_btn = tk.Button(
            button_frame, 
            text="ЗАКРИТИ ТРИВОГУ", 
            command=alert_window.destroy,
            font=("Arial", 16, "bold"),
            bg="white",
            fg="red",
            padx=20,
            pady=10,
            relief=tk.RAISED,
            bd=5
        )
        close_btn.pack(pady=10)
        
        # Function to handle escape key to close alert
        def close_alert(event=None):
            alert_window.destroy()
        
        # Bind escape key to close alert
        alert_window.bind("<Escape>", close_alert)
        
        # Function for blinking effect
        def blink():
            nonlocal blink_color, is_blinking
            if not is_blinking:
                return
            
            blink_color = "black" if blink_color == "red" else "red"
            canvas.config(bg=blink_color)
            button_frame.config(bg=blink_color)
            alert_window.after(500, blink)  # Blink every 500ms
        
        # Start blinking
        blink()
        
        # Auto-close after 30 seconds
        alert_window.after(30000, alert_window.destroy)

    def show_password_dialog(self):
        """Show password dialog to access settings"""
        pwd_dialog = tk.Toplevel(self.root)
        pwd_dialog.title("Доступ до налаштувань")
        pwd_dialog.geometry("350x180")
        pwd_dialog.resizable(False, False)
        pwd_dialog.transient(self.root)
        pwd_dialog.grab_set()

        # Make dialog modal
        pwd_dialog.focus_set()
        pwd_dialog.focus_force()

        # Center on parent
        pwd_dialog.update_idletasks()
        width = pwd_dialog.winfo_width()
        height = pwd_dialog.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        pwd_dialog.geometry(f'{width}x{height}+{x}+{y}')

        # Content frame with padding
        content_frame = ttk.Frame(pwd_dialog, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(
            content_frame,
            text="Введіть пароль",
            font=("Segoe UI", 14, "bold")
        ).pack(pady=(0, 15))

        # Message
        ttk.Label(
            content_frame,
            text="Для доступу до налаштувань необхідно ввести пароль:",
            wraplength=300
        ).pack(pady=(0, 10))

        # Password entry
        pwd_var = tk.StringVar()
        pwd_entry = ttk.Entry(content_frame, textvariable=pwd_var, show="•", width=20)
        pwd_entry.pack(pady=5)
        pwd_entry.focus()

        # Button frame
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))

        # Function to check password
        def check_password():
            if pwd_var.get() == PASSWORD:
                pwd_dialog.destroy()
                self.show_settings_window()
            else:
                messagebox.showerror("Помилка", "Невірний пароль")
                pwd_entry.select_range(0, tk.END)
                pwd_entry.focus()

        # Add enter key binding
        pwd_entry.bind("<Return>", lambda event: check_password())

        # Buttons
        ttk.Button(
            button_frame,
            text="Скасувати",
            command=pwd_dialog.destroy
        ).pack(side=tk.RIGHT)

        ttk.Button(
            button_frame,
            text="OK",
            command=check_password,
            style="Action.TButton"
        ).pack(side=tk.RIGHT, padx=10)

    def show_settings_window(self):
        """Show settings window after successful password verification"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Налаштування")
        settings_window.geometry("700x550")
        settings_window.minsize(650, 500)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Center on parent
        settings_window.update_idletasks()
        width = settings_window.winfo_width()
        height = settings_window.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        settings_window.geometry(f'{width}x{height}+{x}+{y}')

        # Header frame with title
        header_frame = ttk.Frame(settings_window, style="Header.TFrame")
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text="Налаштування системи",
            style="Header.TLabel"
        ).pack(side=tk.LEFT, padx=15, pady=10)

        # Main content with notebook
        content_frame = ttk.Frame(settings_window, padding=15)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Create notebook for settings tabs
        notebook = ttk.Notebook(content_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Create JSON configuration tab
        json_frame = ttk.Frame(notebook, padding=15)
        notebook.add(json_frame, text="Конфігурація біконів")

        # JSON file selection with frame
        file_frame = ttk.Frame(json_frame)
        file_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(file_frame, text="JSON файл:").pack(side=tk.LEFT)

        json_path_var = tk.StringVar(value=self.config.get("settings_file", ""))
        self.json_path_entry = ttk.Entry(file_frame, textvariable=json_path_var, width=50)
        self.json_path_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        ttk.Button(
            file_frame,
            text="Огляд...",
            command=self.select_json_file
        ).pack(side=tk.LEFT)

        # Button to load and display JSON structure
        ttk.Button(
            json_frame,
            text="Завантажити та проаналізувати JSON",
            command=self.load_and_display_json,
            style="Action.TButton"
        ).pack(fill=tk.X, pady=(0, 15))

        # Text area to display JSON structure
        json_display_frame = ttk.Frame(json_frame, relief="sunken", borderwidth=1)
        json_display_frame.pack(fill=tk.BOTH, expand=True)

        self.json_display = scrolledtext.ScrolledText(
            json_display_frame,
            height=10,
            width=60,
            font=("Consolas", 10),
            wrap=tk.WORD,
            background="white"
        )
        self.json_display.pack(fill=tk.BOTH, expand=True)

        # Create AWS certificates tab
        cert_frame = ttk.Frame(notebook, padding=15)
        notebook.add(cert_frame, text="AWS Сертифікати")

        # Create grid for certificate fields
        grid_frame = ttk.Frame(cert_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Certificate fields with better layout
        # Certificate file
        ttk.Label(
            grid_frame,
            text="Сертифікат:",
            anchor=tk.E
        ).grid(row=0, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        cert_path_var = tk.StringVar(value=self.config.get("cert_file", ""))
        self.cert_path_entry = ttk.Entry(grid_frame, textvariable=cert_path_var, width=50)
        self.cert_path_entry.grid(row=0, column=1, sticky=tk.EW, pady=10)

        ttk.Button(
            grid_frame,
            text="Огляд...",
            command=lambda: self.select_file("cert_file")
        ).grid(row=0, column=2, padx=10, pady=10)

        # Private key file
        ttk.Label(
            grid_frame,
            text="Приватний ключ:",
            anchor=tk.E
        ).grid(row=1, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        key_path_var = tk.StringVar(value=self.config.get("key_file", ""))
        self.key_path_entry = ttk.Entry(grid_frame, textvariable=key_path_var, width=50)
        self.key_path_entry.grid(row=1, column=1, sticky=tk.EW, pady=10)

        ttk.Button(
            grid_frame,
            text="Огляд...",
            command=lambda: self.select_file("key_file")
        ).grid(row=1, column=2, padx=10, pady=10)

        # Root CA file
        ttk.Label(
            grid_frame,
            text="Root CA:",
            anchor=tk.E
        ).grid(row=2, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        root_ca_var = tk.StringVar(value=self.config.get("root_ca", ""))
        self.root_ca_entry = ttk.Entry(grid_frame, textvariable=root_ca_var, width=50)
        self.root_ca_entry.grid(row=2, column=1, sticky=tk.EW, pady=10)

        ttk.Button(
            grid_frame,
            text="Огляд...",
            command=lambda: self.select_file("root_ca")
        ).grid(row=2, column=2, padx=10, pady=10)

        # AWS endpoint
        ttk.Label(
            grid_frame,
            text="AWS Endpoint:",
            anchor=tk.E
        ).grid(row=3, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        endpoint_var = tk.StringVar(value=self.config.get("aws", {}).get("endpoint", ""))
        self.endpoint_entry = ttk.Entry(grid_frame, textvariable=endpoint_var, width=50)
        self.endpoint_entry.grid(row=3, column=1, sticky=tk.EW, pady=10)

        # AWS client ID
        ttk.Label(
            grid_frame,
            text="Client ID:",
            anchor=tk.E
        ).grid(row=4, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        client_id_var = tk.StringVar(value=self.config.get("aws", {}).get("client_id", "beacon-client"))
        self.client_id_entry = ttk.Entry(grid_frame, textvariable=client_id_var, width=50)
        self.client_id_entry.grid(row=4, column=1, sticky=tk.EW, pady=10)

        # Topic
        ttk.Label(
            grid_frame,
            text="Topic:",
            anchor=tk.E
        ).grid(row=5, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        topic_var = tk.StringVar(value=self.config.get("aws", {}).get("topic", "#"))
        self.topic_entry = ttk.Entry(grid_frame, textvariable=topic_var, width=50)
        self.topic_entry.grid(row=5, column=1, sticky=tk.EW, pady=10)

        # Alert topic
        ttk.Label(
            grid_frame,
            text="Alert Topic:",
            anchor=tk.E
        ).grid(row=6, column=0, sticky=tk.E, padx=(0, 10), pady=10)

        alert_topic_var = tk.StringVar(value=self.config.get("aws", {}).get("alert_topic", "beacon/alerts"))
        self.alert_topic_entry = ttk.Entry(grid_frame, textvariable=alert_topic_var, width=50)
        self.alert_topic_entry.grid(row=6, column=1, sticky=tk.EW, pady=10)

        # Make entries expand with window
        grid_frame.columnconfigure(1, weight=1)

        # Add test AWS connection button
        test_btn_frame = ttk.Frame(cert_frame)
        test_btn_frame.pack(pady=10)

        ttk.Button(
            test_btn_frame,
            text="Тестувати AWS з'єднання",
            command=self.test_aws_connection,
            style="Action.TButton"
        ).pack()

        # Add separator before buttons
        ttk.Separator(settings_window, orient="horizontal").pack(fill=tk.X, padx=15, pady=15)

        # Add buttons at the bottom
        button_frame = ttk.Frame(settings_window, padding=(15, 0, 15, 15))
        button_frame.pack(fill=tk.X)

        ttk.Button(
            button_frame,
            text="Скасувати",
            command=settings_window.destroy,
            width=12
        ).pack(side=tk.RIGHT)

        ttk.Button(
            button_frame,
            text="Зберегти",
            command=lambda: self.update_and_save_config(settings_window),
            style="Action.TButton",
            width=12
        ).pack(side=tk.RIGHT, padx=10)

    def load_and_display_json(self):
        """Load JSON file and display its structure"""
        json_path = self.json_path_entry.get()

        if not json_path or not os.path.exists(json_path):
            messagebox.showerror("Помилка", "Виберіть коректний JSON файл")
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Clear display
            self.json_display.delete(1.0, tk.END)

            # Check if beacons are at root level (new structure) or in rooms.beacons (old structure)
            beacons = []
            if "beacons" in json_data:
                # New structure - beacons at root level
                beacons = json_data.get("beacons", [])
            elif "rooms" in json_data and "beacons" in json_data.get("rooms", {}):
                # Old structure - beacons inside rooms object
                beacons = json_data.get("rooms", {}).get("beacons", [])

            beacon_count = len(beacons)

            # Show summary with pretty formatting
            self.json_display.insert(tk.END, f"📊 Структура JSON файлу\n", "heading")
            self.json_display.insert(tk.END, f"\n🔹 Кількість біконів: {beacon_count}\n", "subheading")

            # Display first 5 beacons as sample
            if beacon_count > 0:
                self.json_display.insert(tk.END, "\n🔸 Приклади біконів:\n", "subheading")
                for i, beacon in enumerate(beacons[:5]):
                    self.json_display.insert(tk.END, f"\n{i + 1}. Кімната: ", "item")
                    self.json_display.insert(tk.END, f"{beacon.get('room_number', 'Невідомо')}\n", "value")
                    self.json_display.insert(tk.END, f"   MAC: ", "item")
                    # Check both mac_address and mac fields to handle different formats
                    mac = beacon.get('mac_address', beacon.get('mac', 'Невідомо'))
                    self.json_display.insert(tk.END, f"{mac}\n", "value")
                    self.json_display.insert(tk.END, f"   Опис: ", "item")
                    self.json_display.insert(tk.END, f"{beacon.get('description', '')}\n", "value")

                if beacon_count > 5:
                    self.json_display.insert(tk.END, f"\n... та ще {beacon_count - 5} біконів\n")

            # Show AWS configuration if present
            if "aws" in json_data:
                self.json_display.insert(tk.END, "\n🔸 Конфігурація AWS:\n", "subheading")
                aws_config = json_data.get("aws", {})
                for key, value in aws_config.items():
                    if key != "password" and key != "secret":  # Don't show sensitive info
                        self.json_display.insert(tk.END, f"  {key}: ", "item")
                        self.json_display.insert(tk.END, f"{value}\n", "value")
                        
            # Also show version info if present
            if "version" in json_data:
                self.json_display.insert(tk.END, f"\n🔸 Версія файлу: {json_data.get('version')}\n", "subheading")
            if "export_date" in json_data:
                self.json_display.insert(tk.END, f"\n🔸 Дата експорту: {json_data.get('export_date')}\n", "subheading")

            # Configure tags for better display
            self.json_display.tag_configure("heading", font=("Segoe UI", 12, "bold"))
            self.json_display.tag_configure("subheading", font=("Segoe UI", 10, "bold"))
            self.json_display.tag_configure("item", font=("Segoe UI", 10, "bold"))
            self.json_display.tag_configure("value", font=("Consolas", 10))

            self.status_var.set(f"Завантажено JSON з {beacon_count} біконами")
            
            # Ask if user wants to import this mapping
            if beacon_count > 0 and messagebox.askyesno("Імпорт маппінгу", 
                                                       f"Знайдено {beacon_count} біконів у файлі. Імпортувати цей маппінг?"):
                self.import_beacons_mapping(json_path)

        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося обробити JSON файл: {e}")

    def import_beacons_mapping(self, json_file_path):
        """Import beacons mapping from JSON file"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update config with this file
            self.config["settings_file"] = json_file_path
            self.save_config()
            
            # Load beacons mapping from the file
            if self.load_beacons_mapping():
                beacon_count = len(self.beacons_mapping)
                messagebox.showinfo("Імпорт успішний", f"Імпортовано {beacon_count} біконів")
                self.status_var.set(f"Імпортовано маппінг: {beacon_count} біконів")
                return True
            else:
                messagebox.showerror("Помилка", "Не вдалося імпортувати маппінг")
                return False
                
        except Exception as e:
            messagebox.showerror("Помилка імпорту", f"Не вдалося імпортувати маппінг: {e}")
            return False

    def update_and_save_config(self, settings_window=None):
        """Update config with current UI values and save"""
        # Update config from entry fields
        self.config["settings_file"] = self.json_path_entry.get()
        self.config["cert_file"] = self.cert_path_entry.get()
        self.config["key_file"] = self.key_path_entry.get()
        self.config["root_ca"] = self.root_ca_entry.get()

        # Ensure AWS config exists
        if "aws" not in self.config:
            self.config["aws"] = {}

        self.config["aws"]["endpoint"] = self.endpoint_entry.get()
        self.config["aws"]["client_id"] = self.client_id_entry.get()
        self.config["aws"]["topic"] = self.topic_entry.get()
        self.config["aws"]["alert_topic"] = self.alert_topic_entry.get()

        # Save configuration
        if self.save_config():
            messagebox.showinfo("Успіх", "Налаштування успішно збережено")
            self.status_var.set("Налаштування збережено")
            
            # Reload beacon mapping if settings file changed
            self.load_beacons_mapping()

            # If we're currently connected, ask to reconnect with new settings
            if self.aws_client and self.aws_client.connected:
                if messagebox.askyesno("AWS Connection", "AWS налаштування змінено. Перепідключитися зараз?"):
                    self.disconnect_from_aws()
                    self.root.after(1000, self.connect_to_aws)

            # Close settings window if provided
            if settings_window:
                settings_window.destroy()

    def load_beacons_mapping(self):
        """Load beacon room mapping from settings file"""
        settings_file = self.config.get("settings_file", "")
        if settings_file and os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.beacons_mapping = {}
                
                # Check if beacons are at root level or in rooms.beacons
                if "beacons" in data:
                    beacons = data.get("beacons", [])
                elif "rooms" in data and "beacons" in data.get("rooms", {}):
                    beacons = data.get("rooms", {}).get("beacons", [])
                else:
                    beacons = []
                
                # Build mapping dictionary mac_address -> room_number
                for beacon in beacons:
                    mac = beacon.get("mac_address", "")
                    if not mac and "mac" in beacon:
                        mac = beacon.get("mac", "")
                    
                    room = beacon.get("room_number", "")
                    description = beacon.get("description", "")
                    
                    if mac and room:
                        self.beacons_mapping[mac] = {
                            "room_number": room,
                            "description": description
                        }
                
                print(f"Loaded {len(self.beacons_mapping)} beacons from mapping file")
                return True
            except Exception as e:
                print(f"Error loading beacons mapping: {e}")
                return False
        return False

    def select_json_file(self):
        """Open file dialog to select JSON configuration file"""
        filename = filedialog.askopenfilename(
            title="Виберіть JSON файл конфігурації",
            filetypes=[("JSON файли", "*.json"), ("Всі файли", "*.*")]
        )

        if filename:
            self.json_path_entry.delete(0, tk.END)
            self.json_path_entry.insert(0, filename)
            self.config["settings_file"] = filename
            
            # Auto-load the JSON content when a file is selected
            self.load_and_display_json()

    def select_file(self, config_key):
        """Open file dialog to select a file and update config"""
        filename = filedialog.askopenfilename(
            title=f"Виберіть файл",
            filetypes=[("Всі файли", "*.*")]
        )

        if filename:
            if config_key == "cert_file":
                self.cert_path_entry.delete(0, tk.END)
                self.cert_path_entry.insert(0, filename)
            elif config_key == "key_file":
                self.key_path_entry.delete(0, tk.END)
                self.key_path_entry.insert(0, filename)
            elif config_key == "root_ca":
                self.root_ca_entry.delete(0, tk.END)
                self.root_ca_entry.insert(0, filename)

            self.config[config_key] = filename

    def test_aws_connection(self):
        """Test AWS IoT connection with current settings"""
        # Get current settings from fields
        endpoint = self.endpoint_entry.get()
        cert_file = self.cert_path_entry.get()
        key_file = self.key_path_entry.get()
        root_ca = self.root_ca_entry.get()

        # Validate required fields
        if not endpoint or not cert_file or not key_file or not root_ca:
            messagebox.showerror("Error", "All AWS IoT Core fields are required for testing")
            return

        # Check if files exist
        if not os.path.exists(cert_file):
            messagebox.showerror("Error", f"Certificate file not found: {cert_file}")
            return

        if not os.path.exists(key_file):
            messagebox.showerror("Error", f"Key file not found: {key_file}")
            return

        if not os.path.exists(root_ca):
            messagebox.showerror("Error", f"Root CA file not found: {root_ca}")
            return

        # Create temporary config for test
        test_config = {
            "cert_file": cert_file,
            "key_file": key_file,
            "root_ca": root_ca,
            "aws": {
                "endpoint": endpoint,
                "client_id": self.client_id_entry.get(),
                "topic": self.topic_entry.get(),
                "alert_topic": self.alert_topic_entry.get()
            }
        }

        # Show testing dialog
        test_dialog = tk.Toplevel()
        test_dialog.title("Testing AWS Connection")
        test_dialog.geometry("400x200")
        test_dialog.transient(self.root)
        test_dialog.grab_set()

        # Center on parent
        test_dialog.update_idletasks()
        width = test_dialog.winfo_width()
        height = test_dialog.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        test_dialog.geometry(f'{width}x{height}+{x}+{y}')

        # Create progress indicator
        test_frame = ttk.Frame(test_dialog, padding=20)
        test_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            test_frame,
            text="Testing AWS IoT Core Connection...",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(0, 20))

        progress = ttk.Progressbar(test_frame, mode="indeterminate")
        progress.pack(fill=tk.X, pady=10)
        progress.start()

        status_var = tk.StringVar(value="Connecting...")
        status_label = ttk.Label(test_frame, textvariable=status_var)
        status_label.pack(pady=10)

        # Function to run test in background
        def run_test():
            client = AWSIoTClient(test_config)
            result = client.connect()

            # Update UI from main thread
            if result:
                test_dialog.after(0, lambda: status_var.set("Connection successful!"))
                test_dialog.after(0, progress.stop)

                # Disconnect after successful test
                client.disconnect()

                # Close dialog after 2 seconds
                test_dialog.after(2000, test_dialog.destroy)
            else:
                test_dialog.after(0, lambda: status_var.set("Connection failed. Check settings and try again."))
                test_dialog.after(0, progress.stop)

                # Add close button
                test_dialog.after(0, lambda: ttk.Button(
                    test_frame,
                    text="Close",
                    command=test_dialog.destroy
                ).pack(pady=10))

        # Start test in a thread
        threading.Thread(target=run_test, daemon=True).start()

    def refresh_history(self):
        """Refresh the alarm history display with simplified format showing only MAC, room, and time"""
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
            self.history_text.insert(tk.END, "Історія тривог відсутня.", "empty")
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
                timestamp = alarm.get('timestamp', 'Невідома дата')

            # Get room and beacon information
            room = alarm.get('room_number', 'Невідомо')
            beacon_mac = alarm.get('beacon_mac', 'Н/Д')

            # Format entry with simplified styling - only MAC, room, and time
            self.history_text.insert(tk.END, f"ТРИВОГА #{i + 1}\n", 'heading')
            self.history_text.insert(tk.END, f"{timestamp}\n", 'date')
            self.history_text.insert(tk.END, f"Кімната: ", 'label')
            self.history_text.insert(tk.END, f"{room}\n", 'room')
            self.history_text.insert(tk.END, f"MAC: ", 'label')
            self.history_text.insert(tk.END, f"{beacon_mac}\n", 'mac')

            # Add separator line
            self.history_text.insert(tk.END, "\n" + "-" * 60 + "\n\n")
            displayed_count += 1

        # If nothing to display after filtering
        if displayed_count == 0 and search_text:
            self.history_text.insert(tk.END, f"Не знайдено тривог за запитом '{search_text}'.", "empty")

        # Update status
        if search_text:
            self.status_var.set(f"Показано {displayed_count} з {len(sorted_history)} тривог за запитом '{search_text}'")
        else:
            self.status_var.set(f"Показано {displayed_count} тривог")

        self.history_text.config(state=tk.DISABLED)

    def export_history(self):
        """Export alarm history to a file"""
        if not self.alarm_history:
            messagebox.showinfo("Експорт історії", "Немає історії для експорту.")
            return

        # Ask for export location
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON файли", "*.json"), ("Всі файли", "*.*")],
            initialfile=f"alarm_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.alarm_history, f, indent=4)

            messagebox.showinfo("Експорт завершено", f"Історію тривог експортовано до {filename}")
            self.status_var.set(f"Історію експортовано до {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", f"Не вдалося експортувати історію тривог: {e}")

    def clear_history(self):
        """Clear alarm history after confirmation"""
        if not self.alarm_history:
            messagebox.showinfo("Очищення історії", "Немає історії для очищення.")
            return

        if messagebox.askyesno("Очищення історії", "Ви впевнені, що хочете очистити всю історію тривог?"):
            self.alarm_history = []
            self.save_alarm_history()
            self.refresh_history()
            messagebox.showinfo("Очищення історії", "Історію тривог очищено.")
            self.status_var.set("Історію очищено")

    def show_about(self):
        """Show about dialog"""
        about_window = tk.Toplevel(self.root)
        about_window.title("Про програму")
        about_window.geometry("400x320")
        about_window.resizable(False, False)
        about_window.transient(self.root)
        about_window.grab_set()

        # Center on parent
        about_window.update_idletasks()
        width = about_window.winfo_width()
        height = about_window.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        about_window.geometry(f'{width}x{height}+{x}+{y}')

        # Content frame with padding
        content_frame = ttk.Frame(about_window, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Add title and version
        ttk.Label(
            content_frame,
            text=APP_TITLE,
            font=("Segoe UI", 16, "bold"),
            justify="center"
        ).pack(pady=(0, 10))

        ttk.Label(
            content_frame,
            text=f"Версія {APP_VERSION}",
            font=("Segoe UI", 10),
            justify="center"
        ).pack()

        # Add separator
        ttk.Separator(content_frame, orient="horizontal").pack(fill=tk.X, pady=15)

        # Add description
        ttk.Label(
            content_frame,
            text="Програма для керування біконами та моніторингу тривог",
            wraplength=350,
            justify="center"
        ).pack(pady=10)

        ttk.Label(
            content_frame,
            text="Підтримує налаштування JSON-конфігурації та AWS сертифікатів для роботи з біконами.",
            wraplength=350,
            justify="center"
        ).pack(pady=10)

        # Current date at bottom
        current_date = datetime.now().strftime("%Y")
        ttk.Label(
            content_frame,
            text=f"© {current_date}",
            justify="center",
            foreground="gray"
        ).pack(side=tk.BOTTOM, pady=10)

        # Close button
        ttk.Button(
            content_frame,
            text="OK",
            command=about_window.destroy,
            width=10
        ).pack(side=tk.BOTTOM, pady=10)


def main():
    """Main entry point for the application"""
    root = tk.Tk()
    app = BeaconApp(root)

    # Add a friendly reminder about AWS IoT if SDK is not available
    if not AWS_IOT_AVAILABLE:
        messagebox.showwarning(
            "AWS IoT SDK Missing",
            "AWS IoT SDK is not installed. Some features will be unavailable.\n\n"
            "Install with: pip install awsiotsdk"
        )

    root.mainloop()


if __name__ == "__main__":
    main()
