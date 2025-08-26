using Newtonsoft.Json;

namespace BlueArchiveAPI.Models
{
    public class ConnectionGroup
    {
        public string Name { get; set; } = string.Empty;

        [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
        public string ApiUrl { get; set; } = string.Empty;

        [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
        public string GatewayUrl { get; set; } = string.Empty;

        [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
        public bool? DisableWebviewBanner { get; set; }

        [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
        public ConnectionGroup[] OverrideConnectionGroups { get; set; } = System.Array.Empty<ConnectionGroup>();
    }
}
