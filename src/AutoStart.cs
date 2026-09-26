using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32;

namespace CampusAutoLogin;

internal static class AutoStart
{
    internal static string TaskName => "JxnuCampusAutoLogin-" + WindowsIdentity.GetCurrent().User!.Value;
    private static dynamic Connect()
    {
        dynamic service = Activator.CreateInstance(Type.GetTypeFromProgID("Schedule.Service")!)!;
        service.Connect();
        return service;
    }
    internal static bool Enabled
    {
        get
        {
            try { dynamic service = Connect(); return (bool)service.GetFolder(@"\").GetTask(TaskName).Enabled; }
            catch (COMException) { return false; }
        }
        set
        {
            dynamic service = Connect();
            dynamic folder = service.GetFolder(@"\");
            if (value)
            {
                var sid = WindowsIdentity.GetCurrent().User!.Value;
                dynamic task = service.NewTask(0);
                task.RegistrationInfo.Description = "江西师大移动校园网：登录后等待网络，识别校园网后自动认证。";
                task.Principal.UserId = sid;
                task.Principal.LogonType = 3; // InteractiveToken: no stored Windows password.
                task.Principal.RunLevel = 0;
                dynamic trigger = task.Triggers.Create(9); // Logon, this user only.
                trigger.UserId = sid;
                trigger.Delay = "PT15S";
                task.Settings.Enabled = true;
                task.Settings.StartWhenAvailable = true;
                task.Settings.DisallowStartIfOnBatteries = false;
                task.Settings.StopIfGoingOnBatteries = false;
                task.Settings.ExecutionTimeLimit = "PT0S";
                task.Settings.MultipleInstances = 2; // IgnoreNew.
                task.Settings.RestartCount = 3;
                task.Settings.RestartInterval = "PT1M";
                dynamic action = task.Actions.Create(0);
                action.Path = Environment.ProcessPath!;
                action.Arguments = "--background";
                action.WorkingDirectory = AppContext.BaseDirectory;
                folder.RegisterTaskDefinition(TaskName, task, 6, sid, null, 3, null);
            }
            else
            {
                try { folder.DeleteTask(TaskName, 0); }
                catch (COMException e) when ((uint)e.HResult == 0x80070002) { }
            }
            // Clean the legacy entry in this process's registry view, if present.
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true);
            key?.DeleteValue("JxnuCampusAutoLogin", false);
        }
    }
}
