# SD Card Tool

A menu-driven utility for backing up, restoring, formatting, and cloning SD cards.

## Features

- **Backup** - Create compressed image files from SD cards
- **Restore** - Write image files to SD cards
- **Format** - Format SD cards with FAT32, ext4, or NTFS
- **Clone** - Clone one SD card directly to another

## Requirements

- Linux OS
- Python 3
- Root privileges (sudo)
- `pv` package (for progress display)

## Installation

```bash
# Install pv if not present
sudo apt install pv

# Download the tool
wget https://github.com/dakeeper/sd-card-tool/raw/main/sd-card-tool.py

# Make executable
chmod +x sd-card-tool.py
```

## Usage

```bash
sudo python3 sd-card-tool.py
```

### Menu Options

1. **Backup** - Select an SD card and create a compressed image file
2. **Restore** - Write an image file to an SD card
3. **Format** - Format an SD card (FAT32/ext4/NTFS)
4. **Clone** - Clone one SD card to another
5. **Exit** - Quit the application

### Progress Display

The tool shows real-time progress with:
- Progress bar
- Percentage complete
- Transfer speed
- Estimated time remaining

## Notes

- Always use sudo to ensure proper access to block devices
- Be careful when selecting destination drives - all data will be overwritten
- The tool automatically detects removable USB/SD card devices
- Backups are saved as compressed `.img.gz` files to save space
