using BlueArchiveAPI.NetworkModels;
using Microsoft.AspNetCore.Mvc;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BlueArchiveAPI.Models
{
    public class ServerPacket
    {
        /// <summary>
        /// Protocol name as string (required for official server compatibility)
        /// </summary>
        [JsonProperty("protocol")]
        public string Protocol { get; set; }
        
        /// <summary>
        /// JSON-encoded string containing the actual response payload
        /// </summary>
        [JsonProperty("packet")]
        public string Packet { get; set; }

        /// <summary>
        /// Creates a ServerPacket with string protocol name (preferred for new gateway format)
        /// </summary>
        /// <param name="protocol">Protocol name as string (e.g., "Account_Auth", "Queuing_GetTicketGL")</param>
        /// <param name="packet">JSON-encoded string containing the response payload</param>
        public ServerPacket(string protocol, string packet)
        {
            this.Protocol = protocol;
            this.Packet = packet;
        }

        /// <summary>
        /// Creates a ServerPacket with Protocol enum (for backward compatibility)
        /// </summary>
        /// <param name="protocol">Protocol enum value</param>
        /// <param name="packet">JSON-encoded string containing the response payload</param>
        public ServerPacket(Protocol protocol, string packet)
        {
            this.Protocol = protocol.ToString();
            this.Packet = packet;
        }

        /// <summary>
        /// Gets the protocol as Protocol enum if possible
        /// </summary>
        /// <returns>Protocol enum value or null if not parseable</returns>
        public Protocol? GetProtocolEnum()
        {
            if (Enum.TryParse<Protocol>(Protocol, true, out var result))
            {
                return result;
            }
            return null;
        }

        /// <summary>
        /// Creates a ServerPacket from a response object that has a Protocol property
        /// </summary>
        /// <param name="responseObject">Response object with Protocol property</param>
        /// <param name="serializerSettings">JSON serializer settings</param>
        /// <returns>ServerPacket instance</returns>
        public static ServerPacket FromResponse(object responseObject, JsonSerializerSettings? serializerSettings = null)
        {
            var protocolProperty = responseObject.GetType().GetProperty("Protocol");
            if (protocolProperty == null)
            {
                throw new ArgumentException("Response object must have a Protocol property", nameof(responseObject));
            }

            var protocolValue = protocolProperty.GetValue(responseObject);
            string protocolString;

            if (protocolValue is Protocol protocolEnum)
            {
                protocolString = protocolEnum.ToString();
            }
            else if (protocolValue is string protocolStr)
            {
                protocolString = protocolStr;
            }
            else
            {
                throw new ArgumentException($"Protocol property must be of type Protocol or string, got {protocolValue?.GetType()}", nameof(responseObject));
            }

            var packetJson = JsonConvert.SerializeObject(responseObject, Formatting.None, serializerSettings);
            return new ServerPacket(protocolString, packetJson);
        }
    }
}
