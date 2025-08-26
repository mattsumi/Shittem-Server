using BlueArchiveAPI.NetworkModels;
using Newtonsoft.Json;

namespace BlueArchiveAPI.Handlers
{

    public abstract class BaseHandler<TRequest, TResponse> : IHandler
        where TRequest : RequestPacket, IRequest<TResponse>
        where TResponse : ResponsePacket, IResponse<TRequest>
    {
        protected abstract Task<TResponse> Handle(TRequest request);

        public Protocol RequestProtocol { get; }
        public Protocol ResponseProtocol { get; }
        
        protected BaseHandler()
        {
            RequestProtocol = Activator.CreateInstance<TRequest>().Protocol;
            ResponseProtocol = Activator.CreateInstance<TResponse>().Protocol;
        }

        public async Task<byte[]> Handle(string packet)
        {
            var json = Utils.DecryptRequestPacket(packet);
            var req = JsonConvert.DeserializeObject<TRequest>(json);
            if (req == null)
            {
                throw new JsonSerializationException($"Failed to deserialize {typeof(TRequest).Name} from packet");
            }

            var res = await Handle(req);
            if (res == null)
            {
                throw new InvalidOperationException($"Handler returned null {typeof(TResponse).Name}");
            }

            res.ServerTimeTicks = DateTime.Now.Ticks;
            res.SessionKey ??= req.SessionKey;

            return Utils.EncryptResponsePacket(res, ResponseProtocol);
        }
    }
}
