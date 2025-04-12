# Hotel Beacons System Report

Generated on: 2025-04-08 16:36:40.158168

## System Summary

The Hotel Beacons System is designed to manage and monitor Bluetooth beacons within a hotel environment. It provides functionality for:

1. Registering and managing beacons associated with hotel rooms
2. Monitoring beacon status and alerts
3. Tracking beacon activity through AWS IoT integration
4. Maintaining a database of beacon configurations and activity logs

## System Structure

Found 8 Python files:

### 2inone.py
* Size: 76001 bytes
* Last modified: 2025-04-08 16:28:03.802263
* Line count: 1862
* Imports:
  * `import json`
  * `import base64`
  * `import time`
  * `import argparse`
  * `import threading`
  * `import os`
  * `import sys`
  * `from datetime import datetime`
  * `import tkinter as tk`
  * `from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog`
  * ... and 1 more
* Classes:
  * `class BeaconDatabase:`
  * `class SettingsManager:`
  * `class AWSIoTClient:`

### 2inone_fixed.py
* Size: 80587 bytes
* Last modified: 2025-04-07 11:35:39.888099
* Line count: 2007
* Imports:
  * `import json`
  * `import os`
  * `import sys`
  * `import sqlite3`
  * `import tkinter as tk`
  * `from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog`
  * `from datetime import datetime`
  * `import threading`
  * `import base64`
  * `import time`
  * ... and 1 more
* Classes:
  * `class BeaconDatabase:`
  * `class SettingsManager:`
  * `class LoRaClient:`
  * `class Application(tk.Tk):`
  * `class SettingsDialog(tk.Toplevel):`
  * ... and 3 more classes

### admin.py
* Size: 83519 bytes
* Last modified: 2025-04-07 11:35:39.923638
* Line count: 1955
* Imports:
  * `import json`
  * `import base64`
  * `import time`
  * `import argparse`
  * `import threading`
  * `import os`
  * `import sys`
  * `from datetime import datetime`
  * `import tkinter as tk`
  * `from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog`
  * ... and 1 more
* Classes:
  * `class BeaconDatabase:`
  * `class SettingsManager:`
  * `class LoRaClient:`
  * `class BeaconApp:`
* Main functions:
  * `def main():`

### check_db.py
* Size: 1504 bytes
* Last modified: 2025-04-08 16:35:13.097694
* Line count: 44
* Imports:
  * `import sqlite3`
* Main functions:
  * `def inspect_db(db_path):`

### CL.py
* Size: 53770 bytes
* Last modified: 2025-04-07 11:35:39.971194
* Line count: 1324
* Imports:
  * `import json`
  * `import os`
  * `import sys`
  * `import tkinter as tk`
  * `from tkinter import ttk, filedialog, messagebox, scrolledtext`
  * `from datetime import datetime`
  * `import threading`
  * `import base64`
  * `import time`
* Classes:
  * `class AWSIoTClient:`
  * `class BeaconApp:`
* Main functions:
  * `def main():`

### import_beacons.py
* Size: 3665 bytes
* Last modified: 2025-04-08 16:35:35.628006
* Line count: 105
* Imports:
  * `import json`
  * `import sqlite3`
  * `from datetime import datetime`
* Main functions:
  * `def import_beacons_from_json(json_file, db_file):`

### new.py
* Size: 66354 bytes
* Last modified: 2025-04-07 11:35:40.065902
* Line count: 1673
* Imports:
  * `import json`
  * `import os`
  * `import sys`
  * `import tkinter as tk`
  * `from tkinter import ttk, filedialog, messagebox, scrolledtext`
  * `from datetime import datetime`
  * `import threading`
  * `import base64`
  * `import time`
* Classes:
  * `class AWSIoTClient:`
  * `class BeaconApp:`
* Main functions:
  * `def main():`

### report_system_info.py
* Size: 9985 bytes
* Last modified: 2025-04-08 16:36:34.716002
* Line count: 259
* Imports:
  * `import os`
  * `import json`
  * `import sqlite3`
  * `import datetime`
* Main functions:
  * `def analyze_database(db_file):`
  * `def analyze_json_file(json_file):`
  * `def analyze_system_structure():`
  * `def generate_system_summary():`
  * `def main():`

## Database Structure

The database 'hotel_beacons.db' contains 2 tables:

### Table: beacons

* Contains 3 records
* Columns:
  * `id` (INTEGER) - PRIMARY KEY
  * `mac_address` (TEXT) - NOT NULL
  * `room_number` (TEXT) - NOT NULL
  * `description` (TEXT)
  * `last_seen` (TEXT)
  * `last_rssi` (INTEGER)
  * `battery_level` (TEXT)
  * `device_mode` (TEXT)
  * `auxiliary_operation` (TEXT)
  * `estimated_distance` (REAL)
  * `is_charging` (BOOLEAN)
  * `created_at` (TEXT)
* Sample data:
  * (1, 'D3:8D:48:10:63:3C', '6h', '', None, None, None, None, None, None, None, '2025-04-08T16:35:41.860275')
  * (2, 'D6:20:31:E8:D8:1D', '87', '', None, None, None, None, None, None, None, '2025-04-08T16:35:41.860275')
  * (3, 'ED:38:4C:1C:47:93', '8i', '', None, None, None, None, None, None, None, '2025-04-08T16:35:41.860275')

### Table: activity_log

* Contains 9 records
* Columns:
  * `id` (INTEGER) - PRIMARY KEY
  * `timestamp` (TEXT) - NOT NULL
  * `beacon_id` (INTEGER)
  * `event_type` (TEXT) - NOT NULL
  * `details` (TEXT)
* Foreign Keys:
  * `beacon_id` references `beacons(id)`
* Sample data:
  * (1, '2025-04-05T16:20:18.550019', None, 'SYSTEM', 'Application started')
  * (2, '2025-04-08T15:17:22.016644', None, 'SYSTEM', 'Application started')
  * (3, '2025-04-08T15:17:55.070197', None, 'SYSTEM', 'Application started')

## JSON File Structure

File: room_mapping_20250326_011231.json
Size: 512 bytes

Root keys in the JSON structure:
* `version`: 1.0
* `export_date`: 2025-03-26T01:12:31.842004
* `beacons`: Array with 3 items

### Beacon Data Analysis

Total beacons: 3

Beacon properties:
* `mac_address`
* `room_number`
* `description`

Sample beacons (first 3):
* Beacon 1:
  * mac_address: D3:8D:48:10:63:3C
  * room_number: 6h
  * description: 

* Beacon 2:
  * mac_address: D6:20:31:E8:D8:1D
  * room_number: 87
  * description: 

* Beacon 3:
  * mac_address: ED:38:4C:1C:47:93
  * room_number: 8i
  * description: 

## Functional Overview

### Key Components

1. **Database Manager (BeaconDatabase class)**
   - Manages beacon registration and updates
   - Tracks beacon activity and status changes
   - Maintains activity logs

2. **AWS IoT Integration (AWSIoTClient class)**
   - Connects to AWS IoT Core for real-time data exchange
   - Processes incoming messages from beacons
   - Handles connection management and security

3. **User Interface**
   - Provides both admin and client interfaces
   - Displays beacon status and alerts
   - Offers configuration and management tools

4. **Data Management**
   - Imports/exports beacon configurations
   - Maintains room mappings
   - Logs system activity

