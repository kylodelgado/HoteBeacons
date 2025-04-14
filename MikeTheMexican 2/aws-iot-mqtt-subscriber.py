#!/usr/bin/env python3
import json
import base64
import time
import argparse
import threading
import os
import sys
from datetime import datetime
# Removed tkinter imports as they are not used in this script version
# import tkinter as tk
# from tkinter import ttk, scrolledtext, messagebox, simpledialog
import sqlite3 # Keep sqlite3 if DB interactions remain relevant to this script's purpose

# Import AWS IoT SDK
try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder
    AWS_IOT_AVAILABLE = True
except ImportError:
    AWS_IOT_AVAILABLE = False
    # Exit if SDK not found for this command-line script
    print("Error: AWS IoT SDK not found. Install with 'pip install awsiotsdk'. Exiting.")
    sys.exit(1) # Changed to exit if SDK is mandatory

# --- Constants ---
# Using defaults from user-provided script where applicable
DEFAULT_ENDPOINT = "a1zzy9gd1wmh90-ats.iot.us-east-1.amazonaws.com"
DEFAULT_CLIENT_ID = "mqtt-subscriber" # From user script args
DEFAULT_TOPIC = "#"

# --- Helper Functions ---

# Added estimate_distance function provided by user
def estimate_distance(rssi, measured_power=-65, n=2.5):
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

        # Ensure rssi is a number before proceeding
        if not isinstance(rssi, (int, float)):
             return "N/A" # Return N/A if RSSI is not valid

        # Calculate distance using path loss formula
        # Prevent division by zero or log of non-positive if rssi == measured_power
        if rssi == measured_power:
             return 1.0 # Assume 1 meter if RSSI matches measured power at 1m

        ratio = (measured_power - rssi) / (10 * n)
        # Avoid potential math errors (e.g., overflow with very large positive ratio)
        if ratio > 70: # exp(70*ln(10)) is already huge
            return "Infinite"
        distance = pow(10, ratio)
        return round(distance, 2)
    except Exception as e:
        print(f"Error calculating distance for RSSI {rssi}: {e}") # Log error
        return "Error" # Indicate calculation error

# --- LoRa Client Class ---
# Simplified for the subscriber script context, keeping the updated decoder

class LoRaClient:
    """Handles communication with AWS IoT Core for LoRaWAN"""

    def __init__(self, endpoint, cert, key, root_ca, client_id, topic, message_callback=None):
        """Initialize the LoRa client"""
        self.endpoint = endpoint
        self.cert_file = cert
        self.key_file = key
        self.root_ca = root_ca
        self.client_id = client_id
        self.topic = topic
        self.message_callback = message_callback
        self.mqtt_connection = None
        self.connected = False

    def connect(self):
        """Connect to AWS IoT Core"""
        if not AWS_IOT_AVAILABLE: return False # Already checked, but good practice

        try:
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.endpoint,
                cert_filepath=self.cert_file,
                pri_key_filepath=self.key_file,
                client_bootstrap=client_bootstrap,
                ca_filepath=self.root_ca,
                client_id=self.client_id,
                on_connection_interrupted=self._on_connection_interrupted,
                on_connection_resumed=self._on_connection_resumed,
                clean_session=False,
                keep_alive_secs=30
            )

            print(f"Connecting to {self.endpoint} with client ID '{self.client_id}'...")
            connect_future = self.mqtt_connection.connect()
            connect_future.result() # Wait for connection
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
        print(f"Connection interrupted. error: {error}")
        self.connected = False

    def _on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        print(f"Connection resumed. return_code: {return_code} session_present: {session_present}")
        self.connected = True
        if not session_present:
             print("Re-subscribing...")
             self._subscribe()

    def _on_connection_success(self, connection, callback_data):
        print("Connection established!")
        self._subscribe()

    def _subscribe(self):
        if not self.mqtt_connection: return
        print(f"Subscribing to topic: {self.topic}")
        subscribe_future, packet_id = self.mqtt_connection.subscribe(
            topic=self.topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=self._on_message_received # Route to the internal callback
        )
        subscribe_result = subscribe_future.result()
        print(f"Subscribed with {str(subscribe_result['qos'])}")


    def _on_message_received(self, topic, payload, dup, qos, retain, **kwargs):
        """Internal message handler that decodes and calls the external callback"""
        try:
            message = json.loads(payload.decode('utf-8'))
            fport = None
            if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
                fport = message["WirelessMetadata"]["LoRaWAN"].get("FPort")

            decoded_payload = {}
            if "PayloadData" in message:
                payload_data = message["PayloadData"]
                # Use the updated decoder function (now part of the class)
                decoded_payload = self._decode_lw004_pb_payload(payload_data, fport)

            # Call the external message callback provided during init
            if self.message_callback:
                self.message_callback(topic, message, decoded_payload)

        except json.JSONDecodeError:
            print(f"Error decoding JSON payload on topic '{topic}': {payload.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"Error processing message on topic '{topic}': {str(e)}")

    # --- Updated Decoder Function (from user input) ---
    def _decode_lw004_pb_payload(self, payload_data, fport):
        """
        Decode LW004-PB payload from Base64 encoded string
        (Incorporates user-provided logic)
        """
        # Decode Base64 payload
        try:
            binary_data = base64.b64decode(payload_data)
        except Exception as e:
            return {"error": f"Invalid Base64 payload: {e}"}

        # Create result dictionary
        result = {
            "raw_hex": binary_data.hex()
        }

        # Check if we have enough data to parse header
        if len(binary_data) < 4:
            result["error"] = "Payload too short for header"
            return result

        # --- Header Parsing ---
        try:
            # Byte 0: Battery Level and Charging Status
            result["battery_level"] = binary_data[0] & 0x7F
            result["is_charging"] = (binary_data[0] & 0x80) > 0
            result["battery"] = f"{result['battery_level']}%" + (" (Charging)" if result["is_charging"] else "")

            # Byte 1: Device Mode and Auxiliary Operation
            device_status = binary_data[1]
            device_mode_code = (device_status >> 4) & 0x0F
            auxiliary_op_code = device_status & 0x0F

            device_modes = {
                1: "Standby Mode", 2: "Timing Mode", 3: "Periodic Mode",
                4: "Stationary in Motion Mode", 5: "Start of Movement",
                6: "In Movement", 7: "End of Movement"
            }
            aux_operations = {
                0: "None", 1: "Downlink for Position", 2: "Man Down Status",
                3: "Alert Alarm", 4: "SOS Alarm"
            }

            result["device_mode_code"] = device_mode_code
            result["auxiliary_operation_code"] = auxiliary_op_code
            result["device_mode"] = device_modes.get(device_mode_code, f"Unknown ({device_mode_code})")
            result["auxiliary_operation"] = aux_operations.get(auxiliary_op_code, f"Unknown ({auxiliary_op_code})")

            # Bytes 2-3: Age (seconds)
            result["age"] = int.from_bytes(binary_data[2:4], byteorder='big')

        except IndexError:
             result["error"] = "Payload length error during header parsing."
             return result
        except Exception as e:
             result["error"] = f"Header parsing error: {e}"
             return result


        # --- FPort Specific Processing ---
        try:
            if fport in [8, 12]:  # Bluetooth Location Fixed Payload
                beacons = []
                offset = 4  # Start after header
                beacon_count = 0
                while offset + 7 <= len(binary_data) and beacon_count < 3:
                    # Extract MAC address (6 bytes)
                    mac_bytes = binary_data[offset:offset+6]
                    mac_address = ':'.join(f'{b:02X}' for b in mac_bytes)

                    # Extract RSSI (1 byte)
                    rssi_byte = binary_data[offset+6]
                    rssi = rssi_byte - 256 if rssi_byte > 127 else rssi_byte

                    # Add beacon info to the list
                    beacons.append({
                        "mac": mac_address,
                        "rssi": f"{rssi} dBm",
                        "rssi_value": rssi  # Keep raw value
                    })

                    offset += 7
                    beacon_count += 1

                result["beacons"] = beacons
                result["beacon_count"] = len(beacons)

            elif fport in [9, 13]:  # Bluetooth Location Failure Payload
                if len(binary_data) >= 5:
                    failure_code = binary_data[4]
                    failure_reasons = {
                        1: "Hardware Error", 2: "Interrupted by Downlink for Position",
                        3: "Interrupted by Man Down Detection", 4: "Interrupted by Alarm function",
                        5: "Bluetooth positioning timeout", 6: "Bluetooth broadcasting in progress",
                        7: "Interrupted positioning at end of movement",
                        8: "Interrupted positioning at start of movement",
                        9: "GPS PDOP Limit", 10: "Other reason"
                    }
                    result["failure_reason_code"] = failure_code
                    result["failure_reason"] = failure_reasons.get(failure_code, f"Unknown ({failure_code})")

            elif fport == 1:  # Event Message Payload
                if len(binary_data) >= 7:
                    # Byte 2: Time Zone
                    time_zone_byte = binary_data[2]
                    time_zone_offset_half_hours = time_zone_byte if time_zone_byte < 128 else time_zone_byte - 256
                    time_zone_value = time_zone_offset_half_hours / 2.0
                    result["time_zone"] = f"UTC{'+' if time_zone_value >= 0 else ''}{time_zone_value:.1f}"

                    # Bytes 3-6: Timestamp (Unix epoch)
                    timestamp = int.from_bytes(binary_data[3:7], byteorder='big')
                    result["timestamp"] = timestamp
                    try:
                        result["timestamp_utc"] = datetime.utcfromtimestamp(timestamp).isoformat() + "Z"
                    except ValueError:
                        result["timestamp_utc"] = "Invalid Timestamp"


                    # Byte 7: Event Type Code (if present)
                    if len(binary_data) >= 8:
                        event_code = binary_data[7]
                        event_types = {
                            0: "Start of movement", 1: "In movement", 2: "End of movement",
                            3: "Start SOS alarm", 4: "SOS alarm exit", 5: "Start Alert alarm",
                            6: "Alert alarm exit", 7: "Man Down start", 8: "Man Down end"
                        }
                        result["event_type_code"] = event_code
                        result["event_type"] = event_types.get(event_code, f"Unknown ({event_code})")

        except IndexError:
             result["warning"] = "Payload ended unexpectedly during FPort-specific parsing."
        except Exception as e:
             result["warning"] = f"Error parsing FPort-specific data: {e}"

        return result

# --- Main Execution Logic ---
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="AWS IoT MQTT Subscriber for LoRa Beacons")
    parser.add_argument('--ports', type=str, default=None,
                        help="Comma-separated list of FPorts to show (e.g., '12,8'). Default: show all")
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT,
                        help=f"Your AWS IoT custom endpoint (default: {DEFAULT_ENDPOINT})")
    # Make certs optional for flexibility, but LoRaClient checks them
    parser.add_argument('--cert', default=None, help="File path to your device certificate")
    parser.add_argument('--key', default=None, help="File path to your private key")
    parser.add_argument('--root-ca', default=None, help="File path to root CA certificate")
    parser.add_argument('--client-id', default=DEFAULT_CLIENT_ID, help="MQTT client ID")
    parser.add_argument('--topic', default=DEFAULT_TOPIC, help="MQTT topic to subscribe to (default: '#')")
    parser.add_argument('--verbose', action='store_true', default=True, help="Increase output verbosity (default: enabled)") # Kept default true as per user script
    args = parser.parse_args()

    # Validate required arguments for connection
    if not all([args.cert, args.key, args.root_ca]):
         parser.error("--cert, --key, and --root-ca are required for mTLS connection.")

    # --- Message Callback Function ---
    def on_message_received_callback(topic, message, decoded_payload):
        """Callback function to process and print received messages"""
        # Filter by FPort if specified
        fport = None
        if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
            fport = message["WirelessMetadata"]["LoRaWAN"].get("FPort")

        if args.ports is not None:
            try:
                allowed_ports = [int(port.strip()) for port in args.ports.split(',')]
                if fport is None or fport not in allowed_ports:
                    return # Skip message if FPort doesn't match
            except ValueError:
                print(f"Warning: Invalid --ports argument '{args.ports}'. Showing all ports.")


        # Print detailed output
        print("\n----- New Message -----")
        print(f"Topic: {topic}")
        if args.verbose:
            print(f"Full Message: {json.dumps(message, indent=2)}")

        # Print LoRaWAN Metadata
        if "WirelessMetadata" in message and "LoRaWAN" in message["WirelessMetadata"]:
            lorawan = message["WirelessMetadata"]["LoRaWAN"]
            print("\n----- LoRaWAN Metadata -----")
            print(f"DevEui: {lorawan.get('DevEui', 'N/A')}")
            print(f"FPort: {lorawan.get('FPort', 'N/A')}")
            print(f"FCnt: {lorawan.get('FCnt', 'N/A')}")
            print(f"Timestamp: {lorawan.get('Timestamp', 'N/A')}")
            if "Gateways" in lorawan and lorawan["Gateways"]:
                for gateway in lorawan["Gateways"]:
                    print(f"  Gateway: {gateway.get('GatewayEui', 'N/A')}, RSSI: {gateway.get('Rssi', 'N/A')}, SNR: {gateway.get('Snr', 'N/A')}")

        # Print Decoded Payload Details
        print("\n----- Decoded Payload -----")
        if "error" in decoded_payload:
            print(f"Error: {decoded_payload['error']}")
            if "raw_hex" in decoded_payload: print(f"Raw Hex: {decoded_payload['raw_hex']}")
        elif not decoded_payload:
            print("No payload data to decode.")
        else:
            # Print general decoded fields
            for key, value in decoded_payload.items():
                if key not in ["raw_hex", "beacons"]: # Print everything except raw hex and the beacons list itself
                    print(f"{key.replace('_', ' ').title()}: {value}")

            # Special formatting for detected beacons
            if "beacons" in decoded_payload and decoded_payload["beacons"]:
                print("\n📡 BEACONS DETECTED 📡")
                for i, beacon in enumerate(decoded_payload["beacons"]):
                    rssi_val = beacon.get("rssi_value")
                    dist_str = estimate_distance(rssi_val)
                    dist_str = f"{dist_str} meters" if isinstance(dist_str, (float, int)) else dist_str # Add units
                    print(f"  Beacon {i+1}: MAC={beacon.get('mac')}, RSSI={beacon.get('rssi')}, Est. Dist={dist_str}")

            # Special formatting for failure
            elif "failure_reason" in decoded_payload:
                print(f"\n❌ Beacon Detection Failed: {decoded_payload.get('failure_reason')}")

        print("-" * 50) # Separator

    # --- Initialize and Connect ---
    client = LoRaClient(
        endpoint=args.endpoint,
        cert=args.cert,
        key=args.key,
        root_ca=args.root_ca,
        client_id=args.client_id,
        topic=args.topic,
        message_callback=on_message_received_callback
    )

    if client.connect():
        print("Subscriber connected and waiting for messages...")
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nDisconnecting...")
            client.disconnect()
            print("Disconnected!")
    else:
        print("Failed to connect to AWS IoT Core.")