#include <windows.h>
#include <tlhelp32.h>
#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <chrono>
#include <thread>

class ProcessInjector {
private:
    static constexpr DWORD INJECTION_TIMEOUT = 10000; // 10 seconds
    static constexpr DWORD PROCESS_REQUIRED_ACCESS = 
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | 
        PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ;

    static std::wstring GetLastErrorString() {
        DWORD error = GetLastError();
        if (error == 0) return L"Success";

        LPWSTR messageBuffer = nullptr;
        size_t size = FormatMessageW(
            FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
            nullptr, error, MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
            (LPWSTR)&messageBuffer, 0, nullptr);

        std::wstring message(messageBuffer, size);
        LocalFree(messageBuffer);
        return message;
    }

    static DWORD FindProcessByName(const std::wstring& processName) {
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == INVALID_HANDLE_VALUE) {
            std::wcout << L"ERROR: Failed to create process snapshot: " << GetLastErrorString() << std::endl;
            return 0;
        }

        PROCESSENTRY32W pe32;
        pe32.dwSize = sizeof(PROCESSENTRY32W);

        if (!Process32FirstW(snapshot, &pe32)) {
            std::wcout << L"ERROR: Failed to get first process: " << GetLastErrorString() << std::endl;
            CloseHandle(snapshot);
            return 0;
        }

        DWORD targetPid = 0;
        do {
            if (processName == pe32.szExeFile) {
                targetPid = pe32.th32ProcessID;
                break;
            }
        } while (Process32NextW(snapshot, &pe32));

        CloseHandle(snapshot);

        if (targetPid == 0) {
            std::wcout << L"ERROR: Process '" << processName << L"' not found" << std::endl;
        } else {
            std::wcout << L"Found process '" << processName << L"' with PID: " << targetPid << std::endl;
        }

        return targetPid;
    }

    static bool IsModuleLoaded(DWORD processId, const std::wstring& moduleName) {
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, processId);
        if (snapshot == INVALID_HANDLE_VALUE) {
            return false;
        }

        MODULEENTRY32W me32;
        me32.dwSize = sizeof(MODULEENTRY32W);

        if (!Module32FirstW(snapshot, &me32)) {
            CloseHandle(snapshot);
            return false;
        }

        bool found = false;
        do {
            if (_wcsicmp(moduleName.c_str(), me32.szModule) == 0) {
                found = true;
                break;
            }
        } while (Module32NextW(snapshot, &me32));

        CloseHandle(snapshot);
        return found;
    }

public:
    static bool InjectDLL(const std::wstring& processName, const std::wstring& dllPath) {
        std::wcout << L"=== BA-Cheeto Style DLL Injector ===" << std::endl;
        std::wcout << L"Target Process: " << processName << std::endl;
        std::wcout << L"DLL Path: " << dllPath << std::endl;

        // Verify DLL exists
        if (GetFileAttributesW(dllPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
            std::wcout << L"ERROR: DLL file not found: " << dllPath << std::endl;
            return false;
        }

        // Find target process
        DWORD processId = FindProcessByName(processName);
        if (processId == 0) {
            return false;
        }

        // Check if already injected
        std::wstring dllName = dllPath.substr(dllPath.find_last_of(L"\\/") + 1);
        if (IsModuleLoaded(processId, dllName)) {
            std::wcout << L"WARNING: DLL '" << dllName << L"' appears to already be loaded in target process" << std::endl;
            return false;
        }

        // Open target process
        std::wcout << L"Opening process with PID " << processId << L"..." << std::endl;
        HANDLE processHandle = OpenProcess(PROCESS_REQUIRED_ACCESS, FALSE, processId);
        if (processHandle == nullptr) {
            std::wcout << L"ERROR: Failed to open process (are you running as administrator?): " << GetLastErrorString() << std::endl;
            return false;
        }

        bool success = false;
        LPVOID allocatedMemory = nullptr;
        HANDLE remoteThread = nullptr;

        try {
            // Get LoadLibraryW address
            HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
            if (kernel32 == nullptr) {
                throw std::runtime_error("Failed to get kernel32.dll handle");
            }

            LPVOID loadLibraryAddr = (LPVOID)GetProcAddress(kernel32, "LoadLibraryW");
            if (loadLibraryAddr == nullptr) {
                throw std::runtime_error("Failed to get LoadLibraryW address");
            }

            // Allocate memory in target process
            SIZE_T dllPathSize = (dllPath.length() + 1) * sizeof(wchar_t);
            std::wcout << L"Allocating " << dllPathSize << L" bytes in target process..." << std::endl;
            
            allocatedMemory = VirtualAllocEx(
                processHandle,
                nullptr,
                dllPathSize,
                MEM_COMMIT | MEM_RESERVE,
                PAGE_READWRITE
            );

            if (allocatedMemory == nullptr) {
                throw std::runtime_error("Failed to allocate memory in target process");
            }

            // Write DLL path to allocated memory
            std::wcout << L"Writing DLL path to target process memory..." << std::endl;
            SIZE_T bytesWritten;
            if (!WriteProcessMemory(
                processHandle,
                allocatedMemory,
                dllPath.c_str(),
                dllPathSize,
                &bytesWritten
            ) || bytesWritten != dllPathSize) {
                throw std::runtime_error("Failed to write DLL path to target process");
            }

            // Create remote thread to load DLL
            std::wcout << L"Creating remote thread to load DLL..." << std::endl;
            remoteThread = CreateRemoteThread(
                processHandle,
                nullptr,
                0,
                (LPTHREAD_START_ROUTINE)loadLibraryAddr,
                allocatedMemory,
                0,
                nullptr
            );

            if (remoteThread == nullptr) {
                throw std::runtime_error("Failed to create remote thread");
            }

            // Wait for injection to complete
            std::wcout << L"Waiting for injection to complete (timeout: " << INJECTION_TIMEOUT << L"ms)..." << std::endl;
            DWORD waitResult = WaitForSingleObject(remoteThread, INJECTION_TIMEOUT);

            switch (waitResult) {
            case WAIT_OBJECT_0: {
                DWORD exitCode;
                if (GetExitCodeThread(remoteThread, &exitCode)) {
                    if (exitCode != 0) {
                        std::wcout << L"SUCCESS: DLL injection completed! Thread exit code: 0x" 
                                  << std::hex << exitCode << std::dec << std::endl;
                        
                        // Wait a moment then verify injection
                        std::this_thread::sleep_for(std::chrono::milliseconds(500));
                        if (IsModuleLoaded(processId, dllName)) {
                            std::wcout << L"VERIFIED: DLL is loaded in target process!" << std::endl;
                            success = true;
                        } else {
                            std::wcout << L"WARNING: Injection appeared successful but DLL not found in module list" << std::endl;
                        }
                    } else {
                        std::wcout << L"ERROR: LoadLibraryW returned NULL (DLL load failed)" << std::endl;
                        std::wcout << L"This usually means:" << std::endl;
                        std::wcout << L"  - Missing DLL dependencies (try copying minhook.x64.dll to game folder)" << std::endl;
                        std::wcout << L"  - DLL initialization (DllMain) failed" << std::endl;
                        std::wcout << L"  - Architecture mismatch (but both are x64)" << std::endl;
                        std::wcout << L"  - Antivirus blocking the DLL" << std::endl;
                    }
                } else {
                    std::wcout << L"WARNING: Could not get thread exit code: " << GetLastErrorString() << std::endl;
                    success = true; // Assume success
                }
                break;
            }
            case WAIT_TIMEOUT:
                std::wcout << L"ERROR: Injection timed out" << std::endl;
                break;
            default:
                std::wcout << L"ERROR: Wait failed: " << GetLastErrorString() << std::endl;
                break;
            }

        } catch (const std::exception& e) {
            std::wcout << L"ERROR: Exception during injection: ";
            std::wcout << std::wstring(e.what(), e.what() + strlen(e.what())) << std::endl;
        }

        // Cleanup
        if (remoteThread) {
            CloseHandle(remoteThread);
        }
        if (allocatedMemory) {
            VirtualFreeEx(processHandle, allocatedMemory, 0, MEM_RELEASE);
        }
        CloseHandle(processHandle);

        return success;
    }

    static bool UnloadDLL(const std::wstring& processName, const std::wstring& dllName) {
        std::wcout << L"=== DLL Unloader ===" << std::endl;
        std::wcout << L"Target Process: " << processName << std::endl;
        std::wcout << L"DLL Name: " << dllName << std::endl;

        DWORD processId = FindProcessByName(processName);
        if (processId == 0) {
            return false;
        }

        // Find module handle in target process
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, processId);
        if (snapshot == INVALID_HANDLE_VALUE) {
            std::wcout << L"ERROR: Failed to create module snapshot: " << GetLastErrorString() << std::endl;
            return false;
        }

        MODULEENTRY32W me32;
        me32.dwSize = sizeof(MODULEENTRY32W);

        HMODULE targetModule = nullptr;
        if (Module32FirstW(snapshot, &me32)) {
            do {
                if (_wcsicmp(dllName.c_str(), me32.szModule) == 0) {
                    targetModule = me32.hModule;
                    break;
                }
            } while (Module32NextW(snapshot, &me32));
        }

        CloseHandle(snapshot);

        if (targetModule == nullptr) {
            std::wcout << L"ERROR: DLL not found in target process" << std::endl;
            return false;
        }

        // Open target process
        HANDLE processHandle = OpenProcess(PROCESS_REQUIRED_ACCESS, FALSE, processId);
        if (processHandle == nullptr) {
            std::wcout << L"ERROR: Failed to open process: " << GetLastErrorString() << std::endl;
            return false;
        }

        // Get FreeLibrary address
        HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
        LPVOID freeLibraryAddr = (LPVOID)GetProcAddress(kernel32, "FreeLibrary");

        // Create remote thread to unload DLL
        std::wcout << L"Creating remote thread to unload DLL..." << std::endl;
        HANDLE remoteThread = CreateRemoteThread(
            processHandle,
            nullptr,
            0,
            (LPTHREAD_START_ROUTINE)freeLibraryAddr,
            targetModule,
            0,
            nullptr
        );

        bool success = false;
        if (remoteThread) {
            DWORD waitResult = WaitForSingleObject(remoteThread, INJECTION_TIMEOUT);
            if (waitResult == WAIT_OBJECT_0) {
                std::wcout << L"SUCCESS: DLL unload completed!" << std::endl;
                success = true;
            }
            CloseHandle(remoteThread);
        }

        CloseHandle(processHandle);
        return success;
    }
};

int wmain(int argc, wchar_t* argv[]) {
    std::wcout << L"BAUnpin Injector v2.0 - Based on BA-Cheeto Architecture" << std::endl;
    std::wcout << L"======================================================" << std::endl;

    if (argc < 3) {
        std::wcout << L"Usage: " << argv[0] << L" <process_name> <dll_path> [unload]" << std::endl;
        std::wcout << L"Example: " << argv[0] << L" BlueArchive.exe BAUnpin.dll" << std::endl;
        std::wcout << L"Example: " << argv[0] << L" BlueArchive.exe BAUnpin.dll unload" << std::endl;
        return 1;
    }

    std::wstring processName = argv[1];
    std::wstring dllPath = argv[2];
    bool unload = (argc > 3 && _wcsicmp(argv[3], L"unload") == 0);

    if (unload) {
        // Extract DLL name from path for unloading
        std::wstring dllName = dllPath.substr(dllPath.find_last_of(L"\\/") + 1);
        return ProcessInjector::UnloadDLL(processName, dllName) ? 0 : 1;
    } else {
        return ProcessInjector::InjectDLL(processName, dllPath) ? 0 : 1;
    }
}
