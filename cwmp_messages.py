"""TR-069 CWMP SOAP message construction and parsing.

Builders return complete XML document strings (UTF-8 encodable).
Parsers work namespace-agnostically by matching element local names,
so devices using non-standard namespace URNs are still handled.
"""

from __future__ import annotations

import itertools
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_ENC = "http://schemas.xmlsoap.org/soap/encoding/"
NS_XSD = "http://www.w3.org/2001/XMLSchema"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_CWMP = "urn:dslforum-org:cwmp-1-0"

_msg_id_counter = itertools.count(1)


def next_msg_id() -> int:
    return next(_msg_id_counter)


def localname(tag: str) -> str:
    """Strip XML namespace: '{urn:...}Name' -> 'Name'."""
    return tag.rsplit("}", 1)[-1]


def find_child(parent: ET.Element, name: str):
    """Find a direct child by local name (exact match first, then case-insensitive).

    Some devices emit non-standard casing such as <cwmp:Fault> instead of
    <cwmp:fault>, so a case-insensitive fallback is required.
    """
    for child in parent:
        if localname(child.tag) == name:
            return child
    lowered = name.lower()
    for child in parent:
        if localname(child.tag).lower() == lowered:
            return child
    return None


def find_children(parent: ET.Element, name: str) -> list[ET.Element]:
    result = [child for child in parent if localname(child.tag) == name]
    if not result:
        lowered = name.lower()
        result = [child for child in parent if localname(child.tag).lower() == lowered]
    return result


def child_text(elem: ET.Element, name: str, default: str = "") -> str:
    child = find_child(elem, name)
    if child is None:
        return default
    return "".join(child.itertext()).strip()


# --------------------------------------------------------------------------
# Message builders
# --------------------------------------------------------------------------

def envelope(msg_id, body_xml: str) -> str:
    mid = str(msg_id)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap-env:Envelope xmlns:soap-env="{NS_SOAP}"'
        f' xmlns:soap-enc="{NS_ENC}"'
        f' xmlns:xsd="{NS_XSD}"'
        f' xmlns:xsi="{NS_XSI}"'
        f' xmlns:cwmp="{NS_CWMP}">'
        "<soap-env:Header>"
        f'<cwmp:ID soap-env:mustUnderstand="1">{mid}</cwmp:ID>'
        "</soap-env:Header>"
        f"<soap-env:Body>{body_xml}</soap-env:Body>"
        "</soap-env:Envelope>"
    )


def param_value_struct(name: str, value, xsi_type: str | None = None) -> str:
    type_attr = f' xsi:type="{xsi_type}"' if xsi_type else ""
    return (
        "<ParameterValueStruct>"
        f"<Name>{xml_escape(str(name))}</Name>"
        f"<Value{type_attr}>{xml_escape(str(value))}</Value>"
        "</ParameterValueStruct>"
    )


def inform_response(msg_id=None) -> str:
    mid = msg_id if msg_id is not None else next_msg_id()
    return envelope(
        mid,
        "<cwmp:InformResponse><MaxEnvelopes>1</MaxEnvelopes></cwmp:InformResponse>",
    )


def transfer_complete_response(msg_id=None) -> str:
    mid = msg_id if msg_id is not None else next_msg_id()
    return envelope(
        mid,
        "<cwmp:TransferCompleteResponse><Status>0</Status></cwmp:TransferCompleteResponse>",
    )


def get_parameter_values(msg_id, names) -> str:
    names = list(names)
    items = "".join(f"<string>{xml_escape(n)}</string>" for n in names)
    body = (
        "<cwmp:GetParameterValues>"
        f'<ParameterNames soap-enc:arrayType="xsd:string[{len(names)}]">{items}</ParameterNames>'
        "</cwmp:GetParameterValues>"
    )
    return envelope(msg_id, body)


def set_parameter_values(msg_id, params, parameter_key: str = "") -> str:
    """params: iterable of (name, value, xsi_type)."""
    params = list(params)
    structs = "".join(param_value_struct(n, v, t) for n, v, t in params)
    body = (
        "<cwmp:SetParameterValues>"
        f'<ParameterList soap-enc:arrayType="cwmp:ParameterValueStruct[{len(params)}]">'
        f"{structs}</ParameterList>"
        f"<ParameterKey>{xml_escape(parameter_key)}</ParameterKey>"
        "</cwmp:SetParameterValues>"
    )
    return envelope(msg_id, body)


def get_parameter_names(msg_id, path: str, next_level: bool = False) -> str:
    body = (
        "<cwmp:GetParameterNames>"
        f"<ParameterPath>{xml_escape(path)}</ParameterPath>"
        f"<NextLevel>{'true' if next_level else 'false'}</NextLevel>"
        "</cwmp:GetParameterNames>"
    )
    return envelope(msg_id, body)


def reboot(msg_id, command_key: str = "") -> str:
    body = f"<cwmp:Reboot><CommandKey>{xml_escape(command_key)}</CommandKey></cwmp:Reboot>"
    return envelope(msg_id, body)


def download(msg_id, command_key: str = "",
             file_type: str = "1 Firmware Upgrade Image",
             url: str = "", username: str = "", password: str = "",
             file_size: int = 0, target_filename: str = "",
             delay_seconds: int = 0) -> str:
    body = (
        "<cwmp:Download>"
        f"<CommandKey>{xml_escape(command_key)}</CommandKey>"
        f"<FileType>{xml_escape(file_type)}</FileType>"
        f"<URL>{xml_escape(url)}</URL>"
        f"<Username>{xml_escape(username)}</Username>"
        f"<Password>{xml_escape(password)}</Password>"
        f"<FileSize>{int(file_size)}</FileSize>"
        f"<TargetFileName>{xml_escape(target_filename)}</TargetFileName>"
        f"<DelaySeconds>{int(delay_seconds)}</DelaySeconds>"
        "<SuccessURL></SuccessURL>"
        "<FailureURL></FailureURL>"
        "</cwmp:Download>"
    )
    return envelope(msg_id, body)


def factory_reset(msg_id) -> str:
    return envelope(msg_id, "<cwmp:FactoryReset/>")


def add_object(msg_id, object_name: str, parameter_key: str = "") -> str:
    body = (
        "<cwmp:AddObject>"
        f"<ObjectName>{xml_escape(object_name)}</ObjectName>"
        f"<ParameterKey>{xml_escape(parameter_key)}</ParameterKey>"
        "</cwmp:AddObject>"
    )
    return envelope(msg_id, body)


def delete_object(msg_id, object_name: str, parameter_key: str = "") -> str:
    body = (
        "<cwmp:DeleteObject>"
        f"<ObjectName>{xml_escape(object_name)}</ObjectName>"
        f"<ParameterKey>{xml_escape(parameter_key)}</ParameterKey>"
        "</cwmp:DeleteObject>"
    )
    return envelope(msg_id, body)


def get_rpc_methods_response(msg_id, methods) -> str:
    methods = list(methods)
    items = "".join(f"<string>{m}</string>" for m in methods)
    body = (
        "<cwmp:GetRPCMethodsResponse>"
        f'<MethodList soap-enc:arrayType="xsd:string[{len(methods)}]">{items}</MethodList>'
        "</cwmp:GetRPCMethodsResponse>"
    )
    return envelope(msg_id, body)


def soap_fault(msg_id, fault_code: str = "Client", fault_string: str = "",
               cwmp_fault_code: int = 8000) -> str:
    body = (
        "<soap-env:Fault>"
        f"<faultcode>{xml_escape(fault_code)}</faultcode>"
        f"<faultstring>{xml_escape(fault_string)}</faultstring>"
        "<detail><cwmp:fault>"
        f"<FaultCode>{cwmp_fault_code}</FaultCode>"
        f"<FaultString>{xml_escape(fault_string)}</FaultString>"
        "</cwmp:fault></detail>"
        "</soap-env:Fault>"
    )
    return envelope(msg_id, body)


def infer_xsd_type(value: str) -> tuple[str, str]:
    """Infer an XSD type for a console-provided value.

    Returns (xsd_type, normalized_value).
    """
    v = value.strip()
    low = v.lower()
    if low in ("true", "false"):
        return "xsd:boolean", "1" if low == "true" else "0"
    try:
        n = int(v)
        return ("xsd:int" if n < 0 else "xsd:unsignedInt"), str(n)
    except ValueError:
        pass
    try:
        float(v)
        return "xsd:double", v
    except ValueError:
        pass
    return "xsd:string", v


TYPE_ALIASES = {
    "string": "xsd:string", "str": "xsd:string",
    "int": "xsd:int", "integer": "xsd:int",
    "uint": "xsd:unsignedInt", "unsignedint": "xsd:unsignedInt",
    "bool": "xsd:boolean", "boolean": "xsd:boolean",
    "double": "xsd:double", "float": "xsd:double",
    "datetime": "xsd:dateTime", "date": "xsd:dateTime",
}


def resolve_type_alias(name: str) -> str | None:
    """Map a console type alias ('bool', 'string', ...) to an XSD type name."""
    return TYPE_ALIASES.get(name.strip().lower())


def coerce_value(value: str, xsd_type: str) -> str | None:
    """Normalize value for the given XSD type; None if it cannot conform."""
    v = value.strip()
    t = xsd_type.lower()
    if t == "xsd:boolean":
        low = v.lower()
        if low in ("true", "1", "enabled", "enable", "on", "yes"):
            return "1"
        if low in ("false", "0", "disabled", "disable", "off", "no"):
            return "0"
        return None
    if t in ("xsd:int", "xsd:unsignedint"):
        try:
            return str(int(v))
        except ValueError:
            return None
    if t == "xsd:double":
        try:
            float(v)
            return v
        except ValueError:
            return None
    return v


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------

def parse_soap(data: bytes) -> dict:
    """Parse a SOAP document. Returns {id, method, elem, fault}.

    Raises ValueError on malformed input.
    """
    root = ET.fromstring(data)
    if localname(root.tag) != "Envelope":
        raise ValueError("not a SOAP envelope")
    header = find_child(root, "Header")
    body = find_child(root, "Body")
    msg_id = child_text(header, "ID") if header is not None else None
    method_name, method_elem, is_fault = None, None, False
    if body is not None:
        for child in body:
            name = localname(child.tag)
            if name == "Fault":
                method_name, method_elem, is_fault = "Fault", child, True
            else:
                method_name, method_elem = name, child
            break
    return {"id": msg_id, "method": method_name, "elem": method_elem, "fault": is_fault}


def parse_inform(elem: ET.Element) -> dict:
    dev_elem = find_child(elem, "DeviceId")
    device_id = {}
    if dev_elem is not None:
        for field in ("Manufacturer", "OUI", "ProductClass", "SerialNumber"):
            device_id[field] = child_text(dev_elem, field)

    # EventCode normalization: some firmwares (e.g. Arcadyan) put the whole
    # '0 BOOTSTRAP' string inside <EventCode> instead of just the code.
    # Split on whitespace so consumers always see a bare code ('0'), keeping
    # the tail as the command key when <CommandKey> is absent.
    events = []
    ev_elem = find_child(elem, "Event")
    if ev_elem is not None:
        for struct in find_children(ev_elem, "EventStruct"):
            code_text = child_text(struct, "EventCode")
            code, _, tail = code_text.partition(" ")
            command_key = child_text(struct, "CommandKey") or tail.strip()
            events.append({
                "code": code.strip(),
                "command_key": command_key,
            })

    params = {}
    pl_elem = find_child(elem, "ParameterList")
    if pl_elem is not None:
        for struct in find_children(pl_elem, "ParameterValueStruct"):
            name = child_text(struct, "Name")
            value_elem = find_child(struct, "Value")
            value = "".join(value_elem.itertext()) if value_elem is not None else ""
            params[name] = value.strip()

    return {
        "device_id": device_id,
        "events": events,
        "params": params,
        "max_envelopes": child_text(elem, "MaxEnvelopes", "1"),
        "current_time": child_text(elem, "CurrentTime"),
        "retry_count": child_text(elem, "RetryCount", "0"),
    }


def format_event(event: dict) -> str:
    """Human-readable event label ('0 BOOTSTRAP') from a parsed EventStruct."""
    return f"{event.get('code', '')} {event.get('command_key', '')}".strip()


def format_fault(elem: ET.Element) -> str:
    lines = []
    code = child_text(elem, "faultcode")
    string = child_text(elem, "faultstring")
    if code:
        lines.append(f"faultcode={code}")
    if string:
        lines.append(f"faultstring={string}")
    detail = find_child(elem, "detail")
    if detail is not None:
        fault = find_child(detail, "fault")
        if fault is not None:
            fc = child_text(fault, "FaultCode")
            fs = child_text(fault, "FaultString")
            if fc:
                lines.append(f"FaultCode={fc}")
            if fs:
                lines.append(f"FaultString={fs}")
    return "; ".join(lines) or "SOAP Fault"


def extract_param_values(elem: ET.Element) -> dict[str, tuple[str, str | None]]:
    """Extract {name: (value, xsi_type)} from a ParameterList-bearing element."""
    pl = find_child(elem, "ParameterList")
    result: dict[str, tuple[str, str | None]] = {}
    if pl is None:
        return result
    for struct in find_children(pl, "ParameterValueStruct"):
        name = child_text(struct, "Name")
        ve = find_child(struct, "Value")
        value = "".join(ve.itertext()).strip() if ve is not None else ""
        xsi = ve.get(f"{{{NS_XSI}}}type") if ve is not None else None
        result[name] = (value, xsi)
    return result


def extract_param_names(elem: ET.Element) -> list[str]:
    """Extract parameter names from a GetParameterNamesResponse element."""
    return [name for name, _w in extract_param_infos(elem)]


def extract_param_infos(elem: ET.Element) -> list[tuple[str, str | None]]:
    """Extract (name, writable) from a GetParameterNamesResponse element.

    writable is the raw '0'/'1' text, or None when absent.
    """
    pl = find_child(elem, "ParameterList")
    result: list[tuple[str, str | None]] = []
    if pl is None:
        return result
    for struct in find_children(pl, "ParameterInfoStruct"):
        name = child_text(struct, "Name")
        writable = child_text(struct, "Writable", "") or None
        result.append((name, writable))
    return result


def extract_add_object_response(elem: ET.Element) -> dict:
    """Extract InstanceNumber and Status from AddObjectResponse."""
    instance_num = child_text(elem, "InstanceNumber")
    status = child_text(elem, "Status")
    return {"instance_number": instance_num, "status": status}


def extract_delete_object_response(elem: ET.Element) -> dict:
    """Extract Status from DeleteObjectResponse."""
    status = child_text(elem, "Status")
    return {"status": status}


def format_response(method: str, elem: ET.Element | None) -> str:
    """Human-readable summary of a CPE RPC response element."""
    if elem is None:
        return "(empty)"
    pl = find_child(elem, "ParameterList")
    if pl is not None:
        values = extract_param_values(elem)
        if values:
            lines = [f"{n} = {v}{f' [{t}]' if t else ''}"
                     for n, (v, t) in values.items()]
            return "\n".join(lines)
        infos = find_children(pl, "ParameterInfoStruct")
        if infos:
            lines = []
            for struct in infos:
                name = child_text(struct, "Name")
                writable = child_text(struct, "Writable")
                lines.append(f"{name} (writable={writable})")
            return "\n".join(lines) or "(no parameters)"
    if localname(elem.tag) == "DownloadResponse":
        status = child_text(elem, "Status")
        meaning = {"0": "download completed",
                   "1": "in progress (TransferComplete will follow)"}.get(status, "")
        lines = [f"Status={status}" + (f" ({meaning})" if meaning else "")]
        for field in ("StartTime", "CompleteTime"):
            value = child_text(elem, field)
            if value:
                lines.append(f"{field}={value}")
        return "\n".join(lines)
    if localname(elem.tag) == "AddObjectResponse":
        instance_num = child_text(elem, "InstanceNumber")
        status = child_text(elem, "Status")
        meaning = {"0": "created", "1": "created after reboot"}.get(status, "")
        lines = [f"InstanceNumber={instance_num}", f"Status={status}" + (f" ({meaning})" if meaning else "")]
        return "\n".join(lines)
    if localname(elem.tag) == "DeleteObjectResponse":
        status = child_text(elem, "Status")
        meaning = {"0": "deleted", "1": "deleted after reboot"}.get(status, "")
        return f"Status={status}" + (f" ({meaning})" if meaning else "")
    status = child_text(elem, "Status")
    if status:
        return f"Status={status}"
    # Generic flatten of unknown structures.
    lines = []

    def walk(e, prefix):
        for c in e:
            tag = localname(c.tag)
            text = "".join(c.itertext()).strip()
            if len(c) == 0 and text:
                lines.append(f"{prefix}{tag} = {text}")
            else:
                walk(c, prefix + tag + ".")

    walk(elem, "")
    return "\n".join(lines) or "(empty)"
