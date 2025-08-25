#include <windows.h>
#include <wininet.h>
#include <winhttp.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <cstdio>
#include <string>
#include <mutex>
#include <atomic>

#include "MinHook.h"

// Network API hooks for diagnosis
using PFN_InternetOpenA = HINTERNET (WINAPI*)(LPCSTR, DWORD, LPCSTR, LPCSTR, DWORD);
using PFN_InternetConnectA = HINTERNET (WINAPI*)(HINTERNET, LPCSTR, INTERNET_PORT, LPCSTR, LPCSTR, DWORD, DWORD, DWORD_PTR);
using PFN_HttpOpenRequestA = HINTERNET (WINAPI*)(HINTERNET, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPCSTR*, DWORD, DWORD_PTR);
using PFN_InternetSetOptionA = BOOL (WINAPI*)(HINTERNET, DWORD, LPVOID, DWORD);
using PFN_WinHttpOpen = HINTERNET (WINAPI*)(LPCWSTR, DWORD, LPCWSTR, LPCWSTR, DWORD);
using PFN_WinHttpConnect = HINTERNET (WINAPI*)(HINTERNET, LPCWSTR, INTERNET_PORT, DWORD);
using PFN_WinHttpOpenRequest = HINTERNET (WINAPI*)(HINTERNET, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR*, DWORD);
using PFN_WinHttpSetOption = BOOL (WINAPI*)(HINTERNET, DWORD, LPVOID, DWORD);

static PFN_InternetOpenA s_InternetOpenA = nullptr;
static PFN_InternetConnectA s_InternetConnectA = nullptr;
static PFN_HttpOpenRequestA s_HttpOpenRequestA = nullptr;
static PFN_InternetSetOptionA s_InternetSetOptionA = nullptr;
static PFN_WinHttpOpen s_WinHttpOpen = nullptr;
static PFN_WinHttpConnect s_WinHttpConnect = nullptr;
static PFN_WinHttpOpenRequest s_WinHttpOpenRequest = nullptr;
static PFN_WinHttpSetOption s_WinHttpSetOption = nullptr;

static std::mutex g_log_mutex;
static FILE* g_file = nullptr;

static void Log(const char* msg) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    
    char timestamp[64];
    SYSTEMTIME st;
    GetSystemTime(&st);
    snprintf(timestamp, sizeof(timestamp), "[%02d:%02d:%02d.%03d] ", 
             st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    
    char buf[1024];
    snprintf(buf, sizeof(buf), "%s[BAUnpin-Diagnostic] %s\n", timestamp, msg);
    
    if (g_file) {
        fwrite(buf, 1, strlen(buf), g_file);
        fflush(g_file);
    }
    OutputDebugStringA(buf);
}

// WinINet hooks
static HINTERNET WINAPI Hook_InternetOpenA(LPCSTR lpszAgent, DWORD dwAccessType, LPCSTR lpszProxy, LPCSTR lpszProxyBypass, DWORD dwFlags) {
    char msg[256];
    snprintf(msg, sizeof(msg), "InternetOpenA called! Agent: %s", lpszAgent ? lpszAgent : "NULL");
    Log(msg);
    return s_InternetOpenA(lpszAgent, dwAccessType, lpszProxy, lpszProxyBypass, dwFlags);
}

static HINTERNET WINAPI Hook_InternetConnectA(HINTERNET hInternet, LPCSTR lpszServerName, INTERNET_PORT nServerPort, LPCSTR lpszUserName, LPCSTR lpszPassword, DWORD dwService, DWORD dwFlags, DWORD_PTR dwContext) {
    char msg[256];
    snprintf(msg, sizeof(msg), "InternetConnectA called! Server: %s:%d", lpszServerName ? lpszServerName : "NULL", nServerPort);
    Log(msg);
    return s_InternetConnectA(hInternet, lpszServerName, nServerPort, lpszUserName, lpszPassword, dwService, dwFlags, dwContext);
}

static HINTERNET WINAPI Hook_HttpOpenRequestA(HINTERNET hConnect, LPCSTR lpszVerb, LPCSTR lpszObjectName, LPCSTR lpszVersion, LPCSTR lpszReferrer, LPCSTR* lplpszAcceptTypes, DWORD dwFlags, DWORD_PTR dwContext) {
    char msg[512];
    snprintf(msg, sizeof(msg), "HttpOpenRequestA called! %s %s (Flags: 0x%08X)", 
             lpszVerb ? lpszVerb : "NULL", lpszObjectName ? lpszObjectName : "NULL", dwFlags);
    Log(msg);
    return s_HttpOpenRequestA(hConnect, lpszVerb, lpszObjectName, lpszVersion, lpszReferrer, lplpszAcceptTypes, dwFlags, dwContext);
}

static BOOL WINAPI Hook_InternetSetOptionA(HINTERNET hInternet, DWORD dwOption, LPVOID lpBuffer, DWORD dwBufferLength) {
    char msg[256];
    snprintf(msg, sizeof(msg), "InternetSetOptionA called! Option: %d", dwOption);
    Log(msg);
    
    // Disable certificate verification for common options
    if (dwOption == INTERNET_OPTION_SECURITY_FLAGS) {
        DWORD* flags = (DWORD*)lpBuffer;
        if (flags && dwBufferLength >= sizeof(DWORD)) {
            *flags |= SECURITY_FLAG_IGNORE_CERT_CN_INVALID | SECURITY_FLAG_IGNORE_CERT_DATE_INVALID | SECURITY_FLAG_IGNORE_UNKNOWN_CA;
            Log("Modified INTERNET_OPTION_SECURITY_FLAGS to ignore certificate errors!");
        }
    }
    
    return s_InternetSetOptionA(hInternet, dwOption, lpBuffer, dwBufferLength);
}

// WinHTTP hooks
static HINTERNET WINAPI Hook_WinHttpOpen(LPCWSTR pszUserAgent, DWORD dwAccessType, LPCWSTR pszProxy, LPCWSTR pszProxyBypass, DWORD dwFlags) {
    char msg[512];
    char agent[256] = "NULL";
    if (pszUserAgent) {
        WideCharToMultiByte(CP_UTF8, 0, pszUserAgent, -1, agent, sizeof(agent), NULL, NULL);
    }
    snprintf(msg, sizeof(msg), "WinHttpOpen called! Agent: %s", agent);
    Log(msg);
    return s_WinHttpOpen(pszUserAgent, dwAccessType, pszProxy, pszProxyBypass, dwFlags);
}

static HINTERNET WINAPI Hook_WinHttpConnect(HINTERNET hSession, LPCWSTR pswzServerName, INTERNET_PORT nServerPort, DWORD dwReserved) {
    char msg[512];
    char server[256] = "NULL";
    if (pswzServerName) {
        WideCharToMultiByte(CP_UTF8, 0, pswzServerName, -1, server, sizeof(server), NULL, NULL);
    }
    snprintf(msg, sizeof(msg), "WinHttpConnect called! Server: %s:%d", server, nServerPort);
    Log(msg);
    return s_WinHttpConnect(hSession, pswzServerName, nServerPort, dwReserved);
}

static HINTERNET WINAPI Hook_WinHttpOpenRequest(HINTERNET hConnect, LPCWSTR pwszVerb, LPCWSTR pwszObjectName, LPCWSTR pwszVersion, LPCWSTR pwszReferrer, LPCWSTR* ppwszAcceptTypes, DWORD dwFlags) {
    char msg[512];
    char verb[64] = "NULL", object[256] = "NULL";
    if (pwszVerb) WideCharToMultiByte(CP_UTF8, 0, pwszVerb, -1, verb, sizeof(verb), NULL, NULL);
    if (pwszObjectName) WideCharToMultiByte(CP_UTF8, 0, pwszObjectName, -1, object, sizeof(object), NULL, NULL);
    snprintf(msg, sizeof(msg), "WinHttpOpenRequest called! %s %s (Flags: 0x%08X)", verb, object, dwFlags);
    Log(msg);
    return s_WinHttpOpenRequest(hConnect, pwszVerb, pwszObjectName, pwszVersion, pwszReferrer, ppwszAcceptTypes, dwFlags);
}

static BOOL WINAPI Hook_WinHttpSetOption(HINTERNET hInternet, DWORD dwOption, LPVOID lpBuffer, DWORD dwBufferLength) {
    char msg[256];
    snprintf(msg, sizeof(msg), "WinHttpSetOption called! Option: %d", dwOption);
    Log(msg);
    
    // Disable certificate verification for WinHTTP
    if (dwOption == WINHTTP_OPTION_SECURITY_FLAGS) {
        DWORD* flags = (DWORD*)lpBuffer;
        if (flags && dwBufferLength >= sizeof(DWORD)) {
            *flags |= SECURITY_FLAG_IGNORE_CERT_CN_INVALID | SECURITY_FLAG_IGNORE_CERT_DATE_INVALID | SECURITY_FLAG_IGNORE_UNKNOWN_CA;
            Log("Modified WINHTTP_OPTION_SECURITY_FLAGS to ignore certificate errors!");
        }
    }
    
    return s_WinHttpSetOption(hInternet, dwOption, lpBuffer, dwBufferLength);
}

static bool InstallNetworkHooks() {
    Log("Installing network diagnostic hooks...");
    
    if (MH_Initialize() != MH_OK) {
        Log("ERROR: MinHook initialization failed!");
        return false;
    }

    int hooks_installed = 0;
    
    // Try WinINet
    HMODULE hWininet = LoadLibraryA("wininet.dll");
    if (hWininet) {
        Log("Found wininet.dll, installing hooks...");
        
        s_InternetOpenA = (PFN_InternetOpenA)GetProcAddress(hWininet, "InternetOpenA");
        s_InternetConnectA = (PFN_InternetConnectA)GetProcAddress(hWininet, "InternetConnectA");
        s_HttpOpenRequestA = (PFN_HttpOpenRequestA)GetProcAddress(hWininet, "HttpOpenRequestA");
        s_InternetSetOptionA = (PFN_InternetSetOptionA)GetProcAddress(hWininet, "InternetSetOptionA");
        
        if (s_InternetOpenA && MH_CreateHook(s_InternetOpenA, Hook_InternetOpenA, (void**)&s_InternetOpenA) == MH_OK &&
            MH_EnableHook(s_InternetOpenA) == MH_OK) {
            Log("Hooked InternetOpenA");
            hooks_installed++;
        }
        
        if (s_InternetConnectA && MH_CreateHook(s_InternetConnectA, Hook_InternetConnectA, (void**)&s_InternetConnectA) == MH_OK &&
            MH_EnableHook(s_InternetConnectA) == MH_OK) {
            Log("Hooked InternetConnectA");
            hooks_installed++;
        }
        
        if (s_HttpOpenRequestA && MH_CreateHook(s_HttpOpenRequestA, Hook_HttpOpenRequestA, (void**)&s_HttpOpenRequestA) == MH_OK &&
            MH_EnableHook(s_HttpOpenRequestA) == MH_OK) {
            Log("Hooked HttpOpenRequestA");
            hooks_installed++;
        }
        
        if (s_InternetSetOptionA && MH_CreateHook(s_InternetSetOptionA, Hook_InternetSetOptionA, (void**)&s_InternetSetOptionA) == MH_OK &&
            MH_EnableHook(s_InternetSetOptionA) == MH_OK) {
            Log("Hooked InternetSetOptionA");
            hooks_installed++;
        }
    }
    
    // Try WinHTTP
    HMODULE hWinhttp = LoadLibraryA("winhttp.dll");
    if (hWinhttp) {
        Log("Found winhttp.dll, installing hooks...");
        
        s_WinHttpOpen = (PFN_WinHttpOpen)GetProcAddress(hWinhttp, "WinHttpOpen");
        s_WinHttpConnect = (PFN_WinHttpConnect)GetProcAddress(hWinhttp, "WinHttpConnect");
        s_WinHttpOpenRequest = (PFN_WinHttpOpenRequest)GetProcAddress(hWinhttp, "WinHttpOpenRequest");
        s_WinHttpSetOption = (PFN_WinHttpSetOption)GetProcAddress(hWinhttp, "WinHttpSetOption");
        
        if (s_WinHttpOpen && MH_CreateHook(s_WinHttpOpen, Hook_WinHttpOpen, (void**)&s_WinHttpOpen) == MH_OK &&
            MH_EnableHook(s_WinHttpOpen) == MH_OK) {
            Log("Hooked WinHttpOpen");
            hooks_installed++;
        }
        
        if (s_WinHttpConnect && MH_CreateHook(s_WinHttpConnect, Hook_WinHttpConnect, (void**)&s_WinHttpConnect) == MH_OK &&
            MH_EnableHook(s_WinHttpConnect) == MH_OK) {
            Log("Hooked WinHttpConnect");
            hooks_installed++;
        }
        
        if (s_WinHttpOpenRequest && MH_CreateHook(s_WinHttpOpenRequest, Hook_WinHttpOpenRequest, (void**)&s_WinHttpOpenRequest) == MH_OK &&
            MH_EnableHook(s_WinHttpOpenRequest) == MH_OK) {
            Log("Hooked WinHttpOpenRequest");
            hooks_installed++;
        }
        
        if (s_WinHttpSetOption && MH_CreateHook(s_WinHttpSetOption, Hook_WinHttpSetOption, (void**)&s_WinHttpSetOption) == MH_OK &&
            MH_EnableHook(s_WinHttpSetOption) == MH_OK) {
            Log("Hooked WinHttpSetOption");
            hooks_installed++;
        }
    }
    
    char result[128];
    snprintf(result, sizeof(result), "Network hook installation complete! %d hooks active", hooks_installed);
    Log(result);
    
    return hooks_installed > 0;
}

static DWORD WINAPI InitThread(LPVOID param) {
    Log("BAUnpin Network Diagnostic starting...");
    
    // Initialize logging
    wchar_t tpath[MAX_PATH];
    if (GetTempPathW(MAX_PATH, tpath)) {
        wchar_t fpath[MAX_PATH];
        lstrcpyW(fpath, tpath);
        PathAppendW(fpath, L"BAUnpin-NetworkDiag.log");
        char fpathA[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, fpath, -1, fpathA, MAX_PATH, nullptr, nullptr);
        g_file = fopen(fpathA, "ab");
    }
    
    Log("Waiting for process to stabilize...");
    Sleep(3000);
    
    Log("Installing network hooks to see what Blue Archive uses...");
    InstallNetworkHooks();
    
    Log("Network diagnostic hooks installed! Now try connecting to Blue Archive servers.");
    Log("Watch the log file for network API calls to see what Blue Archive uses.");
    
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
        break;
    case DLL_PROCESS_DETACH:
        if (lpReserved == nullptr) {
            Log("Shutting down network diagnostic hooks...");
            MH_DisableHook(MH_ALL_HOOKS);
            MH_Uninitialize();
            if (g_file) {
                fclose(g_file);
                g_file = nullptr;
            }
        }
        break;
    }
    return TRUE;
}
