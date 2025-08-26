using BlueArchiveAPI.Catalog;
using Microsoft.AspNetCore.Mvc;

namespace BlueArchiveAPI.Controllers;

[ApiController]
[Route("admin")]
public sealed class LookupController : ControllerBase
{
    private readonly IEntityCatalog _cat;

    public LookupController(IEntityCatalog cat) => _cat = cat;

    [HttpGet("resolve")]
    public IActionResult Resolve([FromQuery] EntityType type, [FromQuery] int id)
    {
        if (!_cat.TryGetById(type, id, out var e))
            return NotFound(new { error = "not_found", type = (int)type, id });

        return Ok(new {
            type = (int)e.Type,
            id = e.Id,
            name = e.CanonicalName,
            dev = e.DevName,
            rarity = e.Rarity,
            meta = e.Meta
        });
    }

    [HttpGet("lookup")]
    public IActionResult Lookup([FromQuery] EntityType type, [FromQuery] string q, [FromQuery] int limit = 20)
    {
        var res = _cat.Search(type, q, Math.Clamp(limit, 1, 100))
            .Select(e => new {
                type = (int)e.Type,
                id = e.Id,
                name = e.CanonicalName,
                dev = e.DevName,
                rarity = e.Rarity
            });
        return Ok(res);
    }

    [HttpGet("resolve-by-name")]
    public IActionResult ResolveByName([FromQuery] EntityType type, [FromQuery] string name)
    {
        if (_cat.TryGetIdByName(type, name, out var id))
            return Resolve(type, id);
        return NotFound(new { error = "not_found", type = (int)type, name });
    }
}
