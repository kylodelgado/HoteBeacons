import winreg
import os
import sys
import subprocess
import time
import logging
from datetime import datetime

# Set up logging
log_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "HotelBeacons", "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "startup.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def get_main_app_path():
    """Get the absolute path to the main application executable"""
    if getattr(sys, 'frozen', False):
        # If running as compiled executable
        current_dir = os.path.dirname(sys.executable)
    else:
        # If running from Python script
        current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # The main app should be in the same directory
    main_app_path = os.path.join(current_dir, "HotelBeacons.exe")
    return os.path.abspath(main_app_path)

def add_to_startup():
    try:
        # Get the path to the main application
        main_app_path = get_main_app_path()
        logging.info(f"Main application path: {main_app_path}")
        
        # Create the registry key
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        # Set the value with the full path
        winreg.SetValueEx(
            key,
            "HotelBeacons",
            0,
            winreg.REG_SZ,
            f'"{main_app_path}"'
        )
        
        # Close the key
        winreg.CloseKey(key)
        logging.info("Added to Windows Registry successfully")
        
        # Also add to the Startup folder as a backup method
        startup_folder = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft\\Windows\\Start Menu\\Programs\\Startup'
        )
        
        # Create a shortcut in the startup folder
        shortcut_path = os.path.join(startup_folder, "HotelBeacons.lnk")
        
        # Use PowerShell to create the shortcut
        ps_command = f'''
        $WshShell = New-Object -comObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{main_app_path}"
        $Shortcut.WorkingDirectory = "{os.path.dirname(main_app_path)}"
        $Shortcut.Save()
        '''
        
        subprocess.run(['powershell', '-Command', ps_command], capture_output=True)
        logging.info("Added to Startup folder successfully")
        
        # Test if we can launch the application
        try:
            subprocess.Popen([main_app_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE,
                           cwd=os.path.dirname(main_app_path))
            logging.info("Successfully launched the application for testing")
        except Exception as e:
            logging.error(f"Failed to launch application: {str(e)}")
        
        print("Added to Windows startup successfully!")
        return True
        
    except Exception as e:
        logging.error(f"Error adding to startup: {str(e)}")
        print(f"Error adding to startup: {str(e)}")
        return False

def remove_from_startup():
    try:
        # Remove from Registry
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        try:
            winreg.DeleteValue(key, "HotelBeacons")
            logging.info("Removed from Windows Registry successfully")
        except WindowsError:
            logging.info("No registry entry found to remove")
            pass  # Value might not exist
        
        winreg.CloseKey(key)
        
        # Remove from Startup folder
        startup_folder = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft\\Windows\\Start Menu\\Programs\\Startup'
        )
        shortcut_path = os.path.join(startup_folder, "HotelBeacons.lnk")
        
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)
            logging.info("Removed from Startup folder successfully")
        
        print("Removed from Windows startup successfully!")
        return True
        
    except Exception as e:
        logging.error(f"Error removing from startup: {str(e)}")
        print(f"Error removing from startup: {str(e)}")
        return False

if __name__ == "__main__":
    logging.info("Startup script started")
    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_from_startup()
    else:
        add_to_startup()
    logging.info("Startup script completed") 