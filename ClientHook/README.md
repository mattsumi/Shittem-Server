# BAUnpin Enhanced Edition - Blue Archive Certificate Bypass

## Overview

BAUnpin Enhanced Edition is a comprehensive DLL injection-based certificate validation bypass specifically designed for Blue Archive Steam version. This enhanced version addresses critical hook installation failures and implements proven patterns from the BA-Cheeto project.

## Key Features

- **Certificate Validation Bypass**: Hooks and bypasses Windows certificate validation APIs
- **Enhanced Error Handling**: Comprehensive diagnostics and status reporting  
- **Retry Logic**: 3-attempt hook installation with automatic recovery
- **BA-Cheeto Patterns**: Proven hooking techniques for reliable operation
- **Steam Compatibility**: Optimized for Blue Archive Steam version memory layout
- **Health Monitoring**: Background monitoring with periodic status checks
- **Detailed Logging**: Enhanced logging system with rotation and timestamps

## Architecture

### Core Components

1. **BAUnpin.dll** - Main certificate bypass DLL with enhanced hooking implementation
2. **BAUnpinInjector.exe** - Robust injector utility for DLL loading
3. **minhook.x64.dll** - MinHook library dependency for API hooking

### Hooked APIs

- `WinVerifyTrust` (wintrust.dll) - Forces ERROR_SUCCESS for all certificate validation
- `CertVerifyCertificateChainPolicy` (crypt32.dll) - Bypasses certificate chain policy checks  
- `CertGetCertificateChain` (crypt32.dll) - Ensures certificate chain operations succeed

## Usage

### Basic Usage

1. **Build the Project** (if needed):
   ```powershell
   cd ClientHook
   mkdir build
   cd build
   cmake ..
   cmake --build . --config Release
   ```

2. **Run the Injector**:
   ```powershell
   cd ClientHook\build\bin\Release
   .\BAUnpinInjector.exe
   ```

3. **Launch Blue Archive**: The certificate bypass will be automatically active

### Advanced Configuration

#### Enable Debug Console
```powershell
set BAUNPIN_CONSOLE=1
.\BAUnpinInjector.exe
```

#### Monitor Logs
- Log file location: `%TEMP%\BAUnpin-Enhanced.log`
- Automatic rotation when file exceeds 2MB
- Timestamped entries with detailed status information

## Technical Details

### Critical Fixes Applied

#### 1. MinHook Double Initialization Bug (CRITICAL)
- **Problem**: Multiple calls to `MH_Initialize()` causing hook failures
- **Solution**: Atomic flag-based initialization tracking
- **Impact**: Resolves core hook installation failures

#### 2. Module Loading Strategy
- **Problem**: Using `GetModuleHandle()` for delay-loaded modules
- **Solution**: `LoadLibrary()` with 30-second timeout and progress reporting
- **Impact**: Ensures modules are available before hook installation

#### 3. Enhanced Error Diagnostics  
- **Problem**: Limited error reporting hindered debugging
- **Solution**: Comprehensive MinHook status code translation
- **Impact**: Detailed error information for troubleshooting

### Hook Installation Process

1. **Initialization**: MinHook library initialization with atomic tracking
2. **Module Loading**: Ensure target DLLs (wintrust.dll, crypt32.dll) are loaded
3. **Function Resolution**: Get addresses of target certificate validation functions
4. **Hook Creation**: Create MinHook detours for each target function
5. **Hook Activation**: Enable hooks with comprehensive error handling
6. **Retry Logic**: Up to 3 attempts with 1-second delays between failures

### Memory Layout Compatibility

- **Process Stabilization**: 2-second wait for Blue Archive initialization
- **Module Timing**: Handles delay-loaded DLLs common in Steam versions
- **Address Resolution**: Robust function address lookup with error checking
- **Thread Safety**: Mutex-protected logging and atomic state management

## Monitoring & Diagnostics

### Log Analysis

The enhanced logging system provides detailed operational information:

```
[20:44:32.123] [BAUnpin-Enhanced] === BAUnpin Enhanced v2.1 - Blue Archive Certificate Bypass ===
[20:44:32.125] [BAUnpin-Enhanced] OS Version: 10.0 Build 22621
[20:44:34.150] [BAUnpin-Enhanced] Target modules are now loaded and available!
[20:44:34.152] [BAUnpin-Enhanced] Initializing MinHook...
[20:44:34.155] [BAUnpin-Enhanced] MinHook initialized successfully
[20:44:34.158] [BAUnpin-Enhanced] SUCCESS: Hook installed for wintrust.dll::WinVerifyTrust
[20:44:34.161] [BAUnpin-Enhanced] SUCCESS: Hook installed for crypt32.dll::CertVerifyCertificateChainPolicy
[20:44:34.164] [BAUnpin-Enhanced] SUCCESS: Hook installed for crypt32.dll::CertGetCertificateChain
[20:44:34.166] [BAUnpin-Enhanced] Hook installation complete! 3/3 hooks active
[20:44:34.168] [BAUnpin-Enhanced] Certificate validation bypass is now ACTIVE for Blue Archive
```

### Health Monitoring

- **Background Thread**: Monitors hook status every 60 seconds
- **Periodic Reports**: Health check status every 5 minutes
- **State Tracking**: Monitors `g_initialized` and `g_minhook_initialized` flags
- **Graceful Shutdown**: Clean hook removal and resource cleanup

### Error Recovery

- **Automatic Retries**: 3-attempt hook installation with progressive delays
- **Fallback Handling**: Graceful degradation if some hooks fail
- **Status Reporting**: Clear indication of partial vs. complete hook installation
- **Recovery Mechanisms**: MinHook state management and error handling

## Build Requirements

### Dependencies
- CMake 3.15+
- Visual Studio 2019+ or compatible C++ compiler
- Windows SDK 10.0+
- MinHook library (automatically handled by CMake)

### CMake Configuration
```cmake
# Key linking dependencies
target_link_libraries(BAUnpin PRIVATE minhook wintrust crypt32 shlwapi)
```

## Troubleshooting

### Common Issues

1. **Hook Installation Failures**
   - Check log file for MinHook error codes
   - Verify target process has loaded certificate validation modules
   - Ensure proper administrator privileges for injection

2. **Module Loading Timeouts**
   - Increase stabilization wait time if needed
   - Check if Blue Archive is using non-standard DLL loading patterns
   - Monitor log for module availability messages

3. **Certificate Validation Still Active**
   - Verify all 3 hooks are successfully installed
   - Check if additional certificate APIs are being used
   - Monitor hook invocation logs during certificate operations

### Debug Information

Enable detailed debugging:
```powershell
set BAUNPIN_CONSOLE=1
set BAUNPIN_DEBUG=1  # Future enhancement
```

### Log Locations
- Primary: `%TEMP%\BAUnpin-Enhanced.log`
- Backup: `%TEMP%\BAUnpin-Enhanced.log.old` (after rotation)
- Debug: Windows Debug Output (visible in debuggers)

## Security Considerations

⚠️ **Important**: This tool bypasses certificate validation for Blue Archive. Use responsibly:

- Only use with legitimate Blue Archive installations
- Do not use on systems requiring certificate validation for security
- Be aware that certificate bypassing may trigger anti-virus software
- This tool is for educational and compatibility purposes only

## Version History

- **v2.1**: Enhanced Edition with BA-Cheeto patterns and comprehensive fixes
- **v2.0**: MinHook double initialization bug fix and improved error handling  
- **v1.x**: Original implementation with basic certificate bypass functionality

## Technical Support

For technical issues:
1. Check the comprehensive log file for detailed error information
2. Review the CHANGELOG.md for known issues and fixes
3. Verify build requirements and dependencies are met
4. Test with debug console enabled for real-time diagnostics

## License

This project is provided as-is for educational and compatibility purposes. Users are responsible for compliance with all applicable laws and terms of service.
