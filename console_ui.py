"""Interactive console UI for the ACS test server."""

from __future__ import annotations

import cmd
import shlex
import threading
import time
import urllib.error
import urllib.request

import cwmp_messages as cwmp
from cpe_session import OutboundRPC
from version import VERSION

# ---------------------------------------------------------------------------
# Detailed command help (data-driven; rendered by _format_command_help)
# ---------------------------------------------------------------------------

HELP = {
    "list": {
        "summary": "List all known CPE sessions",
        "usage": ["list"],
        "args": [],
        "examples": ["list"],
        "notes": "'*' marks the currently selected CPE. The index column is "
                 "accepted by other commands, e.g. 'select 2'.",
    },
    "select": {
        "summary": "Select the target CPE for subsequent commands",
        "usage": ["select <idx|serial>"],
        "args": [("idx|serial", "1-based index from 'list', an exact serial "
                                "number, or a case-insensitive substring of it")],
        "examples": ["select 1", "select MOCK001"],
        "notes": "The current target is shown in the prompt as acs[SERIAL]>.",
    },
    "info": {
        "summary": "Show detailed information about a CPE",
        "usage": ["info [<idx|serial>]"],
        "args": [("idx|serial", "Optional target; defaults to the selected CPE")],
        "examples": ["info", "info MOCK001"],
        "notes": "Shows DeviceId fields, ConnectionRequestURL, session state, "
                 "pending RPC count and the events of the last Inform.",
    },
    "get": {
        "summary": "Queue GetParameterValues for the selected CPE",
        "usage": ["get <parameter_path> [<parameter_path> ...]"],
        "args": [("parameter_path", "Full TR-069 parameter path; separate "
                                    "multiple paths with spaces")],
        "examples": [
            "get InternetGatewayDevice.DeviceInfo.ModelName",
            "get Device.Services.VoiceService.1.VoiceProfile.1.Enable",
        ],
        "notes": "Requests are queued and delivered when the CPE starts a "
                 "session - use 'cr' to trigger one immediately. Types "
                 "reported by the CPE are remembered and reused by 'set'.",
    },
    "set": {
        "summary": "Queue SetParameterValues for the selected CPE",
        "usage": ["set <path>=<value>[:<type>] [<path>=<value>[:<type>] ...]"],
        "args": [
            ("path=value", "Parameter path and new value separated by '='"),
            (":type", "Optional explicit type suffix. Aliases: bool/boolean, "
                      "int, uint, string/str, double/float, dateTime/date"),
        ],
        "examples": [
            "set InternetGatewayDevice.DeviceInfo.ModelName=NewModel-X",
            "set Device.Services.VoiceService.1.VoiceProfile.1.Enable=true:boolean",
            "set Device.X_Vendor.SomeObject.Timeout=30:uint",
        ],
        "notes": "Type resolution order: explicit ':type' > type remembered "
                 "from the CPE's last GetParameterValuesResponse > auto "
                 "inference (true/false -> boolean, integers -> int, floats -> "
                 "double, else string). Boolean values also accept "
                 "enabled/disabled/on/off and are normalized to 1/0. A Fault "
                 "9003 usually means a type mismatch: run 'get <path>' first, "
                 "then retry with ':<type>'.",
    },
    "names": {
        "summary": "Queue GetParameterNames for the selected CPE",
        "usage": ["names <path> [nextlevel]"],
        "args": [
            ("path", "Parameter path prefix to enumerate; use '' or '.' for "
                     "the whole tree"),
            ("nextlevel", "Optional true/false (default false). true = only "
                          "the next level below <path>, false = all "
                          "descendants"),
        ],
        "examples": [
            "names InternetGatewayDevice.DeviceInfo.",
            "names InternetGatewayDevice. true",
        ],
        "notes": "Responses list each parameter with its writable flag.",
    },
    "reboot": {
        "summary": "Queue Reboot for the selected CPE",
        "usage": ["reboot [command_key]"],
        "args": [("command_key", "Optional key echoed back by the CPE in its "
                                 "next Inform (default: acs-test-reboot)")],
        "examples": ["reboot", "reboot my-key-42"],
        "notes": "Most CPEs re-Inform with event '1 BOOT' after rebooting.",
    },
    "factoryreset": {
        "summary": "Queue FactoryReset for the selected CPE",
        "usage": ["factoryreset"],
        "args": [],
        "examples": ["factoryreset"],
        "notes": "Restores the CPE to factory defaults - use with care. "
                 "Alias: fr.",
    },
    "cr": {
        "summary": "Send an HTTP Connection Request to the CPE",
        "usage": ["cr [<idx|serial>]"],
        "args": [("idx|serial", "Optional target; defaults to the selected CPE")],
        "examples": ["cr", "cr MOCK001"],
        "notes": "GETs the CPE's ConnectionRequestURL so it starts a session "
                 "immediately and picks up queued requests. Authentication "
                 "(Digest) credentials come from config.json "
                 "[connection_request]. HTTP 200 means the CPE accepted it.",
    },
    "hist": {
        "summary": "Show the message exchange history of a CPE",
        "usage": ["hist [<idx|serial>]"],
        "args": [("idx|serial", "Optional target; defaults to the selected CPE")],
        "examples": ["hist", "hist 2"],
        "notes": "Shows the last 40 entries: Informs, ACS->CPE RPCs, CPE "
                 "responses and faults, oldest first.",
    },
    "log": {
        "summary": "Toggle raw SOAP packet logging",
        "usage": ["log"],
        "args": [],
        "examples": ["log"],
        "notes": "When ON, every SOAP envelope sent or received is printed "
                 "(truncated to 2000 chars). Useful for debugging type or "
                 "namespace issues.",
    },
    "status": {
        "summary": "Show server status",
        "usage": ["status"],
        "args": [],
        "examples": ["status"],
        "notes": "Shows endpoint URL, TLS/auth state, uptime, connected CPEs "
                 "and pending RPC totals.",
    },
    "sleep": {
        "summary": "Pause the console (useful in scripted sessions)",
        "usage": ["sleep <seconds>"],
        "args": [("seconds", "Fractional seconds allowed, e.g. 0.5")],
        "examples": ["sleep 5"],
        "notes": "Incoming CPE traffic is still printed while sleeping.",
    },
    "quit": {
        "summary": "Exit the ACS test server",
        "usage": ["quit"],
        "args": [],
        "examples": ["quit"],
        "notes": "Aliases: exit, q. Ctrl-D has the same effect.",
    },
}

ALIASES = {"fr": "factoryreset", "exit": "quit", "q": "quit"}


def _canonical(name: str) -> str:
    name = name.strip().lower()
    return ALIASES.get(name, name)


def complete_parameter_path(text: str, known_paths) -> list[str]:
    """Return completion candidates for a partial TR-069 parameter path.

    All candidates start with <text>; readline then extends to the common
    prefix and lists options on a second Tab (bash-style). Object nodes keep
    their trailing '.', so completion can continue level by level.

    At the top level (no '.' typed yet) a substring fallback applies, so
    e.g. 'Devic' can complete to 'InternetGatewayDevice.' on TR-098 devices.
    """
    text = text.strip()
    if not known_paths:
        return []
    paths = sorted(known_paths)
    if "." not in text:
        tops = sorted({p.split(".", 1)[0] + "." for p in paths})
        matches = [t for t in tops if t.startswith(text)]
        if not matches:
            low = text.lower()
            matches = [t for t in tops if low in t.lower()]
        return matches
    matches = [p for p in paths if p.startswith(text)]
    if not matches:
        # Allow completing an object path typed without its trailing dot.
        partial = text if text.endswith(".") else text + "."
        matches = [p for p in paths if p.startswith(partial)]
    return matches


def _format_command_help(name: str) -> str:
    entry = HELP[name]
    lines = [f"{name} - {entry['summary']}", "", "Usage:"]
    usage = entry["usage"]
    lines += [f"  {u}" for u in usage]
    if entry["args"]:
        width = max(len(arg) for arg, _ in entry["args"])
        lines.append("")
        lines.append("Arguments:")
        lines += [f"  {arg:<{width}}  {desc}" for arg, desc in entry["args"]]
    if entry["examples"]:
        lines += ["", "Examples:"] + [f"  {ex}" for ex in entry["examples"]]
    if entry.get("notes"):
        lines += ["", "Notes:", f"  {entry['notes']}"]
    return "\n".join(lines)


class ConsolePrinter:
    """Thread-safe console output shared between the UI and server threads."""

    def __init__(self):
        self.lock = threading.Lock()

    def print(self, text: str = ""):
        with self.lock:
            print(text, flush=True)

    def notify(self, text: str):
        ts = time.strftime("%H:%M:%S")
        with self.lock:
            print(f"\n[* {ts}] {text}", flush=True)


class ConsoleUI(cmd.Cmd):
    prompt = "acs> "

    def __init__(self, registry, cfg: dict, printer: ConsolePrinter, server_info: dict):
        super().__init__()
        self.registry = registry
        self.cfg = cfg
        self.printer = printer
        self.server_info = server_info
        self.selected: str | None = None
        self.start_time = time.time()
        # Treat each whitespace token as one completion unit so that tokens
        # like 'path=value:type' are handled by our own logic.
        try:
            import readline
            readline.set_completer_delims(" \t\n")
        except ImportError:
            pass
        self.intro = (
            f"\n=== TR-069 ACS Test Server v{VERSION} ===\n"
            f"  CWMP endpoint : {server_info['url']}\n"
            f"  TLS           : {'ON' if server_info['tls'] else 'off'}\n"
            f"  CPE auth      : {'ON' if server_info['auth'] else 'off'}\n"
            "Type 'help' to list commands, '<command> ?' for details.\n"
            "Waiting for CPE connections...\n"
        )

    # ------------------------------------------------------------------ util

    def _resolve(self, token: str = ""):
        return self.registry.resolve(token.strip() if token else self.selected)

    def _need_session(self, token: str = ""):
        sess = self._resolve(token)
        if sess is None:
            self.printer.print("No CPE available yet (waiting for Inform). See `list`.")
        return sess

    def _usage(self, text: str):
        self.printer.print(f"usage: {text}")

    def _hint(self, sess):
        if not sess.session_active and sess.pending:
            self.printer.print(
                f"  ({len(sess.pending)} request(s) pending - "
                f"use `cr` to trigger a session now, or wait for the next Inform)"
            )

    def emptyline(self):
        pass

    # ----------------------------------------------------------- completion

    def completedefault(self, text, line, begidx, endidx):
        """Tab completion for command arguments (paths and serial numbers)."""
        tokens = line.split()
        if not tokens:
            return []
        cmd_name = _canonical(tokens[0])
        if cmd_name in ("select", "info", "hist", "cr"):
            serials = sorted(s.serial for s in self.registry.all())
            return [s for s in serials if s.startswith(text)]
        if cmd_name in ("get", "names"):
            return self._path_matches(text)
        if cmd_name == "set":
            # 'path=value[:type]' - only complete while the path portion is
            # being typed (no '=' yet).
            if "=" in text:
                return []
            return self._path_matches(text)
        return []

    def _path_matches(self, text: str) -> list[str]:
        sessions = self.registry.all()
        if not sessions:
            return []
        sess = self._resolve()
        known = sess.known_params if sess is not None else set()
        if not known:
            known = set().union(*(s.known_params for s in sessions))
        return complete_parameter_path(text, known)

    def onecmd(self, line):
        """Intercept '<command> ?' (anywhere in the line) to show detailed
        help instead of executing the command."""
        tokens = line.split()
        if len(tokens) >= 2 and "?" in tokens[1:]:
            name = _canonical(tokens[0])
            if name in HELP:
                self.printer.print(_format_command_help(name))
                return False
            if not hasattr(self, "do_" + name):
                self.printer.print(f"Unknown command '{tokens[0]}'. "
                                   "Type 'help' to list commands.")
                return False
        return super().onecmd(line)

    def do_help(self, arg):
        """help [<command>] : list commands, or show detailed help"""
        if not arg.strip():
            self.printer.print("Available commands:")
            width = max(len(name) for name in HELP)
            for name, entry in HELP.items():
                aliases = [a for a, target in ALIASES.items() if target == name]
                label = f"{name} ({','.join(aliases)})" if aliases else name
                self.printer.print(f"  {label:<{width + 12}}{entry['summary']}")
            self.printer.print("")
            self.printer.print("Type '<command> ?' or 'help <command>' for details.")
            self.printer.print("Typical workflow: select <cpe> -> get/set/names/"
                               "reboot -> cr")
            return
        name = _canonical(arg)
        if name in HELP:
            self.printer.print(_format_command_help(name))
        else:
            self.printer.print(f"Unknown command '{arg.strip()}'. "
                               "Type 'help' to list commands.")

    def postcmd(self, stop, line):
        self.prompt = f"acs[{self.selected or '-'}]> "
        return stop

    # -------------------------------------------------------------- commands

    def do_list(self, arg):
        """list : show all known CPE sessions"""
        sessions = self.registry.all()
        if not sessions:
            self.printer.print("No CPE has connected yet.")
            return
        self.printer.print(f"{'#':>2}  {'SerialNumber':<20} {'ProductClass':<16} "
                           f"{'LastEvent':<22} {'Informs':>7}  {'Pending':>7}  LastSeen")
        for i, s in enumerate(sessions, 1):
            marker = "*" if s.serial == self.selected else " "
            event = s.events[0]["code"] if s.events else "-"
            last = time.strftime("%H:%M:%S", time.localtime(s.last_seen))
            self.printer.print(
                f"{marker}{i:<2} {s.serial:<20} {s.product_class or '?':<16} "
                f"{event:<22} {s.inform_count:>7}  {len(s.pending):>7}  {last}"
            )
        self.printer.print("('*' = selected)")

    def do_select(self, arg):
        """select <idx|serial> : select target CPE for subsequent commands"""
        if not arg.strip():
            return self._usage("select <idx|serial>")
        sess = self.registry.resolve(arg)
        if sess is None:
            self.printer.print(f"No CPE matches '{arg}'. See `list`.")
            return
        self.selected = sess.serial
        self.printer.print(f"Selected {sess.serial} ({sess.manufacturer or '?'} "
                           f"{sess.product_class or '?'})")

    def do_info(self, arg):
        """info [idx|serial] : show details of the selected (or given) CPE"""
        sess = self._need_session(arg)
        if not sess:
            return
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sess.created_at))
        last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sess.last_seen))
        events = ", ".join(e["code"] for e in sess.events) or "-"
        lines = [
            f"SerialNumber   : {sess.serial}",
            f"Manufacturer   : {sess.manufacturer}",
            f"OUI            : {sess.oui}",
            f"ProductClass   : {sess.product_class}",
            f"ConnectionReq  : {sess.conn_req_url or '-'}",
            f"First seen     : {created}",
            f"Last seen      : {last}",
            f"Informs        : {sess.inform_count}",
            f"Session active : {sess.session_active}",
            f"Pending RPCs   : {len(sess.pending)}",
            f"Last events    : {events}",
            f"Inform params  : {len(sess.inform_params)}",
        ]
        self.printer.print("\n".join(lines))

    def do_get(self, arg):
        """get <path> [path ...] : queue GetParameterValues for the selected CPE"""
        names = shlex.split(arg)
        if not names:
            return self._usage('get InternetGatewayDevice.DeviceInfo.ModelName')
        sess = self._need_session()
        if not sess:
            return
        rpc = OutboundRPC("GetParameterValues", {"names": names}, ", ".join(names))
        self.registry.enqueue(sess.serial, rpc)
        self.printer.print(f"Queued GetParameterValues for {sess.serial}: {', '.join(names)}")
        self._hint(sess)

    def do_set(self, arg):
        """set <path>=<value>[:type] [...] : queue SetParameterValues

        Optional explicit type suffix: bool, boolean, int, uint, string,
        double, dateTime (e.g. ...Enable=true:boolean).
        Otherwise the type reported by the CPE in the last
        GetParameterValuesResponse is used when known.
        """
        tokens = shlex.split(arg)
        if not tokens:
            return self._usage("set InternetGatewayDevice.DeviceInfo.ModelName=Mock-200")
        sess = self._need_session()
        if not sess:
            return
        params = []
        warnings = []
        for tok in tokens:
            name, sep, raw = tok.partition("=")
            if not sep or not name:
                return self._usage(f"...invalid pair '{tok}' (expected path=value[:type])")
            value, xsd = self._resolve_set_value(sess, name, raw, warnings)
            params.append((name, value, xsd))
        summary = ", ".join(f"{n}={v} [{t}]" for n, v, t in params)
        rpc = OutboundRPC("SetParameterValues", {"params": params}, summary)
        self.registry.enqueue(sess.serial, rpc)
        for warning in warnings:
            self.printer.print(f"WARNING: {warning}")
        self.printer.print(f"Queued SetParameterValues for {sess.serial}: {summary}")
        self._hint(sess)

    def _resolve_set_value(self, sess, name: str, raw: str, warnings: list):
        """Decide (value, xsd_type) for one set token.

        Priority: explicit ':type' suffix > type remembered from the CPE's
        last GetParameterValuesResponse > auto-inference.
        """
        base, colon, suffix = raw.rpartition(":")
        explicit = None
        if colon and suffix:
            alias = cwmp.resolve_type_alias(suffix)
            if alias:
                explicit = alias
                raw = base
        if explicit:
            coerced = cwmp.coerce_value(raw, explicit)
            if coerced is None:
                warnings.append(f"{name}: '{raw}' does not conform to {explicit}, "
                                "sending as-is")
                coerced = raw
            return coerced, explicit
        remembered = sess.param_types.get(name)
        if remembered:
            coerced = cwmp.coerce_value(raw, remembered)
            if coerced is not None:
                return coerced, remembered
            warnings.append(
                f"{name}: CPE previously reported type {remembered}, but '{raw}' "
                f"does not match - falling back to auto-inferred type")
        xsd, value = cwmp.infer_xsd_type(raw)  # infer_xsd_type returns (type, value)
        return value, xsd

    def do_names(self, arg):
        """names <path> [nextlevel] : queue GetParameterNames (nextlevel: true/false)"""
        tokens = shlex.split(arg)
        if not tokens:
            return self._usage("names InternetGatewayDevice.DeviceInfo. true")
        path = tokens[0]
        next_level = False
        if len(tokens) > 1:
            next_level = tokens[1].lower() in ("true", "1", "yes", "on")
        sess = self._need_session()
        if not sess:
            return
        args = {"path": path, "next_level": next_level}
        summary = f"path={path} nextlevel={next_level}"
        self.registry.enqueue(sess.serial, OutboundRPC("GetParameterNames", args, summary))
        self.printer.print(f"Queued GetParameterNames for {sess.serial}: {summary}")
        self._hint(sess)

    def do_reboot(self, arg):
        """reboot [command_key] : queue Reboot for the selected CPE"""
        key = arg.strip() or "acs-test-reboot"
        sess = self._need_session()
        if not sess:
            return
        self.registry.enqueue(sess.serial, OutboundRPC("Reboot", {"command_key": key}, f"key={key}"))
        self.printer.print(f"Queued Reboot for {sess.serial}")
        self._hint(sess)

    def do_factoryreset(self, arg):
        """factoryreset : queue FactoryReset for the selected CPE (alias: fr)"""
        sess = self._need_session()
        if not sess:
            return
        self.registry.enqueue(sess.serial, OutboundRPC("FactoryReset", {}, ""))
        self.printer.print(f"Queued FactoryReset for {sess.serial}")
        self._hint(sess)

    do_fr = do_factoryreset

    def do_cr(self, arg):
        """cr [idx|serial] : send an HTTP Connection Request to the CPE"""
        sess = self._need_session(arg)
        if not sess:
            return
        if not sess.conn_req_url:
            self.printer.print(f"[{sess.serial}] No ConnectionRequestURL known "
                               "(not present in the last Inform).")
            return
        cred = self.cfg.get("connection_request", {})
        user = cred.get("username") or ""
        pwd = cred.get("password") or ""
        timeout = float(cred.get("timeout", 10))
        try:
            if user:
                mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                mgr.add_password(None, sess.conn_req_url, user, pwd)
                opener = urllib.request.build_opener(
                    urllib.request.HTTPBasicAuthHandler(mgr),
                    urllib.request.HTTPDigestAuthHandler(mgr),
                )
            else:
                opener = urllib.request.build_opener()
            req = urllib.request.Request(sess.conn_req_url, method="GET")
            with opener.open(req, timeout=timeout) as resp:
                self.printer.print(f"[{sess.serial}] Connection request -> HTTP {resp.code}")
        except urllib.error.HTTPError as exc:
            self.printer.print(f"[{sess.serial}] Connection request failed: "
                               f"HTTP {exc.code} {exc.reason}")
        except Exception as exc:
            self.printer.print(f"[{sess.serial}] Connection request failed: {exc}")

    def do_hist(self, arg):
        """hist [idx|serial] : show the message exchange history of a CPE"""
        sess = self._need_session(arg)
        if not sess:
            return
        if not sess.history:
            self.printer.print(f"[{sess.serial}] No history yet.")
            return
        arrows = {"->": "ACS->CPE", "<-": "CPE->ACS"}
        for entry in sess.history[-40:]:
            ts = time.strftime("%H:%M:%S", time.localtime(entry["ts"]))
            direction = arrows.get(entry["dir"], entry["dir"])
            body = entry["text"].replace("\n", "\n      ")
            self.printer.print(f"{ts}  {direction}: {body}")

    def do_log(self, arg):
        """log : toggle raw SOAP packet logging"""
        cfg_cwmp = self.cfg.setdefault("cwmp", {})
        cfg_cwmp["log_soap"] = not cfg_cwmp.get("log_soap")
        state = "ON" if cfg_cwmp["log_soap"] else "OFF"
        self.printer.print(f"SOAP logging: {state}")

    def do_status(self, arg):
        """status : show server status"""
        uptime = int(time.time() - self.start_time)
        sessions = self.registry.all()
        info = self.server_info
        lines = [
            f"Version        : {VERSION}",
            f"CWMP URL       : {info['url']}",
            f"Bind           : {info['bind']}",
            f"TLS            : {'enabled' if info['tls'] else 'disabled'}",
            f"CPE auth       : {'enabled' if info['auth'] else 'disabled'}",
            f"Uptime         : {uptime // 60}m {uptime % 60}s",
            f"CPE sessions   : {len(sessions)}",
            f"Pending RPCs   : {self.registry.pending_total()}",
            f"Selected       : {self.selected or '-'}",
            f"SOAP logging   : {'ON' if self.cfg['cwmp'].get('log_soap') else 'OFF'}",
        ]
        self.printer.print("\n".join(lines))

    def do_sleep(self, arg):
        """sleep <seconds> : pause the console (useful in scripted sessions)"""
        try:
            time.sleep(max(0.0, float(arg or 0)))
        except ValueError:
            self._usage("sleep <seconds>")

    def do_quit(self, arg):
        """quit : exit the ACS test server (aliases: exit, q)"""
        self.printer.print("Shutting down...")
        return True

    do_exit = do_quit
    do_q = do_quit

    def do_EOF(self, arg):
        self.printer.print("")
        return True
