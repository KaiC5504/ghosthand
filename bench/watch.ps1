Add-Type @"
using System; using System.Runtime.InteropServices; using System.Threading;
public static class WW {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [StructLayout(LayoutKind.Sequential)] public struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam; public IntPtr lParam; public uint time; public int x; public int y; }
  public delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int id, HookProc fn, IntPtr mod, uint thread);
  [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] static extern int GetMessage(out MSG msg, IntPtr hwnd, uint min, uint max);
  [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string name);
  public static int Injected;
  static HookProc keep;
  // Counts mouse input that software injected (LLMHF_INJECTED), so KaiC's own hand is not blamed on a tool.
  public static void Start() {
    var t = new Thread(() => {
      keep = (code, w, l) => {
        if (code >= 0 && (Marshal.ReadInt32(l, 12) & 1) != 0) Interlocked.Increment(ref Injected);
        return CallNextHookEx(IntPtr.Zero, code, w, l);
      };
      SetWindowsHookEx(14, keep, GetModuleHandle(null), 0);
      MSG m;
      while (GetMessage(out m, IntPtr.Zero, 0, 0) > 0) { }
    });
    t.IsBackground = true;
    t.Start();
  }
}
"@
[WW]::Start()
$p = New-Object WW+POINT
while ($true) {
  [void][WW]::GetCursorPos([ref]$p)
  [Console]::Out.WriteLine("$($p.X),$($p.Y),$([WW]::GetForegroundWindow().ToInt64()),$([WW]::Injected)")
  [Console]::Out.Flush()
  Start-Sleep -Milliseconds 40
}
