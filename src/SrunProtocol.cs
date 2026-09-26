using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CampusAutoLogin;

internal static class SrunProtocol
{
    internal static string Account(string value)
    {
        value = value.Trim();
        if (value.Length == 0 || value.Any(char.IsWhiteSpace)) throw new ArgumentException("请输入校园网账号。");
        if (value.Contains('@') && !value.EndsWith("@cmcc", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("本程序配置为移动，请输入不带后缀的账号，或使用 @cmcc 后缀。");
        return value.EndsWith("@cmcc", StringComparison.OrdinalIgnoreCase) ? value[..^5] + "@cmcc" : value + "@cmcc";
    }

    internal static Dictionary<string, string> LoginFields(string account, string password, string ip, string token)
    {
        var info = JsonSerializer.Serialize(new { username = account, password, ip, acid = "1", enc_ver = "srun_bx1" },
            new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        var encrypted = Encode(info, token);
        var md5 = Convert.ToHexString(HMACMD5.HashData(Encoding.UTF8.GetBytes(token), Encoding.UTF8.GetBytes(password))).ToLowerInvariant();
        var checksum = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(
            token + account + token + md5 + token + "1" + token + ip + token + "200" + token + "1" + token + encrypted))).ToLowerInvariant();
        return new()
        {
            ["action"] = "login", ["username"] = account, ["password"] = "{MD5}" + md5,
            ["ac_id"] = "1", ["ip"] = ip, ["info"] = encrypted, ["chksum"] = checksum,
            ["n"] = "200", ["type"] = "1", ["os"] = "Windows", ["name"] = "Windows", ["double_stack"] = "0"
        };
    }

    internal static string Encode(string input, string key)
    {
        if (input.Length == 0) return "{SRBX1}";
        static uint[] Words(string s, bool length)
        {
            var words = new uint[(s.Length + 3) / 4 + (length ? 1 : 0)];
            for (var i = 0; i < s.Length; i++) words[i / 4] |= (uint)s[i] << ((i % 4) * 8);
            if (length) words[^1] = (uint)s.Length;
            return words;
        }
        var v = Words(input, true);
        var k = Words(key, false);
        if (k.Length < 4) Array.Resize(ref k, 4);
        var n = v.Length - 1;
        uint z = v[n], y, sum = 0;
        unchecked
        {
            for (var q = 6 + 52 / v.Length; q > 0; q--)
            {
                sum += 0x9E3779B9;
                var e = (sum >> 2) & 3;
                for (var p = 0; p <= n; p++)
                {
                    y = v[p == n ? 0 : p + 1];
                    var m = (z >> 5) ^ (y << 2);
                    m += (y >> 3) ^ (z << 4) ^ (sum ^ y);
                    m += k[(p & 3) ^ (int)e] ^ z;
                    z = v[p] += m;
                }
            }
        }
        var bytes = new byte[v.Length * 4];
        for (var i = 0; i < bytes.Length; i++) bytes[i] = (byte)(v[i / 4] >> (i % 4 * 8));
        const string standard = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        const string alphabet = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA";
        return "{SRBX1}" + new string(Convert.ToBase64String(bytes).Select(c => c == '=' ? c : alphabet[standard.IndexOf(c)]).ToArray());
    }

    internal static JsonElement Parse(string text)
    {
        text = text.Trim();
        if (text.StartsWith("campus(") && Regex.IsMatch(text, @"\)\s*;?$"))
            text = Regex.Replace(text[7..], @"\)\s*;?$", "");
        using var doc = JsonDocument.Parse(text);
        return doc.RootElement.Clone();
    }
    internal static string Field(JsonElement obj, string name) => obj.TryGetProperty(name, out var v) ? v.ToString() : "";
}

internal sealed class SrunClient : IDisposable
{
    private readonly HttpClient http;
    internal SrunClient(HttpMessageHandler? handler = null)
    {
        http = new HttpClient(handler ?? CampusNetwork.CreateHandler())
        { BaseAddress = new Uri("http://172.17.1.2"), Timeout = TimeSpan.FromSeconds(12) };
    }

    internal async Task<JsonElement> Request(string path, Dictionary<string, string>? fields, CancellationToken ct)
    {
        fields ??= new();
        fields["callback"] = "campus";
        fields["_"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString();
        var query = string.Join("&", fields.Select(p => Uri.EscapeDataString(p.Key) + "=" + Uri.EscapeDataString(p.Value)));
        using var response = await http.GetAsync(path + "?" + query, ct);
        response.EnsureSuccessStatusCode();
        return SrunProtocol.Parse(await response.Content.ReadAsStringAsync(ct));
    }
    internal Task<JsonElement> Status(CancellationToken ct) => Request("/cgi-bin/rad_user_info", null, ct);

    internal async Task<JsonElement> Login(string account, string password, CancellationToken ct)
    {
        // Read a fresh address from the actual school portal, never a cached adapter address.
        using var page = await http.GetAsync("/srun_portal_pc?ac_id=1&theme=pro", ct);
        page.EnsureSuccessStatusCode();
        var html = await page.Content.ReadAsStringAsync(ct);
        if (!html.Contains("self.jxnu.edu.cn") || !html.Contains("@cmcc")) throw new InvalidDataException("校园网登录页发生变化，已停止提交账号。");
        var match = Regex.Match(html, "\\bip\\s*:\\s*\"([0-9.]+)\"");
        if (!match.Success || !IPAddress.TryParse(match.Groups[1].Value, out var address) || address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork)
            throw new InvalidDataException("暂时无法获取校园网 IP。");
        var ip = address.ToString();
        var challenge = await Request("/cgi-bin/get_challenge", new() { ["username"] = account, ["ip"] = ip }, ct);
        var token = SrunProtocol.Field(challenge, "challenge");
        if (SrunProtocol.Field(challenge, "error") != "ok" || !Regex.IsMatch(token, "^[a-zA-Z0-9]{16,128}$"))
            throw new InvalidDataException("认证服务器暂时未提供有效挑战码。");
        return await Request("/cgi-bin/srun_portal", SrunProtocol.LoginFields(account, password, ip, token), ct);
    }
    public void Dispose() => http.Dispose();
}
