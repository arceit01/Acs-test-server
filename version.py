"""Single source of truth for the ACS test tool version.

Bump VERSION here only; all display points (console banner, status command,
HTTP Server header, --version flag, mock CPE) read from this module.
"""

VERSION = "1.4"  # 1.0 initial; 1.1 tab completion; 1.2 firmware upgrade (fw download); 1.3 fw completion + SOAP log default off; 1.4 auto-diagnostics on Set/Get faults
