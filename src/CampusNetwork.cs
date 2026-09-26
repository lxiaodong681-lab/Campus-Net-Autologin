using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace CampusAutoLogin;

internal static class CampusNetwork
{
    // Observed JXNU access network. Deliberately do not treat arbitrary private IPs as campus.
    internal static bool IsCampusAddress(IPAddress address)
    {
        var bytes = address.GetAddressBytes();
        return address.AddressFamily == AddressFamily.InterNetwork && bytes[0] == 10 && (bytes[1] == 128 || bytes[1] == 129);
    }
    internal static IPAddress? CurrentAddress()
    {
        foreach (var adapter in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (adapter.OperationalStatus != OperationalStatus.Up ||
                (adapter.NetworkInterfaceType != NetworkInterfaceType.Ethernet && adapter.NetworkInterfaceType != NetworkInterfaceType.Wireless80211)) continue;
            var properties = adapter.GetIPProperties();
            if (!properties.GatewayAddresses.Any(g => IsCampusAddress(g.Address))) continue;
            var address = properties.UnicastAddresses.Select(a => a.Address).FirstOrDefault(IsCampusAddress);
            if (address != null) return address;
        }
        return null;
    }
    internal static SocketsHttpHandler CreateHandler() => new()
    {
        UseProxy = false,
        AllowAutoRedirect = false,
        PooledConnectionLifetime = TimeSpan.Zero,
        ConnectCallback = async (context, cancellation) =>
        {
            var address = CurrentAddress() ?? throw new IOException("Campus network unavailable.");
            var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            try
            {
                socket.Bind(new IPEndPoint(address, 0));
                await socket.ConnectAsync(context.DnsEndPoint, cancellation);
                return new NetworkStream(socket, ownsSocket: true);
            }
            catch { socket.Dispose(); throw; }
        }
    };
}
