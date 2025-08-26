using BlueArchiveAPI.NetworkModels;
using Newtonsoft.Json;

namespace BlueArchiveAPI.Gateway.Models
{
    public class ServerPacket
    {
        [JsonProperty("protocol")]
        public Protocol Protocol { get; set; }

        [JsonProperty("packet")]
        public string Packet { get; set; } = "{}";

        public ServerPacket() { }

        public ServerPacket(Protocol protocol, string packet)
        {
            Protocol = protocol;
            Packet = string.IsNullOrWhiteSpace(packet) ? "{}" : packet;
        }
    }
}