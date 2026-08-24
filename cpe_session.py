"""Thread-safe CPE session registry for the ACS test server."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

HISTORY_LIMIT = 200


@dataclass
class OutboundRPC:
    """An ACS-initiated RPC waiting to be delivered to a CPE."""
    method: str
    args: dict = field(default_factory=dict)
    summary: str = ""
    diagnostic: bool = False  # auto-queued by fault diagnostics


@dataclass
class CPESession:
    serial: str
    device_id: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    inform_params: dict = field(default_factory=dict)
    param_types: dict = field(default_factory=dict)  # name -> last reported xsi:type
    known_params: set = field(default_factory=set)   # learned paths for tab completion
    param_writable: dict = field(default_factory=dict)  # name -> writable flag from GetParameterNames
    conn_req_url: str = ""
    cr_username: str = ""  # dynamic ConnectionRequest credentials (bootstrap-provisioned)
    cr_password: str = ""
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    inform_count: int = 0
    session_active: bool = False
    last_sent: str = ""  # method name of the most recent ACS->CPE RPC
    last_set_params: list = field(default_factory=list)  # [(name, value, type)] of most recent SetParameterValues
    last_get_names: list = field(default_factory=list)   # names of the most recent GetParameterValues
    diag_keys: set = field(default_factory=set)  # diagnostics already queued for the current command
    last_rpc: OutboundRPC | None = None  # most recent RPC sent (response correlation)
    provision_pending: tuple | None = None  # (username, password) awaiting set confirmation
    pending: deque = field(default_factory=deque)
    history: list = field(default_factory=list)

    def note(self, direction: str, text: str):
        self.history.append({"ts": time.time(), "dir": direction, "text": text})
        if len(self.history) > HISTORY_LIMIT:
            del self.history[: len(self.history) - HISTORY_LIMIT]

    @property
    def product_class(self) -> str:
        return self.device_id.get("ProductClass", "")

    @property
    def oui(self) -> str:
        return self.device_id.get("OUI", "")

    @property
    def manufacturer(self) -> str:
        return self.device_id.get("Manufacturer", "")


class SessionRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, CPESession] = {}

    def upsert_inform(self, info: dict) -> tuple[CPESession, bool]:
        """Create/update a session from parsed Inform data.

        Returns (session, created).
        """
        device_id = info.get("device_id", {})
        serial = device_id.get("SerialNumber") or "UNKNOWN"
        now = time.time()
        with self._lock:
            created = False
            sess = self._sessions.get(serial)
            if sess is None:
                sess = CPESession(serial=serial, created_at=now)
                self._sessions[serial] = sess
                created = True
            sess.device_id = device_id
            sess.events = info.get("events", [])
            sess.inform_params = info.get("params", {})
            sess.known_params.update(sess.inform_params.keys())
            sess.conn_req_url = next(
                (v for k, v in sess.inform_params.items()
                 if k.endswith("ConnectionRequestURL")),
                sess.conn_req_url,
            )
            sess.last_seen = now
            sess.inform_count += 1
            sess.session_active = True
            return sess, created

    def get(self, serial: str) -> CPESession | None:
        with self._lock:
            return self._sessions.get(serial)

    def all(self) -> list[CPESession]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.created_at)

    def most_recent(self) -> CPESession | None:
        with self._lock:
            sessions = self._sessions.values()
            return max(sessions, key=lambda s: s.last_seen) if sessions else None

    def resolve(self, token=None) -> CPESession | None:
        """Resolve a target CPE.

        token: None/"" -> most recent; digit -> 1-based index into all();
        otherwise exact serial or case-insensitive substring match.
        """
        with self._lock:
            sessions = self.all()
            if not sessions:
                return None
            if token in (None, ""):
                return sessions[-1]
            s = str(token).strip()
            if not s:
                return sessions[-1]
            if s.isdigit():
                idx = int(s)
                if 1 <= idx <= len(sessions):
                    return sessions[idx - 1]
                return None
            exact = self._sessions.get(s)
            if exact:
                return exact
            matches = [x for x in sessions if s.lower() in x.serial.lower()]
            return matches[0] if matches else None

    def enqueue(self, serial: str, rpc: OutboundRPC) -> bool:
        with self._lock:
            sess = self._sessions.get(serial)
            if sess is None:
                return False
            sess.pending.append(rpc)
            return True

    def pop_next(self, serial: str) -> OutboundRPC | None:
        with self._lock:
            sess = self._sessions.get(serial)
            if sess is None:
                return None
            while sess.pending:
                rpc = sess.pending.popleft()
                if rpc is not None:
                    return rpc
            return None

    def pending_total(self) -> int:
        with self._lock:
            return sum(len(s.pending) for s in self._sessions.values())
