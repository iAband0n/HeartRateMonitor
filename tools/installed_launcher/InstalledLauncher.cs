using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("心率悬浮窗")]
[assembly: AssemblyDescription("HeartRateOverlay installed launcher")]
[assembly: AssemblyProduct("心率悬浮窗")]
[assembly: AssemblyCompany("W's Thing")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace HeartRateOverlayInstalledLauncher
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            string installDir = Path.GetDirectoryName(
                Process.GetCurrentProcess().MainModule.FileName);
            string appExe = Path.Combine(installDir, "runtime", "心率悬浮窗.exe");
            string cacheDir = Path.Combine(installDir, "cache");
            Directory.CreateDirectory(cacheDir);

            ProcessStartInfo start = new ProcessStartInfo(appExe);
            start.WorkingDirectory = installDir;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.EnvironmentVariables["HEART_RATE_OVERLAY_DATA_DIR"] = cacheDir;
            if (args.Length > 0)
            {
                start.Arguments = string.Join(" ", Array.ConvertAll(args, Quote));
            }
            using (Process child = Process.Start(start))
            {
                return child == null ? 1 : child.ExitCode;
            }
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
        }
    }
}
