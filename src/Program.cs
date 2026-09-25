using System.Diagnostics;
using System.Text.RegularExpressions;

namespace CampusAutoLogin;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        // Verify the packaged runtime and WinForms without reading credentials or using the network.
        if (args.Contains("--smoke-test"))
        {
            ApplicationConfiguration.Initialize();
            using var form = new Form();
            _ = form.Handle;
            return;
        }
        using var mutex = new Mutex(true, @"Local\JxnuCampusAutoLogin", out var first);
        if (!first) { if (!args.Contains("--background")) MessageBox.Show("程序已在运行，请双击右下角托盘中的校园网图标打开设置。", "校园网自动登录"); return; }
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm(args.Contains("--background")));
    }
}

internal sealed class MainForm : Form
{
    private readonly TextBox account = new() { Width = 380, PlaceholderText = "校园网账号（不需要填写 @cmcc）" };
    private readonly TextBox password = new() { Width = 380, UseSystemPasswordChar = true, PlaceholderText = "校园网密码" };
    private readonly CheckBox startup = new() { Text = "登录 Windows 后自动运行", AutoSize = true };
    private readonly Label status = new() { Text = "正在检查校园网…", AutoSize = false, Width = 410, Height = 80 };
    private readonly Button save = new() { Text = "保存并启用", Width = 180, Height = 38 };
    private readonly Button retry = new() { Text = "立即检查 / 重试", Width = 180, Height = 38 };
    private readonly NotifyIcon tray;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 1000 };
    private readonly CancellationTokenSource stop = new();
    private readonly SrunClient client = new();
    private readonly RetryPolicy policy = new();
    private Settings? settings;
    private DateTime next = DateTime.MinValue;
    private bool busy, exiting;
    private readonly bool background;
    private string lastMessage = "";

    internal MainForm(bool background)
    {
        this.background = background;
        Text = "江西师大 · 校园网自动登录";
        Font = new Font("Microsoft YaHei UI", 10F);
        ClientSize = new Size(480, 480);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Icon = SystemIcons.Application;
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(26), AutoScroll = true };
        Controls.Add(layout);
        layout.Controls.Add(new Label { Text = "校园网，开机自动登录", AutoSize = true, Font = new Font(Font.FontFamily, 17, FontStyle.Bold), Margin = new Padding(0, 0, 0, 10) });
        layout.Controls.Add(new Label { Text = "江西师范大学  /  中国移动", AutoSize = true, Margin = new Padding(0, 0, 0, 18) });
        layout.Controls.Add(account);
        password.Margin = new Padding(3, 12, 3, 8);
        layout.Controls.Add(password);
        var show = new CheckBox { Text = "显示密码", AutoSize = true };
        show.CheckedChanged += (_, _) => password.UseSystemPasswordChar = !show.Checked;
        layout.Controls.Add(show);
        layout.Controls.Add(startup);
        var buttons = new FlowLayoutPanel { Width = 410, Height = 52, Margin = new Padding(0, 14, 0, 8) };
        buttons.Controls.Add(save); buttons.Controls.Add(retry); layout.Controls.Add(buttons);
        layout.Controls.Add(status);
        layout.Controls.Add(new Label { Text = "关闭窗口后仍在托盘运行。\n密码由 Windows 加密，仅当前 Windows 用户可解密。", AutoSize = true, ForeColor = Color.DimGray });
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开设置", null, (_, _) => ShowWindow());
        menu.Items.Add("立即检查", null, (_, _) => { policy.ConfigurationChanged(); next = DateTime.MinValue; });
        menu.Items.Add("查看日志", null, (_, _) => {
            var path = Path.Combine(Storage.DirectoryPath, "activity.log");
            if (File.Exists(path)) Process.Start(new ProcessStartInfo("notepad.exe", $"\"{path}\"") { UseShellExecute = true });
        });
        menu.Items.Add("退出", null, (_, _) => { exiting = true; Close(); });
        tray = new NotifyIcon { Icon = SystemIcons.Application, Text = "江西师大校园网自动登录", Visible = true, ContextMenuStrip = menu };
        tray.DoubleClick += (_, _) => ShowWindow();
        try
        {
            settings = Storage.Load();
            if (settings != null) { account.Text = settings.Account; _ = Storage.Unprotect(settings.Secret); password.PlaceholderText = "已保存密码；留空保留原密码"; }
            startup.Checked = settings == null || Storage.AutoStart;
        }
        catch { settings = null; SetStatus("无法读取原配置，请重新填写账号密码。"); }
        save.Click += (_, _) => SaveSettings();
        retry.Click += (_, _) => { policy.ConfigurationChanged(); next = DateTime.MinValue; };
        timer.Tick += async (_, _) => { if (!busy && DateTime.UtcNow >= next) await Check(); };
        timer.Start();
        FormClosing += (_, e) => { if (!exiting && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
        FormClosed += (_, _) => { stop.Cancel(); timer.Dispose(); tray.Dispose(); client.Dispose(); };
    }
    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        if (background) Hide();
        if (background && settings == null) tray.ShowBalloonTip(7000, "校园网尚未配置", "双击托盘图标填写账号密码。", ToolTipIcon.Info);
    }
    private void ShowWindow() { Show(); WindowState = FormWindowState.Normal; Activate(); }
    private void SaveSettings()
    {
        try
        {
            if (busy) return;
            var name = SrunProtocol.Account(account.Text);
            if (password.Text.Length == 0 && (settings == null || name != settings.Account)) throw new ArgumentException("请输入该账号的密码。");
            var secret = password.Text.Length > 0 ? password.Text : Storage.Unprotect(settings!.Secret);
            Storage.Save(name, secret);
            settings = Storage.Load();
            Storage.AutoStart = startup.Checked;
            account.Text = name; password.Clear(); password.PlaceholderText = "已保存密码；留空保留原密码";
            policy.ConfigurationChanged(); next = DateTime.MinValue;
            SetStatus("已加密保存，自动登录已启用。");
        }
        catch (ArgumentException ex) { MessageBox.Show(this, ex.Message, "请检查输入"); }
        catch { MessageBox.Show(this, "保存失败，请检查配置目录权限后重试。", "保存失败"); }
    }
    private void SetStatus(string message)
    {
        if (exiting || IsDisposed) return;
        status.Text = message;
        if (message != lastMessage) { Storage.Log(message); lastMessage = message; }
        tray.Text = "校园网：" + (message.Length > 52 ? message[..52] : message);
    }
    private async Task Check()
    {
        busy = true; save.Enabled = false; retry.Enabled = false;
        try
        {
            var online = await client.Status(stop.Token);
            var error = SrunProtocol.Field(online, "error");
            if (error == "ok" && SrunProtocol.Field(online, "user_name").Length > 0)
            {
                policy.Connected(); next = DateTime.UtcNow.AddSeconds(60);
                if (settings == null)
                {
                    var current = SrunProtocol.Field(online, "user_name");
                    if (account.Text.Length == 0 && current.EndsWith("@cmcc")) account.Text = current;
                    SetStatus("校园网已在线。填写并保存密码后，才能自动重新登录。");
                }
                else SetStatus(policy.CredentialsRejected ? "校园网已在线；自动登录已暂停，请检查账号后点击重试。" : "校园网已在线，正在后台守候。");
                return;
            }
            if (error != "not_online_error") throw new InvalidDataException("无法确认校园网状态。");
            if (settings == null) { SetStatus("请先填写账号和密码，点击“保存并启用”。"); next = DateTime.UtcNow.AddSeconds(30); return; }
            if (policy.CredentialsRejected) { next = DateTime.UtcNow.AddMinutes(1); return; }
            SetStatus("校园网未登录，正在自动认证…");
            var result = await client.Login(settings.Account, Storage.Unprotect(settings.Secret), stop.Token);
            if (SrunProtocol.Field(result, "error") == "ok")
            {
                var verified = await client.Status(stop.Token);
                if (SrunProtocol.Field(verified, "error") == "ok" && SrunProtocol.Field(verified, "user_name").Length > 0)
                {
                    policy.Connected(); SetStatus("自动登录成功，校园网已在线。"); next = DateTime.UtcNow.AddSeconds(60); return;
                }
                throw new IOException("等待在线状态更新。");
            }
            var code = SrunProtocol.Field(result, "ecode");
            var detail = SrunProtocol.Field(result, "error") + " " + SrunProtocol.Field(result, "error_msg");
            // Explicit account failures need human attention. Service/outage errors keep backing off.
            if (new[] { "E2531", "E2533", "E2534", "E2536", "E2553", "E2601", "E2602", "E2606", "E2607", "E2611", "E2613", "E2614", "E2615", "E2616", "E2621", "E6501", "E6506", "E6508", "E6510", "E6516", "E6517", "E6520", "E3001" }.Contains(code)
                || detail.Contains("password", StringComparison.OrdinalIgnoreCase) || detail.Contains("user_not_exist"))
            {
                policy.AuthenticationRejected();
                var safeCode = Regex.IsMatch(code, "^E[0-9]{4}$") ? code : "账号认证失败";
                SetStatus($"自动登录已暂停（{safeCode}）。请检查账号、密码或欠费状态后点击重试。");
                tray.ShowBalloonTip(10000, "校园网需要处理", status.Text, ToolTipIcon.Warning);
                next = DateTime.UtcNow.AddMinutes(1); return;
            }
            throw new IOException("认证服务暂未恢复。");
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        catch
        {
            policy.NetworkFailure(); next = DateTime.UtcNow + policy.NextDelay;
            SetStatus($"等待校园网恢复，{(int)policy.NextDelay.TotalSeconds} 秒后重试。");
        }
        finally { busy = false; if (!IsDisposed) { save.Enabled = true; retry.Enabled = true; } }
    }
}
