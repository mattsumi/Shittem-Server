namespace BlueArchiveAPI.Catalog;

public interface IEntityCatalog
{
    bool TryGetById(EntityType type, int id, out Entity entity);
    bool TryGetIdByName(EntityType type, string nameOrAlias, out int id);
    IEnumerable<Entity> Search(EntityType type, string query, int limit = 20);
}
