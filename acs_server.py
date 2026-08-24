#!/usr/bin/env python3
"""TR-069 CWMP ACS test server with an interactive console.

Usage:
    python3 acs_server.py [-c config.json]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cwmp_messages as cwmp
from cpe_session import OutboundRPC, SessionRegistry
from console_ui import ConsolePrinter, ConsoleUI
from version import VERSION

log = logging.getLogger("acs")

# Max parameters auto-diagnosed after a single failed Set/Get.
DIAGNOSTIC_PARAM_LIMIT = 5

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 7547,
        "path": "/acs",
        "tls": {"enabled": False, "cert_file": "certs/server.crt",
                "key_file": "certs/server.key"},
        "auth": {"enabled": False, "username": "acsuser", "password": "acspass"},
    },
    "connection_request": {"username": "", "password": "", "timeout": 10},
    "cwmp": {"parameter_key": "acs-test-key", "log_soap": False,
             "auto_provision_cr": True},
    "logging": {"level": "INFO"},
}

SUPPORTED_RPC_METHODS = [
    "GetRPCMethods", "GetParameterNames", "GetParameterValues",
    "SetParameterValues", "AddObject", "DeleteObject", "Reboot", "FactoryReset",
]


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
    except FileNotFoundError:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(DEFAULT_CONFIG, fh, indent=2)
            fh.write("\n")
        log.warning("Config file not found - wrote defaults to %s", path)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON in config %s: %s", path, exc)
        sys.exit(1)
    return deep_merge(DEFAULT_CONFIG, user_cfg)


def build_rpc_xml(rpc, default_parameter_key: str) -> str | None:
    mid = cwmp.next_msg_id()
    method, args = rpc.method, rpc.args
    if method == "GetParameterValues":
        return cwmp.get_parameter_values(mid, args["names"])
    if method == "SetParameterValues":
        return cwmp.set_parameter_values(
            mid, args["params"], args.get("parameter_key", default_parameter_key))
    if method == "GetParameterNames":
        return cwmp.get_parameter_names(mid, args["path"], args.get("next_level", False))
    if method == "Reboot":
        return cwmp.reboot(mid, args.get("command_key", ""))
    if method == "Download":
        return cwmp.download(
            mid,
            command_key=args.get("command_key", ""),
            file_type=args.get("file_type", "1 Firmware Upgrade Image"),
            url=args.get("url", ""),
            username=args.get("username", ""),
            password=args.get("password", ""),
            file_size=args.get("file_size", 0),
            target_filename=args.get("target_filename", ""),
            delay_seconds=args.get("delay_seconds", 0),
        )
    if method == "FactoryReset":
        return cwmp.factory_reset(mid)
    if method == "AddObject":
        return cwmp.add_object(mid, args["object_name"], args.get("parameter_key", default_parameter_key))
    if method == "DeleteObject":
        return cwmp.delete_object(mid, args["object_name"], args.get("parameter_key", default_parameter_key))
    return None


class ACSRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"ACSTestServer/{VERSION}"

    def setup(self):
        super().setup()
        # Serial of the CPE bound to this TCP connection (set on Inform).
        self.session_serial: str | None = None

    @property
    def registry(self) -> SessionRegistry:
        return self.server.registry

    @property
    def cfg(self) -> dict:
        return self.server.cfg

    @property
    def printer(self) -> ConsolePrinter:
        return self.server.printer

    @property
    def config_path(self) -> str:
        return self.server.config_path

    def log_message(self, fmt, *args):
        if self.cfg["cwmp"].get("log_soap"):
            return  # raw SOAP mode: keep the console clean
        log.info("%s %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------- plumbing

    def _summary_notify(self, text: str):
        """Console notification shown only when raw SOAP logging is OFF.

        In SOAP mode the console shows raw packets only; everything here is
        still recorded in the CPE session history (see `hist`).
        """
        if not self.cfg["cwmp"].get("log_soap"):
            self.printer.notify(text)

    def _read_body(self) -> bytes:
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            body = b""
            while True:
                size_line = self.rfile.readline(65536).strip()
                try:
                    size = int(size_line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline(65536)
                    break
                body += self.rfile.read(size)
                self.rfile.readline(65536)
            return body
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    def _send(self, status: int, body: bytes, content_type="text/xml; charset=utf-8"):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_empty_ok(self):
        self._send(200, b"", "text/plain")

    def _check_auth(self) -> bool:
        auth = self.cfg["server"]["auth"]
        if not auth.get("enabled"):
            return True
        header = (self.headers.get("Authorization") or "").strip()
        expected = "Basic " + base64.b64encode(
            f'{auth.get("username", "")}:{auth.get("password", "")}'.encode()).decode()
        if header != expected:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="ACS"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        return True

    def _current_session(self):
        serial = self.session_serial
        if not serial:
            recent = self.registry.most_recent()
            serial = recent.serial if recent else None
        return self.registry.get(serial) if serial else None

    def _advance_session(self):
        """Send the next queued RPC to the CPE, or an empty 200 to end the session."""
        sess = self._current_session()
        if sess is None:
            self._send_empty_ok()
            return
        rpc = self.registry.pop_next(sess.serial)
        if rpc is None:
            sess.session_active = False
            self._send_empty_ok()
            return
        sess.last_rpc = rpc
        xml = build_rpc_xml(rpc, self.cfg["cwmp"].get("parameter_key", ""))
        if xml is None:
            self._summary_notify(f"[{sess.serial}] Skipped unknown RPC {rpc.method}")
            self._send_empty_ok()
            return
        sess.note("->", f"{rpc.method} {rpc.summary}".strip())
        sess.last_sent = rpc.method
        if rpc.method == "SetParameterValues":
            sess.last_set_params = [tuple(p) for p in (rpc.args.get("params") or [])]
        elif rpc.method == "GetParameterValues":
            sess.last_get_names = list(rpc.args.get("names") or [])
        elif rpc.method == "AddObject":
            sess.last_add_object = rpc.args.get("object_name", "")
        elif rpc.method == "DeleteObject":
            sess.last_delete_object = rpc.args.get("object_name", "")
        if not rpc.diagnostic:
            sess.diag_keys.clear()  # new user-initiated command: fresh diagnostics
        self._summary_notify(f"[{sess.serial}] >> {rpc.method} {rpc.summary}".strip())
        self._send(200, xml.encode("utf-8"))

    # ------------------------------------------------------------ HTTP verbs

    def do_GET(self):
        acs_path = self.cfg["server"]["path"]
        if self.path == acs_path:
            body = (f"TR-069 ACS test server\nCWMP endpoint: {self.path}\n"
                    f"TLS: {'on' if self.cfg['server']['tls'].get('enabled') else 'off'}\n")
            self._send(200, body.encode(), "text/plain; charset=utf-8")
        else:
            self._send(404, b"Not Found\n", "text/plain")

    def do_POST(self):
        acs_path = self.cfg["server"]["path"]
        if self.path != acs_path:
            self._send(404, b"Not Found\n", "text/plain")
            return
        if not self._check_auth():
            return
        body = self._read_body()
        if not body.strip():
            self._advance_session()
            return
        try:
            parsed = cwmp.parse_soap(body)
        except Exception as exc:
            log.warning("Bad SOAP from %s: %s", self.address_string(), exc)
            self._send(400, b"Bad Request\n", "text/plain")
            return
        if self.cfg["cwmp"].get("log_soap"):
            snippet = body.decode("utf-8", "replace")[:2000]
            self.printer.notify(f"SOAP from {self.address_string()}: "
                                f"{parsed['method'] or '?'}\n{snippet}")
        method = parsed["method"]
        if method == "Inform":
            self._handle_inform(parsed)
        elif parsed["fault"]:
            self._handle_fault(parsed)
        elif method == "TransferComplete":
            self._handle_transfer_complete(parsed)
        elif method and method.endswith("Response"):
            self._handle_rpc_response(parsed)
        elif method == "GetRPCMethods":
            self._handle_get_rpc_methods(parsed)
        else:
            log.info("Unhandled CPE request: %s", method)
            self._advance_session()

    # ------------------------------------------------------------- handlers

    def _handle_inform(self, parsed):
        info = cwmp.parse_inform(parsed["elem"])
        sess, created = self.registry.upsert_inform(info)
        self.session_serial = sess.serial
        events = ", ".join(cwmp.format_event(e) for e in info["events"]) or "-"
        summary = (f"[{sess.serial}] {'New CPE registered' if created else 'Inform'}:"
                   f" events=[{events}] retry={info['retry_count']}"
                   f" ({sess.manufacturer} {sess.product_class})")
        self._summary_notify(summary)
        sess.note("<-", f"Inform events=[{events}]")
        self._maybe_provision_cr(sess, info)
        self._send(200, cwmp.inform_response(parsed["id"]).encode())

    def _maybe_provision_cr(self, sess, info):
        """On '0 BOOTSTRAP', queue Connection Request credential provisioning.

        Mirrors common ACS provisioning scripts: Username =
        OUI-ProductClass-SerialNumber, Password = lowercase MD5 hex of the
        username, written to ManagementServer.ConnectionRequestUsername/
        Password (root prefix auto-detected from the Inform data model).
        Credentials are applied per-CPE and persisted to config.json once the
        CPE confirms the set.
        """
        if not self.cfg["cwmp"].get("auto_provision_cr", True):
            return
        if not any(e.get("code") == "0" for e in info.get("events", [])):
            return
        username = "-".join(str(sess.device_id.get(k) or "")
                            for k in ("OUI", "ProductClass", "SerialNumber"))
        password = hashlib.md5(username.encode()).hexdigest()
        root = ("Device." if any(k.startswith("Device.")
                                 for k in info.get("params", {}))
                else "InternetGatewayDevice.")
        params = [
            (f"{root}ManagementServer.ConnectionRequestUsername",
             username, "xsd:string"),
            (f"{root}ManagementServer.ConnectionRequestPassword",
             password, "xsd:string"),
        ]
        rpc = OutboundRPC(
            "SetParameterValues",
            {"params": params, "purpose": "provision_cr"},
            ", ".join(f"{n}={v} [{t}]" for n, v, t in params))
        self.registry.enqueue(sess.serial, rpc)
        sess.provision_pending = (username, password)
        self._summary_notify(
            f"[{sess.serial}] BOOTSTRAP: queued CR credential provisioning "
            f"({root[:-1]} data model)\n"
            f"  Username={username}\n  Password={password}")

    def _check_cr_provisioning(self, sess, parsed):
        """Confirm CR credential provisioning on SetParameterValuesResponse."""
        rpc = sess.last_rpc
        if rpc is None or rpc.args.get("purpose") != "provision_cr":
            return
        pending, sess.provision_pending = sess.provision_pending, None
        status = cwmp.child_text(parsed["elem"], "Status")
        if status == "0" and pending:
            username, password = pending
            sess.cr_username, sess.cr_password = username, password
            self._persist_credentials(username, password)
            self._summary_notify(
                f"[{sess.serial}] CR credentials applied & saved to config - "
                f"use `cr` to verify them")
        else:
            self._summary_notify(
                f"[{sess.serial}] WARNING: CR credential provisioning not "
                f"confirmed (Status={status or '?'}) - previous credentials "
                f"remain active")

    def _persist_credentials(self, username: str, password: str):
        try:
            cred = self.cfg.setdefault("connection_request", {})
            cred["username"] = username
            cred["password"] = password
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        except OSError as exc:
            log.error("Cannot write config %s: %s", self.config_path, exc)
            self.printer.notify(f"WARNING: could not save credentials to "
                                f"config: {exc}")

    def _handle_rpc_response(self, parsed):
        summary = cwmp.format_response(parsed["method"], parsed["elem"])
        sess = self._current_session()
        if sess:
            if parsed["method"] == "GetParameterValuesResponse":
                values = cwmp.extract_param_values(parsed["elem"])
                for name, (_value, xsi) in values.items():
                    if xsi:
                        sess.param_types[name] = xsi
                sess.known_params.update(values.keys())
            elif parsed["method"] == "GetParameterNamesResponse":
                infos = cwmp.extract_param_infos(parsed["elem"])
                sess.known_params.update(name for name, _w in infos)
                for name, writable in infos:
                    if writable is not None:
                        sess.param_writable[name] = writable == "1"
            elif parsed["method"] == "SetParameterValuesResponse":
                self._check_cr_provisioning(sess, parsed)
            elif parsed["method"] == "AddObjectResponse":
                result = cwmp.extract_add_object_response(parsed["elem"])
                instance_num = result.get("instance_number", "")
                if instance_num:
                    self._summary_notify(f"[{sess.serial}] AddObject created instance: {instance_num}")
            elif parsed["method"] == "DeleteObjectResponse":
                pass  # Status handled in format_response
            sess.note("<-", f"{parsed['method']}:\n{summary}")
            self._summary_notify(f"[{sess.serial}] << {parsed['method']}\n{summary}")
        else:
            self._summary_notify(f"<< {parsed['method']}\n{summary}")
        self._advance_session()

    def _queue_fault_diagnostics(self, sess) -> list[str]:
        """After a failed Set/Get, queue RPCs that reveal why: whether each
        parameter exists, whether it is writable, and its CPE-reported type.

        Diagnostics for the current command are issued once only (a failed
        diagnostic get must not re-queue the same names request).
        """
        if sess.last_sent == "SetParameterValues":
            source = [str(p[0]) for p in sess.last_set_params]
        elif sess.last_sent == "GetParameterValues":
            source = list(sess.last_get_names)
        else:
            return []
        names = list(dict.fromkeys(source))[:DIAGNOSTIC_PARAM_LIMIT]
        if not names:
            return []

        def once(key: str) -> bool:
            if key in sess.diag_keys:
                return False
            sess.diag_keys.add(key)
            return True

        lines = []
        parents_done: set[str] = set()
        for name in names:
            parent = name[:name.rfind(".") + 1]
            if (sess.last_sent == "SetParameterValues"
                    and once(f"get:{name}")):
                self.registry.enqueue(sess.serial, OutboundRPC(
                    "GetParameterValues", {"names": [name]}, name,
                    diagnostic=True))
                lines.append(f"  get {name}  (fault here = path does not exist)")
            if (parent and parent not in parents_done
                    and once(f"names:{parent}")):
                parents_done.add(parent)
                self.registry.enqueue(sess.serial, OutboundRPC(
                    "GetParameterNames",
                    {"path": parent, "next_level": True},
                    f"path={parent} nextlevel=True", diagnostic=True))
                lines.append(f"  names {parent}  (writable=0 = read-only/locked)")
        return lines

    def _handle_fault(self, parsed):
        summary = cwmp.format_fault(parsed["elem"])
        hint = ""
        sess = self._current_session()
        if sess and sess.last_sent == "SetParameterValues":
            hint = ("\nhint: invalid arguments usually mean a type mismatch, "
                    "a read-only (vendor-locked) parameter, or a path that "
                    "does not exist on this firmware")
            rpc = sess.last_rpc
            if rpc is not None and rpc.args.get("purpose") == "provision_cr":
                sess.provision_pending = None
                hint += "\nnote: this was the CR credential provisioning - " \
                        "previous CPE credentials remain active"
        if sess:
            diag = self._queue_fault_diagnostics(sess)
            if diag:
                hint += "\nauto-diagnosis queued:\n" + "\n".join(diag)
        if sess:
            sess.note("<-", f"Fault:\n{summary}")
            self._summary_notify(f"[{sess.serial}] << FAULT\n{summary}{hint}")
        else:
            self._summary_notify(f"<< FAULT\n{summary}{hint}")
        self._advance_session()

    def _handle_transfer_complete(self, parsed):
        cmd_key = cwmp.child_text(parsed["elem"], "CommandKey")
        fault_code = ""
        fault_elem = cwmp.find_child(parsed["elem"], "FaultStruct")
        if fault_elem is not None:
            fault_code = cwmp.child_text(fault_elem, "FaultCode")
        text = f"TransferComplete command_key={cmd_key or '-'}"
        if fault_code:
            text += f" fault={fault_code}"
        sess = self._current_session()
        if sess:
            sess.note("<-", text)
            self._summary_notify(f"[{sess.serial}] << {text}")
        else:
            self._summary_notify(f"<< {text}")
        self._send(200, cwmp.transfer_complete_response(parsed["id"]).encode())

    def _handle_get_rpc_methods(self, parsed):
        self._summary_notify(f"<< GetRPCMethods -> replying with "
                             f"{len(SUPPORTED_RPC_METHODS)} methods")
        xml = cwmp.get_rpc_methods_response(parsed["id"] or cwmp.next_msg_id(),
                                            SUPPORTED_RPC_METHODS)
        self._send(200, xml.encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description="TR-069 CWMP ACS test server")
    parser.add_argument("-c", "--config", default="config.json",
                        help="path to JSON config file (default: config.json)")
    parser.add_argument("--version", action="store_true",
                        help="print version and exit")
    args = parser.parse_args(argv)
    if args.version:
        print(f"acs_server {VERSION}")
        return

    cfg = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, str(cfg["logging"].get("level", "INFO")).upper(),
                      logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s")
    srv_cfg = cfg["server"]
    tls_cfg = srv_cfg.get("tls", {})
    host, port = srv_cfg.get("host", "0.0.0.0"), int(srv_cfg.get("port", 7547))
    path = srv_cfg.get("path", "/acs")

    try:
        httpd = ThreadingHTTPServer((host, port), ACSRequestHandler)
    except OSError as exc:
        log.error("Cannot bind %s:%s - %s", host, port, exc)
        sys.exit(1)
    httpd.daemon_threads = True

    registry = SessionRegistry()
    printer = ConsolePrinter()
    httpd.registry = registry
    httpd.cfg = cfg
    httpd.printer = printer
    httpd.config_path = args.config

    tls_enabled = bool(tls_cfg.get("enabled"))
    if tls_enabled:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(tls_cfg["cert_file"], tls_cfg["key_file"])
        except (FileNotFoundError, ssl.SSLError) as exc:
            log.error("Failed to load TLS cert/key: %s", exc)
            sys.exit(1)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    thread = threading.Thread(target=httpd.serve_forever,
                              kwargs={"poll_interval": 0.5}, daemon=True)
    thread.start()

    display_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    scheme = "https" if tls_enabled else "http"
    server_info = {
        "url": f"{scheme}://{display_host}:{port}{path}",
        "bind": f"{host}:{port}",
        "tls": tls_enabled,
        "auth": bool(srv_cfg.get("auth", {}).get("enabled")),
    }

    try:
        ConsoleUI(registry, cfg, printer, server_info).cmdloop()
    except KeyboardInterrupt:
        printer.print("\nInterrupted.")
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
