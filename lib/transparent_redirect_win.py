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
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

try:
    from pydivert import WinDivert, Packet
except ImportError as e:
    raise ImportError(f"pydivert is required: {e}") from e


@dataclass
class RedirectRule:
    ports: List[int]
    to_port: int
    domains: Optional[List[str]] = None  # If set, only redirect these domains' IPs
    _ip_cache: Set[str] = field(default_factory=set, init=False, repr=False)

    def update_ips(self):
        """Update IP cache by resolving domains. Handles both IPv4 and IPv6."""
        if not self.domains:
            return
        updated: Set[str] = set()
        for d in self.domains:
            try:
                # Resolve both A and AAAA records; store as strings
                infos = socket.getaddrinfo(d, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                for info in infos:
                    ip = info[4][0]
                    # Only add IPv4 addresses for WinDivert compatibility
                    if '.' in ip and ':' not in ip:  # Simple IPv4 check
                        updated.add(ip)
            except (socket.gaierror, socket.error) as e:
                # Log DNS resolution failures if debug enabled
                if hasattr(self, 'debug') and getattr(self, 'debug', False):
                    print(f"[Redirector] DNS resolution failed for {d}: {e}")
            except Exception as e:
                # Catch any other errors but don't let them break the entire update
                if hasattr(self, 'debug') and getattr(self, 'debug', False):
                    print(f"[Redirector] Unexpected error resolving {d}: {e}")
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
        self._windivert_handle: Optional[WinDivert] = None
        # NAT map: (src_ip, src_port, dst_ip, dst_port) -> (to_ip, to_port, rule)
        self._nat_map: Dict[Tuple[str, int, str, int], Tuple[str, int, RedirectRule]] = {}
        self._nat_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()  # Protects start/stop operations

        # Resolve domains initially, passing debug flag
        for r in self.rules:
            r.debug = debug  # Add debug flag to rules
            r.update_ips()

        # Build initial filter
        self._filter = ""
        self._last_dns_refresh = 0.0

    def _build_filter(self) -> str:
        """Build WinDivert filter with valid syntax and early exits."""
        ports = set()
        ips: Set[str] = set()
        wildcard_ip = False
        for r in self.rules:
            ports.update(r.ports)
            if r.domains is None:
                wildcard_ip = True  # match any IP on the given ports
            ips.update(r._ip_cache)

        # Build destination port predicate
        if not ports:
            return "tcp.DstPort == 65536"  # no ports -> match nothing
        else:
            port_filter = " or ".join([f"tcp.DstPort == {p}" for p in sorted(ports)])

        # Build destination IP predicate
        if wildcard_ip:
            ip_filter = "ip"
        else:
            if not ips:
                return "tcp.DstPort == 65536"  # no IPs -> match nothing
            else:
                def ip_sort_key(ip_str: str):
                    try:
                        return tuple(int(part) for part in ip_str.split('.'))
                    except Exception:
                        return (999, 999, 999, 999)
                sorted_ips = sorted(ips, key=ip_sort_key)
                ip_conditions = [f"ip.DstAddr == {ip}" for ip in sorted_ips]
                ip_filter = " or ".join(ip_conditions)

        outbound_f = f"(outbound and tcp and ip and (({port_filter}) and ({ip_filter})))"

        # Build inbound src-port filter for our listener ports
        to_ports = sorted({r.to_port for r in self.rules})
        if to_ports:
            src_port_filter = " or ".join([f"tcp.SrcPort == {p}" for p in to_ports])
            inbound_f = (
                f"(inbound and tcp and ip and ip.SrcAddr == 127.0.0.1 and ({src_port_filter})) or "
                f"(loopback and tcp and ip and ({src_port_filter}))"
            )
        else:
            return "tcp.DstPort == 65536"  # no listener ports -> match nothing

        flt = f"{outbound_f} or {inbound_f}"
        if self.debug:
            print(f"[Redirector] Filter built: {flt}")
        return flt

    def get_filter(self) -> str:
        """Return last built WinDivert filter (for debugging)."""
        return self._filter or self._build_filter()

    def start(self):
        """Start the redirector thread with proper error handling."""
        with self._lifecycle_lock:
            if self._thread and self._thread.is_alive():
                return
            
            self._stop_event.clear()
            self._filter = self._build_filter()
            
            # Validate filter before starting thread
            if self._filter == "false":
                if self.debug:
                    print("[Redirector] No valid rules, not starting")
                return
            
            self._thread = threading.Thread(
                target=self._run,
                name="WinDivertTransparentRedirect",
                daemon=True,
            )
            self._thread.start()
            if self.debug:
                print("[Redirector] Started WinDivert thread")

    def stop(self, timeout: float = 2.0):
        """Stop the redirector thread with proper cleanup."""
        with self._lifecycle_lock:
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=timeout)
                if self._thread.is_alive():
                    if self.debug:
                        print("[Redirector] Warning: Thread didn't stop within timeout")
            self._thread = None
            
            # Clear NAT map on stop
            with self._nat_lock:
                self._nat_map.clear()
            
            if self.debug:
                print("[Redirector] Stopped WinDivert thread")

    def update_rules(self, rules: List[RedirectRule]):
        """Replace rules and restart capture with proper synchronization."""
        with self._lifecycle_lock:
            # Replace rules and update IPs
            self.rules = rules
            for r in self.rules:
                r.debug = self.debug  # Propagate debug flag
                r.update_ips()
            
            if self.debug:
                print(f"[Redirector] Updating rules: ports={sorted({p for rr in self.rules for p in rr.ports})} domains={[rr.domains for rr in self.rules]}")
            
            # Restart if running
            was_running = self._thread is not None and self._thread.is_alive()
            if was_running:
                self.stop()
                # Small delay to allow WinDivert driver to release handle properly
                time.sleep(0.1)
            self.start()

    def _refresh_domains_periodically(self):
        """Refresh domain DNS resolutions periodically with error handling."""
        now = time.time()
        if now - self._last_dns_refresh > 30.0:
            try:
                for r in self.rules:
                    r.update_ips()
                self._last_dns_refresh = now
            except Exception as e:
                if self.debug:
                    print(f"[Redirector] Error during DNS refresh: {e}")

    def _select_rule(self, dst_ip: str, dst_port: int) -> Optional[RedirectRule]:
        for r in self.rules:
            if r.matches(dst_ip, dst_port):
                return r
        return None

    def _run(self):
        """Main packet processing loop with comprehensive error handling."""
        try:
            # Set queue parameters for better performance - WinDivert defaults
            with WinDivert(self._filter, priority=0, flags=0) as w:
                self._windivert_handle = w
                if self.debug:
                    print("[Redirector] WinDivert handle opened successfully")
                
                while not self._stop_event.is_set():
                    try:
                        # Use timeout to allow periodic checking of stop event
                        packet: Packet = w.recv(timeout=1000)  # 1 second timeout
                    except TimeoutError:
                        # Normal timeout, check stop event and continue
                        continue
                    except OSError as e:
                        if e.winerror == 995:  # ERROR_OPERATION_ABORTED
                            # Normal shutdown, break quietly
                            break
                        if self.debug:
                            print(f"[Redirector] WinDivert recv error: {e}")
                        continue
                    except Exception as e:
                        if self.debug:
                            print(f"[Redirector] Unexpected recv error: {e}")
                        continue

                    # Periodically refresh DNS resolutions
                    try:
                        self._refresh_domains_periodically()
                    except Exception as e:
                        if self.debug:
                            print(f"[Redirector] DNS refresh error: {e}")

                    # Process packet
                    try:
                        modified = self._process_packet(packet)
                        # Send packet back (modified or original)
                        w.send(packet)
                    except OSError as e:
                        if e.winerror == 995:  # ERROR_OPERATION_ABORTED
                            break
                        if self.debug:
                            print(f"[Redirector] Packet processing error: {e}")
                    except Exception as e:
                        if self.debug:
                            print(f"[Redirector] Unexpected packet error: {e}")
                        # Try to send original packet to avoid breaking connection
                        try:
                            w.send(packet)
                        except Exception:
                            pass
                            
        except OSError as e:
            if e.winerror == 87:  # ERROR_INVALID_PARAMETER
                print(f"[Redirector] WinDivert filter error: {e}")
                print(f"[Redirector] Filter was: {self._filter}")
            elif e.winerror == 5:  # ERROR_ACCESS_DENIED
                print(f"[Redirector] Access denied - run as Administrator: {e}")
            else:
                print(f"[Redirector] WinDivert system error: {e}")
        except Exception as e:
            print(f"[Redirector] Fatal error in packet loop: {e}")
        finally:
            self._windivert_handle = None
            if self.debug:
                print("[Redirector] WinDivert handle closed")

    def _process_packet(self, packet: Packet) -> bool:
        """Process a packet and return True if it was modified."""
        if not packet.tcp or not packet.ip:
            return False

        src_ip = packet.src_addr
        dst_ip = packet.dst_addr
        src_port = packet.tcp.src_port
        dst_port = packet.tcp.dst_port

        if packet.is_outbound:
            # Outbound packet - check if it matches our redirect rules
            rule = self._select_rule(dst_ip, dst_port)
            if rule is None:
                return False  # No rule matches, pass through unchanged

            # Apply redirect: rewrite destination to localhost:rule.to_port
            key = (src_ip, src_port, dst_ip, dst_port)
            with self._nat_lock:
                self._nat_map[key] = ("127.0.0.1", rule.to_port, rule)
            
            # Modify packet
            packet.dst_addr = "127.0.0.1"
            packet.tcp.dst_port = rule.to_port
            # Ensure reasonable TTL
            if packet.ip.ttl is not None:
                packet.ip.ttl = max(32, packet.ip.ttl)
            else:
                packet.ip.ttl = 64
            packet.recalculate_checksums()
            
            if self.debug:
                print(f"[Redirector] OUT redirect {src_ip}:{src_port} -> 127.0.0.1:{rule.to_port} (orig {dst_ip}:{dst_port})")
            
            return True
        else:
            # Inbound packet - check if it's from our listener that needs reverse NAT
            if src_ip != "127.0.0.1":
                return False
                
            # Find original connection tuple by matching listener port and client address/port
            with self._nat_lock:
                orig_dst_ip = None
                orig_dst_port = None
                
                # More efficient lookup - iterate through NAT map
                for (c_src_ip, c_src_port, c_dst_ip, c_dst_port), (to_ip, to_port, _r) in self._nat_map.items():
                    if (to_port == src_port and
                        packet.dst_addr == c_src_ip and
                        packet.tcp.dst_port == c_src_port):
                        orig_dst_ip, orig_dst_port = c_dst_ip, c_dst_port
                        break
            
            if orig_dst_ip is not None:
                # Rewrite source back to original remote IP:port so client believes it's talking to the server
                packet.src_addr = orig_dst_ip
                packet.tcp.src_port = orig_dst_port
                packet.recalculate_checksums()
                
                if self.debug:
                    print(f"[Redirector] IN reverse NAT 127.0.0.1:{src_port} -> {orig_dst_ip}:{orig_dst_port}")
                
                return True
            else:
                # No mapping found - this might be a legitimate local connection
                if self.debug:
                    print(f"[Redirector] IN no-mapping src=127.0.0.1:{src_port} dst={packet.dst_addr}:{packet.tcp.dst_port}")
                return False
