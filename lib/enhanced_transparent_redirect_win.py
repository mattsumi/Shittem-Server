# Enhanced Windows Transparent Redirector using WinDivert (pydivert)
# Production-ready implementation with comprehensive error handling and diagnostics
# Addresses critical WinDivert [WinError 87] parameter issues and performance optimization

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
import sys
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import concurrent.futures

# Enhanced logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('windivert_enhanced.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('EnhancedTransparentRedirect')

try:
    from pydivert import WinDivert, Packet
    WINDIVERT_AVAILABLE = True
except Exception as e:
    logger.error(f"WinDivert import failed: {e}")
    WINDIVERT_AVAILABLE = False
    # Create mock classes for testing/development
    class WinDivert:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WinDivert not available")
    class Packet:
        pass

class WinDivertError(Exception):
    """Custom exception for WinDivert-specific errors"""
    def __init__(self, message: str, error_code: int = None, filter_string: str = None):
        self.error_code = error_code
        self.filter_string = filter_string
        super().__init__(message)

class RedirectStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"

@dataclass
class PerformanceMetrics:
    """Performance tracking for the redirector"""
    packets_processed: int = 0
    packets_redirected: int = 0
    packets_errors: int = 0
    dns_resolutions: int = 0
    dns_failures: int = 0
    filter_rebuilds: int = 0
    start_time: float = field(default_factory=time.time)
    
    def get_runtime_seconds(self) -> float:
        return time.time() - self.start_time
    
    def get_packets_per_second(self) -> float:
        runtime = self.get_runtime_seconds()
        return self.packets_processed / runtime if runtime > 0 else 0

@dataclass
class EnhancedRedirectRule:
    """Enhanced redirect rule with comprehensive validation and caching"""
    ports: List[int]
    to_port: int
    domains: Optional[List[str]] = None
    description: str = ""
    enabled: bool = True
    _ip_cache: Set[str] = field(default_factory=set, init=False, repr=False)
    _last_dns_update: float = field(default=0.0, init=False, repr=False)
    _dns_failures: int = field(default=0, init=False, repr=False)
    
    def __post_init__(self):
        """Validate rule parameters"""
        if not self.ports:
            raise ValueError("Rule must have at least one port")
        if not (1 <= self.to_port <= 65535):
            raise ValueError(f"Invalid to_port: {self.to_port}")
        for port in self.ports:
            if not (1 <= port <= 65535):
                raise ValueError(f"Invalid port: {port}")
    
    def update_ips(self, timeout: float = 5.0) -> bool:
        """Update IP cache with enhanced error handling and timeout"""
        if not self.domains or not self.enabled:
            return True
            
        updated: Set[str] = set()
        success = True
        
        for domain in self.domains:
            try:
                # Use socket.getaddrinfo with timeout
                socket.setdefaulttimeout(timeout)
                infos = socket.getaddrinfo(domain, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                
                for info in infos:
                    ip = info[4][0]
                    # Validate IP address
                    try:
                        ipaddress.ip_address(ip)
                        updated.add(ip)
                    except ValueError:
                        logger.warning(f"Invalid IP address from DNS: {ip} for domain {domain}")
                        continue
                        
            except socket.gaierror as e:
                logger.warning(f"DNS resolution failed for {domain}: {e}")
                self._dns_failures += 1
                success = False
            except Exception as e:
                logger.error(f"Unexpected error resolving {domain}: {e}")
                self._dns_failures += 1
                success = False
            finally:
                socket.setdefaulttimeout(None)
        
        if updated or not self.domains:
            self._ip_cache = updated
            self._last_dns_update = time.time()
            logger.debug(f"Updated IPs for rule {self.description}: {updated}")
        
        return success
    
    def matches(self, dst_ip: str, dst_port: int) -> bool:
        """Check if destination matches this rule"""
        if not self.enabled:
            return False
        if dst_port not in self.ports:
            return False
        if self.domains is None:
            return True
        return dst_ip in self._ip_cache
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about this rule's cache"""
        return {
            "cached_ips": len(self._ip_cache),
            "ips": list(self._ip_cache),
            "last_update": self._last_dns_update,
            "dns_failures": self._dns_failures,
            "enabled": self.enabled
        }

class FilterValidator:
    """Validates WinDivert filter strings to prevent [WinError 87] parameter errors"""
    
    # Valid WinDivert filter syntax patterns
    VALID_OPERATORS = {'==', '!=', '<', '>', '<=', '>='}
    VALID_FIELDS = {
        'ip.SrcAddr', 'ip.DstAddr', 'ip.Length', 'ip.TOS', 'ip.TTL', 'ip.Id', 'ip.Checksum',
        'tcp.SrcPort', 'tcp.DstPort', 'tcp.SeqNum', 'tcp.AckNum', 'tcp.Window', 'tcp.Checksum',
        'udp.SrcPort', 'udp.DstPort', 'udp.Length', 'udp.Checksum',
        'outbound', 'inbound', 'loopback'
    }
    
    @staticmethod
    def validate_ip_address(ip: str) -> bool:
        """Validate IP address format"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_port(port: int) -> bool:
        """Validate port number"""
        return 1 <= port <= 65535
    
    @staticmethod
    def validate_filter_syntax(filter_str: str) -> Tuple[bool, Optional[str]]:
        """Validate WinDivert filter syntax"""
        if not filter_str or not filter_str.strip():
            return False, "Empty filter string"
        
        try:
            # Basic syntax checks
            if filter_str.count('(') != filter_str.count(')'):
                return False, "Unmatched parentheses"
            
            # Check for common invalid patterns that cause [WinError 87]
            invalid_patterns = [
                r'ip\.(?:Src|Dst)Addr\s*==\s*0\.0\.0\.0',  # Invalid IP
                r'tcp\.(?:Src|Dst)Port\s*==\s*0\b',        # Port 0
                r'\bor\s*or\b',                             # Double operators
                r'\band\s*and\b',                           # Double operators
                r'\(\s*\)',                                 # Empty parentheses
            ]
            
            for pattern in invalid_patterns:
                if re.search(pattern, filter_str, re.IGNORECASE):
                    return False, f"Invalid pattern detected: {pattern}"
            
            # Check for valid structure
            if not any(field in filter_str for field in FilterValidator.VALID_FIELDS):
                return False, "No valid filter fields found"
            
            return True, None
            
        except Exception as e:
            return False, f"Filter validation error: {e}"

class EnhancedTransparentRedirector:
    """Production-ready transparent redirector with comprehensive error handling"""
    
    def __init__(
        self,
        rules: List[EnhancedRedirectRule],
        debug: bool = False,
        max_packet_buffer: int = 65535,
        dns_refresh_interval: float = 300.0,  # 5 minutes
        performance_monitoring: bool = True,
        queue_length: int = 8192
    ):
        self.rules = rules
        self.debug = debug
        self.max_packet_buffer = max_packet_buffer
        self.dns_refresh_interval = dns_refresh_interval
        self.performance_monitoring = performance_monitoring
        self.queue_length = queue_length
        
        # Threading and control
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status = RedirectStatus.STOPPED
        self._status_lock = threading.Lock()
        
        # NAT mapping: (src_ip, src_port, dst_ip, dst_port) -> (to_ip, to_port, rule)
        self._nat_map: Dict[Tuple[str, int, str, int], Tuple[str, int, EnhancedRedirectRule]] = {}
        self._nat_lock = threading.Lock()
        
        # Performance tracking
        self.metrics = PerformanceMetrics() if performance_monitoring else None
        
        # Filter management
        self._current_filter = ""
        self._last_dns_refresh = 0.0
        self._filter_validator = FilterValidator()
        
        # Error tracking
        self._error_count = 0
        self._last_error: Optional[Exception] = None
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5
        
        # Initialize DNS resolution
        self._initialize_dns_cache()
        
        logger.info(f"Enhanced Transparent Redirector initialized with {len(rules)} rules")
    
    def _initialize_dns_cache(self):
        """Initialize DNS cache for all rules"""
        logger.info("Initializing DNS cache...")
        successful_rules = 0
        
        for rule in self.rules:
            try:
                if rule.update_ips(timeout=10.0):
                    successful_rules += 1
            except Exception as e:
                logger.error(f"Failed to initialize DNS for rule {rule.description}: {e}")
        
        logger.info(f"DNS cache initialized for {successful_rules}/{len(self.rules)} rules")
    
    def get_status(self) -> RedirectStatus:
        """Get current redirector status"""
        with self._status_lock:
            return self._status
    
    def _set_status(self, status: RedirectStatus):
        """Set redirector status thread-safely"""
        with self._status_lock:
            old_status = self._status
            self._status = status
            if old_status != status:
                logger.info(f"Status changed: {old_status.value} -> {status.value}")
    
    def _build_enhanced_filter(self) -> str:
        """Build WinDivert filter with comprehensive validation and error handling"""
        try:
            ports = set()
            ips: Set[str] = set()
            
            # Collect all ports and IPs from enabled rules
            active_rules = [r for r in self.rules if r.enabled]
            if not active_rules:
                logger.warning("No active rules found")
                return "false"  # WinDivert filter that matches nothing
            
            for rule in active_rules:
                ports.update(rule.ports)
                ips.update(rule._ip_cache)
            
            # Build port filter
            if not ports:
                logger.warning("No ports defined in active rules")
                return "false"
            
            valid_ports = [p for p in ports if self._filter_validator.validate_port(p)]
            if not valid_ports:
                logger.error("No valid ports found")
                return "false"
            
            port_conditions = [f"tcp.DstPort == {p}" for p in sorted(valid_ports)]
            port_filter = " or ".join(port_conditions)
            
            # Build IP filter
            if ips:
                valid_ips = [ip for ip in ips if self._filter_validator.validate_ip_address(ip)]
                if valid_ips:
                    ip_conditions = [f"ip.DstAddr == {ip}" for ip in sorted(valid_ips)]
                    ip_filter = " or ".join(ip_conditions)
                    outbound_filter = f"(outbound and tcp and ip and ({port_filter}) and ({ip_filter}))"
                else:
                    logger.warning("No valid IPs found, using port-only filter")
                    outbound_filter = f"(outbound and tcp and ip and ({port_filter}))"
            else:
                logger.info("No domain-specific IPs, using port-only filter")
                outbound_filter = f"(outbound and tcp and ip and ({port_filter}))"
            
            # Build inbound filter for proxy responses
            to_ports = sorted({r.to_port for r in active_rules if r.enabled})
            if to_ports:
                valid_to_ports = [p for p in to_ports if self._filter_validator.validate_port(p)]
                if valid_to_ports:
                    src_port_conditions = [f"tcp.SrcPort == {p}" for p in valid_to_ports]
                    src_port_filter = " or ".join(src_port_conditions)
                    inbound_filter = (
                        f"((inbound and tcp and ip and ip.SrcAddr == 127.0.0.1 and ({src_port_filter})) or "
                        f"(loopback and tcp and ip and ({src_port_filter})))"
                    )
                else:
                    logger.error("No valid to_ports found")
                    inbound_filter = "false"
            else:
                logger.warning("No to_ports defined")
                inbound_filter = "false"
            
            # Combine filters
            final_filter = f"{outbound_filter} or {inbound_filter}"
            
            # Validate final filter
            is_valid, error_msg = self._filter_validator.validate_filter_syntax(final_filter)
            if not is_valid:
                logger.error(f"Filter validation failed: {error_msg}")
                logger.error(f"Invalid filter: {final_filter}")
                return "false"
            
            if self.metrics:
                self.metrics.filter_rebuilds += 1
            
            logger.info(f"Built filter: {final_filter[:200]}{'...' if len(final_filter) > 200 else ''}")
            return final_filter
            
        except Exception as e:
            logger.error(f"Filter construction failed: {e}")
            logger.error(traceback.format_exc())
            return "false"
    
    def start(self) -> bool:
        """Start the transparent redirector with enhanced error handling"""
        if not WINDIVERT_AVAILABLE:
            logger.error("WinDivert not available - cannot start redirector")
            return False
        
        if self._thread and self._thread.is_alive():
            logger.warning("Redirector already running")
            return True
        
        try:
            self._set_status(RedirectStatus.STARTING)
            self._stop_event.clear()
            self._error_count = 0
            self._consecutive_errors = 0
            
            # Build and validate filter
            self._current_filter = self._build_enhanced_filter()
            if self._current_filter == "false":
                logger.error("Cannot start with invalid filter")
                self._set_status(RedirectStatus.ERROR)
                return False
            
            # Start worker thread
            self._thread = threading.Thread(
                target=self._run_with_recovery,
                name="EnhancedWinDivertRedirect",
                daemon=True
            )
            self._thread.start()
            
            # Wait for successful startup
            start_timeout = 10.0
            start_time = time.time()
            while time.time() - start_time < start_timeout:
                if self.get_status() == RedirectStatus.RUNNING:
                    logger.info("Enhanced Transparent Redirector started successfully")
                    return True
                elif self.get_status() == RedirectStatus.ERROR:
                    logger.error("Failed to start redirector")
                    return False
                time.sleep(0.1)
            
            logger.error("Startup timeout - redirector may not be running correctly")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start redirector: {e}")
            logger.error(traceback.format_exc())
            self._set_status(RedirectStatus.ERROR)
            return False
    
    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the redirector gracefully"""
        if self.get_status() == RedirectStatus.STOPPED:
            return True
        
        try:
            self._set_status(RedirectStatus.STOPPING)
            self._stop_event.set()
            
            if self._thread:
                self._thread.join(timeout=timeout)
                if self._thread.is_alive():
                    logger.warning(f"Thread did not stop within {timeout}s timeout")
                    return False
            
            self._thread = None
            self._set_status(RedirectStatus.STOPPED)
            logger.info("Enhanced Transparent Redirector stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping redirector: {e}")
            return False
    
    def _run_with_recovery(self):
        """Main run loop with automatic recovery"""
        while not self._stop_event.is_set():
            try:
                self._run_windivert_loop()
                break  # Normal exit
            except Exception as e:
                self._consecutive_errors += 1
                self._error_count += 1
                self._last_error = e
                
                logger.error(f"WinDivert loop error #{self._consecutive_errors}: {e}")
                logger.error(traceback.format_exc())
                
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({self._consecutive_errors}), stopping")
                    self._set_status(RedirectStatus.ERROR)
                    break
                
                # Exponential backoff for recovery
                sleep_time = min(2 ** self._consecutive_errors, 30)
                logger.info(f"Attempting recovery in {sleep_time}s...")
                if self._stop_event.wait(sleep_time):
                    break  # Stop requested during sleep
        
        self._set_status(RedirectStatus.STOPPED)
    
    def _run_windivert_loop(self):
        """Main WinDivert packet processing loop with enhanced error handling"""
        windivert_params = {
            'layer': 'NETWORK',
            'priority': 1000,
            'flags': 0
        }
        
        # Add queue length if supported
        try:
            with WinDivert(self._current_filter, **windivert_params) as w:
                logger.info("WinDivert handle opened successfully")
                self._set_status(RedirectStatus.RUNNING)
                self._consecutive_errors = 0  # Reset error counter on successful start
                
                while not self._stop_event.is_set():
                    try:
                        # Receive packet with timeout
                        packet: Packet = w.recv()
                        if self.metrics:
                            self.metrics.packets_processed += 1
                        
                        # Periodic maintenance
                        self._perform_maintenance()
                        
                        # Process packet
                        try:
                            if self._process_packet_enhanced(packet):
                                if self.metrics:
                                    self.metrics.packets_redirected += 1
                        except Exception as packet_error:
                            logger.debug(f"Packet processing error: {packet_error}")
                            if self.metrics:
                                self.metrics.packets_errors += 1
                        
                        # Send packet (modified or original)
                        try:
                            w.send(packet)
                        except Exception as send_error:
                            logger.debug(f"Packet send error: {send_error}")
                            if self.metrics:
                                self.metrics.packets_errors += 1
                                
                    except Exception as recv_error:
                        if not self._stop_event.is_set():
                            logger.debug(f"Packet receive error: {recv_error}")
                        continue
                        
        except OSError as e:
            if e.winerror == 87:  # The parameter is incorrect
                logger.error("WinDivert parameter error [87] - invalid filter or parameters")
                logger.error(f"Filter: {self._current_filter}")
                logger.error("Common causes:")
                logger.error("1. Invalid IP addresses in filter (e.g., 0.0.0.0)")
                logger.error("2. Invalid port numbers (e.g., 0)")
                logger.error("3. Malformed filter syntax")
                logger.error("4. Insufficient privileges")
                raise WinDivertError(f"Invalid filter parameters: {e}", 87, self._current_filter)
            elif e.winerror == 5:  # Access denied
                logger.error("WinDivert access denied [5] - insufficient privileges")
                logger.error("Solution: Run as Administrator")
                raise WinDivertError(f"Access denied: {e}", 5, self._current_filter)
            elif e.winerror == 2:  # System cannot find the file specified
                logger.error("WinDivert driver not found [2] - driver installation issue")
                logger.error("Solution: Reinstall pydivert or WinDivert")
                raise WinDivertError(f"Driver not found: {e}", 2, self._current_filter)
            else:
                logger.error(f"WinDivert error [{e.winerror}]: {e}")
                raise WinDivertError(f"WinDivert error: {e}", e.winerror, self._current_filter)
        except Exception as e:
            logger.error(f"Unexpected WinDivert error: {e}")
            raise
    
    def _perform_maintenance(self):
        """Periodic maintenance tasks"""
        now = time.time()
        
        # DNS refresh
        if now - self._last_dns_refresh > self.dns_refresh_interval:
            self._refresh_dns_cache()
            self._last_dns_refresh = now
        
        # NAT table cleanup (remove old entries)
        if len(self._nat_map) > 10000:  # Prevent memory bloat
            self._cleanup_nat_table()
    
    def _refresh_dns_cache(self):
        """Refresh DNS cache for all rules"""
        logger.debug("Refreshing DNS cache...")
        successful = 0
        
        # Use thread pool for parallel DNS resolution
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_rule = {executor.submit(rule.update_ips, 3.0): rule for rule in self.rules}
            
            for future in concurrent.futures.as_completed(future_to_rule):
                rule = future_to_rule[future]
                try:
                    if future.result():
                        successful += 1
                        if self.metrics:
                            self.metrics.dns_resolutions += 1
                except Exception as e:
                    logger.warning(f"DNS refresh failed for rule {rule.description}: {e}")
                    if self.metrics:
                        self.metrics.dns_failures += 1
        
        logger.debug(f"DNS cache refreshed for {successful}/{len(self.rules)} rules")
        
        # Rebuild filter if DNS results changed
        new_filter = self._build_enhanced_filter()
        if new_filter != self._current_filter:
            logger.info("Filter needs updating due to DNS changes - restart required")
    
    def _cleanup_nat_table(self):
        """Clean up old NAT table entries"""
        with self._nat_lock:
            # Simple cleanup - in production, you might want TTL-based cleanup
            if len(self._nat_map) > 5000:
                # Keep only the most recent half
                items = list(self._nat_map.items())
                self._nat_map = dict(items[-5000:])
                logger.info(f"NAT table cleaned up, {len(self._nat_map)} entries remaining")
    
    def _process_packet_enhanced(self, packet: Packet) -> bool:
        """Enhanced packet processing with detailed logging"""
        if not packet.tcp or not packet.ip:
            return False
        
        src_ip = packet.src_addr
        dst_ip = packet.dst_addr
        src_port = packet.tcp.src_port
        dst_port = packet.tcp.dst_port
        
        if packet.is_outbound:
            return self._process_outbound_packet(packet, src_ip, src_port, dst_ip, dst_port)
        else:
            return self._process_inbound_packet(packet, src_ip, src_port, dst_ip, dst_port)
    
    def _process_outbound_packet(self, packet: Packet, src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> bool:
        """Process outbound packet (client -> server)"""
        # Find matching rule
        matching_rule = None
        for rule in self.rules:
            if rule.matches(dst_ip, dst_port):
                matching_rule = rule
                break
        
        if not matching_rule:
            return False  # No redirect needed
        
        # Create NAT mapping
        nat_key = (src_ip, src_port, dst_ip, dst_port)
        with self._nat_lock:
            self._nat_map[nat_key] = ("127.0.0.1", matching_rule.to_port, matching_rule)
        
        # Modify packet
        packet.dst_addr = "127.0.0.1"
        packet.tcp.dst_port = matching_rule.to_port
        packet.ip.ttl = max(32, packet.ip.ttl or 64)
        packet.recalculate_checksums()
        
        if self.debug:
            logger.debug(f"OUT redirect {src_ip}:{src_port} -> 127.0.0.1:{matching_rule.to_port} (orig {dst_ip}:{dst_port})")
        
        return True
    
    def _process_inbound_packet(self, packet: Packet, src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> bool:
        """Process inbound packet (proxy -> client)"""
        if src_ip != "127.0.0.1":
            return False
        
        # Find reverse NAT mapping
        with self._nat_lock:
            for (orig_src_ip, orig_src_port, orig_dst_ip, orig_dst_port), (_, to_port, _) in self._nat_map.items():
                if to_port == src_port and dst_ip == orig_src_ip and dst_port == orig_src_port:
                    # Rewrite source to appear as original destination
                    packet.src_addr = orig_dst_ip
                    packet.tcp.src_port = orig_dst_port
                    packet.recalculate_checksums()
                    
                    if self.debug:
                        logger.debug(f"IN rewrite 127.0.0.1:{src_port} -> {orig_dst_ip}:{orig_dst_port}")
                    
                    return True
        
        if self.debug:
            logger.debug(f"IN no-mapping for 127.0.0.1:{src_port} -> {dst_ip}:{dst_port}")
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        stats = {
            "status": self.get_status().value,
            "rules": len(self.rules),
            "active_rules": len([r for r in self.rules if r.enabled]),
            "nat_entries": len(self._nat_map),
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "last_error": str(self._last_error) if self._last_error else None,
            "current_filter": self._current_filter[:200] + "..." if len(self._current_filter) > 200 else self._current_filter
        }
        
        if self.metrics:
            stats.update({
                "performance": {
                    "runtime_seconds": self.metrics.get_runtime_seconds(),
                    "packets_processed": self.metrics.packets_processed,
                    "packets_redirected": self.metrics.packets_redirected,
                    "packets_errors": self.metrics.packets_errors,
                    "packets_per_second": self.metrics.get_packets_per_second(),
                    "dns_resolutions": self.metrics.dns_resolutions,
                    "dns_failures": self.metrics.dns_failures,
                    "filter_rebuilds": self.metrics.filter_rebuilds
                }
            })
        
        # Rule-specific stats
        rule_stats = []
        for i, rule in enumerate(self.rules):
            rule_stats.append({
                "index": i,
                "description": rule.description,
                "ports": rule.ports,
                "to_port": rule.to_port,
                "domains": rule.domains,
                "enabled": rule.enabled,
                "cache": rule.get_cache_stats()
            })
        stats["rule_details"] = rule_stats
        
        return stats
    
    def update_rules(self, new_rules: List[EnhancedRedirectRule]) -> bool:
        """Update rules with automatic restart"""
        logger.info(f"Updating rules: {len(new_rules)} new rules")
        
        was_running = self.get_status() == RedirectStatus.RUNNING
        
        if was_running:
            if not self.stop(timeout=10.0):
                logger.error("Failed to stop redirector for rule update")
                return False
        
        self.rules = new_rules
        self._initialize_dns_cache()
        
        if was_running:
            return self.start()
        
        return True
    
    def export_config(self, filename: str):
        """Export configuration to JSON file"""
        config = {
            "rules": [
                {
                    "ports": rule.ports,
                    "to_port": rule.to_port,
                    "domains": rule.domains,
                    "description": rule.description,
                    "enabled": rule.enabled
                }
                for rule in self.rules
            ],
            "settings": {
                "debug": self.debug,
                "max_packet_buffer": self.max_packet_buffer,
                "dns_refresh_interval": self.dns_refresh_interval,
                "performance_monitoring": self.performance_monitoring,
                "queue_length": self.queue_length
            }
        }
        
        Path(filename).write_text(json.dumps(config, indent=2))
        logger.info(f"Configuration exported to {filename}")
    
    @classmethod
    def import_config(cls, filename: str) -> 'EnhancedTransparentRedirector':
        """Import configuration from JSON file"""
        config = json.loads(Path(filename).read_text())
        
        rules = [
            EnhancedRedirectRule(
                ports=rule_data["ports"],
                to_port=rule_data["to_port"],
                domains=rule_data.get("domains"),
                description=rule_data.get("description", ""),
                enabled=rule_data.get("enabled", True)
            )
            for rule_data in config["rules"]
        ]
        
        settings = config.get("settings", {})
        return cls(rules=rules, **settings)

# Usage example and testing
if __name__ == "__main__":
    # Example Blue Archive rules
    blue_archive_rules = [
        EnhancedRedirectRule(
            ports=[443],
            to_port=9443,
            domains=[
                "nxm-tw-bagl.nexon.com",
                "d2vaidpni345rp.cloudfront.net",
                "ba.dn.nexoncdn.co.kr"
            ],
            description="Blue Archive HTTPS Traffic"
        ),
        EnhancedRedirectRule(
            ports=[80],
            to_port=9080,
            domains=[
                "public.api.nexon.com",
                "x-update.ngs.nexon.com"
            ],
            description="Blue Archive HTTP Traffic"
        )
    ]
    
    # Create enhanced redirector
    redirector = EnhancedTransparentRedirector(
        rules=blue_archive_rules,
        debug=True,
        performance_monitoring=True
    )
    
    # Start redirector
    if redirector.start():
        logger.info("Redirector started successfully!")
        
        try:
            # Monitor for a few seconds
            time.sleep(10)
            
            # Print statistics
            stats = redirector.get_stats()
            logger.info(f"Statistics: {json.dumps(stats, indent=2)}")
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            redirector.stop()
    else:
        logger.error("Failed to start redirector")