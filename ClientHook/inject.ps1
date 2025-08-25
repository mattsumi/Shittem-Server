param(
  [Parameter(Mandatory=$true)][string]$ProcessName,
  [Parameter(Mandatory=$true)][string]$DllPath
)

# Simple LoadLibrary-based DLL injector. Run as Administrator.

$code = @"
using System;
using System.Runtime.InteropServices;
public static class Injector
{
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint acc, bool inh, int pid);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr h, IntPtr a, uint s, uint t, uint p);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool WriteProcessMemory(IntPtr h, IntPtr a, byte[] b, uint s, out UIntPtr w);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateRemoteThread(IntPtr h, IntPtr a, uint s, IntPtr addr, IntPtr param, uint f, out uint tid);
    [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr h, uint ms);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, SetLastError=true)] static extern IntPtr GetProcAddress(IntPtr h, string name);
    public static void Inject(int pid, string dll)
    {
        const uint PROCESS_ALL_ACCESS = 0x1F0FFF;
        const uint MEM_COMMIT = 0x1000; const uint MEM_RESERVE = 0x2000; const uint PAGE_READWRITE = 0x04;
        IntPtr hProc = OpenProcess(PROCESS_ALL_ACCESS, false, pid);
        if (hProc == IntPtr.Zero) throw new Exception("OpenProcess failed");
        byte[] path = System.Text.Encoding.Unicode.GetBytes(dll + "\0");
        IntPtr remote = VirtualAllocEx(hProc, IntPtr.Zero, (uint)path.Length, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
        if (remote == IntPtr.Zero) throw new Exception("VirtualAllocEx failed");
        UIntPtr written;
        if (!WriteProcessMemory(hProc, remote, path, (uint)path.Length, out written)) throw new Exception("WriteProcessMemory failed");
        IntPtr k32 = GetModuleHandle("kernel32.dll");
        IntPtr loadLibW = GetProcAddress(k32, "LoadLibraryW");
        uint tid;
        IntPtr hThread = CreateRemoteThread(hProc, IntPtr.Zero, 0, loadLibW, remote, 0, out tid);
        if (hThread == IntPtr.Zero) throw new Exception("CreateRemoteThread failed");
        WaitForSingleObject(hThread, 5000);
        CloseHandle(hThread);
        CloseHandle(hProc);
    }
}
"@

Add-Type -Language CSharp -TypeDefinition $code -ErrorAction Stop

if (-not (Test-Path $DllPath)) { throw "DLL not found: $DllPath" }
$proc = Get-Process -Name $ProcessName -ErrorAction Stop
Write-Host "Injecting into PID $($proc.Id) ..."
[Injector]::Inject($proc.Id, (Resolve-Path $DllPath).Path)
Write-Host "Done. Use DebugView to look for [BAUnpin] Hooks installed"
