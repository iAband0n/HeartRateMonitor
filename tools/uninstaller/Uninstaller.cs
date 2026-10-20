using System;
using System.Diagnostics;
using System.IO;
using Microsoft.Win32;
using System.Windows.Forms;

namespace HeartRateOverlayUninstaller
{
    internal static class Program
    {
        private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\HeartRateMonitor";

        [STAThread]
        private static int Main()
        {
            Application.EnableVisualStyles();
            string installDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
            if (MessageBox.Show("确定要卸载心率悬浮窗吗？\n\n安装目录中的配置、历史记录和缓存也会被删除。",
                "卸载心率悬浮窗", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return 0;
            try
            {
                foreach (Process process in Process.GetProcessesByName("心率悬浮窗"))
                {
                    if (process.Id != Process.GetCurrentProcess().Id)
                    {
                        try { process.Kill(); process.WaitForExit(3000); } catch { }
                    }
                    process.Dispose();
                }
                string shortcut = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "心率悬浮窗.lnk");
                if (File.Exists(shortcut)) File.Delete(shortcut);
                Registry.LocalMachine.DeleteSubKeyTree(UninstallKey, false);
                string command = "/c timeout /t 2 /nobreak >nul & rmdir /s /q " + Quote(installDir);
                Process.Start(new ProcessStartInfo("cmd.exe", command) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetTempPath() });
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show("卸载失败：\n\n" + ex.Message, "卸载心率悬浮窗", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }
    }
}
