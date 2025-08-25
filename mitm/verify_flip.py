#!/usr/bin/env python3
"""
Blue Archive MITM Proxy Verification Script

Tests the flip/unflip functionality by making requests through the proxy
and verifying that the X-Proxy-Upstream header correctly indicates which
upstream handled each request.
"""

import json
import ssl
import sys
import urllib.request
from urllib.error import HTTPError, URLError


# Configuration
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 9443
CONTROL_PORT = 9080

# Test URL - using a simple BA domain
TEST_URL = "https://public.api.nexon.com/"


def make_request_via_proxy() -> tuple[int, dict, str]:
    """
    Make a request via the proxy and return status, headers, and upstream info.
    Returns: (status_code, headers, upstream)
    """
    # Configure proxy
    proxy_handler = urllib.request.ProxyHandler({
        "http": f"http://{PROXY_HOST}:{PROXY_PORT}",
        "https": f"http://{PROXY_HOST}:{PROXY_PORT}",
    })
    
    opener = urllib.request.build_opener(proxy_handler)
    
    # Create unverified SSL context (mitmproxy resigns certificates)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    try:
        request = urllib.request.Request(TEST_URL)
        with opener.open(request, context=context, timeout=10) as response:
            status = response.getcode()
            headers = dict(response.headers)
            upstream = headers.get("X-Proxy-Upstream", "UNKNOWN")
            return status, headers, upstream
    except (HTTPError, URLError, Exception) as e:
        raise RuntimeError(f"Request failed: {e}")


def control_request(endpoint: str) -> dict:
    """Make a request to the control API"""
    url = f"http://{PROXY_HOST}:{CONTROL_PORT}/_proxy/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data
    except Exception as e:
        raise RuntimeError(f"Control request to {endpoint} failed: {e}")


def main():
    """Main verification routine"""
    print("Blue Archive MITM Proxy Verification")
    print("=" * 50)
    print()
    
    results = {"pass": True, "tests": []}
    
    try:
        # Test 1: Ensure proxy is unflipped initially
        print("🔄 Setting proxy to unflipped state...")
        unflip_response = control_request("unflip")
        print(f"   Unflip response: {unflip_response}")
        
        if not unflip_response.get("flipped") == False:
            raise RuntimeError("Failed to unflip proxy")
        
        # Test 2: Make request while unflipped - should go to OFFICIAL
        print("\n📡 Making request while unflipped...")
        status1, headers1, upstream1 = make_request_via_proxy()
        print(f"   Status: {status1}")
        print(f"   Upstream: {upstream1}")
        
        test1_pass = upstream1 == "OFFICIAL"
        results["tests"].append({
            "name": "Unflipped request",
            "expected": "OFFICIAL", 
            "actual": upstream1,
            "pass": test1_pass
        })
        
        if not test1_pass:
            results["pass"] = False
            print(f"   ❌ FAIL: Expected OFFICIAL, got {upstream1}")
        else:
            print(f"   ✅ PASS: Request routed to {upstream1}")
        
        # Test 3: Flip the proxy
        print("\n🔄 Flipping proxy to private server...")
        flip_response = control_request("flip")
        print(f"   Flip response: {flip_response}")
        
        if not flip_response.get("flipped") == True:
            raise RuntimeError("Failed to flip proxy")
            
        # Test 4: Make request while flipped - should go to PRIVATE
        print("\n📡 Making request while flipped...")
        status2, headers2, upstream2 = make_request_via_proxy()
        print(f"   Status: {status2}")
        print(f"   Upstream: {upstream2}")
        
        test2_pass = upstream2 == "PRIVATE"
        results["tests"].append({
            "name": "Flipped request",
            "expected": "PRIVATE",
            "actual": upstream2, 
            "pass": test2_pass
        })
        
        if not test2_pass:
            results["pass"] = False
            print(f"   ❌ FAIL: Expected PRIVATE, got {upstream2}")
        else:
            print(f"   ✅ PASS: Request routed to {upstream2}")
        
        # Test 5: Get status to verify counters
        print("\n📊 Checking proxy status...")
        status_response = control_request("status")
        print(f"   Flipped: {status_response.get('flipped')}")
        print(f"   Total requests: {status_response.get('requests_total')}")
        print(f"   Private count: {status_response.get('private_count')}")
        print(f"   Official count: {status_response.get('official_count')}")
        
        # Cleanup: Unflip proxy
        print("\n🔄 Cleaning up (unflipping proxy)...")
        control_request("unflip")
        print("   Proxy unflipped")
        
    except Exception as e:
        results["pass"] = False
        results["error"] = str(e)
        print(f"\n❌ ERROR: {e}")
    
    # Print final results
    print("\n" + "=" * 50)
    print("VERIFICATION RESULTS")
    print("=" * 50)
    
    for test in results["tests"]:
        status = "✅ PASS" if test["pass"] else "❌ FAIL"
        print(f"{status} {test['name']}: {test['actual']} (expected {test['expected']})")
    
    if "error" in results:
        print(f"\n❌ FATAL ERROR: {results['error']}")
    
    overall_status = "✅ PASS" if results["pass"] else "❌ FAIL"
    print(f"\nOVERALL RESULT: {overall_status}")
    
    if results["pass"]:
        print("\n🎉 All tests passed! The flip functionality is working correctly.")
        print("   - Unflipped requests go to OFFICIAL upstream")
        print("   - Flipped requests go to PRIVATE upstream")
        print("   - Proxy status reflects the changes correctly")
    else:
        print("\n💥 One or more tests failed. Check the proxy configuration.")
    
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Verification cancelled by user")
        sys.exit(130)