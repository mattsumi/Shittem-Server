# Windows transparent redirector using WinDivert (pydivert)
# This creates a lightweight TCP NAT that rewrites outbound flows matching rules
# to local ports (your MITM listeners) and rewrites return packets so the client
# still believes it talks to the original remote IP:port.
#
# Requirements:
# - Admin privileges
# - pydivert (pip install pydivert) which bundles WinDivert driver
# - Windows only

from __future__ import annotations

import socket
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

try:
    from pydivert import WinDivert, Packet
except Exception as e:
    raise


@dataclass
class RedirectRule:
    ports: List[int]
    to_port: int
    domains: Optional[List[str]] = None  # If set, only redirect these domains' IPs
    _ip_cache: Set[str] = field(default_factory=set, init=False, repr=False)

    def update_ips(self):
        if not self.domains:
            return
        updated: Set[str] = set()
        for d in self.domains:
            try:
                # Resolve both A and AAAA; store as strings
                infos = socket.getaddrinfo(d, None)
                for info in infos:
                    ip = info[4][0]
                    updated.add(ip)
            except Exception:
                pass
        if updated:
            self._ip_cache = updated

    def matches(self, dst_ip: str, dst_port: int) -> bool:
        if dst_port not in self.ports:
            return False
        if self.domains is None:
            return True
        return dst_ip in self._ip_cache


class TransparentRedirector:
    def __init__(self, rules: List[RedirectRule], debug: bool = False):
        self.rules = rules
        self._stop_event = threading.Event()
        self.debug = debug
        self._thread: Optional[threading.Thread] = None
        # NAT map: (src_ip, src_port, dst_ip, dst_port) -> (to_ip, to_port, rule)
        self._nat_map: Dict[Tuple[str, int, str, int], Tuple[str, int, RedirectRule]] = {}
        self._nat_lock = threading.Lock()

        # Resolve domains initially
        for r in self.rules:
            r.update_ips()

        # Build initial filter
        self._filter = ""
        self._last_dns_refresh = 0.0

    def _build_filter(self) -> str:
        ports = set()
        ips: Set[str] = set()
        for r in self.rules:
            ports.update(r.ports)
            ips.update(r._ip_cache)
        if not ports:
            port_filter = "tcp.DstPort == 0"
        else:
            port_filter = " or ".join([f"tcp.DstPort == {p}" for p in sorted(ports)])
        if not ips:
            ip_filter = "ip.DstAddr == 0.0.0.0"  # matches nothing
        else:
            ip_filter = " or ".join([f"ip.DstAddr == {ip}" for ip in sorted(ips)])
        # Restrict outbound to only our BA destination IPs and ports
        outbound_f = f"(outbound and tcp and ip and (({port_filter}) and ({ip_filter})))"
        # Build inbound src-port filter for our listener ports (include loopback to be safe)
        to_ports = sorted({r.to_port for r in self.rules})
        if to_ports:
            src_port_filter = " or ".join([f"tcp.SrcPort == {p}" for p in to_ports])
            inbound_f = (
                f"(inbound and tcp and ip and ip.SrcAddr == 127.0.0.1 and ({src_port_filter})) or "
                f"(loopback and tcp and ip and ({src_port_filter}))"
            )
        else:
            inbound_f = "(inbound and tcp and ip and ip.SrcAddr == 127.0.0.1 and tcp.SrcPort == 0)"  # matches nothing
        flt = f"{outbound_f} or {inbound_f}"
        if self.debug:
            print(f"[Redirector] Filter built: {flt}")
        return flt

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._filter = self._build_filter()
        self._thread = threading.Thread(
            target=self._run,
            name="WinDivertTransparentRedirect",
            daemon=True,
        )
        self._thread.start()
        if self.debug:
            print("[Redirector] Started WinDivert thread")

    def stop(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None
        if self.debug:
            print("[Redirector] Stopped WinDivert thread")

    def update_rules(self, rules: List[RedirectRule]):
        # Replace rules and restart capture
        self.rules = rules
        for r in self.rules:
            r.update_ips()
        if self.debug:
            print(f"[Redirector] Updating rules: ports={sorted({p for rr in self.rules for p in rr.ports})} domains={[rr.domains for rr in self.rules]}")
        was_running = self._thread is not None and self._thread.is_alive()
        if was_running:
            self.stop()
            # Small delay to allow driver to release handle
            time.sleep(0.05)
        self.start()

    def _refresh_domains_periodically(self):
        now = time.time()
        if now - self._last_dns_refresh > 30.0:
            for r in self.rules:
                r.update_ips()
            self._last_dns_refresh = now

    def _select_rule(self, dst_ip: str, dst_port: int) -> Optional[RedirectRule]:
        for r in self.rules:
            if r.matches(dst_ip, dst_port):
                return r
        return None

    def _run(self):
        # Note: setting queue length to reduce drops under load
        with WinDivert(self._filter) as w:
            if self.debug:
                print("[Redirector] WinDivert handle opened")
            while not self._stop_event.is_set():
                try:
                    packet: Packet = w.recv()
                except Exception:
                    continue

                # Periodically refresh DNS resolutions
                self._refresh_domains_periodically()

                try:
                    self._process_packet(packet)
                except Exception:
                    # On error, just reinject original packet to avoid breaking connections
                    try:
                        w.send(packet)
                    except Exception:
                        pass
                else:
                    try:
                        w.send(packet)
                    except Exception:
                        pass

    def _process_packet(self, packet: Packet):
        if not packet.tcp or not packet.ip:
            return

        src_ip = packet.src_addr
        dst_ip = packet.dst_addr
        src_port = packet.tcp.src_port
        dst_port = packet.tcp.dst_port

        if packet.is_outbound:
            key = (src_ip, src_port, dst_ip, dst_port)
            rule = self._select_rule(dst_ip, dst_port)
            if rule is None:
                return  # passthrough

            # Apply redirect: rewrite destination to localhost:rule.to_port
            with self._nat_lock:
                self._nat_map[key] = ("127.0.0.1", rule.to_port, rule)
            packet.dst_addr = "127.0.0.1"
            packet.tcp.dst_port = rule.to_port
            packet.ip.ttl = max(32, (packet.ip.ttl or 64))
            packet.recalculate_checksums()
            if self.debug:
                print(f"[Redirector] OUT redir {src_ip}:{src_port} -> 127.0.0.1:{rule.to_port} (orig {dst_ip}:{dst_port})")
                print(f"[Redirector] MAP add key=({src_ip},{src_port},{dst_ip},{dst_port}) to_port={rule.to_port}")
        else:
            # inbound: maybe from our listener back to the client; reverse NAT
            if src_ip != "127.0.0.1":
                return
            # Find original tuple by matching to_port
            with self._nat_lock:
                # Find a mapping with this to_port and client addr/port
                rev_key = None
                orig_dst_ip = None
                orig_dst_port = None
                for (c_src_ip, c_src_port, c_dst_ip, c_dst_port), (to_ip, to_port, _r) in list(self._nat_map.items()):
                    if to_port == src_port and packet.dst_addr == c_src_ip and packet.tcp.dst_port == c_src_port:
                        rev_key = (c_src_ip, c_src_port, c_dst_ip, c_dst_port)
                        orig_dst_ip, orig_dst_port = c_dst_ip, c_dst_port
                        break
            if rev_key and orig_dst_ip:
                # Rewrite src back to original remote IP:port so client believes it's the server
                packet.src_addr = orig_dst_ip
                packet.tcp.src_port = orig_dst_port
                packet.recalculate_checksums()
                if self.debug:
                    print(f"[Redirector] IN rewrite 127.0.0.1:{src_port} -> {orig_dst_ip}:{orig_dst_port}")
            else:
                # no mapping; leave as-is
                if self.debug:
                    print(f"[Redirector] IN no-map src=127.0.0.1:{src_port} dst={packet.dst_addr}:{packet.tcp.dst_port}")
                return
