using System.Net;
using System.Text.Json;
using CampusAutoLogin;

var count = 0;
void Assert(bool test, string description) { if (!test) throw new Exception(description); count++; }
foreach (var vector in JsonDocument.Parse(File.ReadAllText("tests/vectors.json")).RootElement.EnumerateArray())
{
    string V(string key) => vector.GetProperty(key).GetString()!;
    var fields = SrunProtocol.LoginFields(V("account"), V("password"), V("ip"), V("token"));
    Assert(fields["info"] == V("info"), "Portal encryption mismatch");
    Assert(fields["password"] == "{MD5}" + V("md5"), "HMAC mismatch");
    Assert(fields["chksum"] == V("chksum"), "Checksum mismatch");
}
Assert(SrunProtocol.Account(" 123 ") == "123@cmcc", "Mobile suffix");
Assert(SrunProtocol.Account("123@cmcc") == "123@cmcc", "No duplicate suffix");
try { SrunProtocol.Account("123@ctcc"); throw new Exception("Wrong operator accepted"); } catch (ArgumentException) { count++; }
Assert(SrunProtocol.Field(SrunProtocol.Parse("campus({\"error\":\"ok\"});"), "error") == "ok", "JSONP");
Assert(SrunProtocol.Field(SrunProtocol.Parse("{\"error\":\"not_online_error\"}"), "error") == "not_online_error", "Offline status");
try { SrunProtocol.Parse("<html>redirect</html>"); throw new Exception("HTML accepted as JSON"); } catch (JsonException) { count++; }
var policy = new RetryPolicy();
for (var i = 0; i < 100; i++) policy.NetworkFailure();
Assert(policy.NextDelay == TimeSpan.FromMinutes(5), "Bounded backoff");
policy.AuthenticationRejected(); policy.Connected();
Assert(policy.CredentialsRejected, "Online status must not clear invalid credentials");
policy.ConfigurationChanged(); Assert(!policy.CredentialsRejected, "Manual retry");
const string secret = "synthetic-password-中文123";
var encrypted = Storage.Protect(secret);
Assert(!encrypted.Contains(secret) && Storage.Unprotect(encrypted) == secret, "Windows DPAPI round trip");
var handler = new FakeHandler();
using (var client = new SrunClient(handler))
{
    var result = await client.Login("test@cmcc", "synthetic & + password", CancellationToken.None);
    Assert(SrunProtocol.Field(result,"error") == "ok", "Mock login flow");
    Assert(handler.Paths.Count == 3 && handler.Paths[0].StartsWith("/srun_portal_pc") && handler.Paths[1].StartsWith("/cgi-bin/get_challenge") && handler.Paths[2].StartsWith("/cgi-bin/srun_portal"), "Handshake order");
    Assert(handler.Paths[2].Contains("ip=10.128.88.99") && !handler.Paths[2].Contains("synthetic"), "Fresh IP and encoded credentials");
}
handler = new FakeHandler { ChangedPortal = true };
using (var client = new SrunClient(handler))
{
    try { await client.Login("test@cmcc", "test", CancellationToken.None); throw new Exception("Changed portal accepted"); }
    catch (InvalidDataException) { Assert(handler.Paths.Count == 1, "No credentials sent to changed portal"); }
}
if (args.Contains("--live"))
{
    using var live = new SrunClient();
    var state = await live.Status(CancellationToken.None);
    Assert(SrunProtocol.Field(state,"error") == "ok", "Live school status");
    Console.WriteLine("LIVE: campus server confirms online (read-only; no logout/login requests).");
}
Console.WriteLine($"PASS: {count} assertions.");

sealed class FakeHandler : HttpMessageHandler
{
    internal List<string> Paths = new();
    internal bool ChangedPortal;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var path = request.RequestUri!.PathAndQuery; Paths.Add(path);
        var body = path.StartsWith("/srun_portal_pc") ? (ChangedPortal ? "unrelated page" : "self.jxnu.edu.cn @cmcc CONFIG = { ip: \"10.128.88.99\" }")
            : path.StartsWith("/cgi-bin/get_challenge") ? "campus({\"error\":\"ok\",\"challenge\":\"0123456789abcdef0123456789abcdef\"})" : "campus({\"error\":\"ok\"})";
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body) });
    }
}
