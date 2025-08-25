# BAUnpin Enhanced Edition - Testing Guide

## Pre-Testing Checklist

### Requirements Verification
- ✅ **Build Status**: BAUnpin.dll and BAUnpinInjector.exe compiled successfully
- ✅ **Dependencies**: minhook.x64.dll present in output directory
- ✅ **Blue Archive**: Steam version installed and accessible
- ✅ **Permissions**: Administrator privileges for DLL injection
- ✅ **Antivirus**: Temporary exclusion for ClientHook directory (if needed)

### Testing Environment Setup

1. **Navigate to Build Directory**:
   ```powershell
   cd ClientHook\build\bin\Release
   ```

2. **Verify Files Present**:
   ```powershell
   ls
   # Should show: BAUnpin.dll, BAUnpinInjector.exe, minhook.x64.dll
   ```

3. **Enable Enhanced Logging** (Recommended):
   ```powershell
   set BAUNPIN_CONSOLE=1
   ```

## Testing Protocol

### Phase 1: Injection Verification

1. **Launch Blue Archive** (but don't start playing yet)
   - Start Blue Archive Steam version
   - Wait for the main menu to appear
   - Keep the game running in the background

2. **Run Enhanced Injector**:
   ```powershell
   .\BAUnpinInjector.exe
   ```

3. **Expected Output**:
   ```
   [BAUnpin Enhanced Injector v2.1]
   Searching for Blue Archive process...
   Process found: BlueArchive.exe (PID: XXXX)
   Injecting BAUnpin.dll...
   DLL injected successfully!
   Certificate bypass is now active.
   ```

4. **Check Console Output** (if enabled):
   - Real-time initialization messages should appear
   - Look for "Certificate validation bypass is now ACTIVE"

### Phase 2: Log Analysis

1. **Locate Log File**:
   ```powershell
   notepad $env:TEMP\BAUnpin-Enhanced.log
   ```

2. **Verify Successful Initialization**:
   ```
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] === BAUnpin Enhanced v2.1 - Blue Archive Certificate Bypass ===
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] Target modules are now loaded and available!
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] MinHook initialized successfully
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] SUCCESS: Hook installed for wintrust.dll::WinVerifyTrust
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] SUCCESS: Hook installed for crypt32.dll::CertVerifyCertificateChainPolicy
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] SUCCESS: Hook installed for crypt32.dll::CertGetCertificateChain
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] Hook installation complete! 3/3 hooks active
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] Certificate validation bypass is now ACTIVE for Blue Archive
   ```

3. **Success Indicators**:
   - ✅ All 3 hooks installed successfully (3/3 hooks active)
   - ✅ MinHook initialization completed without errors
   - ✅ Background monitor started successfully
   - ✅ No critical errors or exceptions reported

### Phase 3: Certificate Bypass Verification

1. **Trigger Certificate Operations**:
   - In Blue Archive, perform actions that would normally trigger certificate validation:
     - Login to account
     - Download game updates
     - Connect to game servers
     - Access in-game store or purchases

2. **Monitor Hook Activity**:
   - Watch log file for certificate bypass messages:
   ```
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] WinVerifyTrust -> forcing ERROR_SUCCESS (certificate bypass active)
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] CertVerifyCertificateChainPolicy -> forcing TRUE (certificate bypass active)
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] CertGetCertificateChain -> forcing TRUE (certificate bypass active)
   ```

3. **Expected Behavior**:
   - ✅ Game continues to function normally without certificate errors
   - ✅ Network operations complete successfully
   - ✅ No certificate validation failures reported by the game

### Phase 4: Health Monitoring Verification

1. **Wait for Health Check** (5 minutes):
   ```
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] Health check #1: BAUnpin Enhanced running normally
   ```

2. **Verify Persistent Operation**:
   - Leave game running for 10-15 minutes
   - Confirm periodic health checks appear in logs
   - Ensure no unexpected crashes or errors

### Phase 5: Cleanup Testing

1. **Close Blue Archive**:
   - Exit the game normally
   - DLL should perform graceful cleanup

2. **Verify Clean Shutdown**:
   ```
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] BAUnpin Enhanced shutting down...
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] All hooks disabled successfully
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] MinHook uninitialized successfully
   [XX:XX:XX.XXX] [BAUnpin-Enhanced] Closing enhanced log file...
   ```

## Troubleshooting Test Issues

### Common Test Failures

#### 1. Injection Fails
**Symptoms**: "Failed to inject DLL" or "Process not found"
**Solutions**:
- Ensure Blue Archive is running
- Run injector as Administrator
- Check antivirus isn't blocking injection
- Verify process name matches (might be different than "BlueArchive.exe")

#### 2. Hook Installation Fails
**Symptoms**: Log shows "0/3 hooks active" or MinHook errors
**Solutions**:
- Check if another hooking software is interfering
- Restart Blue Archive and try again
- Enable debug console for real-time error information
- Verify Windows certificate modules are loaded

#### 3. No Certificate Bypass Activity
**Symptoms**: No certificate hook messages in logs during network operations
**Solutions**:
- Trigger more network-intensive game operations
- Check if game is using alternative certificate validation methods
- Verify hooks are properly installed and active
- Consider if game caches certificate validation results

#### 4. Game Crashes or Instability
**Symptoms**: Blue Archive crashes after injection
**Solutions**:
- Check for MinHook compatibility issues
- Review exception handling in hook functions
- Test with debug console to identify crash points
- Verify hook function signatures match Windows APIs

### Advanced Diagnostics

#### 1. Enable Maximum Logging
```powershell
set BAUNPIN_CONSOLE=1
set BAUNPIN_DEBUG=1  # Future enhancement
```

#### 2. Monitor Windows API Calls
- Use Process Monitor (ProcMon) to watch certificate-related file/registry access
- Use API Monitor to trace certificate validation function calls
- Compare behavior with and without BAUnpin active

#### 3. Verify Hook Addresses
- Use a debugger to verify hook installation addresses
- Check that hooked functions are being called by Blue Archive
- Ensure hook detour functions are executing correctly

## Test Results Documentation

### Success Criteria
- [ ] **Injection**: DLL successfully injected without errors
- [ ] **Initialization**: All 3 certificate hooks installed (3/3 active)
- [ ] **Functionality**: Game operates normally with certificate bypass active
- [ ] **Monitoring**: Health checks report normal operation
- [ ] **Certificate Bypass**: Hook activity visible during certificate operations
- [ ] **Stability**: No crashes or instability during extended testing
- [ ] **Cleanup**: Graceful shutdown when game exits

### Test Report Template
```
BAUnpin Enhanced Edition - Test Results
======================================
Date: [DATE]
Blue Archive Version: [VERSION]
Windows Version: [VERSION]
Test Duration: [DURATION]

Injection Results:
- Process Detection: [PASS/FAIL]
- DLL Injection: [PASS/FAIL]
- Initialization: [PASS/FAIL]

Hook Installation:
- WinVerifyTrust: [PASS/FAIL]
- CertVerifyCertificateChainPolicy: [PASS/FAIL]  
- CertGetCertificateChain: [PASS/FAIL]
- Total Hooks Active: [X/3]

Certificate Bypass Activity:
- Network Operations: [WORKING/FAILING]
- Certificate Hooks Triggered: [YES/NO]
- Game Functionality: [NORMAL/DEGRADED]

Stability:
- Test Duration: [MINUTES]
- Crashes: [COUNT]
- Health Checks: [PASS/FAIL]
- Clean Shutdown: [PASS/FAIL]

Additional Notes:
[Any specific observations or issues]
```

## Next Steps After Testing

### If Testing Succeeds
1. **Production Deployment**: BAUnpin Enhanced is ready for regular use
2. **User Documentation**: Share README.md and TESTING_GUIDE.md with users
3. **Monitoring**: Set up routine log monitoring for any issues
4. **Updates**: Monitor for Blue Archive updates that might affect certificate validation

### If Testing Reveals Issues
1. **Log Analysis**: Review detailed logs for specific error patterns
2. **Code Review**: Examine hook implementation for compatibility issues
3. **API Analysis**: Consider if Blue Archive is using additional certificate APIs
4. **Community Feedback**: Gather user reports for common issues

The comprehensive fixes applied should resolve the original hook installation failures and provide reliable certificate validation bypass for Blue Archive Steam version.