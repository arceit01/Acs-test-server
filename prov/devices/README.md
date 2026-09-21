# Device-Specific Scripts

This directory contains event scripts specific to individual CPE devices (by Serial Number).

## Naming Convention

Files should be named: `{SerialNumber}_{event_name}.txt`

Examples:
- `MOCK001_bootstrap.txt` - Bootstrap script for device MOCK001
- `CPE12345_boot.txt` - Boot script for device CPE12345
- `ROUTER999_periodic.txt` - Periodic script for device ROUTER999

## Priority

Device-specific scripts have **highest priority** and override:
- OUI-specific scripts
- ProductClass-specific scripts
- Default event scripts

## Usage

Configure in `config.json`:

```json
{
  "event_scripts": {
    "enabled": true,
    "device_overrides": {
      "MOCK001": {
        "0": {
          "mode": "set",
          "script": "prov/devices/MOCK001_bootstrap.txt"
        }
      }
    }
  }
}
```
