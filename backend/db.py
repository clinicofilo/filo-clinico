import asyncio
import copy
import json
import logging
import os
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
_pool: Optional[asyncpg.Pool] = None


def normalize_pg_url(url: str):
    """Normalize postgres URL and determine SSL requirements for Supabase / asyncpg."""
    parsed = urllib.parse.urlparse(url)
    scheme = "postgresql" if parsed.scheme in ("postgres", "postgresql") else parsed.scheme

    query_params = urllib.parse.parse_qs(parsed.query)
    sslmode = query_params.get("sslmode", [""])[0].lower()

    # Cloud PostgreSQL hosts always require SSL
    is_supabase = (
        "supabase.co" in parsed.netloc
        or "pooler.supabase.com" in parsed.netloc
        or "supabase.com" in parsed.netloc
    )
    is_neon = "neon.tech" in parsed.netloc or "neon." in parsed.netloc
    needs_ssl = is_supabase or is_neon or sslmode in ("require", "prefer", "verify-ca", "verify-full")

    # Strip params that asyncpg does not accept in DSN query string
    filtered_query = {k: v[0] for k, v in query_params.items() if k not in ("sslmode", "pgbouncer")}
    clean_query_str = urllib.parse.urlencode(filtered_query)
    clean_url = urllib.parse.urlunparse(
        (scheme, parsed.netloc, parsed.path, parsed.params, clean_query_str, parsed.fragment)
    )

    return clean_url, ("require" if needs_ssl else None)


async def _init_connection(conn):
    """Register JSON/JSONB codecs so asyncpg automatically converts jsonb columns to/from Python dict/list."""
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog"
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog"
    )


async def init_pool(dsn: Optional[str] = None) -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    raw_url = (
        dsn
        or os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRES_PRISMA_URL")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
        or os.environ.get("SUPABASE_DB_URL")
        or "postgresql://postgres:postgres@localhost:5432/filoclinico"
    )

    clean_url, ssl = normalize_pg_url(raw_url)
    logger.info("Inizializzazione pool PostgreSQL/Supabase (SSL: %s)...", ssl is not None)

    try:
        pool_kwargs = {
            "min_size": 1,
            "max_size": int(os.environ.get("PG_POOL_MAX_SIZE", "10")),
            "init": _init_connection,
            "command_timeout": 60,
        }
        if ssl:
            pool_kwargs["ssl"] = ssl

        _pool = await asyncpg.create_pool(clean_url, **pool_kwargs)
        logger.info("Pool PostgreSQL/Supabase connesso con successo")

        # Esegui migrazione automatica schema
        await run_schema_migration()
        return _pool
    except Exception as e:
        logger.error("Errore durante la connessione a PostgreSQL/Supabase: %s", e)
        raise


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Pool PostgreSQL chiuso")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool non inizializzato. Chiamare init_pool() prima di effettuare query.")
    return _pool


async def run_schema_migration():
    """Esegue supabase_schema.sql per creare le tabelle e gli indici necessari."""
    schema_path = ROOT_DIR / "supabase_schema.sql"
    if not schema_path.exists():
        logger.warning("File supabase_schema.sql non trovato in %s", schema_path)
        return

    sql = schema_path.read_text(encoding="utf-8")
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(sql)
            logger.info("Schema Supabase/PostgreSQL verificato ed applicato con successo")
        except Exception as e:
            logger.error("Errore durante l'applicazione dello schema: %s", e)
            raise


def _apply_projection(doc: Optional[Dict[str, Any]], projection: Optional[Dict[str, int]]) -> Optional[Dict[str, Any]]:
    if doc is None or not projection:
        return doc
    doc_copy = copy.deepcopy(doc)
    include_mode = any(v == 1 for k, v in projection.items() if k != "_id")
    if include_mode:
        res = {}
        for k, v in projection.items():
            if v == 1 and k in doc_copy:
                res[k] = doc_copy[k]
        return res
    else:
        for k, v in projection.items():
            if v == 0 and k in doc_copy:
                doc_copy.pop(k, None)
        return doc_copy


def _matches_filter(doc: Dict[str, Any], filter_dict: Optional[Dict[str, Any]]) -> bool:
    if not filter_dict:
        return True
    for k, expected in filter_dict.items():
        if k == "$or":
            if not any(_matches_filter(doc, sub) for sub in expected):
                return False
            continue

        val = doc.get(k)
        if isinstance(expected, dict):
            if "$ne" in expected and val == expected["$ne"]:
                return False
            if "$gte" in expected and (val is None or val < expected["$gte"]):
                return False
            if "$lte" in expected and (val is None or val > expected["$lte"]):
                return False
            if "$gt" in expected and (val is None or val <= expected["$gt"]):
                return False
            if "$lt" in expected and (val is None or val >= expected["$lt"]):
                return False
            if "$in" in expected and val not in expected["$in"]:
                return False
        else:
            if val != expected:
                return False
    return True


class AsyncCursor:
    def __init__(self, table: "AsyncTable", filter_dict: Optional[Dict[str, Any]], projection: Optional[Dict[str, int]]):
        self.table = table
        self.filter_dict = filter_dict or {}
        self.projection = projection
        self.sort_key: Optional[str] = None
        self.sort_desc: bool = False

    def sort(self, key: str, direction: int = -1) -> "AsyncCursor":
        self.sort_key = key
        self.sort_desc = (direction == -1)
        return self

    async def to_list(self, limit: int = 500) -> List[Dict[str, Any]]:
        # Fetch all candidate documents for table
        docs = await self.table._fetch_all_raw()
        filtered = [d for d in docs if _matches_filter(d, self.filter_dict)]

        if self.sort_key:
            filtered.sort(
                key=lambda x: (x.get(self.sort_key) is None, x.get(self.sort_key)),
                reverse=self.sort_desc
            )

        if limit:
            filtered = filtered[:limit]

        return [_apply_projection(d, self.projection) for d in filtered]


class AsyncTable:
    def __init__(self, table_name: str, pk_col: str, dedicated_cols: Optional[List[str]] = None):
        self.table_name = table_name
        self.pk_col = pk_col
        self.dedicated_cols = dedicated_cols or []

    async def _fetch_all_raw(self) -> List[Dict[str, Any]]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT {self.pk_col}, data FROM {self.table_name}")
            res = []
            for r in rows:
                data = r["data"]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                d = dict(data)
                d[self.pk_col] = r[self.pk_col]
                res.append(d)
            return res

    async def find_one(self, filter_dict: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None) -> Optional[Dict[str, Any]]:
        filter_dict = filter_dict or {}
        pool = get_pool()

        # Ottimizzazione: se la ricerca è per chiave primaria
        if self.pk_col in filter_dict and isinstance(filter_dict[self.pk_col], (str, int)):
            pk_val = filter_dict[self.pk_col]
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT {self.pk_col}, data FROM {self.table_name} WHERE {self.pk_col} = $1",
                    str(pk_val)
                )
                if not row:
                    return None
                data = row["data"]
                if isinstance(data, str):
                    data = json.loads(data)
                doc = dict(data)
                doc[self.pk_col] = row[self.pk_col]
                if _matches_filter(doc, filter_dict):
                    return _apply_projection(doc, projection)
                return None

        # Ricerca generale
        docs = await self._fetch_all_raw()
        for d in docs:
            if _matches_filter(d, filter_dict):
                return _apply_projection(d, projection)
        return None

    def find(self, filter_dict: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None) -> AsyncCursor:
        return AsyncCursor(self, filter_dict, projection)

    async def insert_one(self, doc: Dict[str, Any]):
        doc_copy = copy.deepcopy(doc)
        pool = get_pool()

        # Handle auto-incrementing serial PK (e.g. id in consents, email_log)
        is_serial_pk = (self.pk_col == "id" and doc_copy.get(self.pk_col) is None)
        if not is_serial_pk:
            pk_val = doc_copy.get(self.pk_col)
            if not pk_val:
                pk_val = f"{self.table_name}_{uuid.uuid4().hex[:12]}"
                doc_copy[self.pk_col] = pk_val
            pk_val_str = str(pk_val)
            cols = [self.pk_col]
            vals = [pk_val_str]
            param_placeholders = ["$1"]
            idx = 2
        else:
            cols = []
            vals = []
            param_placeholders = []
            idx = 1
            pk_val_str = None

        for c in self.dedicated_cols:
            if c in doc_copy and doc_copy[c] is not None:
                cols.append(c)
                vals.append(doc_copy[c])
                param_placeholders.append(f"${idx}")
                idx += 1

        cols.append("data")
        vals.append(doc_copy)
        param_placeholders.append(f"${idx}")

        has_updated_at = self.table_name in ("users", "dossiers", "drive_credentials")

        if is_serial_pk:
            sql = f"""
                INSERT INTO {self.table_name} ({', '.join(cols)})
                VALUES ({', '.join(param_placeholders)})
                RETURNING id
            """
            async with pool.acquire() as conn:
                inserted_id = await conn.fetchval(sql, *vals)
                pk_val_str = str(inserted_id)
        else:
            conflict_update = "data = EXCLUDED.data"
            if has_updated_at:
                conflict_update += ", updated_at = CURRENT_TIMESTAMP"
            for c in self.dedicated_cols:
                if c in doc_copy and doc_copy[c] is not None:
                    conflict_update += f", {c} = EXCLUDED.{c}"

            sql = f"""
                INSERT INTO {self.table_name} ({', '.join(cols)})
                VALUES ({', '.join(param_placeholders)})
                ON CONFLICT ({self.pk_col}) DO UPDATE SET
                    {conflict_update}
            """
            async with pool.acquire() as conn:
                await conn.execute(sql, *vals)

        class InsertResult:
            inserted_id = pk_val_str
        return InsertResult()

    async def update_one(self, filter_dict: Dict[str, Any], update_dict: Dict[str, Any], upsert: bool = False):
        current = await self.find_one(filter_dict)
        if not current:
            if not upsert:
                return None
            new_doc = copy.deepcopy(filter_dict)
            if "$set" in update_dict:
                new_doc.update(update_dict["$set"])
            return await self.insert_one(new_doc)

        updated_doc = copy.deepcopy(current)

        # 1. $set
        if "$set" in update_dict:
            for k, v in update_dict["$set"].items():
                updated_doc[k] = v

        # 2. $inc
        if "$inc" in update_dict:
            for k, v in update_dict["$inc"].items():
                updated_doc[k] = updated_doc.get(k, 0) + v

        # 3. $push
        if "$push" in update_dict:
            for k, v in update_dict["$push"].items():
                lst = updated_doc.setdefault(k, [])
                if isinstance(v, dict) and "$each" in v:
                    lst.extend(v["$each"])
                else:
                    lst.append(v)

        # 4. $pull
        if "$pull" in update_dict:
            for k, v in update_dict["$pull"].items():
                if k in updated_doc and isinstance(updated_doc[k], list):
                    for cond_k, cond_v in v.items():
                        updated_doc[k] = [
                            item for item in updated_doc[k]
                            if not (isinstance(item, dict) and item.get(cond_k) == cond_v)
                        ]

        # Salva in PostgreSQL
        pk_val = updated_doc.get(self.pk_col)
        pool = get_pool()
        has_updated_at = self.table_name in ("users", "dossiers", "drive_credentials")

        set_clauses = ["data = $1"]
        vals = [updated_doc]
        idx = 2

        if has_updated_at:
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

        for c in self.dedicated_cols:
            if c in updated_doc:
                set_clauses.append(f"{c} = ${idx}")
                vals.append(updated_doc[c])
                idx += 1

        vals.append(str(pk_val) if not isinstance(pk_val, int) else pk_val)
        pk_param = f"${idx}"

        sql = f"UPDATE {self.table_name} SET {', '.join(set_clauses)} WHERE {self.pk_col} = {pk_param}"

        async with pool.acquire() as conn:
            await conn.execute(sql, *vals)
        return True

    async def delete_one(self, filter_dict: Dict[str, Any]):
        target = await self.find_one(filter_dict)
        if not target:
            return False
        pk_val = target.get(self.pk_col)
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self.table_name} WHERE {self.pk_col} = $1",
                str(pk_val)
            )
        return True

    async def delete_many(self, filter_dict: Dict[str, Any]):
        all_matches = await self.find(filter_dict).to_list(1000)
        if not all_matches:
            return 0
        pks = [str(d[self.pk_col]) for d in all_matches if self.pk_col in d]
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self.table_name} WHERE {self.pk_col} = ANY($1::varchar[])",
                pks
            )
        return len(pks)

    async def create_index(self, *args, **kwargs):
        """No-op per compatibilità con il codice esistente."""
        return True


class SupabaseDatabase:
    def __init__(self):
        self.users = AsyncTable("users", "user_id", ["email", "role"])
        self.user_sessions = AsyncTable("user_sessions", "session_token", ["user_id"])
        self.login_attempts = AsyncTable("login_attempts", "identifier")
        self.consents = AsyncTable("consents", "id", ["user_id"])
        self.password_resets = AsyncTable("password_resets", "token", ["email"])
        self.dossiers = AsyncTable("dossiers", "dossier_id", ["patient_id", "status"])
        self.slots = AsyncTable("slots", "slot_id", ["doctor_id", "status"])
        self.payment_transactions = AsyncTable("payment_transactions", "session_id", ["user_id"])
        self.email_log = AsyncTable("email_log", "id", ["recipient"])
        self.drive_credentials = AsyncTable("drive_credentials", "user_id")


db = SupabaseDatabase()
