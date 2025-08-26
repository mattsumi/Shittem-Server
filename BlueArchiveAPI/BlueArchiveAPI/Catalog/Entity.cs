using System.Text.Json.Nodes;

namespace BlueArchiveAPI.Catalog;

public sealed class Entity
{
    public EntityType Type { get; init; }
    public int Id { get; init; }
    public string CanonicalName { get; init; } = "";
    public string? DevName { get; init; }
    public int? Rarity { get; init; }
    public JsonObject Meta { get; init; } = new();
}
