#!/usr/bin/env python3
"""
SD Card Backup & Restore Utility
A menu-driven tool for backing up, restoring, and formatting SD cards.
"""

import os
import sys
import subprocess
import glob
import time
import re
from datetime import datetime
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'


def normalize_size(size_str):
    """Normalize size string (convert comma to dot for European format)."""
    if size_str and isinstance(size_str, str):
        return size_str.replace(',', '.')
    return size_str


def parse_dd_progress(line, total_bytes):
    """Parse dd progress line and return progress info."""
    import re
    
    bytes_pattern = r'(\d+)\s*bytes?'
    time_pattern = r',\s*([\d.,]+)\s*s'
    speed_pattern = r',\s*([\d.,]+)\s*(\w+/s)'
    
    bytes_match = re.search(bytes_pattern, line)
    time_match = re.search(time_pattern, line)
    speed_match = re.search(speed_pattern, line)
    
    if bytes_match:
        copied = int(bytes_match.group(1))
        percent = (copied / total_bytes) * 100 if total_bytes > 0 else 0
        
        elapsed_str = time_match.group(1).replace(',', '.') if time_match else "0"
        elapsed = float(elapsed_str) if elapsed_str else 0
        
        speed = "?"
        eta_str = "?:??"
        
        if speed_match and elapsed > 0:
            speed_str = speed_match.group(1).replace(',', '.')
            speed_val = float(speed_str)
            speed_unit = speed_match.group(2)
            speed = f"{speed_val}{speed_unit}"
            
            if speed_val > 0:
                multiplier = 1024 * 1024 if 'M' in speed_unit else (1024 * 1024 * 1024 if 'G' in speed_unit else 1)
                eta_sec = (total_bytes - copied) / (speed_val * multiplier)
                if eta_sec > 0:
                    eta_min = int(eta_sec // 60)
                    eta_sec = int(eta_sec % 60)
                    eta_str = f"{eta_min}:{eta_sec:02d}"
        
        return {
            'copied': copied,
            'percent': percent,
            'speed': speed,
            'eta': eta_str
        }
    return None


def display_progress(proc, total_bytes, drive_size_gb):
    """Display live progress with ETA."""
    import sys
    
    last_line = ""
    while True:
        output = proc.stdout.readline()
        if output == b'' and proc.poll() is not None:
            break
        if output:
            line = output.decode('utf-8', errors='replace').strip()
            if line:
                last_line = line
                info = parse_dd_progress(line, total_bytes)
                if info:
                    bar_len = 30
                    filled = int(bar_len * info['percent'] / 100)
                    bar = '█' * filled + '░' * (bar_len - filled)
                    
                    print(f"\r{Colors.CYAN}[{bar}] {info['percent']:.1f}% | {info['speed']} | ETA: {info['eta']}{Colors.ENDC}", end='', flush=True)
                else:
                    print(f"\r{Colors.CYAN}{line}{Colors.ENDC}", end='', flush=True)
    
    return last_line


def run_command(cmd, capture=True, check=True):
    """Execute a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture,
            text=True, check=check
        )
        return result.stdout.strip() if capture else None
    except subprocess.CalledProcessError as e:
        if capture:
            print(f"{Colors.FAIL}Error: {e.stderr}{Colors.ENDC}")
        raise


def get_removable_drives():
    """Get list of removable drives with detailed info."""
    output = run_command("lsblk -o NAME,SIZE,TYPE,RM,TRAN,MODEL,MOUNTPOINT -J 2>/dev/null || lsblk -o NAME,SIZE,TYPE,RM,TRAN,MODEL,MOUNTPOINT")
    
    if not output:
        return []
    
    try:
        import json
        data = json.loads(output)
        
        drives = []
        for device in data.get('blockdevices', []):
            if device.get('rm') == 1 and device.get('type') == 'disk':
                partitions = []
                for part in device.get('children', []):
                    partitions.append((part['name'], normalize_size(part.get('size', 'Unknown'))))
                
                drives.append({
                    'device': f"/dev/{device['name']}",
                    'size': normalize_size(device.get('size', 'Unknown')),
                    'model': device.get('model', 'Storage Device'),
                    'partitions': partitions
                })
        return drives
    except (Exception, KeyError):
        pass
    
    drives = []
    lines = output.split('\n')
    
    current_drive = None
    partitions = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('NAME'):
            continue
        
        parts = line.split()
        if len(parts) < 4:
            continue
        
        name = parts[0]
        is_partition = 'part' in line.lower()
        
        if is_partition:
            if current_drive:
                size_match = re.search(r'(\d+\.?\d*[GMKT])', line)
                size = size_match.group(1) if size_match else 'Unknown'
                partitions.append((name, size))
        else:
            if current_drive and partitions:
                current_drive['partitions'] = partitions
            
            if 'disk' in line.lower() and ('usb' in line.lower() or '1' in line):
                size_match = re.search(r'(\d+\.?\d*[GMKT])', line)
                size = size_match.group(1) if size_match else 'Unknown'
                
                model = 'Storage Device'
                if 'MODEL' in line.upper():
                    model_idx = -1
                    for i, p in enumerate(parts):
                        if 'GB' in p or 'M' in p:
                            model_idx = i - 1 if i > 0 else -1
                            break
                    if model_idx >= 0 and model_idx < len(parts):
                        model = parts[model_idx]
                
                current_drive = {
                    'device': f'/dev/{name}',
                    'size': size,
                    'model': model,
                    'partitions': []
                }
                partitions = []
    
    if current_drive and partitions:
        current_drive['partitions'] = partitions
        drives.append(current_drive)
    
    try:
        result = run_command("lsblk -J -o NAME,SIZE,TYPE,RM,TRAN,MODEL,MOUNTPOINT,PARTNAME")
        if not result:
            return drives
        import json
        data = json.loads(result)
        
        drives = []
        for device in data.get('blockdevices', []):
            if device.get('rm') == 1 and device.get('type') == 'disk':
                partitions = []
                for part in device.get('children', []):
                    partitions.append((part['name'], part.get('size', 'Unknown')))
                
                drives.append({
                    'device': f"/dev/{device['name']}",
                    'size': device.get('size', 'Unknown'),
                    'model': device.get('model', 'Storage Device'),
                    'partitions': partitions
                })
    except:
        pass
    
    return drives


def get_image_files(directory='~/backups'):
    """Get list of image files in the backups directory."""
    backup_dir = os.path.expanduser(directory)
    
    if not os.path.exists(backup_dir):
        return []
    
    patterns = ['*.img', '*.img.gz', '*.img.xz']
    files = []
    
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(backup_dir, pattern)))
    
    files_with_info = []
    for f in files:
        stat = os.stat(f)
        size_mb = stat.st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        
        files_with_info.append({
            'path': f,
            'name': os.path.basename(f),
            'size': f"{size_mb:.1f}M" if size_mb < 1024 else f"{size_mb/1024:.2f}G",
            'date': mtime.strftime('%Y-%m-%d %H:%M')
        })
    
    return sorted(files_with_info, key=lambda x: x['date'], reverse=True)


def ensure_backup_dir(directory='~/backups'):
    """Ensure backup directory exists."""
    backup_dir = os.path.expanduser(directory)
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def print_header():
    """Print the main menu header."""
    title_text = "Holgi's SD-Card Tool - Backup • Restore • Format"
    width = 90
    centered = title_text.center(width)
    
    print(f"""
{Colors.CYAN}{Colors.BOLD}
    __  __      __      _         _____ ____        ______               __   ______            __
   / / / /___  / /___ _(_)____   / ___// __ \\      / ____/___ __________/ /  /_  __/___  ____  / /
  / /_/ / __ \\/ / __ `/ / ___/   \\__ \\/ / / /_____/ /   / __ `/ ___/ __  /    / / / __ \\/ __ \\/ / 
 / __  / /_/ / / /_/ / (__  )   ___/ / /_/ /_____/ /___/ /_/ / /  / /_/ /    / / / /_/ / /_/ / /  
/_/ /_/\\____/_/\\__, /_/____/   /____/_____/      \\____/\\__,_/_/   \\__,_/    /_/  \\____/\\____/_/   
              /____/ 
{Colors.ENDC}
{Colors.GRAY}{'─' * width}{Colors.ENDC}
  {Colors.BOLD}{centered}{Colors.ENDC}
{Colors.GRAY}{'─' * width}{Colors.ENDC}
""")


def print_drives(drives, title="Available drives:"):
    """Print list of drives with detailed info."""
    print(f"\n{Colors.CYAN}{title}{Colors.ENDC}")
    print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
    print(f"{Colors.BOLD}[#]  Device      Size    Model{Colors.ENDC}")
    print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
    
    for i, drive in enumerate(drives, 1):
        device = drive['device']
        size = drive['size']
        model = drive['model'][:20]
        
        print(f"[{i}]  {device:<10} {size:<8} {model}")
        
        if drive['partitions']:
            for part_name, part_size in drive['partitions']:
                print(f"      ├─ {part_name} ({part_size})")
    
    print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")


def select_drive(drives, title="Select a drive:"):
    """Prompt user to select a drive."""
    if not drives:
        print(f"{Colors.FAIL}No removable drives found!{Colors.ENDC}")
        return None
    
    print_drives(drives, title)
    
    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Select drive [1-{len(drives)}]: {Colors.ENDC}").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(drives):
                return drives[idx]
            else:
                print(f"{Colors.FAIL}Invalid selection. Please try again.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")


def select_image_file():
    """Prompt user to select an image file."""
    home_dir = os.path.expanduser("~")
    
    print(f"\n{Colors.CYAN}Enter image directory (press Enter for home):{Colors.ENDC}")
    print(f"  Default: {home_dir}")
    dir_input = input(f"{Colors.BOLD}Directory: {Colors.ENDC}").strip()
    
    if not dir_input:
        search_dir = home_dir
    else:
        search_dir = os.path.expanduser(dir_input)
    
    files = get_image_files(search_dir)
    
    if not files:
        print(f"{Colors.FAIL}No image files found in {search_dir}{Colors.ENDC}")
        print(f"{Colors.CYAN}Tip: First create a backup to have image files.{Colors.ENDC}")
        return None
    
    print(f"\n{Colors.CYAN}Available image files:{Colors.ENDC}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.BOLD}[#]  Filename                        Size     Date{Colors.ENDC}")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.ENDC}")
    
    for i, f in enumerate(files, 1):
        print(f"[{i}]  {f['name']:<30} {f['size']:<8} {f['date']}")
    
    print(f"{Colors.GRAY}{'─' * 60}{Colors.ENDC}")
    
    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Select image file [1-{len(files)}]: {Colors.ENDC}").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx]
            else:
                print(f"{Colors.FAIL}Invalid selection. Please try again.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")


def confirm_action(operation, source, destination, extra_info=None):
    """Show confirmation dialog for a dangerous action."""
    print(f"\n{Colors.WARNING}{Colors.BOLD}")
    print("╔" + "═" * 50 + "╗")
    print("║" + " ⚠️  FINAL WARNING!  ".center(50) + "║")
    print("╠" + "═" * 50 + "╣")
    print(f"║  Operation:   {operation:<36}║")
    print(f"║  Source:      {source:<36}║")
    print(f"║  Destination: {destination:<36}║")
    if extra_info:
        for info in extra_info:
            print(f"║  {info:<48}║")
    print("╠" + "═" * 50 + "╣")
    
    if "READ" in operation.upper():
        print("║  This will READ from the source drive.            ║")
    else:
        print("║  This will ERASE ALL DATA on the target drive!     ║")
    
    print("╠" + "═" * 50 + "╣")
    print("║  Type \"YES\" to confirm:                            ║")
    print("╚" + "═" * 50 + "╝")
    print(f"{Colors.ENDC}")
    
    confirmation = input(f"{Colors.BOLD}Confirm: {Colors.ENDC}").strip()
    return confirmation.upper() == "YES"


def format_drive_selection():
    """Get filesystem selection."""
    print(f"\n{Colors.CYAN}Select filesystem:{Colors.ENDC}")
    print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
    print(f"[1] FAT32  - Compatible with most devices (cameras, phones, etc.)")
    print(f"[2] ext4   - Linux-only, better performance")
    print(f"[3] NTFS   - Windows-compatible")
    print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
    
    while True:
        choice = input(f"{Colors.BOLD}Filesystem [1-3] (default: 1): {Colors.ENDC}").strip()
        if not choice:
            return 'fat32', 'vfat'
        if choice in ['1', '2', '3']:
            fs_map = {
                '1': ('fat32', 'vfat'),
                '2': ('ext4', 'ext4'),
                '3': ('ntfs', 'ntfs')
            }
            return fs_map[choice]
        print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")


def get_volume_label():
    """Get optional volume label."""
    print(f"\n{Colors.CYAN}Enter volume label (press Enter for no label):{Colors.ENDC}")
    label = input(f"{Colors.BOLD}Label: {Colors.ENDC}").strip()
    return label if label else None


def backup_drive():
    """Create a backup image of the selected drive."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== BACKUP MODE ==={Colors.ENDC}")
    
    drives = get_removable_drives()
    drive = select_drive(drives, "Select source drive to backup:")
    
    if not drive:
        return
    
    print(f"\n{Colors.GREEN}Selected source:{Colors.ENDC}")
    print(f"  Device:     {drive['device']}")
    print(f"  Size:       {drive['size']}")
    print(f"  Model:      {drive['model']}")
    if drive['partitions']:
        print(f"  Partitions: {len(drive['partitions'])}")
    
    home_dir = os.path.expanduser("~")
    default_dir = home_dir
    default_name = f"sd-card-{datetime.now().strftime('%Y%m%d-%H%M%S')}.img.gz"
    
    print(f"\n{Colors.CYAN}Enter output directory (press Enter for home):{Colors.ENDC}")
    print(f"  Default: {default_dir}")
    backup_dir_input = input(f"{Colors.BOLD}Directory: {Colors.ENDC}").strip()
    
    if not backup_dir_input:
        backup_dir = default_dir
    else:
        backup_dir = os.path.expanduser(backup_dir_input)
    
    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            print(f"{Colors.FAIL}Cannot create directory: {e}{Colors.ENDC}")
            return
    
    print(f"\n{Colors.CYAN}Enter output filename:{Colors.ENDC}")
    print(f"  Default: {default_name}")
    print(f"  Directory: {backup_dir}")
    filename = input(f"{Colors.BOLD}Filename: {Colors.ENDC}").strip()
    
    if not filename:
        filename = default_name
    
    if not filename.endswith('.gz'):
        filename += '.gz'
    
    output_path = os.path.join(backup_dir, filename)
    
    if os.path.exists(output_path):
        print(f"{Colors.FAIL}File already exists!{Colors.ENDC}")
        return
    
    if not confirm_action("BACKUP (READ)", drive['device'], output_path, 
                         [f"Size: {drive['size']}"]):
        print(f"{Colors.WARNING}Backup cancelled.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Starting backup...{Colors.ENDC}")
    print(f"{Colors.GRAY}(This may take several minutes){Colors.ENDC}\n")
    
    try:
        run_command(f"umount {drive['device']}* 2>/dev/null", capture=False, check=False)
        
        start_time = time.time()
        
        size_match = re.search(r'(\d+\.?\d*)', drive['size'])
        total_bytes = int(float(size_match.group(1)) * 1024 * 1024 * 1024) if size_match else 0
        
        print(f"\n{Colors.CYAN}Starting backup... (Progress will show below){Colors.ENDC}\n")
        
        cmd = f"pv -f -s {total_bytes} -p -t -e -b -r {drive['device']} | gzip > {output_path}"
        result = subprocess.run(cmd, shell=True)
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            file_size = os.path.getsize(output_path)
            file_size_gb = file_size / (1024 * 1024 * 1024)
            size_match = re.search(r'(\d+\.?\d*)', drive['size'])
            drive_size_gb = float(size_match.group(1)) if size_match else 1.0
            
            print(f"\n{Colors.GREEN}✓ BACKUP COMPLETED SUCCESSFULLY!{Colors.ENDC}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
            print(f"  Source:      {drive['device']} ({drive['size']})")
            print(f"  Output:      {output_path}")
            print(f"  Size:        {drive['size']} → {file_size_gb:.2f}GB ({file_size_gb/drive_size_gb*100:.1f}% of original)")
            print(f"  Time:        {int(elapsed//60)}:{int(elapsed%60):02d}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}Backup failed!{Colors.ENDC}")
            
    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def restore_image():
    """Restore an image to the selected drive."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== RESTORE MODE ==={Colors.ENDC}")
    
    image_file = select_image_file()
    if not image_file:
        return
    
    print(f"\n{Colors.GREEN}Selected image:{Colors.ENDC}")
    print(f"  File:  {image_file['name']}")
    print(f"  Size:  {image_file['size']}")
    print(f"  Date:  {image_file['date']}")
    
    drives = get_removable_drives()
    if not drives:
        print(f"{Colors.FAIL}No removable drives found!{Colors.ENDC}")
        return
    
    drive = select_drive(drives, "Select target drive:")
    
    if not drive:
        return
    
    print(f"\n{Colors.WARNING}⚠ WARNING: ALL DATA WILL BE DESTROYED!{Colors.ENDC}")
    print(f"  Target: {drive['device']} ({drive['size']})")
    
    if not confirm_action("RESTORE (WRITE)", image_file['path'], drive['device'],
                         [f"Image size: {image_file['size']}"]):
        print(f"{Colors.WARNING}Restore cancelled.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Starting restore... (Progress will show below){Colors.ENDC}\n")
    
    try:
        run_command(f"umount {drive['device']}* 2>/dev/null", capture=False, check=False)
        
        start_time = time.time()
        
        size_match = re.search(r'(\d+\.?\d*)', drive['size'])
        total_bytes = int(float(size_match.group(1)) * 1024 * 1024 * 1024) if size_match else 0
        
        if image_file['name'].endswith('.gz'):
            cmd = f"pv -f -s {total_bytes} {image_file['path']} | gzip -dc | pv -f -s {total_bytes} -p -t -e -b -r > {drive['device']}"
        else:
            cmd = f"pv -f -s {total_bytes} -p -t -e -b -r {image_file['path']} > {drive['device']}"
        
        result = subprocess.run(cmd, shell=True)
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"\n{Colors.GREEN}✓ RESTORE COMPLETED SUCCESSFULLY!{Colors.ENDC}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
            print(f"  Source:      {image_file['path']}")
            print(f"  Target:      {drive['device']}")
            print(f"  Time:        {int(elapsed//60)}:{int(elapsed%60):02d}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}Restore failed!{Colors.ENDC}")
            
    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def format_drive():
    """Format the selected drive."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== FORMAT MODE ==={Colors.ENDC}")
    
    drives = get_removable_drives()
    drive = select_drive(drives, "Select drive to format:")
    
    if not drive:
        return
    
    print(f"\n{Colors.GREEN}Selected drive:{Colors.ENDC}")
    print(f"  Device:     {drive['device']}")
    print(f"  Size:       {drive['size']}")
    print(f"  Model:      {drive['model']}")
    
    fs_name, fs_tool = format_drive_selection()
    label = get_volume_label()
    
    if not confirm_action("FORMAT (ERASE)", drive['device'], fs_name.upper(),
                         [f"Filesystem: {fs_name.upper()}", f"Label: {label or 'None'}"]):
        print(f"{Colors.WARNING}Format cancelled.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Starting format...{Colors.ENDC}")
    print(f"{Colors.GRAY}(This may take a few minutes){Colors.ENDC}\n")
    
    try:
        run_command(f"umount {drive['device']}* 2>/dev/null", capture=False, check=False)
        
        mkfs_cmd = f"mkfs.{fs_tool}"
        if label:
            mkfs_cmd += f" -n '{label}'"
        
        run_command(f"{mkfs_cmd} {drive['device']}", capture=False)
        
        print(f"\n{Colors.GREEN}✓ FORMAT COMPLETED SUCCESSFULLY!{Colors.ENDC}")
        print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        print(f"  Device:      {drive['device']}")
        print(f"  Size:       {drive['size']}")
        print(f"  Filesystem: {fs_name.upper()}")
        print(f"  Label:      {label or 'None'}")
        print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        
    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def clone_card():
    """Clone one SD card to another."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== CLONE CARD MODE ==={Colors.ENDC}")
    
    drives = get_removable_drives()
    
    if len(drives) < 2:
        print(f"{Colors.FAIL}Need at least 2 removable drives to clone!{Colors.ENDC}")
        print(f"{Colors.WARNING}Found: {len(drives)} drive(s){Colors.ENDC}")
        return
    
    print(f"\n{Colors.CYAN}Select SOURCE drive (will be read from):{Colors.ENDC}")
    source_drive = select_drive(drives, "Select source drive:")
    
    if not source_drive:
        return
    
    remaining_drives = [d for d in drives if d['device'] != source_drive['device']]
    
    print(f"\n{Colors.CYAN}Select DESTINATION drive (will be written to):{Colors.ENDC}")
    dest_drive = select_drive(remaining_drives, "Select destination drive:")
    
    if not dest_drive:
        return
    
    print(f"\n{Colors.GREEN}Selected drives:{Colors.ENDC}")
    print(f"  Source:      {source_drive['device']} ({source_drive['size']}) - {source_drive['model']}")
    print(f"  Destination: {dest_drive['device']} ({dest_drive['size']}) - {dest_drive['model']}")
    
    if not confirm_action("CLONE (ERASE DESTINATION)", source_drive['device'], dest_drive['device'],
                         [f"Source: {source_drive['size']}", f"Destination: {dest_drive['size']}"]):
        print(f"{Colors.WARNING}Clone cancelled.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Starting clone...{Colors.ENDC}")
    print(f"{Colors.WARNING}ALL DATA ON {dest_drive['device']} WILL BE DESTROYED!{Colors.ENDC}")
    print(f"{Colors.GRAY}(This may take several minutes){Colors.ENDC}\n")
    
    try:
        run_command(f"umount {source_drive['device']}* 2>/dev/null", capture=False, check=False)
        run_command(f"umount {dest_drive['device']}* 2>/dev/null", capture=False, check=False)
        
        start_time = time.time()
        
        size_match = re.search(r'(\d+\.?\d*)', source_drive['size'])
        total_bytes = int(float(size_match.group(1)) * 1024 * 1024 * 1024) if size_match else 0
        
        print(f"\n{Colors.CYAN}Starting clone... (Progress will show below){Colors.ENDC}\n")
        
        cmd = f"pv -s {total_bytes} -p -t -e -b -r {source_drive['device']} > {dest_drive['device']}"
        result = subprocess.run(cmd, shell=True)
        
        print()
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"\n{Colors.GREEN}✓ CLONE COMPLETED SUCCESSFULLY!{Colors.ENDC}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
            print(f"  Source:      {source_drive['device']} ({source_drive['size']})")
            print(f"  Destination: {dest_drive['device']} ({dest_drive['size']})")
            print(f"  Time:        {int(elapsed//60)}:{int(elapsed%60):02d}")
            print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}Clone failed!{Colors.ENDC}")
            
    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def mass_clone():
    """Clone a drive to multiple SD cards simultaneously."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== MASS CLONE MODE ==={Colors.ENDC}")
    
    drives = get_removable_drives()
    
    if len(drives) < 2:
        print(f"{Colors.FAIL}Need at least 2 removable drives for mass clone!{Colors.ENDC}")
        print(f"{Colors.WARNING}Found: {len(drives)} drive(s){Colors.ENDC}")
        return
    
    print(f"\n{Colors.CYAN}Select SOURCE drive (will be read from):{Colors.ENDC}")
    source_drive = select_drive(drives, "Select source drive:")
    
    if not source_drive:
        return
    
    remaining_drives = [d for d in drives if d['device'] != source_drive['device']]
    
    print(f"\n{Colors.GREEN}Selected source: {source_drive['device']} ({source_drive['size']}){Colors.ENDC}")
    
    print(f"\n{Colors.CYAN}Select DESTINATION drives (one at a time):{Colors.ENDC}")
    print(f"{Colors.GRAY}Available drives:{Colors.ENDC}")
    
    dest_drives = []
    while True:
        available = [d for d in remaining_drives if d['device'] not in [x['device'] for x in dest_drives]]
        
        if not available:
            print(f"{Colors.WARNING}No more drives available.{Colors.ENDC}")
            break
        
        print(f"\n{Colors.GRAY}Currently selected: {len(dest_drives)} drive(s){Colors.ENDC}")
        for i, d in enumerate(dest_drives, 1):
            print(f"  [{i}] {d['device']} ({d['size']})")
        
        print(f"\n{Colors.GRAY}Available:{Colors.ENDC}")
        for i, d in enumerate(available, 1):
            print(f"  [{i}] {d['device']} ({d['size']}) - {d['model']}")
        
        print(f"\n{Colors.CYAN}[A]{Colors.ENDC} - Add another destination drive")
        print(f"{Colors.CYAN}[D]{Colors.ENDC} - Done, start cloning")
        print(f"{Colors.CYAN}[C]{Colors.ENDC} - Cancel")
        
        choice = input(f"\n{Colors.BOLD}Choice: {Colors.ENDC}").strip().upper()
        
        if choice == 'A':
            print(f"\n{Colors.CYAN}Select drive to add:{Colors.ENDC}")
            drive = select_drive(available, "Select destination:")
            if drive:
                dest_drives.append(drive)
                print(f"{Colors.GREEN}Added: {drive['device']}{Colors.ENDC}")
        elif choice == 'D':
            break
        elif choice == 'C':
            print(f"{Colors.WARNING}Mass clone cancelled.{Colors.ENDC}")
            return
        else:
            print(f"{Colors.FAIL}Invalid option.{Colors.ENDC}")
    
    if not dest_drives:
        print(f"{Colors.WARNING}No destination drives selected.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Selected drives:{Colors.ENDC}")
    print(f"  Source:      {source_drive['device']} ({source_drive['size']})")
    print(f"  Destinations:")
    for d in dest_drives:
        print(f"    - {d['device']} ({d['size']})")
    
    if not confirm_action("MASS CLONE (ERASE ALL DESTINATIONS)", 
                         source_drive['device'], 
                         f"{len(dest_drives)} drives",
                         [f"Source: {source_drive['size']}", f"Destinations: {len(dest_drives)}"]):
        print(f"{Colors.WARNING}Mass clone cancelled.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}Starting mass clone to {len(dest_drives)} drives...{Colors.ENDC}")
    print(f"{Colors.WARNING}ALL DATA ON DESTINATION DRIVES WILL BE DESTROYED!{Colors.ENDC}")
    print(f"{Colors.GRAY}(This may take several minutes){Colors.ENDC}\n")
    
    try:
        run_command(f"umount {source_drive['device']}* 2>/dev/null", capture=False, check=False)
        for d in dest_drives:
            run_command(f"umount {d['device']}* 2>/dev/null", capture=False, check=False)
        
        start_time = time.time()
        
        size_match = re.search(r'(\d+\.?\d*)', source_drive['size'])
        total_bytes = int(float(size_match.group(1)) * 1024 * 1024 * 1024) if size_match else 0
        
        processes = []
        for d in dest_drives:
            cmd = f"pv -s {total_bytes} -p -t -e -b -r {source_drive['device']} > {d['device']}"
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            processes.append((d, proc, 0))
        
        print(f"\n{Colors.CYAN}Cloning to {len(dest_drives)} drives in parallel... (Progress will show below){Colors.ENDC}\n")
        
        completed = 0
        while completed < len(dest_drives):
            time.sleep(1)
            for i, (d, proc, _) in enumerate(processes):
                if proc.poll() is not None:
                    completed += 1
                    processes[i] = (d, proc, 1)
            
            progress_info = []
            for d, proc, done in processes:
                if done:
                    progress_info.append(f"{d['device']}: Done")
                else:
                    progress_info.append(f"{d['device']}: ...")
            
            print(f"\r{Colors.CYAN}{' | '.join(progress_info)}{Colors.ENDC}", end='', flush=True)
            
            print(f"\r{Colors.CYAN}{' | '.join(progress_info)}{Colors.ENDC}", end='', flush=True)
        
        print(f"\n\n{Colors.GREEN}All clones completed!{Colors.ENDC}")
        
        elapsed = time.time() - start_time
        
        print(f"\n{Colors.GREEN}✓ MASS CLONE COMPLETED SUCCESSFULLY!{Colors.ENDC}")
        print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        print(f"  Source:      {source_drive['device']} ({source_drive['size']})")
        print(f"  Destinations: {len(dest_drives)} drives")
        print(f"  Time:        {int(elapsed//60)}:{int(elapsed%60):02d}")
        print(f"{Colors.GRAY}{'─' * 50}{Colors.ENDC}")
        
    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def print_menu():
    """Print the main menu."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}[1]{Colors.ENDC} Backup   - Create image from SD card")
    print(f"{Colors.CYAN}{Colors.BOLD}[2]{Colors.ENDC} Restore  - Write image to SD card")
    print(f"{Colors.CYAN}{Colors.BOLD}[3]{Colors.ENDC} Format   - Format SD card")
    print(f"{Colors.CYAN}{Colors.BOLD}[4]{Colors.ENDC} Clone    - Clone SD card to another SD card")
    print(f"{Colors.CYAN}{Colors.BOLD}[5]{Colors.ENDC} Mass Clone - Clone to multiple SD cards")
    print(f"{Colors.FAIL}{Colors.BOLD}[6]{Colors.ENDC} Exit{Colors.ENDC}")


def main():
    """Main menu loop."""
    if os.geteuid() != 0:
        print(f"{Colors.WARNING}Warning: This script works best with sudo/root privileges.{Colors.ENDC}")
        print(f"{Colors.WARNING}Some operations may fail without sudo.{Colors.ENDC}\n")
    
    while True:
        print_header()
        print_menu()
        
        choice = input(f"\n{Colors.BOLD}Select option [1-6]: {Colors.ENDC}").strip()
        
        if choice == '1':
            backup_drive()
        elif choice == '2':
            restore_image()
        elif choice == '3':
            format_drive()
        elif choice == '4':
            clone_card()
        elif choice == '5':
            mass_clone()
        elif choice == '6':
            print(f"\n{Colors.GREEN}Goodbye!{Colors.ENDC}")
            break
        else:
            print(f"{Colors.FAIL}Invalid option. Please try again.{Colors.ENDC}")
        
        input(f"\n{Colors.GRAY}Press Enter to continue...{Colors.ENDC}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Interrupted by user.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.FAIL}Fatal error: {e}{Colors.ENDC}")
        sys.exit(1)
