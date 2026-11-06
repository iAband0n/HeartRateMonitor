using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using Microsoft.Win32;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Windows.Forms;

namespace HeartRateOverlayInstaller
{
    internal sealed class InstallerForm : Form
    {
        private const string PayloadResource = "payload.zip";
        private const string LauncherResource = "installed-launcher.exe";
        private const string UninstallerResource = "uninstaller.exe";
        private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\HeartRateMonitor";
        private readonly TextBox folderBox;
        private readonly Button installButton;
        private readonly Label status;

        public InstallerForm()
        {
            Text = "安装心率悬浮窗";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ClientSize = new Size(560, 190);
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);

            Label title = new Label { Text = "选择安装目录", AutoSize = true, Location = new Point(24, 22) };
            folderBox = new TextBox { Location = new Point(24, 55), Width = 410 };
            folderBox.Text = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs");
            Button browse = new Button { Text = "浏览…", Location = new Point(445, 53), Width = 85 };
            browse.Click += Browse;
            installButton = new Button { Text = "安装", Location = new Point(445, 105), Width = 85 };
            installButton.Click += Install;
            Button cancel = new Button { Text = "取消", Location = new Point(350, 105), Width = 85 };
            cancel.Click += (sender, args) => { DialogResult = DialogResult.Cancel; Close(); };
            status = new Label { AutoSize = false, Location = new Point(24, 108), Width = 310, Height = 45, Text = "安装后将在桌面创建快捷方式。" };
            Controls.AddRange(new Control[] { title, folderBox, browse, status, cancel, installButton });
            AcceptButton = installButton;
            CancelButton = cancel;
        }

        private void Browse(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择心率悬浮窗的安装目录";
                dialog.SelectedPath = folderBox.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    folderBox.Text = dialog.SelectedPath;
                }
            }
        }

        private void Install(object sender, EventArgs e)
        {
            string target = folderBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(target))
            {
                MessageBox.Show(this, "请选择安装目录。", "安装心率悬浮窗", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            installButton.Enabled = false;
            try
            {
                target = InstallationDirectory(Path.GetFullPath(target));
                Directory.CreateDirectory(target);
                PrepareTarget(target);
                status.Text = "正在解压运行文件…";
                string runtime = Path.Combine(target, "runtime");
                ExtractPayload(runtime);
                string cache = Path.Combine(target, "cache");
                Directory.CreateDirectory(cache);
                GrantUserAccess(cache);
                WriteInstalledLauncher(target);
                WriteUninstaller(target);
                RegisterUninstaller(target);
                CreateShortcut(target);
                status.Text = "安装完成。桌面快捷方式已创建。";
                DialogResult result = MessageBox.Show(
                    this, "安装完成，是否立即启动？", "心率悬浮窗",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                if (result == DialogResult.Yes)
                {
                    Process.Start(new ProcessStartInfo(Path.Combine(target, "心率悬浮窗.exe")) { UseShellExecute = true });
                }
                DialogResult = DialogResult.OK;
                Close();
            }
            catch (Exception ex)
            {
                installButton.Enabled = true;
                status.Text = "安装失败。";
                MessageBox.Show(this, "安装失败：\n\n" + ex.Message +
                    "\n\n安装器已经请求管理员权限；请确认目标磁盘可写。",
                    "安装心率悬浮窗", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static string InstallationDirectory(string selected)
        {
            string name = Path.GetFileName(selected.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            return string.Equals(name, "HeartRateMonitor", StringComparison.OrdinalIgnoreCase)
                ? selected
                : Path.Combine(selected, "HeartRateMonitor");
        }

        private static void PrepareTarget(string target)
        {
            string oldLauncher = Path.Combine(target, "HeartRateOverlayLauncher.exe");
            if (File.Exists(oldLauncher)) File.Delete(oldLauncher);
            string oldUninstaller = Path.Combine(target, "uninstall.exe");
            if (File.Exists(oldUninstaller)) File.Delete(oldUninstaller);
            string oldRootExe = Path.Combine(target, "心率悬浮窗.exe");
            if (File.Exists(oldRootExe)) File.Delete(oldRootExe);
            string oldInternal = Path.Combine(target, "_internal");
            if (Directory.Exists(oldInternal)) Directory.Delete(oldInternal, true);
            string oldRuntime = Path.Combine(target, "runtime");
            if (Directory.Exists(oldRuntime)) Directory.Delete(oldRuntime, true);
        }

        private static void ExtractPayload(string target)
        {
            using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadResource))
            {
                if (stream == null) throw new InvalidOperationException("安装文件缺少运行包。");
                using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string path = Path.GetFullPath(Path.Combine(target, entry.FullName));
                        if (!path.StartsWith(Path.GetFullPath(target) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("运行包包含无效路径。");
                        if (string.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(path); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(path));
                        entry.ExtractToFile(path, true);
                    }
                }
            }
        }

        private static void WriteInstalledLauncher(string target)
        {
            string path = Path.Combine(target, "心率悬浮窗.exe");
            using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream(LauncherResource))
            using (FileStream output = File.Create(path))
            {
                if (input == null) throw new InvalidOperationException("安装文件缺少启动器。");
                input.CopyTo(output);
            }
        }

        private static void CreateShortcut(string target)
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string shortcutPath = Path.Combine(desktop, "心率悬浮窗.lnk");
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(shellType);
            dynamic shortcut = shell.CreateShortcut(shortcutPath);
            shortcut.TargetPath = Path.Combine(target, "心率悬浮窗.exe");
            shortcut.WorkingDirectory = target;
            shortcut.IconLocation = Path.Combine(target, "心率悬浮窗.exe") + ",0";
            shortcut.Description = "心率悬浮窗";
            shortcut.Save();
        }

        private static void WriteUninstaller(string target)
        {
            string path = Path.Combine(target, "uninstall.exe");
            using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream(UninstallerResource))
            using (FileStream output = File.Create(path))
            {
                if (input == null) throw new InvalidOperationException("安装文件缺少卸载程序。");
                input.CopyTo(output);
            }
        }

        private static void RegisterUninstaller(string target)
        {
            using (RegistryKey key = Registry.LocalMachine.CreateSubKey(UninstallKey))
            {
                if (key == null) throw new InvalidOperationException("无法注册卸载信息。");
                string uninstall = Path.Combine(target, "uninstall.exe");
                key.SetValue("DisplayName", "心率悬浮窗");
                key.SetValue("DisplayVersion", "1.1.0");
                key.SetValue("Publisher", "W's Thing");
                key.SetValue("InstallLocation", target);
                key.SetValue("UninstallString", "\"" + uninstall + "\"");
                key.SetValue("DisplayIcon", Path.Combine(target, "心率悬浮窗.exe"));
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }

        private static void GrantUserAccess(string directory)
        {
            WindowsIdentity identity = WindowsIdentity.GetCurrent();
            if (identity.User == null) throw new InvalidOperationException("无法确定当前用户。");
            DirectoryInfo info = new DirectoryInfo(directory);
            DirectorySecurity security = info.GetAccessControl();
            FileSystemAccessRule rule = new FileSystemAccessRule(
                identity.User,
                FileSystemRights.Modify | FileSystemRights.ReadAndExecute |
                    FileSystemRights.ListDirectory | FileSystemRights.Read | FileSystemRights.Write,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None,
                AccessControlType.Allow);
            security.AddAccessRule(rule);
            info.SetAccessControl(security);
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }
}
