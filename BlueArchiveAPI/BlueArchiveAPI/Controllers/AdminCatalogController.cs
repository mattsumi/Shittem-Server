using BlueArchiveAPI.Catalog;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace BlueArchiveAPI.Controllers
{
    [ApiController]
    [Route("admin/catalog")]
    public sealed class AdminCatalogController : ControllerBase
    {
        private readonly IEntityCatalog _catalog;
        private readonly ILogger<AdminCatalogController> _logger;

        public AdminCatalogController(IEntityCatalog catalog, ILogger<AdminCatalogController> logger)
        {
            _catalog = catalog;
            _logger = logger;
        }

        // Combined handler to avoid route ambiguity and support legacy shims:
        // - GET /admin/catalog/types
        // - GET /admin/catalog            (no params) => types
        // - GET /admin/catalog?type=Item  (query)     => entities
        // - GET ~/admin/items/types
        // - GET ~/admin/items?type=Item
        [HttpGet]
        [HttpGet("types")]
        [HttpGet("~/admin/items")]
        [HttpGet("~/admin/items/types")]
        public ActionResult<IEnumerable<object>> Get([FromQuery] string? type, CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(type))
            {
                var types = _catalog.GetTypes() ?? Array.Empty<string>();
                _logger.LogInformation("[ADMIN][CATALOG] types={Count}", types.Count);
                return Ok(types);
            }

            if (!TryResolveType(type!, out var et))
            {
                _logger.LogInformation("[ADMIN][CATALOG] unknown type '{Type}', returning empty", type);
                return Ok(Array.Empty<object>());
            }

            var list = _catalog.GetEntities(et) ?? Array.Empty<Entity>();
            _logger.LogInformation("[ADMIN][CATALOG] {Type} entities={Count}", et, list.Count);
            var dtos = list.Select(e => new { id = e.Id, name = e.CanonicalName });
            return Ok(dtos);
        }

        // GET /admin/catalog/{type}
        [HttpGet("{type}")]
        public ActionResult<IEnumerable<object>> GetByPath([FromRoute] string type, CancellationToken ct)
        {
            if (!TryResolveType(type, out var et))
            {
                _logger.LogInformation("[ADMIN][CATALOG] unknown type '{Type}', returning empty", type);
                return Ok(Array.Empty<object>());
            }

            var list = _catalog.GetEntities(et) ?? Array.Empty<Entity>();
            _logger.LogInformation("[ADMIN][CATALOG] {Type} entities={Count}", et, list.Count);
            var dtos = list.Select(e => new { id = e.Id, name = e.CanonicalName });
            return Ok(dtos);
        }

        private static bool TryResolveType(string input, out EntityType type)
        {
            var key = (input ?? "").Trim().ToLowerInvariant();
            switch (key)
            {
                case "student":
                case "students":
                case "character":
                case "characters":
                case "unit":
                case "units":
                    type = EntityType.Student; return true;
                case "item":
                case "items":
                    type = EntityType.Item; return true;
                case "currency":
                case "currencies":
                    type = EntityType.Currency; return true;
                case "weapon":
                case "weapons":
                    type = EntityType.Weapon; return true;
                case "gear":
                case "gears":
                    type = EntityType.Gear; return true;
                case "gachagroup":
                case "gacha group":
                case "gacha-group":
                case "gacha_groups":
                case "gacha-groups":
                case "gachagroups":
                    type = EntityType.GachaGroup; return true;
                default:
                    if (Enum.TryParse<EntityType>(input, true, out var parsed))
                    {
                        type = parsed; return true;
                    }
                    type = default; return false;
            }
        }
    }
}