#!/usr/bin/env python3
"""Minimal TR-069 CPE simulator for testing the ACS test server.

Starts a CWMP session against the ACS, then keeps polling (empty POSTs)
and answers any ACS RPCs. Also listens for HTTP Connection Requests on
a local endpoint and triggers a new session per request.

Usage:
    python3 mock_cpe.py --url http://127.0.0.1:7547/acs --serial MOCK001 \
        --cr-port 18080 --cr-user admin --cr-pass secret
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import secrets
import ssl
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cwmp_messages as cwmp
from version import VERSION

REALM = "mockcpe"


def verify_digest(header_value: str, method: str, username: str, password: str) -> bool:
    """Validate a Digest auth 'Authorization' header (qop=auth or legacy)."""
    try:
        fields = {}
        for part in header_value[len("Digest "):].split(","):
            key, _, val = part.strip().partition("=")
            fields[key.lower()] = val.strip().strip('"')
    except Exception:
        return False
    required = ("username", "realm", "nonce", "uri", "response")
    if any(k not in fields for k in required):
        return False
    if fields["username"] != username or fields["realm"] != REALM:
        return False
    ha1 = hashlib.md5(f"{username}:{REALM}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{fields['uri']}".encode()).hexdigest()
    if fields.get("qop"):
        expected = hashlib.md5(
            f"{ha1}:{fields['nonce']}:{fields.get('nc', '00000001')}:"
            f"{fields.get('cnonce', '')}:{fields['qop']}:{ha2}".encode()
        ).hexdigest()
    else:
        expected = hashlib.md5(f"{ha1}:{fields['nonce']}:{ha2}".encode()).hexdigest()
    return hmac.compare_digest(expected, fields["response"])


class MockCPE:
    def __init__(self, acs_url: str, serial: str, oui: str, manufacturer: str,
                 product_class: str, software_version: str, cr_host: str,
                 cr_port: int, cr_user: str, cr_pass: str):
        self.acs_url = acs_url
        self.serial = serial
        self.oui = oui
        self.manufacturer = manufacturer
        self.product_class = product_class
        self.software_version = software_version
        self.cr_host = cr_host
        self.cr_port = cr_port
        self.cr_user = cr_user
        self.cr_pass = cr_pass
        self._session_lock = threading.Lock()

        self.params = {
            "InternetGatewayDevice.DeviceSummary":
                "InternetGatewayDevice:1.0[](MockCPE:1.0)",
            "InternetGatewayDevice.DeviceInfo.Manufacturer": manufacturer,
            "InternetGatewayDevice.DeviceInfo.ManufacturerOUI": oui,
            "InternetGatewayDevice.DeviceInfo.ModelName": "MockCPE-100",
            "InternetGatewayDevice.DeviceInfo.ProductClass": product_class,
            "InternetGatewayDevice.DeviceInfo.SerialNumber": serial,
            "InternetGatewayDevice.DeviceInfo.SoftwareVersion": software_version,
            "InternetGatewayDevice.DeviceInfo.HardwareVersion": "hw-1.0",
            "InternetGatewayDevice.DeviceInfo.SpecVersion": "1.0",
            "InternetGatewayDevice.ManagementServer.ConnectionRequestURL":
                f"http://{cr_host}:{cr_port}/cr",
            "InternetGatewayDevice.ManagementServer.ParameterKey": "",
            "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1."
            "WANIPConnection.1.ExternalIPAddress": "192.168.1.100",
            "InternetGatewayDevice.LANDevice.1.Hosts.HostNumberOfEntries": "2",
        }

        if acs_url.lower().startswith("https"):
            # Test tool: accept self-signed certificates by default.
            context = ssl._create_unverified_context()
            self.opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context))
        else:
            self.opener = urllib.request.build_opener()

    # ------------------------------------------------------------- CWMP I/O

    def post_soap(self, xml: str | None) -> bytes:
        data = xml.encode("utf-8") if xml else b""
        req = urllib.request.Request(
            self.acs_url, data=data, method="POST",
            headers={"Content-Type": 'text/xml; charset="utf-8"'})
        with self.opener.open(req, timeout=15) as resp:
            return resp.read()

    def _build_inform(self, event_code: str) -> str:
        code, _, cmd_key = event_code.partition(" ")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        events = (f"<EventStruct><EventCode>{cwmp.xml_escape(code)}</EventCode>"
                  f"<CommandKey>{cwmp.xml_escape(cmd_key)}</CommandKey></EventStruct>")
        pvs = "".join(cwmp.param_value_struct(n, v, "xsd:string")
                      for n, v in sorted(self.params.items()))
        body = (
            "<cwmp:Inform>"
            f"<DeviceId><Manufacturer>{cwmp.xml_escape(self.manufacturer)}</Manufacturer>"
            f"<OUI>{cwmp.xml_escape(self.oui)}</OUI>"
            f"<ProductClass>{cwmp.xml_escape(self.product_class)}</ProductClass>"
            f"<SerialNumber>{cwmp.xml_escape(self.serial)}</SerialNumber></DeviceId>"
            f'<Event soap-enc:arrayType="cwmp:EventStruct[1]">{events}</Event>'
            "<MaxEnvelopes>1</MaxEnvelopes>"
            f"<CurrentTime>{now}</CurrentTime>"
            "<RetryCount>0</RetryCount>"
            f'<ParameterList soap-enc:arrayType="cwmp:ParameterValueStruct['
            f'{len(self.params)}]">{pvs}</ParameterList>'
            "</cwmp:Inform>"
        )
        return cwmp.envelope(cwmp.next_msg_id(), body)

    def run_session(self, event_code: str = "1 BOOT"):
        if not self._session_lock.acquire(blocking=False):
            print("[cpe] session already in progress - skipping", flush=True)
            return
        try:
            print(f"[cpe] starting session (event {event_code})", flush=True)
            response = self.post_soap(self._build_inform(event_code))
            for _ in range(20):
                if not response or not response.strip():
                    print("[cpe] ACS returned empty response - session complete",
                          flush=True)
                    return
                parsed = cwmp.parse_soap(response)
                if parsed["method"] is None:
                    print("[cpe] no method in ACS response - ending session", flush=True)
                    return
                if parsed["fault"] or parsed["method"].endswith("Response"):
                    # ACS acknowledged our previous request: poll for the
                    # next ACS request with an empty POST (per TR-069).
                    response = self.post_soap(None)
                    continue
                response = self.post_soap(self._handle_acs_request(parsed))
            print("[cpe] too many round trips - aborting session", flush=True)
        except Exception as exc:
            print(f"[cpe] session error: {exc}", flush=True)
        finally:
            self._session_lock.release()

    def _handle_acs_request(self, parsed: dict) -> str:
        mid = parsed["id"] or cwmp.next_msg_id()
        elem, method = parsed["elem"], parsed["method"]
        print(f"[cpe] ACS request: {method}", flush=True)

        if method == "GetParameterValues":
            names_elem = cwmp.find_child(elem, "ParameterNames")
            names = [t.strip() for t in (s.text for s in names_elem)
                     if t and t.strip()] if names_elem is not None else []
            missing = [n for n in names if n not in self.params]
            if missing:
                return cwmp.soap_fault(mid, "Client", "Invalid parameter name", 9003)
            structs = "".join(cwmp.param_value_struct(n, self.params[n], "xsd:string")
                              for n in names)
            body = (
                "<cwmp:GetParameterValuesResponse>"
                f'<ParameterList soap-enc:arrayType="cwmp:ParameterValueStruct['
                f'{len(names)}]">{structs}</ParameterList>'
                "</cwmp:GetParameterValuesResponse>"
            )
            return cwmp.envelope(mid, body)

        if method == "SetParameterValues":
            pl = cwmp.find_child(elem, "ParameterList")
            applied = []
            for struct in cwmp.find_children(pl, "ParameterValueStruct"):
                name = cwmp.child_text(struct, "Name")
                ve = cwmp.find_child(struct, "Value")
                value = "".join(ve.itertext()).strip() if ve is not None else ""
                self.params[name] = value
                applied.append(name)
            param_key = cwmp.child_text(elem, "ParameterKey")
            if param_key:
                self.params["InternetGatewayDevice.ManagementServer.ParameterKey"] = param_key
            print(f"[cpe] applied {len(applied)} parameter(s): "
                  f"{', '.join(applied)}", flush=True)
            return cwmp.envelope(
                mid,
                "<cwmp:SetParameterValuesResponse><Status>0</Status>"
                "</cwmp:SetParameterValuesResponse>")

        if method == "GetParameterNames":
            path = cwmp.child_text(elem, "ParameterPath")
            next_level = cwmp.child_text(elem, "NextLevel").lower() == "true"
            infos = []
            for name in sorted(self.params):
                if not name.startswith(path):
                    continue
                rest = name[len(path):]
                if next_level and "." in rest.rstrip("."):
                    continue
                writable = "0" if name.endswith(("SerialNumber", "ManufacturerOUI")) else "1"
                infos.append(f"<ParameterInfoStruct><Name>{name}</Name>"
                             f"<Writable>{writable}</Writable></ParameterInfoStruct>")
            body = (
                "<cwmp:GetParameterNamesResponse>"
                f'<ParameterList soap-enc:arrayType="cwmp:ParameterInfoStruct['
                f'{len(infos)}]">{"".join(infos)}</ParameterList>'
                "</cwmp:GetParameterNamesResponse>"
            )
            return cwmp.envelope(mid, body)

        if method == "Reboot":
            print("[cpe] *** REBOOT requested ***", flush=True)
            threading.Timer(2.0, lambda: self.run_session("1 BOOT")).start()
            return cwmp.envelope(
                mid, "<cwmp:RebootResponse><Status>0</Status></cwmp:RebootResponse>")

        if method == "FactoryReset":
            print("[cpe] *** FACTORY RESET requested ***", flush=True)
            return cwmp.envelope(mid, "<cwmp:FactoryResetResponse/>")

        if method == "GetRPCMethods":
            return cwmp.get_rpc_methods_response(mid, [
                "GetRPCMethods", "GetParameterNames", "GetParameterValues",
                "SetParameterValues", "Reboot", "FactoryReset"])

        return cwmp.soap_fault(mid, "Client", f"Unsupported method {method}", 8000)


class CRHandler(BaseHTTPRequestHandler):
    """Connection Request endpoint (GET /cr) with optional Digest auth."""
    cpe: MockCPE = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):
        pass

    def _plain(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] != "/cr":
            return self._plain(404, b"not found\n")
        cpe = type(self).cpe
        if cpe.cr_user:
            authz = self.headers.get("Authorization") or ""
            if not authz.startswith("Digest "):
                nonce = secrets.token_hex(16)
                self.send_response(401)
                self.send_header(
                    "WWW-Authenticate",
                    f'Digest realm="{REALM}", nonce="{nonce}", qop="auth"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not verify_digest(authz, "GET", cpe.cr_user, cpe.cr_pass):
                return self._plain(403, b"forbidden\n")
        self._plain(200, b"OK")
        print("[cpe] connection request accepted - starting session", flush=True)
        threading.Thread(target=cpe.run_session,
                         kwargs={"event_code": "6 CONNECTION REQUEST"},
                         daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Mock TR-069 CPE simulator")
    parser.add_argument("--url", required=True, help="ACS URL, e.g. http://host:7547/acs")
    parser.add_argument("--serial", default=uuid.uuid4().hex[:10].upper())
    parser.add_argument("--oui", default="AABBCC")
    parser.add_argument("--manufacturer", default="MockCorp")
    parser.add_argument("--product-class", default="MockCPE")
    parser.add_argument("--software-version", default="1.0.0-mock")
    parser.add_argument("--cr-host", default="127.0.0.1",
                        help="bind host for the Connection Request server")
    parser.add_argument("--cr-port", type=int, default=18080)
    parser.add_argument("--cr-user", default="", help="require Digest auth user for /cr")
    parser.add_argument("--cr-pass", default="")
    parser.add_argument("--bootstrap", action="store_true",
                        help="first Inform uses event 0 BOOTSTRAP instead of 1 BOOT")
    parser.add_argument("--periodic", type=int, default=0, metavar="SEC",
                        help="send a periodic Inform every SEC seconds")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="delay before the first Inform (seconds)")
    args = parser.parse_args()

    cpe = MockCPE(args.url, args.serial, args.oui, args.manufacturer,
                  args.product_class, args.software_version, args.cr_host,
                  args.cr_port, args.cr_user, args.cr_pass)
    CRHandler.cpe = cpe

    cr_server = ThreadingHTTPServer((args.cr_host, args.cr_port), CRHandler)
    cr_server.daemon_threads = True
    threading.Thread(target=cr_server.serve_forever, daemon=True).start()
    auth_note = f" (digest auth: {args.cr_user})" if args.cr_user else ""
    print(f"[cpe] MockCPE simulator v{VERSION}", flush=True)
    print(f"[cpe] serial={args.serial} acs={args.url}", flush=True)
    print(f"[cpe] connection request endpoint: "
          f"http://{args.cr_host}:{args.cr_port}/cr{auth_note}", flush=True)

    first_event = "0 BOOTSTRAP" if args.bootstrap else "1 BOOT"
    threading.Timer(args.delay, lambda: cpe.run_session(first_event)).start()

    if args.periodic > 0:
        def periodic_loop():
            while True:
                time.sleep(args.periodic)
                cpe.run_session("2 PERIODIC")
        threading.Thread(target=periodic_loop, daemon=True).start()

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[cpe] bye", flush=True)


if __name__ == "__main__":
    main()
