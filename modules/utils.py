import json
import os
import logging
import subprocess
import pandas as pd

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def load_json(filename, default=None):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default or {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default or {}

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def load_members_from_excel():
    """
    Reads members from HOSPITALITY MEMBERS.xlsx (fallback to protocol data.xlsx) in the root directory.
    Headers are normalized (stripped and upper-cased) to map to internal keys.
    Handles Excel locks on Windows by creating a shadow copy via PowerShell Copy-Item.
    """
    root_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root_dir, 'HOSPITALITY MEMBERS.xlsx')
    
    # Fallback to old name if the new one doesn't exist
    if not os.path.exists(path):
        fallback_path = os.path.join(root_dir, 'protocol data.xlsx')
        if os.path.exists(fallback_path):
            path = fallback_path
        else:
            logger.warning(f"Excel file not found at {path} or {fallback_path}")
            return []
    
    df = None
    temp_path = None
    
    try:
        # Try to read directly first
        df = pd.read_excel(path)
    except PermissionError:
        # File is probably locked by Excel on Windows
        logger.info(f"Excel file {os.path.basename(path)} is locked. Attempting to read via a shadow copy...")
        temp_path = os.path.join(root_dir, 'temp_shadow_copy.xlsx')
        try:
            # Use PowerShell's Copy-Item which successfully copies Excel-locked files on Windows
            cmd = f'powershell -Command "Copy-Item -Path \'{path}\' -Destination \'{temp_path}\' -Force"'
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(temp_path):
                df = pd.read_excel(temp_path)
            else:
                raise FileNotFoundError("Shadow copy failed to create.")
        except Exception as e:
            logger.error(f"Failed to bypass Excel lock using shadow copy: {e}")
            return []
    except Exception as e:
        logger.error(f"Error reading Excel file directly: {e}")
        return []
    finally:
        # Clean up shadow copy if created
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Could not remove temporary shadow copy {temp_path}: {e}")
                
    if df is None:
        return []

    try:
        # Normalize column names by stripping spaces and upper-casing
        df.columns = [str(col).strip().upper() for col in df.columns]
        
        # Map messy Excel headers to internal keys
        mapping = {
            'FULL NAME': 'NAME',
            'NAME': 'NAME',
            'COLLEGE': 'COLLEGE',
            'HALL OF RESIDENCE': 'HALL',
            'HALL': 'HALL',
            'ROOM NUMBER': 'ROOM',
            'ROOM': 'ROOM',
            'TELEGRAM USERNAME': 'TELEGRAM_HANDLE',
            'TELEGRAM HANDLE': 'TELEGRAM_HANDLE',
            'TELEGRAM USER NAME': 'TELEGRAM_HANDLE',
            'USERNAME': 'TELEGRAM_HANDLE',
            'TELEGRAM_HANDLE': 'TELEGRAM_HANDLE',
            'TELEGRAM PHONE NUMBER': 'PHONE',
            'PHONE': 'PHONE',
            'NUMBER': 'PHONE',
            'TELEGRAM_ID': 'TELEGRAM_ID'
        }
        
        # Rename based on mapping if column found
        df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
        
        required = ['NAME', 'COLLEGE', 'HALL']
        for col in required:
            if col not in df.columns:
                logger.error(f"Missing required column {col} in Excel (tried mapping as well). Available: {df.columns.tolist()}")
                return []
        
        members = []
        for _, row in df.iterrows():
            if pd.notna(row['NAME']):
                members.append({
                    "name": str(row['NAME']).strip(),
                    "college": str(row['COLLEGE']).strip() if pd.notna(row['COLLEGE']) else "",
                    "hall": str(row['HALL']).strip() if pd.notna(row['HALL']) else "",
                    "telegram_id": int(row['TELEGRAM_ID']) if 'TELEGRAM_ID' in row and pd.notna(row['TELEGRAM_ID']) else None,
                    "telegram_handle": str(row['TELEGRAM_HANDLE']).strip() if 'TELEGRAM_HANDLE' in row and pd.notna(row['TELEGRAM_HANDLE']) else None
                })
        return members
    except Exception as e:
        logger.error(f"Error processing excel data: {e}")
        return []

def save_weekly_roster(roster):
    save_json('weekly_roster.json', roster)

def load_weekly_roster():
    """Load the current weekly roster from json."""
    return load_json('weekly_roster.json', default={})

def load_roster_history():
    """Load the assignment history to ensure fair rotation."""
    return load_json('roster_history.json', default={})

def save_roster_history(history):
    """Save the assignment history."""
    save_json('roster_history.json', history)
