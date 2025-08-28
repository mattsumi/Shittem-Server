using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace BlueArchiveAPI.Catalog
{
    public interface IEntityCatalog
    {
        IReadOnlyList<string> GetTypes();
        Task<IReadOnlyList<EntityDto>> GetEntitiesAsync(string type, CancellationToken ct = default);
        bool TryGetById(EntityType type, int id, [NotNullWhen(true)] out Entity? entity);
        bool TryGetIdByName(EntityType type, string nameOrAlias, out int id);
        IEnumerable<Entity> Search(EntityType type, string query, int limit = 20);
    }
}
