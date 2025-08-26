#!/usr/bin/env python3
import argparse, json, re, sqlite3, zipfile, io
from pathlib import Path

# -------- helpers --------

def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

def detect_type(path: str) -> int:
    p = path.lower()
    # tweak these rules to your bundle naming
    if "student" in p or "character" in p:
        return 1
    if "currency" in p:
        return 2
    if "item" in p and "gacha" not in p:
        return 3
    if "weapon" in p:
        return 4
    if "gear" in p or "equipment" in p:
        return 5
    if "gacha" in p and ("group" in p or "pool" in p or "table" in p):
        return 6
    return 0  # unknown => skip

ID_KEYS      = ["Id","ID","id","CharacterId","StudentId","ItemId","CurrencyId","WeaponId"]
NAME_KEYS    = ["NameEn","NameEN","Name","name","DisplayName","LocalizedName"]
DEVNAME_KEYS = ["DevName","devName","CodeName","InternalName","Key"]
RARITY_KEYS  = ["Rarity","rarity","Star","Stars"]

def pick(d: dict, keys: list[str], default=None):
    for k in keys:
        if k in d and d[k] not in (None,""):
            return d[k]
    return default

# -------- main build --------

def build(zip_path: Path, out_sqlite: Path):
    out_sqlite.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out_sqlite)
    cur = con.cursor()

    schema = (Path(__file__).parent / "../data/catalog.sql").resolve()
    if not schema.exists():
        # inline fallback if file not laid out the same
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS entity (
          entity_type INTEGER NOT NULL, entity_id INTEGER NOT NULL,
          canonical_name TEXT NOT NULL, dev_name TEXT, rarity INTEGER, meta_json TEXT,
          PRIMARY KEY (entity_type, entity_id)
        );
        CREATE TABLE IF NOT EXISTS entity_alias (
          entity_type INTEGER NOT NULL, entity_id INTEGER NOT NULL,
          alias TEXT NOT NULL, alias_slug TEXT NOT NULL, lang TEXT,
          UNIQUE (entity_type, alias_slug)
        );
        CREATE INDEX IF NOT EXISTS idx_alias_type_slug ON entity_alias(entity_type, alias_slug);
        """)
    else:
        cur.executescript(schema.read_text(encoding="utf-8"))

    cur.execute("DELETE FROM entity")
    cur.execute("DELETE FROM entity_alias")

    added = 0
    aliases = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if not info.filename.lower().endswith(".json"):
                continue
            etype = detect_type(info.filename)
            if etype == 0:
                continue

            raw = zf.read(info.filename).decode("utf-8","replace")
            try:
                data = json.loads(raw)
            except Exception:
                continue

            rows = data
            if isinstance(data, dict):
                # sometimes tables wrap arrays under "Rows" or table name
                for k in ("Rows","rows","Data","data"):
                    if k in data and isinstance(data[k], list):
                        rows = data[k]
                        break

            if not isinstance(rows, list):
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue
                _id = pick(row, ID_KEYS)
                if _id is None: 
                    continue
                try:
                    _id = int(_id)
                except Exception:
                    continue

                name = pick(row, NAME_KEYS) or pick(row, DEVNAME_KEYS) or f"{Path(info.filename).stem}#{_id}"
                dev  = pick(row, DEVNAME_KEYS)
                rar  = pick(row, RARITY_KEYS)

                # stash everything else into meta_json (minus obvious cols)
                meta = {k:v for k,v in row.items() if k not in set(ID_KEYS+NAME_KEYS+DEVNAME_KEYS+RARITY_KEYS)}
                cur.execute(
                    "INSERT OR REPLACE INTO entity(entity_type,entity_id,canonical_name,dev_name,rarity,meta_json) VALUES (?,?,?,?,?,?)",
                    (etype, _id, str(name), (str(dev) if dev else None), (int(rar) if isinstance(rar,int) or (isinstance(rar,str) and rar.isdigit()) else None), json.dumps(meta, ensure_ascii=False))
                )
                added += 1

                # collect obvious alias fields (all Name* keys)
                for k,v in row.items():
                    if not isinstance(k,str): 
                        continue
                    if not isinstance(v,(str,int,float)): 
                        continue
                    if re.match(r"^(Name|NAME)[A-Za-z]*$", k) and str(v).strip():
                        a = str(v).strip()
                        cur.execute(
                            "INSERT OR IGNORE INTO entity_alias(entity_type,entity_id,alias,alias_slug,lang) VALUES (?,?,?,?,?)",
                            (etype, _id, a, slug(a), None)
                        )
                        aliases += 1
                # dev name as alias
                if dev:
                    cur.execute(
                        "INSERT OR IGNORE INTO entity_alias(entity_type,entity_id,alias,alias_slug,lang) VALUES (?,?,?,?,?)",
                        (etype, _id, str(dev), slug(str(dev)), None)
                    )
                    aliases += 1

    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('built_at', datetime('now'))")
    con.commit()
    con.close()
    print(f"Built {out_sqlite} with {added} entities and {aliases} aliases.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="Path to TableBundles.zip")
    ap.add_argument("--out", default="data/catalog.sqlite", help="Output sqlite path")
    args = ap.parse_args()
    build(Path(args.zip), Path(args.out))
