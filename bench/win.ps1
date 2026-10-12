param([string]$op, [long]$h = 0, [string]$arg = "")
Add-Type @"
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class WB {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  public static List<string> List(string proc) {
    var r = new List<string>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      string name = "";
      try { name = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch {}
      if (proc != "" && !name.Equals(proc, StringComparison.OrdinalIgnoreCase)) return true;
      var sb = new StringBuilder(512); GetWindowText(h, sb, 512);
      if (sb.Length > 0) r.Add(h.ToInt64() + "`t" + sb.ToString());
      return true;
    }, IntPtr.Zero);
    return r;
  }
}
"@
switch ($op) {
  "list" { [WB]::List($arg) }
  "close" { [void][WB]::PostMessage([IntPtr]$h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero); "closed" }
  "show" { [void][WB]::ShowWindow([IntPtr]$h, 5); "visible=" + [WB]::IsWindowVisible([IntPtr]$h) }
  "visible" { [WB]::IsWindowVisible([IntPtr]$h) }
  "cursor" { $p = New-Object WB+POINT; [void][WB]::GetCursorPos([ref]$p); "$($p.X),$($p.Y)" }
  "fg" { [WB]::GetForegroundWindow().ToInt64() }
}
