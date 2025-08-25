#include <windows.h>
#include <wintrust.h>
#include <softpub.h>
#include <wincrypt.h>
#include <cstdio>
#include <string>
#include <shlwapi.h>
#include <thread>
#include <chrono>
#include <memory>
#include <vector>
#include <mutex>
#include <atomic>

#include "MinHook.h"

// Typedefs for targets
using PFN_WinVerifyTrust = LONG (WINAPI*)(HWND, GUID*, LPVOID);
using PFN_CertVerifyCertificateChainPolicy = BOOL (WINAPI*)(LPCSTR, PCCERT_CHAIN_CONTEXT, PCERT_CHAIN_POLICY_PARA, PCERT_CHAIN_POLICY_STATUS);
using PFN_CertGetCertificateChain = BOOL (WINAPI*)(HCERTCHAINENGINE, PCCERT_CONTEXT, LPFILETIME, HCERTSTORE, PCERT_CHAIN_PARA, DWORD, LPVOID, PCCERT_CHAIN_CONTEXT*);

static PFN_WinVerifyTrust s_WinVerifyTrust = nullptr;
static PFN_CertVerifyCertificateChainPolicy s_CertVerifyCertificateChainPolicy = nullptr;
static PFN_CertGetCertificateChain s_CertGetCertificateChain = nullptr;

static bool g_console = false;
static FILE* g_file = nullptr;
static std::atomic<bool> g_initialized = false;
static std::atomic<bool> g_shutdown = false;
static std::atomic<bool> g_minhook_initialized = false;
static std::mutex g_log_mutex;

static void SetupConsole() {
    if (AllocConsole()) {
        g_console = true;
        FILE* f;
        freopen_s(&f, "CONOUT$", "w", stdout);
        freopen_s(&f, "CONOUT$", "w", stderr);
        SetConsoleTitleW(L"BAUnpin Console - Enhanced");
        printf("[BAUnpin] Console attached - Enhanced Edition\n");
    }
}

static const char* GetMHStatusString(MH_STATUS status) {
    switch (status) {
        case MH_OK: return "MH_OK";
        case MH_ERROR_ALREADY_INITIALIZED: return "MH_ERROR_ALREADY_INITIALIZED";
        case MH_ERROR_NOT_INITIALIZED: return "MH_ERROR_NOT_INITIALIZED";
        case MH_ERROR_ALREADY_CREATED: return "MH_ERROR_ALREADY_CREATED";
        case MH_ERROR_NOT_CREATED: return "MH_ERROR_NOT_CREATED";
        case MH_ERROR_ENABLED: return "MH_ERROR_ENABLED";
        case MH_ERROR_DISABLED: return "MH_ERROR_DISABLED";
        case MH_ERROR_NOT_EXECUTABLE: return "MH_ERROR_NOT_EXECUTABLE";
        case MH_ERROR_UNSUPPORTED_FUNCTION: return "MH_ERROR_UNSUPPORTED_FUNCTION";
        case MH_ERROR_MEMORY_ALLOC: return "MH_ERROR_MEMORY_ALLOC";
        case MH_ERROR_MEMORY_PROTECT: return "MH_ERROR_MEMORY_PROTECT";
        case MH_ERROR_MODULE_NOT_FOUND: return "MH_ERROR_MODULE_NOT_FOUND";
        case MH_ERROR_FUNCTION_NOT_FOUND: return "MH_ERROR_FUNCTION_NOT_FOUND";
        default: return "MH_UNKNOWN_ERROR";
    }
}

static void Log(const char* msg) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    
    char timestamp[64];
    SYSTEMTIME st;
    GetSystemTime(&st);
    snprintf(timestamp, sizeof(timestamp), "[%02d:%02d:%02d.%03d] ",
             st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    
    char buf[1024];
    snprintf(buf, sizeof(buf), "%s[BAUnpin-Enhanced] %s\n", timestamp, msg);
    
    if (g_console) {
        printf("%s", buf);
        fflush(stdout);
    }
    if (g_file) {
        fwrite(buf, 1, strlen(buf), g_file);
        fflush(g_file);
    }
    OutputDebugStringA(buf);
}

static LONG WINAPI Hook_WinVerifyTrust(HWND hwnd, GUID* pgActionID, LPVOID pWVTData) {
    Log("WinVerifyTrust -> forcing ERROR_SUCCESS (certificate bypass active)");
    return ERROR_SUCCESS;
}

static BOOL WINAPI Hook_CertVerifyCertificateChainPolicy(LPCSTR pszPolicyOID, PCCERT_CHAIN_CONTEXT pChainContext,
    PCERT_CHAIN_POLICY_PARA pPolicyPara, PCERT_CHAIN_POLICY_STATUS pPolicyStatus) {
    if (pPolicyStatus) {
        pPolicyStatus->dwError = ERROR_SUCCESS;
        pPolicyStatus->lChainIndex = 0;
        pPolicyStatus->lElementIndex = 0;
        pPolicyStatus->pvExtraPolicyStatus = nullptr;
    }
    Log("CertVerifyCertificateChainPolicy -> forcing TRUE (certificate bypass active)");
    return TRUE;
}

static BOOL WINAPI Hook_CertGetCertificateChain(HCERTCHAINENGINE hChainEngine, PCCERT_CONTEXT pCertContext, LPFILETIME pTime,
    HCERTSTORE hAdditionalStore, PCERT_CHAIN_PARA pChainPara, DWORD dwFlags, LPVOID pvReserved, PCCERT_CHAIN_CONTEXT* ppChainContext) {
    Log("CertGetCertificateChain -> forcing TRUE (certificate bypass active)");
    
    // We need to return a valid chain context or some applications might crash
    // Call the original function but we'll still return TRUE regardless of result
    BOOL result = s_CertGetCertificateChain(hChainEngine, pCertContext, pTime, hAdditionalStore, pChainPara, dwFlags, pvReserved, ppChainContext);
    
    // Always return TRUE to bypass certificate validation
    return TRUE;
}

static bool EnsureModulesLoaded() {
    Log("Ensuring target modules are loaded...");
    
    const int max_attempts = 30; // 30 seconds
    for (int i = 0; i < max_attempts; ++i) {
        if (g_shutdown.load()) return false;
        
        // Try to load modules if not already loaded
        HMODULE hWintrust = LoadLibraryW(L"wintrust.dll");
        HMODULE hCrypt32 = LoadLibraryW(L"crypt32.dll");
        
        if (hWintrust && hCrypt32) {
            Log("Target modules are now loaded and available!");
            return true;
        }
        
        if (i % 5 == 0) {
            char progress[128];
            snprintf(progress, sizeof(progress), "Still waiting for modules... attempt %d/30", i + 1);
            Log(progress);
        }
        
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    }
    
    Log("WARNING: Timeout waiting for target modules, proceeding anyway");
    return true; // Continue even if modules aren't loaded yet
}

static bool InitializeMinHook() {
    if (g_minhook_initialized.load()) {
        Log("MinHook already initialized, skipping");
        return true;
    }
    
    Log("Initializing MinHook...");
    MH_STATUS status = MH_Initialize();
    
    if (status == MH_OK) {
        g_minhook_initialized.store(true);
        Log("MinHook initialized successfully");
        return true;
    } else if (status == MH_ERROR_ALREADY_INITIALIZED) {
        g_minhook_initialized.store(true);
        Log("MinHook was already initialized by another component");
        return true;
    } else {
        char error_msg[256];
        snprintf(error_msg, sizeof(error_msg), "MinHook initialization failed: %s", GetMHStatusString(status));
        Log(error_msg);
        return false;
    }
}

static bool CreateSingleHook(const char* module_name, const char* function_name, LPVOID target_func, LPVOID detour_func, LPVOID* original_func) {
    char log_msg[256];
    
    if (!target_func) {
        snprintf(log_msg, sizeof(log_msg), "WARNING: %s::%s not found - function may not be available", module_name, function_name);
        Log(log_msg);
        return false;
    }
    
    // Create hook
    MH_STATUS create_status = MH_CreateHook(target_func, detour_func, original_func);
    if (create_status != MH_OK && create_status != MH_ERROR_ALREADY_CREATED) {
        snprintf(log_msg, sizeof(log_msg), "FAILED to create hook for %s::%s - %s",
                module_name, function_name, GetMHStatusString(create_status));
        Log(log_msg);
        return false;
    }
    
    if (create_status == MH_ERROR_ALREADY_CREATED) {
        snprintf(log_msg, sizeof(log_msg), "Hook for %s::%s already exists, skipping creation", module_name, function_name);
        Log(log_msg);
    }
    
    // Enable hook
    MH_STATUS enable_status = MH_EnableHook(target_func);
    if (enable_status != MH_OK && enable_status != MH_ERROR_ENABLED) {
        snprintf(log_msg, sizeof(log_msg), "FAILED to enable hook for %s::%s - %s",
                module_name, function_name, GetMHStatusString(enable_status));
        Log(log_msg);
        return false;
    }
    
    if (enable_status == MH_ERROR_ENABLED) {
        snprintf(log_msg, sizeof(log_msg), "Hook for %s::%s already enabled", module_name, function_name);
        Log(log_msg);
    } else {
        snprintf(log_msg, sizeof(log_msg), "SUCCESS: Hook installed for %s::%s", module_name, function_name);
        Log(log_msg);
    }
    
    return true;
}

static bool InstallHooksWithRetry() {
    Log("Installing certificate validation bypass hooks...");
    
    if (!InitializeMinHook()) {
        return false;
    }

    // Load and get function addresses
    HMODULE hWintrust = LoadLibraryW(L"wintrust.dll");
    HMODULE hCrypt32 = LoadLibraryW(L"crypt32.dll");
    
    if (!hWintrust) {
        Log("CRITICAL: Failed to load wintrust.dll");
        return false;
    }
    
    if (!hCrypt32) {
        Log("CRITICAL: Failed to load crypt32.dll");
        return false;
    }

    int hooks_installed = 0;
    int hooks_attempted = 0;

    // Get function addresses
    s_WinVerifyTrust = reinterpret_cast<PFN_WinVerifyTrust>(GetProcAddress(hWintrust, "WinVerifyTrust"));
    s_CertVerifyCertificateChainPolicy = reinterpret_cast<PFN_CertVerifyCertificateChainPolicy>(GetProcAddress(hCrypt32, "CertVerifyCertificateChainPolicy"));
    s_CertGetCertificateChain = reinterpret_cast<PFN_CertGetCertificateChain>(GetProcAddress(hCrypt32, "CertGetCertificateChain"));

    // Install WinVerifyTrust hook
    hooks_attempted++;
    if (CreateSingleHook("wintrust.dll", "WinVerifyTrust",
                        reinterpret_cast<LPVOID>(s_WinVerifyTrust),
                        Hook_WinVerifyTrust,
                        reinterpret_cast<LPVOID*>(&s_WinVerifyTrust))) {
        hooks_installed++;
    }
    
    // Install CertVerifyCertificateChainPolicy hook
    hooks_attempted++;
    if (CreateSingleHook("crypt32.dll", "CertVerifyCertificateChainPolicy",
                        reinterpret_cast<LPVOID>(s_CertVerifyCertificateChainPolicy),
                        Hook_CertVerifyCertificateChainPolicy,
                        reinterpret_cast<LPVOID*>(&s_CertVerifyCertificateChainPolicy))) {
        hooks_installed++;
    }
    
    // Install CertGetCertificateChain hook
    hooks_attempted++;
    if (CreateSingleHook("crypt32.dll", "CertGetCertificateChain",
                        reinterpret_cast<LPVOID>(s_CertGetCertificateChain),
                        Hook_CertGetCertificateChain,
                        reinterpret_cast<LPVOID*>(&s_CertGetCertificateChain))) {
        hooks_installed++;
    }

    char result[256];
    snprintf(result, sizeof(result), "Hook installation complete! %d/%d hooks active", hooks_installed, hooks_attempted);
    Log(result);
    
    if (hooks_installed == 0) {
        Log("CRITICAL: No hooks were installed successfully! Certificate bypass will not work!");
        return false;
    } else if (hooks_installed < hooks_attempted) {
        Log("WARNING: Some hooks failed to install. Certificate bypass may be partial.");
    } else {
        Log("SUCCESS: All certificate validation hooks installed successfully!");
    }
    
    return hooks_installed > 0;
}

static void RemoveHooks() {
    Log("Removing hooks and cleaning up...");
    
    if (g_minhook_initialized.load()) {
        MH_STATUS disable_status = MH_DisableHook(MH_ALL_HOOKS);
        if (disable_status == MH_OK) {
            Log("All hooks disabled successfully");
        } else {
            char error_msg[128];
            snprintf(error_msg, sizeof(error_msg), "Warning: Hook disable failed - %s", GetMHStatusString(disable_status));
            Log(error_msg);
        }
        
        MH_STATUS uninit_status = MH_Uninitialize();
        if (uninit_status == MH_OK) {
            Log("MinHook uninitialized successfully");
            g_minhook_initialized.store(false);
        } else {
            char error_msg[128];
            snprintf(error_msg, sizeof(error_msg), "Warning: MinHook uninitialize failed - %s", GetMHStatusString(uninit_status));
            Log(error_msg);
        }
    }
}

static void InitializeLogging() {
    // File log in %TEMP%\BAUnpin-Enhanced.log with rotation
    wchar_t tpath[MAX_PATH];
    if (GetTempPathW(MAX_PATH, tpath)) {
        wchar_t fpath[MAX_PATH];
        lstrcpyW(fpath, tpath);
        PathAppendW(fpath, L"BAUnpin-Enhanced.log");
        char fpathA[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, fpath, -1, fpathA, MAX_PATH, nullptr, nullptr);
        
        // Check file size and rotate if needed (>2MB)
        WIN32_FILE_ATTRIBUTE_DATA fad;
        if (GetFileAttributesExA(fpathA, GetFileExInfoStandard, &fad)) {
            ULARGE_INTEGER size;
            size.LowPart = fad.nFileSizeLow;
            size.HighPart = fad.nFileSizeHigh;
            if (size.QuadPart > 2 * 1024 * 1024) { // 2MB
                char backup_path[MAX_PATH];
                snprintf(backup_path, sizeof(backup_path), "%s.old", fpathA);
                DeleteFileA(backup_path);
                MoveFileA(fpathA, backup_path);
                Log("Log file rotated due to size");
            }
        }
        
        g_file = fopen(fpathA, "ab");
        if (g_file) {
            Log("Enhanced log file initialized");
        } else {
            OutputDebugStringA("[BAUnpin-Enhanced] WARNING: Failed to initialize log file\n");
        }
    }
}

static DWORD WINAPI InitThread(LPVOID param) {
    Log("BAUnpin Enhanced Edition initialization starting...");
    
    try {
        // Initialize logging first
        InitializeLogging();
        
        // Log system information
        Log("=== BAUnpin Enhanced v2.1 - Blue Archive Certificate Bypass ===");
        char sys_info[256];
        OSVERSIONINFOA osvi = { sizeof(OSVERSIONINFOA) };
        if (GetVersionExA(&osvi)) {
            snprintf(sys_info, sizeof(sys_info), "OS Version: %d.%d Build %d",
                    osvi.dwMajorVersion, osvi.dwMinorVersion, osvi.dwBuildNumber);
            Log(sys_info);
        }
        
        // Setup console for debugging if needed
        if (GetEnvironmentVariableA("BAUNPIN_CONSOLE", nullptr, 0) > 0) {
            SetupConsole();
            Log("Debug console enabled via environment variable");
        }
        
        // BA-Cheeto style stabilization wait
        Log("Waiting for process stabilization...");
        std::this_thread::sleep_for(std::chrono::milliseconds(2000));
        
        // Ensure target modules are available
        if (!EnsureModulesLoaded()) {
            Log("ERROR: Failed to ensure target modules are loaded");
            return 1;
        }
        
        // Install hooks with retry logic
        bool hooks_success = false;
        for (int retry = 0; retry < 3; retry++) {
            if (retry > 0) {
                char retry_msg[128];
                snprintf(retry_msg, sizeof(retry_msg), "Hook installation attempt %d/3...", retry + 1);
                Log(retry_msg);
                std::this_thread::sleep_for(std::chrono::milliseconds(1000));
            }
            
            hooks_success = InstallHooksWithRetry();
            if (hooks_success) {
                break;
            }
            
            Log("Hook installation failed, retrying...");
        }
        
        if (!hooks_success) {
            Log("CRITICAL: All hook installation attempts failed!");
            return 1;
        }
        
        g_initialized.store(true);
        Log("BAUnpin Enhanced initialization completed successfully!");
        Log("Certificate validation bypass is now ACTIVE for Blue Archive");
        
        // Background monitoring thread (BA-Cheeto style)
        std::thread monitor_thread([]() {
            Log("Starting enhanced background monitor...");
            int health_check_count = 0;
            
            while (!g_shutdown.load()) {
                std::this_thread::sleep_for(std::chrono::seconds(60));
                
                // Periodic health check
                if (g_initialized.load() && g_minhook_initialized.load()) {
                    health_check_count++;
                    if (health_check_count % 5 == 0) { // Every 5 minutes
                        char health_msg[128];
                        snprintf(health_msg, sizeof(health_msg), "Health check #%d: BAUnpin Enhanced running normally", health_check_count);
                        Log(health_msg);
                    }
                }
            }
            Log("Enhanced background monitor stopped");
        });
        monitor_thread.detach();
        
    } catch (const std::exception& e) {
        char error_msg[512];
        snprintf(error_msg, sizeof(error_msg), "EXCEPTION during initialization: %s", e.what());
        Log(error_msg);
        return 1;
    } catch (...) {
        Log("UNKNOWN EXCEPTION during initialization");
        return 1;
    }
    
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH: {
        // Critical: Disable thread library calls for performance
        DisableThreadLibraryCalls(hModule);
        
        // Initialize in a separate thread to avoid blocking DLL load (BA-Cheeto pattern)
        HANDLE hThread = CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
        if (hThread) {
            CloseHandle(hThread);
            return TRUE;
        } else {
            // Fallback: try direct initialization
            OutputDebugStringA("[BAUnpin-Enhanced] WARNING: Failed to create init thread, trying direct init\n");
            return InitThread(nullptr) == 0 ? TRUE : FALSE;
        }
    }
    case DLL_PROCESS_DETACH: {
        // Only cleanup if we're being unloaded normally, not during process termination
        if (lpReserved == nullptr) {
            g_shutdown.store(true);
            
            // Wait a bit for background threads to notice shutdown
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            
            Log("BAUnpin Enhanced shutting down...");
            RemoveHooks();
            
            if (g_console) {
                Log("Closing debug console...");
                FreeConsole();
            }
            
            if (g_file) {
                Log("Closing enhanced log file...");
                fclose(g_file);
                g_file = nullptr;
            }
            
            // Give a moment for final log writes
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        break;
    }
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
        // Nothing to do
        break;
    }
    return TRUE;
}
