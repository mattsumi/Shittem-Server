#!/usr/bin/env python3
"""
Test WinDivert filter generation without modifying main code
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

try:
    from transparent_redirect_win import TransparentRedirector, RedirectRule
    from pydivert import WinDivert
    print("✓ Imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

def test_basic_windivert():
    """Test basic WinDivert functionality"""
    print("\n=== Testing Basic WinDivert ===")
    try:
        # Try simplest possible filter
        with WinDivert("tcp.DstPort == 65536") as w:
            print("✓ Basic WinDivert works")
    except Exception as e:
        print(f"✗ Basic WinDivert failed: {e}")
        return False
    return True

def test_dns_resolution():
    """Test DNS resolution for Blue Archive domain"""
    print("\n=== Testing DNS Resolution ===")
    rule = RedirectRule(
        ports=[5000, 5100],
        to_port=9443,
        domains=["nxm-eu-bagl.nexon.com"]
    )
    
    print(f"Before update_ips(): {rule._ip_cache}")
    rule.update_ips()
    print(f"After update_ips(): {rule._ip_cache}")
    
    if rule._ip_cache:
        print(f"✓ DNS resolved {len(rule._ip_cache)} IPs")
        for ip in rule._ip_cache:
            print(f"  - {ip}")
        return True
    else:
        print("✗ DNS resolution failed")
        return False

def test_filter_generation():
    """Test the actual filter generation"""
    print("\n=== Testing Filter Generation ===")
    
    # Create the exact same rule as in your main code
    gateway_rule = RedirectRule(
        ports=[5000, 5100],
        to_port=9443,
        domains=["nxm-eu-bagl.nexon.com"]
    )
    
    gateway_rule.update_ips()
    rules = [gateway_rule]
    
    redirector = TransparentRedirector(rules=[], debug=True)
    redirector.rules = rules
    
    try:
        filter_str = redirector._build_filter()
        print(f"✓ Filter generated successfully")
        print(f"Filter: {filter_str}")
        print(f"Length: {len(filter_str)} characters")
        
        if len(filter_str) > 1024:
            print(f"⚠ Warning: Filter exceeds 1024 character limit")
            
        return filter_str
    except Exception as e:
        print(f"✗ Filter generation failed: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def test_windivert_with_filter(filter_str):
    """Test WinDivert with the actual generated filter"""
    print("\n=== Testing WinDivert with Generated Filter ===")
    try:
        with WinDivert(filter_str) as w:
            print("✓ WinDivert accepts the filter")
            return True
    except Exception as e:
        print(f"✗ WinDivert rejected filter: {e}")
        print(f"Filter was: {filter_str}")
        return False

def main():
    print("WinDivert Filter Test for Blue Archive")
    print("="*50)
    
    # Test basic functionality first
    if not test_basic_windivert():
        print("\n❌ Basic WinDivert test failed - check admin rights")
        return 1
    
    # Test DNS resolution
    if not test_dns_resolution():
        print("\n❌ DNS resolution failed")
        return 1
    
    # Test filter generation
    filter_str = test_filter_generation()
    if not filter_str:
        print("\n❌ Filter generation failed")
        return 1
    
    # Test WinDivert with the filter
    if not test_windivert_with_filter(filter_str):
        print("\n❌ WinDivert rejected the generated filter")
        return 1
    
    print("\n✅ All tests passed! The issue is elsewhere.")
    return 0

if __name__ == "__main__":
    sys.exit(main())