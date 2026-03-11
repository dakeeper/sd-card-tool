# SD Card Tool

A menu-driven utility for backing up, restoring, formatting, and cloning SD cards.

## Features

- **Backup** - Create compressed image files from SD cards
- **Restore** - Write image files to SD cards
- **Format** - Format SD cards with FAT32, ext4, or NTFS
- **Clone** - Clone one SD card directly to another
- **Mass Clone** - Clone one SD card to multiple SD cards simultaneously

## Requirements

- Linux OS
- Python 3
- Root privileges (sudo)
- `pv` package (for progress display)

## Installation Step by Step

### Step 1: Install Dependencies

```bash
# Update package list
sudo apt update

# Install pv (pipe viewer for progress display)
sudo apt install pv
```

### Step 2: Download the Tool

```bash
# Create a directory for the tool
mkdir -p ~/sd-card-tool
cd ~/sd-card-tool

# Download the tool from GitHub
wget https://github.com/dakeeper/sd-card-tool/raw/main/sd-card-tool.py
```

### Step 3: Make Executable

```bash
chmod +x sd-card-tool.py
```

### Step 4: Run the Tool

```bash
sudo python3 sd-card-tool.py
```

**Note:** The tool requires root privileges to access block devices (SD cards).

## Usage

```bash
sudo python3 sd-card-tool.py
```

### Menu Options

1. **Backup** - Select an SD card and create a compressed image file
2. **Restore** - Write an image file to an SD card
3. **Format** - Format an SD card (FAT32/ext4/NTFS)
4. **Clone** - Clone one SD card to another
5. **Mass Clone** - Clone one SD card to multiple SD cards simultaneously
6. **Exit** - Quit the application

### Progress Display

The tool shows real-time progress with:
- Progress bar
- Percentage complete
- Transfer speed
- Estimated time remaining

## Example Workflow

### Backup an SD Card

1. Select option `1` for Backup
2. Choose your SD card from the list
3. Enter the output directory (press Enter for home)
4. Enter a filename or use the default
5. Confirm with `YES`
6. Wait for the backup to complete

### Restore an SD Card

1. Select option `2` for Restore
2. Enter the directory containing your image files
3. Choose the image file to restore
4. Choose the target SD card
5. Confirm with `YES`
6. Wait for the restore to complete

### Mass Clone (Clone to Multiple SD Cards)

1. Select option `5` for Mass Clone
2. Choose the source SD card (the one to clone from)
3. Add destination drives one by one (press `A` to add, repeat for each drive)
4. When done adding drives, press `D` to start cloning
5. Confirm with `YES`
6. The tool will clone to all selected drives in parallel
7. Progress is shown for each drive

## Troubleshooting

### "Permission denied" error
Make sure to run the tool with sudo:
```bash
sudo python3 sd-card-tool.py
```

### "No removable drives found"
- Check if the SD card is properly inserted
- Try reinserting the SD card reader
- Use `lsblk` to verify the device is detected

### "pv: command not found"
Install pv:
```bash
sudo apt install pv
```

## Notes

- Always use sudo to ensure proper access to block devices
- Be careful when selecting destination drives - all data will be overwritten
- The tool automatically detects removable USB/SD card devices
- Backups are saved as compressed `.img.gz` files to save space
- Always unmount the SD card before removing it
