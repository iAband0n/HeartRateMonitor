using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("心率悬浮窗")]
[assembly: AssemblyDescription("HeartRateOverlay single-file launcher")]
[assembly: AssemblyProduct("心率悬浮窗")]
[assembly: AssemblyCompany("W's Thing")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace HeartRateOverlayLauncher
{
    internal static class Program
    {
        private const string AppVersion = "1.1.0";
        private const string PayloadResource = "payload.zip";
        private const string LauncherTitle = "心率悬浮窗";

        [STAThread]
        private static int Main(string[] args)
        {
            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                string runtimeRoot = ResolveRuntimeRoot();
                string versionDir = Path.Combine(runtimeRoot, "v" + AppVersion);
                string appExe = Path.Combine(versionDir, "心率悬浮窗.exe");
                string readyMarker = Path.Combine(versionDir, ".ready");
                string dataRoot = ResolveDataRoot();

                if (!(File.Exists(appExe) && File.Exists(readyMarker)))
                {
                    ExtractPayload(runtimeRoot, versionDir);
                }

                ProcessStartInfo startInfo = new ProcessStartInfo(appExe);
                startInfo.WorkingDirectory = versionDir;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;
                startInfo.EnvironmentVariables["HEART_RATE_OVERLAY_DATA_DIR"] = dataRoot;
                if (args.Length > 0)
                {
                    startInfo.Arguments = JoinQuoted(args);
                }

                using (Process child = Process.Start(startInfo))
                {
                    if (child == null)
                    {
                        throw new InvalidOperationException("无法启动心率悬浮窗主程序。");
                    }
                    child.WaitForExit();
                    return child.ExitCode;
                }
            }
            catch (Exception ex)
            {
                try
                {
                    string logDir = ResolveAppRoot();
                    Directory.CreateDirectory(logDir);
                    File.AppendAllText(
                        Path.Combine(logDir, "launcher.log"),
                        DateTime.Now.ToString("s") + "  " + ex + Environment.NewLine);
                }
                catch
                {
                    // Ignore logging failures.
                }

                MessageBox.Show(
                    "程序启动失败：\n\n" + ex.Message +
                    "\n\n请确认系统用户目录（%LOCALAPPDATA%）可写后重试。",
                    LauncherTitle,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
            }
        }

        private static string ResolveRuntimeRoot()
        {
            return EnsureDirectory(Path.Combine(ResolveAppRoot(), "runtime"));
        }

        private static string ResolveDataRoot()
        {
            return EnsureDirectory(Path.Combine(ResolveAppRoot(), "data"));
        }

        private static string ResolveAppRoot()
        {
            // DoNotVerify resolves the known folder even before it exists.
            string localAppData = Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData,
                Environment.SpecialFolderOption.DoNotVerify);
            if (string.IsNullOrWhiteSpace(localAppData))
            {
                localAppData = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            }
            // Never allow an empty or relative base to create folders beside the exe.
            if (string.IsNullOrWhiteSpace(localAppData) ||
                !(Path.IsPathRooted(localAppData) &&
                  (localAppData.StartsWith(@"\\") ||
                   (localAppData.Length >= 3 && localAppData[1] == ':' &&
                    (localAppData[2] == '\\' || localAppData[2] == '/')))))
            {
                throw new IOException("无法确定当前用户的本地应用数据目录（%LOCALAPPDATA%）。");
            }
            string preferred = Path.Combine(localAppData, "HeartRateOverlay");
            if (CanUseAppRoot(preferred))
            {
                return preferred;
            }

            // A previous elevated launch may have left files owned by an
            // administrator. Keep the normal user independent of that ACL.
            string userName = Environment.UserName;
            string safeName = new string(userName.Select(c =>
                char.IsLetterOrDigit(c) || c == '-' || c == '_' ? c : '_').ToArray());
            string perUser = Path.Combine(localAppData, "HeartRateOverlay-" + safeName);
            if (CanUseAppRoot(perUser))
            {
                return perUser;
            }

            string tempRoot = Path.Combine(Path.GetTempPath(), "HeartRateOverlay-" + safeName);
            if (CanUseAppRoot(tempRoot))
            {
                return tempRoot;
            }
            throw new UnauthorizedAccessException(
                "无法创建当前用户可写的运行目录。请检查 %LOCALAPPDATA% 的权限。");
        }

        private static string EnsureDirectory(string path)
        {
            Directory.CreateDirectory(path);
            return path;
        }

        private static bool CanUseAppRoot(string root)
        {
            try
            {
                if (TryWritableDirectory(Path.Combine(root, "runtime")) == null ||
                    TryWritableDirectory(Path.Combine(root, "data")) == null)
                {
                    return false;
                }
                string history = Path.Combine(root, "data", "history.sqlite3");
                if (File.Exists(history))
                {
                    using (FileStream stream = new FileStream(
                        history, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite))
                    {
                    }
                }
                return true;
            }
            catch (UnauthorizedAccessException)
            {
                return false;
            }
            catch (IOException)
            {
                return false;
            }
        }

        private static string TryWritableDirectory(string path)
        {
            try
            {
                Directory.CreateDirectory(path);
                string probe = Path.Combine(path, ".write-test-" + Guid.NewGuid().ToString("N"));
                using (FileStream stream = new FileStream(
                    probe, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    stream.WriteByte(0);
                }
                File.Delete(probe);
                return path;
            }
            catch (UnauthorizedAccessException)
            {
                return null;
            }
            catch (IOException)
            {
                return null;
            }
        }

        private static void ExtractPayload(string runtimeRoot, string versionDir)
        {
            Directory.CreateDirectory(runtimeRoot);
            try
            {
                if (Directory.Exists(versionDir))
                {
                    Directory.Delete(versionDir, true);
                }
                Directory.CreateDirectory(versionDir);

                Assembly assembly = Assembly.GetExecutingAssembly();
                using (Stream stream = assembly.GetManifestResourceStream(PayloadResource))
                {
                    if (stream == null)
                    {
                        throw new InvalidOperationException("内置运行文件缺失：" + PayloadResource);
                    }
                    using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
                    {
                        archive.ExtractToDirectory(versionDir);
                    }
                }

                File.WriteAllText(
                    Path.Combine(versionDir, ".ready"),
                    DateTime.UtcNow.ToString("o"));
            }
            catch
            {
                try
                {
                    if (Directory.Exists(versionDir))
                    {
                        Directory.Delete(versionDir, true);
                    }
                }
                catch
                {
                }
                throw;
            }
        }

        private static string JoinQuoted(string[] args)
        {
            return string.Join(" ", args.Select(Quote).ToArray());
        }

        private static string Quote(string value)
        {
            if (value == null)
            {
                return "\"\"";
            }
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }
    }
}

