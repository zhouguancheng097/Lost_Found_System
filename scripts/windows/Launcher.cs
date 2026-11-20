using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;
[assembly: AssemblyTitle("拾光 · 失物招领系统")]
[assembly: AssemblyProduct("拾光 · 失物招领系统")]
[assembly: AssemblyVersion("1.1.1.0")]
[assembly: AssemblyFileVersion("1.1.1.0")]
internal static class Launcher
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string action = "Start";
        bool quiet = false;
        bool noBrowser = false;
        foreach (string arg in args)
        {
            if (arg == "--stop") action = "Stop";
            else if (arg == "--data") action = "Data";
            else if (arg == "--admin") action = "Admin";
            else if (arg == "--quiet") quiet = true;
            else if (arg == "--demo") action = "Demo";
            else if (arg == "--no-browser") noBrowser = true;
            else { if (!quiet) MessageBox.Show("启动参数不正确。", "拾光"); return 2; }
        }
        string script = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "scripts", "desktop.ps1");
        string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        string error = "";
        string errorFile = Path.Combine(Path.GetTempPath(), "Shiguang-" + Guid.NewGuid().ToString("N") + ".error.txt");
        Func<int> execute = delegate
        {
            try
            {
                // Background services can inherit redirected pipe handles. Waiting for
                // their EOF keeps the startup form open for the service lifetime.
                // Use a per-operation error file and wait only for the script itself.
                string arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\" -Action " + action + " -NoUI -NoBrowser -ErrorFile \"" + errorFile + "\"";
                var info = new ProcessStartInfo(powershell, arguments);
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                using (Process process = Process.Start(info))
                {
                    process.WaitForExit();
                    if (File.Exists(errorFile)) error = File.ReadAllText(errorFile, System.Text.Encoding.UTF8).Trim();
                    return process.ExitCode;
                }
            }
            catch (Exception ex) { error = ex.Message; return 1; }
            finally { try { if (File.Exists(errorFile)) File.Delete(errorFile); } catch { } }
        };
        if (quiet) return execute();
        int result = 1;
        using (var form = new Form())
        {
            form.Text = "拾光 · 失物招领系统";
            form.ClientSize = new Size(460, 150);
            form.FormBorderStyle = FormBorderStyle.FixedDialog;
            form.StartPosition = FormStartPosition.CenterScreen;
            form.MaximizeBox = false;
            form.MinimizeBox = false;
            form.ControlBox = false;
            form.BackColor = Color.FromArgb(250, 246, 238);
            var label = new Label { Left = 24, Top = 25, Width = 412, Height = 55, Font = new Font("Microsoft YaHei UI", 11) };
            label.Text = action == "Start" ? "正在启动拾光和 AI 检索，请稍候…\r\n启动完成后会自动打开浏览器。" : action == "Stop" ? "正在停止拾光系统…" : action == "Demo" ? "正在准备虚构测试账号和物品…" : "正在打开…";
            var progress = new ProgressBar { Left = 24, Top = 100, Width = 412, Height = 16, Style = ProgressBarStyle.Marquee };
            form.Controls.Add(label);
            form.Controls.Add(progress);
            form.Shown += async delegate
            {
                result = await Task.Run(execute);
                form.Close();
            };
            Application.Run(form);
        }
        if (result != 0) MessageBox.Show(error.Length > 0 ? error : "操作失败，请打开数据目录检查日志。", "拾光 · 失物招领系统", MessageBoxButtons.OK, MessageBoxIcon.Error);
        else if (action == "Start" && !noBrowser)
        {
            try { Process.Start(new ProcessStartInfo("http://127.0.0.1:8080") { UseShellExecute = true }); }
            catch { MessageBox.Show("系统已启动。请在浏览器中打开 http://127.0.0.1:8080", "拾光"); }
        }
        else if (action == "Demo") MessageBox.Show("测试数据已准备完成。\r\n普通测试账号初始密码：Demo123456!\r\ndemo_finder、demo_owner、demo_claimant、demo_delete 可登录。\r\ndemo_banned 初始为封禁状态。\r\n重复初始化保留已修改的密码与业务。\r\n账号清单保存在数据目录 data 中。", "拾光", MessageBoxButtons.OK, MessageBoxIcon.Information);
        else if (action == "Stop") MessageBox.Show("拾光系统已停止。", "拾光", MessageBoxButtons.OK, MessageBoxIcon.Information);
        return result;
    }
}
