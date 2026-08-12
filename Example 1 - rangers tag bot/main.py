import asyncio
import datetime
import json
import os
import secrets
from io import BytesIO

import aiohttp
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN     = os.environ["BOT_TOKEN"]
_raw_cookie   = os.environ["ROBLOX_COOKIE"]
ROBLOX_COOKIE = _raw_cookie if _raw_cookie.startswith(".ROBLOSECURITY=") else f".ROBLOSECURITY={_raw_cookie}"
DATABASE_URL  = os.environ["DATABASE_URL"]

ALLOWED_GUILDS = [1238584928002904151, 1511221374042243122]
BOTDEV_IDS     = {878416460924465193, 1232468301150683229, 1507056301921009856, 1268087399154585650, 1311139704800022549, 1320827552759287903}
FOUNDER_IDS    = {878416460924465193, 1232468301150683229, 1507056301921009856, 1268087399154585650, 1311139704800022549, 1320827552759287903}

GROUPS: dict[str, int] = {
    "Rangers":  575770529,
    "Rangers2": 584349032,
    "ST6": 32023448,
}

GROUP_KEYS    = list(GROUPS.keys())
GROUP_CHOICES = [app_commands.Choice(name=k, value=k) for k in GROUP_KEYS]
GUILD_OBJECTS = [discord.Object(id=g) for g in ALLOWED_GUILDS]

_group_roles: dict[str, list[tuple[int, str]]] = {}


# Roblox


def _rbx_headers(xcsrf: str = "") -> dict:
    h = {"Cookie": ROBLOX_COOKIE, "Content-Type": "application/json"}
    if xcsrf:
        h["x-csrf-token"] = xcsrf
    return h

async def _xcsrf() -> str:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.post(
            "https://auth.roblox.com/v2/logout",
            headers={"Cookie": ROBLOX_COOKIE, "Content-Type": "application/json"},
        ) as r:
            return r.headers.get("x-csrf-token", "")

async def rbx_fetch_group_roles(session: aiohttp.ClientSession, group_id: int) -> list[tuple[int, str]]:
    async with session.get(
        f"https://groups.roblox.com/v1/groups/{group_id}/roles",
        headers={"Cookie": ROBLOX_COOKIE},
    ) as r:
        if r.status != 200:
            return []
        roles = (await r.json()).get("roles", [])
        return [
            (role["id"], role["name"])
            for role in sorted(roles, key=lambda x: x["rank"])
            if role["rank"] > 0
        ]

async def refresh_group_roles():
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        for key, gid in GROUPS.items():
            if gid:
                _group_roles[key] = await rbx_fetch_group_roles(session, gid)

async def rbx_user(session: aiohttp.ClientSession, username: str) -> dict | None:
    async with session.post(
        "https://users.roblox.com/v1/usernames/users",
        json={"usernames": [username], "excludeBannedUsers": False},
        headers={"Content-Type": "application/json"},
    ) as r:
        if r.status != 200:
            return None
        data = (await r.json()).get("data", [])
        return data[0] if data else None

async def rbx_avatar(session: aiohttp.ClientSession, uid: int) -> bytes | None:
    url = (
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
        f"?userIds={uid}&size=150x150&format=Png&isCircular=false"
    )
    async with session.get(url) as r:
        if r.status != 200:
            return None
        entries = (await r.json()).get("data", [])
        if not entries:
            return None
        img_url = entries[0].get("imageUrl")
        if not img_url:
            return None
    async with session.get(img_url) as r:
        return await r.read() if r.status == 200 else None

async def rbx_get_role(group_id: int, uid: int) -> tuple[int, str] | None:
    """Returns (role_id, role_name) for the user in the group, or None.
    Tries v2 (no auth needed for public data) then v1 with cookie as fallback."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        # v2 first — no cookie, more reliable
        async with s.get(f"https://groups.roblox.com/v2/users/{uid}/groups/roles") as r:
            if r.status == 200:
                data = (await r.json()).get("data", [])
                for entry in data:
                    if int(entry.get("group", {}).get("id", 0)) == int(group_id):
                        role = entry.get("role", {})
                        return (role.get("id"), role.get("name", ""))
                print(f"rbx_get_role[v2]: uid={uid} group={group_id} not-in-list ({len(data)} groups)")
                return None
            print(f"rbx_get_role[v2]: uid={uid} group={group_id} status={r.status}, falling back to v1")

        # v1 fallback
        async with s.get(
            f"https://groups.roblox.com/v1/users/{uid}/groups/roles",
            headers={"Cookie": ROBLOX_COOKIE},
        ) as r:
            if r.status != 200:
                print(f"rbx_get_role[v1]: uid={uid} group={group_id} status={r.status}")
                return None
            data = (await r.json()).get("data", [])
            for entry in data:
                if int(entry.get("group", {}).get("id", 0)) == int(group_id):
                    role = entry.get("role", {})
                    return (role.get("id"), role.get("name", ""))
            print(f"rbx_get_role[v1]: uid={uid} group={group_id} not-in-list ({len(data)} groups)")
            return None

async def rbx_get_role_id(group_id: int, uid: int) -> int | None:
    result = await rbx_get_role(group_id, uid)
    return result[0] if result else None

async def rbx_fetch_user_groups(uid: int) -> list[tuple[int, str]]:
    """Returns [(group_id, group_name), ...] for every group the user is in."""
    details = await rbx_fetch_user_groups_detailed(uid)
    return [(d["id"], d["name"]) for d in details]


async def rbx_fetch_group_icon(gid: int) -> str | None:
    """Returns a fresh CDN URL for the group's icon (150x150), or None.
    Not cached — Roblox thumbnail URLs are signed and expire."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.get(
            f"https://thumbnails.roblox.com/v1/groups/icons"
            f"?groupIds={gid}&size=150x150&format=Png&isCircular=false"
        ) as r:
            if r.status != 200:
                print(f"rbx_fetch_group_icon: gid={gid} status={r.status}", flush=True)
                return None
            entries = (await r.json()).get("data", [])
            if not entries:
                print(f"rbx_fetch_group_icon: gid={gid} no data entries", flush=True)
                return None
            entry = entries[0]
            state = entry.get("state", "")
            url = entry.get("imageUrl")
            print(f"rbx_fetch_group_icon: gid={gid} state={state} url={url}", flush=True)
            if state != "Completed" or not url:
                return None
            return url


async def rbx_fetch_user_groups_detailed(uid: int) -> list[dict]:
    """Returns [{id, name, members, public, rank}, ...] for every group the user is in."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        # No auth — public endpoint. Cookie has been causing scoped/stale responses.
        async with s.get(
            f"https://groups.roblox.com/v2/users/{uid}/groups/roles",
        ) as r:
            if r.status != 200:
                print(f"rbx_fetch_user_groups_detailed: uid={uid} status={r.status}")
                return []
            data = (await r.json()).get("data", [])
            out: list[dict] = []
            for entry in data:
                g = entry.get("group") or {}
                role = entry.get("role") or {}
                if not g:
                    continue
                out.append({
                    "id":      g.get("id"),
                    "name":    g.get("name", ""),
                    "members": g.get("memberCount", 0),
                    "public":  g.get("publicEntryAllowed", False),
                    "rank":    role.get("name", ""),
                })
            print(f"rbx_fetch_user_groups_detailed: uid={uid} returned {len(out)} groups: {[g['id'] for g in out][:20]}")
            return out

def _rbx_error_code(text: str) -> int | None:
    try:
        return json.loads(text)["errors"][0]["code"]
    except Exception:
        return None

_RBX_ERRORS: dict[int, str] = {
    1:  "Group not found.",
    3:  "No perms in group.",
    4:  "Roblox rejected: bot account can't manage this user's rank (bot may not be in the group, may lack Manage Lower Ranks permission, or the target's rank is above the bot's).",
    17: "XCSRF token invalid.",
    23: "Rank not found.",
}

def _rbx_err_msg(text: str, fallback: str = "Request failed.") -> str:
    code = _rbx_error_code(text)
    return _RBX_ERRORS.get(code, fallback) if code is not None else fallback

async def _rbx_bot_uid() -> int | None:
    """Returns the Roblox uid of the account whose cookie we're using, or None."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.get(
            "https://users.roblox.com/v1/users/authenticated",
            headers={"Cookie": ROBLOX_COOKIE},
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data.get("id")


async def _rbx_diagnose_set_rank(group_id: int, target_uid: int, target_role_id: int) -> str:
    """Called when rbx_set_rank returns error 4. Figures out WHY and returns a message."""
    bot_uid = await _rbx_bot_uid()
    if bot_uid is None:
        return "Rank change failed. Bot's Roblox cookie appears invalid/expired."

    # Check bot's own membership in the group
    bot_role = await rbx_get_role(group_id, bot_uid)
    if bot_role is None:
        return f"Rank change failed. Bot ({bot_uid}) is not a member of group {group_id}."

    # Check target's membership per read endpoint
    target_role = await rbx_get_role(group_id, target_uid)
    if target_role is None:
        return (
            f"Rank change failed. Read endpoint says target ({target_uid}) is not in group {group_id}, "
            f"even though bot is (as {bot_role[1]})."
        )

    # Both in group. Get all group roles to compare ranks numerically.
    roles = _group_roles.get(next((k for k, v in GROUPS.items() if v == group_id), ""), [])
    role_names = {rid: name for rid, name in roles}
    bot_rank_name    = bot_role[1]
    target_rank_name = target_role[1]
    new_rank_name    = role_names.get(target_role_id, f"role#{target_role_id}")

    return (
        f"Rank change failed (Roblox error 4). Diagnostic:\n"
        f"- Bot ({bot_uid}) rank in group: `{bot_rank_name}`\n"
        f"- Target ({target_uid}) current rank: `{target_rank_name}`\n"
        f"- Trying to set target to: `{new_rank_name}`\n"
        f"Likely: bot's rank isn't high enough to assign that rank (must be strictly above the target rank), "
        f"or the bot lacks Manage Lower Ranks permission on its rank."
    )


async def rbx_set_rank(group_id: int, uid: int, role_id: int) -> tuple[bool, str]:
    token = await _xcsrf()
    url   = f"https://groups.roblox.com/v1/groups/{group_id}/users/{uid}"
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.patch(
            url, json={"roleId": role_id}, headers=_rbx_headers(token)
        ) as r:
            text = await r.text()
            if r.status == 200:
                return (True, "ok")
            code = _rbx_error_code(text)
            if code == 4:
                return (False, await _rbx_diagnose_set_rank(group_id, uid, role_id))
            return (False, _rbx_err_msg(text))

async def rbx_accept(group_id: int, uid: int) -> tuple[bool, str]:
    token = await _xcsrf()
    url   = f"https://groups.roblox.com/v1/groups/{group_id}/join-requests/users/{uid}"
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.post(url, headers=_rbx_headers(token)) as r:
            text = await r.text()
            return (True, "ok") if r.status == 200 else (False, _rbx_err_msg(text))

async def rbx_exile(group_id: int, uid: int) -> tuple[bool, str]:
    token = await _xcsrf()
    url   = f"https://groups.roblox.com/v1/groups/{group_id}/users/{uid}"
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as s:
        async with s.delete(url, headers=_rbx_headers(token)) as r:
            text = await r.text()
            return (True, "ok") if r.status == 200 else (False, _rbx_err_msg(text))


# Database


async def init_db(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_whitelist (
                discord_id BIGINT,
                group_key  TEXT,
                tier       TEXT NOT NULL CHECK (tier IN ('owner', 'staff')),
                PRIMARY KEY (discord_id, group_key)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_role_whitelist (
                role_id   BIGINT,
                group_key TEXT,
                PRIMARY KEY (role_id, group_key)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_members (
                discord_id  BIGINT PRIMARY KEY,
                joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                roblox_user TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                discord_id BIGINT,
                type       TEXT NOT NULL CHECK (type IN ('group', 'whitelist')),
                group_key  TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (discord_id, type, group_key)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS locked_ranks (
                group_key TEXT,
                rank_name TEXT,
                PRIMARY KEY (group_key, rank_name)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crew_blacklist (
                group_id  BIGINT PRIMARY KEY,
                added_by  BIGINT NOT NULL,
                added_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

async def db_wl_get_tier(pool: asyncpg.Pool, uid: int, group_key: str) -> str | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tier FROM group_whitelist WHERE discord_id=$1 AND group_key=$2",
            uid, group_key,
        )
        return row["tier"] if row else None

async def db_wl_set(pool: asyncpg.Pool, uid: int, group_key: str, tier: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO group_whitelist (discord_id, group_key, tier) VALUES ($1,$2,$3)
               ON CONFLICT (discord_id, group_key) DO UPDATE SET tier=EXCLUDED.tier""",
            uid, group_key, tier,
        )

async def db_wl_remove(pool: asyncpg.Pool, uid: int, group_key: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM group_whitelist WHERE discord_id=$1 AND group_key=$2",
            uid, group_key,
        )

async def db_rwl_get(pool: asyncpg.Pool, group_key: str) -> list[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role_id FROM group_role_whitelist WHERE group_key=$1", group_key
        )
        return [r["role_id"] for r in rows]

async def db_rwl_toggle(pool: asyncpg.Pool, role_id: int, group_key: str) -> bool:
    async with pool.acquire() as conn:
        exists = await conn.fetchrow(
            "SELECT 1 FROM group_role_whitelist WHERE role_id=$1 AND group_key=$2",
            role_id, group_key,
        )
        if exists:
            await conn.execute(
                "DELETE FROM group_role_whitelist WHERE role_id=$1 AND group_key=$2",
                role_id, group_key,
            )
            return False
        else:
            await conn.execute(
                "INSERT INTO group_role_whitelist VALUES ($1,$2)", role_id, group_key
            )
            return True

async def db_set_config(pool: asyncpg.Pool, key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO config VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
            key, value,
        )

async def db_get_config(pool: asyncpg.Pool, key: str) -> str | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM config WHERE key=$1", key)
        return row["value"] if row else None

async def db_track(pool: asyncpg.Pool, uid: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tracked_members (discord_id) VALUES ($1) ON CONFLICT DO NOTHING", uid
        )

async def db_untrack(pool: asyncpg.Pool, uid: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM tracked_members WHERE discord_id=$1", uid)

async def db_tracked_count(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) AS c FROM tracked_members")
        return int(row["c"]) if row else 0

async def db_set_roblox(pool: asyncpg.Pool, uid: int, roblox: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO tracked_members (discord_id, roblox_user) VALUES ($1,$2)
               ON CONFLICT (discord_id) DO UPDATE SET roblox_user=EXCLUDED.roblox_user""",
            uid, roblox,
        )

async def db_cmd_disable(pool: asyncpg.Pool, cmd: str, reason: str):
    await db_set_config(pool, f"disabled_{cmd}", reason)

async def db_cmd_enable(pool: asyncpg.Pool, cmd: str):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM config WHERE key=$1", f"disabled_{cmd}")

async def db_cmd_disabled_reason(pool: asyncpg.Pool, cmd: str) -> str | None:
    return await db_get_config(pool, f"disabled_{cmd}")

async def db_wl_list(pool: asyncpg.Pool, group_key: str) -> list[tuple[int, str]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT discord_id, tier FROM group_whitelist WHERE group_key=$1 ORDER BY tier, discord_id",
            group_key,
        )
        return [(r["discord_id"], r["tier"]) for r in rows]

async def db_bl_list(pool: asyncpg.Pool) -> list[tuple[int, str, str]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT discord_id, type, group_key FROM blacklist ORDER BY type, discord_id")
        return [(r["discord_id"], r["type"], r["group_key"]) for r in rows]

async def db_bl_add(pool: asyncpg.Pool, uid: int, bl_type: str, group_key: str = ""):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO blacklist VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
            uid, bl_type, group_key,
        )

async def db_bl_remove(pool: asyncpg.Pool, uid: int, bl_type: str, group_key: str = ""):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM blacklist WHERE discord_id=$1 AND type=$2 AND group_key=$3",
            uid, bl_type, group_key,
        )

async def db_bl_check(pool: asyncpg.Pool, uid: int, bl_type: str, group_key: str = "") -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM blacklist WHERE discord_id=$1 AND type=$2 AND group_key=$3",
            uid, bl_type, group_key,
        )
        return row is not None

async def db_rank_lock_toggle(pool: asyncpg.Pool, group_key: str, rank_name: str) -> bool:
    async with pool.acquire() as conn:
        exists = await conn.fetchrow(
            "SELECT 1 FROM locked_ranks WHERE group_key=$1 AND rank_name=$2", group_key, rank_name
        )
        if exists:
            await conn.execute(
                "DELETE FROM locked_ranks WHERE group_key=$1 AND rank_name=$2", group_key, rank_name
            )
            return False
        else:
            await conn.execute(
                "INSERT INTO locked_ranks VALUES ($1,$2)", group_key, rank_name
            )
            return True

async def db_rank_is_locked(pool: asyncpg.Pool, group_key: str, rank_name: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM locked_ranks WHERE group_key=$1 AND rank_name=$2", group_key, rank_name
        )
        return row is not None

async def db_rank_locked_list(pool: asyncpg.Pool, group_key: str) -> list[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT rank_name FROM locked_ranks WHERE group_key=$1 ORDER BY rank_name", group_key
        )
        return [r["rank_name"] for r in rows]

async def db_crewbl_check(pool: asyncpg.Pool, group_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM crew_blacklist WHERE group_id=$1", group_id)
        return row is not None

async def db_crewbl_check_many(pool: asyncpg.Pool, group_ids: list[int]) -> set[int]:
    if not group_ids:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT group_id FROM crew_blacklist WHERE group_id = ANY($1::bigint[])", group_ids
        )
        return {r["group_id"] for r in rows}

async def db_crewbl_toggle(pool: asyncpg.Pool, group_id: int, added_by: int) -> bool:
    async with pool.acquire() as conn:
        exists = await conn.fetchrow("SELECT 1 FROM crew_blacklist WHERE group_id=$1", group_id)
        if exists:
            await conn.execute("DELETE FROM crew_blacklist WHERE group_id=$1", group_id)
            return False
        else:
            await conn.execute(
                "INSERT INTO crew_blacklist (group_id, added_by) VALUES ($1,$2)",
                group_id, added_by,
            )
            return True

async def db_crewbl_list(pool: asyncpg.Pool) -> list[tuple[int, int]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT group_id, added_by FROM crew_blacklist ORDER BY group_id")
        return [(r["group_id"], r["added_by"]) for r in rows]

async def db_wl_clear(pool: asyncpg.Pool, group_key: str, keep_owners: bool) -> int:
    async with pool.acquire() as conn:
        if keep_owners:
            result = await conn.execute(
                "DELETE FROM group_whitelist WHERE group_key=$1 AND tier='staff'", group_key
            )
        else:
            result = await conn.execute(
                "DELETE FROM group_whitelist WHERE group_key=$1", group_key
            )
        return int(result.split()[-1])

# Permissions


def is_botdev(uid: int) -> bool:
    return uid in BOTDEV_IDS

def is_founder(uid: int) -> bool:
    return uid in FOUNDER_IDS

async def get_group_tier(pool: asyncpg.Pool, uid: int, group_key: str) -> str | None:
    if is_botdev(uid):
        return "owner"
    return await db_wl_get_tier(pool, uid, group_key)

async def can_tag(pool: asyncpg.Pool, user: discord.Member | discord.User, group_key: str) -> bool:
    if is_botdev(user.id):
        return True
    if await db_bl_check(pool, user.id, "whitelist"):
        return False
    if await get_group_tier(pool, user.id, group_key) is not None:
        return True
    # Role-whitelist check requires a Member (has .roles) — skip silently for User
    if isinstance(user, discord.Member):
        allowed_roles = set(await db_rwl_get(pool, group_key))
        return any(r.id in allowed_roles for r in user.roles)
    return False

async def can_fa(pool: asyncpg.Pool, uid: int, group_key: str) -> bool:
    if await db_bl_check(pool, uid, "whitelist"):
        return False
    return (await get_group_tier(pool, uid, group_key)) == "owner"

# Components v2


def _container(accent: int, *text_blocks: str) -> dict:
    components: list[dict] = []
    for i, text in enumerate(text_blocks):
        if i > 0:
            components.append({"type": 14, "spacing": 1, "divider": True})
        components.append({"type": 10, "content": text})
    return {
        "type": 17,
        "accent_color": accent,
        "spoiler": False,
        "components": components,
    }

async def send_v2(channel_id: int, *containers: dict, file: discord.File | None = None):
    payload = {
        "components": list(containers),
        "flags": 32768,
        "allowed_mentions": {"parse": []},
    }
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
    }
    async with aiohttp.ClientSession() as s:
        if file:
            form = aiohttp.FormData()
            form.add_field("payload_json", json.dumps(payload), content_type="application/json")
            file.fp.seek(0)
            form.add_field("files[0]", file.fp, filename=file.filename, content_type="image/png")
            async with s.post(url, data=form, headers=headers) as r:
                return r.status
        else:
            async with s.post(url, json=payload, headers=headers) as r:
                return r.status

async def reply_v2(interaction: discord.Interaction, *containers: dict, file: discord.File | None = None):
    """Edit the deferred interaction response to a components v2 message."""
    payload = {
        "components": list(containers),
        "flags": 32768,
        "allowed_mentions": {"parse": []},
    }
    url = f"https://discord.com/api/v10/webhooks/{interaction.application_id}/{interaction.token}/messages/@original"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        if file:
            form = aiohttp.FormData()
            form.add_field("payload_json", json.dumps(payload), content_type="application/json")
            file.fp.seek(0)
            form.add_field("files[0]", file.fp, filename=file.filename, content_type="image/png")
            async with s.patch(url, data=form, headers=headers) as r:
                return r.status
        else:
            async with s.patch(url, json=payload, headers=headers) as r:
                return r.status

async def post_log(pool: asyncpg.Pool, *containers: dict):
    channel_id = await db_get_config(pool, "log_channel")
    if not channel_id:
        return
    try:
        await send_v2(int(channel_id), *containers)
    except Exception:
        pass


# Rank card

CARD_W, CARD_H = 680, 190
BG           = (15,  15,  22)
STRIPE       = (63,  63,  230)
FG           = (240, 240, 240)
MUTED        = (140, 140, 160)
BADGE_BG     = (30,  30,  50)
BADGE_BORDER = (63,  63,  230)

def _now_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y  %H:%M UTC")

def _load_fonts():
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ]
    bold = next((p for p in candidates if os.path.exists(p)), None)
    reg  = candidates[1] if os.path.exists(candidates[1]) else bold
    try:
        if bold:
            return (
                ImageFont.truetype(bold, 28),
                ImageFont.truetype(reg or bold, 19),
                ImageFont.truetype(reg or bold, 15),
            )
    except IOError:
        pass
    d = ImageFont.load_default()
    return d, d, d

def make_rank_card(
    display_name: str,
    username: str,
    rank: str,
    group_name: str,
    avatar: bytes | None,
) -> BytesIO:
    img  = Image.new("RGBA", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (5, CARD_H)], fill=STRIPE)

    av_size = 110
    av_x    = 26
    av_y    = (CARD_H - av_size) // 2
    if avatar:
        av   = Image.open(BytesIO(avatar)).convert("RGBA").resize((av_size, av_size))
        mask = Image.new("L", (av_size, av_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, av_size, av_size), fill=255)
        av.putalpha(mask)
        img.paste(av, (av_x, av_y), av)
    else:
        draw.ellipse((av_x, av_y, av_x + av_size, av_y + av_size), fill=STRIPE)

    f_big, f_med, f_sm = _load_fonts()
    tx = av_x + av_size + 20

    draw.text((tx, 32), display_name,   font=f_big, fill=FG)
    draw.text((tx, 68), f"@{username}", font=f_med, fill=MUTED)
    draw.text((tx, 94), group_name,     font=f_sm,  fill=MUTED)

    pad_x, pad_y = 12, 5
    bb = draw.textbbox((0, 0), rank, font=f_sm)
    pw = bb[2] - bb[0] + pad_x * 2
    ph = bb[3] - bb[1] + pad_y * 2
    rx, ry = tx, 118
    draw.rounded_rectangle((rx, ry, rx + pw, ry + ph), radius=5, fill=BADGE_BG, outline=BADGE_BORDER)
    draw.text((rx + pad_x, ry + pad_y), rank, font=f_sm, fill=FG)

    draw.text((CARD_W - 196, CARD_H - 22), _now_str(), font=f_sm, fill=MUTED)

    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf

# Bot


intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
bot  = commands.Bot(command_prefix=",", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
    bot.db = await asyncpg.create_pool(DATABASE_URL)  # type: ignore[attr-defined]
    bot.started_at = datetime.datetime.now(datetime.timezone.utc)  # type: ignore[attr-defined]
    await init_db(bot.db)
    await refresh_group_roles()

    for guild_obj in GUILD_OBJECTS:
        try:
            await tree.sync(guild=guild_obj)
        except discord.Forbidden:
            print(f"missing access to sync guild {guild_obj.id} — invite the bot first")

    # Global sync for commands without @app_commands.guilds() (e.g. /tag, /crewblacklist)
    try:
        await tree.sync()
    except Exception as e:
        print(f"global sync failed: {e}")

    for gid in ALLOWED_GUILDS:
        guild = bot.get_guild(gid)
        if guild:
            async for member in guild.fetch_members(limit=None):
                if not member.bot:
                    await db_track(bot.db, member.id)

    print(f"online as {bot.user}")


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id not in ALLOWED_GUILDS or member.bot:
        return
    await db_track(bot.db, member.id)


@bot.event
async def on_member_remove(member: discord.Member):
    if member.guild.id not in ALLOWED_GUILDS:
        return
    await db_untrack(bot.db, member.id)

# /tag

_pending_tags: dict[str, dict] = {}


def _profile_url(uid: int) -> str:
    return f"https://www.roblox.com/users/{uid}/profile"


TAG_ACCENT = 0x3F3FE6


def _user_container(
    title: str,
    uid: int,
    display_name: str,
    roblox_username: str,
    body: str,
) -> dict:
    """Plain container: title, name line, optional body. Single accent color."""
    if not display_name or display_name.lower() == roblox_username.lower():
        name_line = f"[**@{roblox_username}**](<{_profile_url(uid)}>)"
    else:
        name_line = f"[**{display_name}**](<{_profile_url(uid)}>) `@{roblox_username}`"

    components: list[dict] = [
        {"type": 10, "content": f"## {title}"},
        {"type": 10, "content": name_line},
    ]
    if body:
        components.append({"type": 14, "spacing": 1, "divider": True})
        components.append({"type": 10, "content": body})
    return {
        "type": 17,
        "accent_color": TAG_ACCENT,
        "spoiler": False,
        "components": components,
    }


def _action_row_confirm(nonce: str) -> dict:
    return {
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "Confirm", "custom_id": f"tagconf:{nonce}:confirm"},
            {"type": 2, "style": 4, "label": "Cancel",  "custom_id": f"tagconf:{nonce}:cancel"},
        ],
    }


def _action_row_nav(nonce: str, page: int, total: int) -> dict:
    return {
        "type": 1,
        "components": [
            {
                "type": 2, "style": 2, "label": "◄",
                "custom_id": f"tagnav:{nonce}:prev",
                "disabled": page <= 0,
            },
            {
                "type": 2, "style": 2, "label": "►",
                "custom_id": f"tagnav:{nonce}:next",
                "disabled": page >= total - 1,
            },
        ],
    }


async def _run_with_loader(
    interaction: discord.Interaction,
    api_coro,
    frame_text_fn,
    frame_interval: float = 0.6,
    min_duration: float = 2.0,
):
    """
    Run api_coro concurrently with a dot-animation loader. Loader runs for at
    least min_duration seconds even if the API returns sooner, so the state
    is visible. If the API takes longer, loader keeps cycling until it lands.
    """
    api_task = asyncio.create_task(api_coro)
    dots_cycle = [".", "..", "...", ".", "..", "..."]
    start = asyncio.get_event_loop().time()

    for dots in dots_cycle:
        payload = {
            "type": 17,
            "accent_color": TAG_ACCENT,
            "spoiler": False,
            "components": [{"type": 10, "content": frame_text_fn(dots)}],
        }
        try:
            await _edit_interaction_v2(interaction, payload)
        except Exception:
            break
        await asyncio.sleep(frame_interval)
        elapsed = asyncio.get_event_loop().time() - start
        if api_task.done() and elapsed >= min_duration:
            break

    # If API still not done, keep cycling until it is
    while not api_task.done():
        for dots in dots_cycle:
            if api_task.done():
                break
            payload = {
                "type": 17,
                "accent_color": TAG_ACCENT,
                "spoiler": False,
                "components": [{"type": 10, "content": frame_text_fn(dots)}],
            }
            try:
                await _edit_interaction_v2(interaction, payload)
            except Exception:
                break
            await asyncio.sleep(frame_interval)

    return await api_task


def _prompt_container(prompt_line: str) -> dict:
    return {
        "type": 17,
        "accent_color": TAG_ACCENT,
        "spoiler": False,
        "components": [{"type": 10, "content": prompt_line}],
    }


def _groupcheck_container(
    roblox_username: str,
    uid: int,
    groups: list[dict],
    page: int,
    group_icon_url: str | None = None,
) -> dict:
    """Paginated groupcheck view — one group per page, mirrors reference layout."""
    total = len(groups)
    fallback_avatar_url = (
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
        f"?userIds={uid}&size=150x150&format=Png&isCircular=false"
    )
    accessory_url = group_icon_url or fallback_avatar_url
    accessory = {
        "type": 11,
        "media": {"url": accessory_url},
    }

    if total == 0:
        header = {
            "type": 9,
            "components": [
                {"type": 10, "content": "## Roblox"},
                {
                    "type": 10,
                    "content": (
                        f"[**{roblox_username}**](<{_profile_url(uid)}>)'s Joined groups\n"
                        f"No groups found."
                    ),
                },
            ],
            "accessory": accessory,
        }
        return {
            "type": 17,
            "accent_color": TAG_ACCENT,
            "spoiler": False,
            "components": [header],
        }

    g = groups[page]
    gid       = g["id"]
    members   = g["members"]
    public    = g["public"]
    rank      = g["rank"]

    header_section = {
        "type": 9,
        "components": [
            {"type": 10, "content": "## Roblox"},
            {
                "type": 10,
                "content": f"[**{roblox_username}**](<{_profile_url(uid)}>)'s Joined groups",
            },
        ],
        "accessory": accessory,
    }

    fields = (
        f"> Members: {members}\n"
        f"> Public: {public}\n"
        f"> Rank: {rank}\n"
        f"> Group Id: `{gid}`"
    )

    return {
        "type": 17,
        "accent_color": TAG_ACCENT,
        "spoiler": False,
        "components": [
            header_section,
            {"type": 14, "spacing": 1, "divider": True},
            {"type": 10, "content": fields},
            {"type": 10, "content": f"-# Page {page + 1}/{total}"},
        ],
    }


async def _edit_interaction_v2(
    interaction: discord.Interaction,
    *components: dict,
    file: discord.File | None = None,
):
    payload = {
        "components": list(components),
        "flags": 32768,
        "allowed_mentions": {"parse": []},
    }
    url = f"https://discord.com/api/v10/webhooks/{interaction.application_id}/{interaction.token}/messages/@original"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        if file:
            form = aiohttp.FormData()
            form.add_field("payload_json", json.dumps(payload), content_type="application/json")
            file.fp.seek(0)
            form.add_field("files[0]", file.fp, filename=file.filename, content_type="image/png")
            async with s.patch(url, data=form, headers=headers) as r:
                return r.status
        else:
            async with s.patch(url, json=payload, headers=headers) as r:
                return r.status


async def _ack_component_edit(interaction: discord.Interaction, *components: dict):
    """Respond to a button click by editing the source message (type 7)."""
    payload = {
        "type": 7,
        "data": {
            "components": list(components),
            "flags": 32768,
            "allowed_mentions": {"parse": []},
        },
    }
    url = f"https://discord.com/api/v10/interactions/{interaction.id}/{interaction.token}/callback"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload) as r:
            return r.status


async def rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    group_key = interaction.namespace.group
    roles     = _group_roles.get(group_key, [])
    return [
        app_commands.Choice(name=name, value=name)
        for _, name in roles
        if current.lower() in name.lower()
    ][:25]


@tree.command(name="tag", description="Rank someone in a Roblox group")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    roblox="Their Roblox username",
    group="Which group",
    rank="Rank to assign",
)
@app_commands.choices(group=GROUP_CHOICES)
@app_commands.autocomplete(rank=rank_autocomplete)
async def tag_cmd(
    interaction: discord.Interaction,
    roblox: str,
    group: str,
    rank: str,
):
    reason = await db_cmd_disabled_reason(bot.db, "tag")  # type: ignore[attr-defined]
    if reason and not is_botdev(interaction.user.id):
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if not await can_tag(bot.db, interaction.user, group):  # type: ignore[attr-defined]
        await interaction.response.send_message("Not whitelisted.", ephemeral=True)
        return

    roles   = _group_roles.get(group, [])
    role_id = next((rid for rid, name in roles if name == rank), None)
    if role_id is None:
        await interaction.response.send_message("Rank not found.", ephemeral=True)
        return

    if await db_rank_is_locked(bot.db, group, rank) and not is_botdev(interaction.user.id):  # type: ignore[attr-defined]
        await interaction.response.send_message("That rank is locked.", ephemeral=True)
        return

    await interaction.response.defer()

    # Step 1: resolve user + verify they're in the target group
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        user_data = await rbx_user(session, roblox)
        if not user_data:
            await _edit_interaction_v2(interaction, _container(0xE63F3F, "User not found."))
            return

        uid          = user_data["id"]
        display_name = user_data.get("displayName", roblox)
        avatar       = await rbx_avatar(session, uid)

    # Single loader: fetches all groups, then derives membership + current rank locally
    user_groups_detailed = await _run_with_loader(
        interaction,
        rbx_fetch_user_groups_detailed(uid),
        lambda dots: f"checking [{roblox}](<{_profile_url(uid)}>)'s groups{dots}",
    )

    target_gid = GROUPS[group]
    target_entry = next((g for g in user_groups_detailed if int(g["id"]) == int(target_gid)), None)

    if target_entry is None:
        print(
            f"/tag not-in-group: looking for gid={target_gid} ({group}) "
            f"in uid={uid} groups={[(g['id'], g['name']) for g in user_groups_detailed]}"
        )
        # Cross-check with the v1 endpoint before giving up (v2 has been unreliable)
        v1_check = await rbx_get_role(GROUPS[group], uid)
        if v1_check is not None:
            print(f"/tag not-in-group: v1 fallback found user! role={v1_check}")
            target_entry = {
                "id":      target_gid,
                "name":    group,
                "members": 0,
                "public":  False,
                "rank":    v1_check[1],
            }
        else:
            # Surface the diagnostic in the message so we can see what's happening
            found_list = ", ".join(f"`{g['name']}`({g['id']})" for g in user_groups_detailed[:15])
            if not found_list:
                found_list = "*(none)*"
            debug_body = (
                f"Not a member of `{group}` (looking for id `{target_gid}`).\n\n"
                f"**API returned {len(user_groups_detailed)} groups:**\n{found_list}"
            )
            await _edit_interaction_v2(
                interaction,
                _user_container(
                    "Not in group",
                    uid,
                    display_name,
                    roblox,
                    debug_body,
                ),
            )
            return

    current_rank_name = target_entry["rank"]
    # Resolve the role_id of the user's current rank from _group_roles
    current_role_id = next((rid for rid, name in _group_roles.get(group, []) if name == current_rank_name), None)
    if current_role_id == role_id:
        await _edit_interaction_v2(
            interaction,
            _user_container(
                "Already tagged",
                uid,
                display_name,
                roblox,
                f"Already `{rank}` in `{group}`.",
            ),
        )
        return

    group_ids   = [g["id"] for g in user_groups_detailed]
    blocked_ids = await db_crewbl_check_many(bot.db, group_ids)  # type: ignore[attr-defined]

    blocked_hits = [(g["id"], g["name"]) for g in user_groups_detailed if g["id"] in blocked_ids]

    if blocked_hits:
        for dots in [".", "..", "...", ".", "..", "..."]:
            payload = {
                "type": 17,
                "accent_color": TAG_ACCENT,
                "spoiler": False,
                "components": [
                    {"type": 10, "content": f"found blacklisted groups **loading groups{dots}**"},
                ],
            }
            try:
                await _edit_interaction_v2(interaction, payload)
            except Exception:
                break
            await asyncio.sleep(0.6)

    if blocked_hits and not is_botdev(interaction.user.id):
        blocked_list = ", ".join(f"`{gname}`" for _, gname in blocked_hits)
        await _edit_interaction_v2(
            interaction,
            _user_container(
                "Blocked",
                uid,
                display_name,
                roblox,
                f"In blacklisted crew: {blocked_list}",
            ),
        )
        return

    # Only show groups that are blacklisted (only reachable if botdev; regular users hit the Blocked branch above)
    shown_groups = [g for g in user_groups_detailed if g["id"] in blocked_ids]

    nonce = secrets.token_urlsafe(8)
    prompt_line = (
        f"Do you want to give {display_name} "
        f"([@{roblox}](<{_profile_url(uid)}>))  ``{rank}``?"
    )
    if blocked_hits:
        prompt_line += (
            "\n\nOverride: blacklisted groups — "
            + ", ".join(f"`{gname}`" for _, gname in blocked_hits)
        )

    _pending_tags[nonce] = {
        "initiator_id": interaction.user.id,
        "roblox":       roblox,
        "uid":          uid,
        "display_name": display_name,
        "group":        group,
        "role_id":      role_id,
        "rank":         rank,
        "avatar":       avatar,
        "groups":       shown_groups,
        "blocked_ids":  blocked_ids,
        "page":         0,
        "prompt":       prompt_line,
    }

    if shown_groups:
        first_icon = await rbx_fetch_group_icon(shown_groups[0]["id"])
        container = _groupcheck_container(
            roblox_username=roblox,
            uid=uid,
            groups=shown_groups,
            page=0,
            group_icon_url=first_icon,
        )
        await _edit_interaction_v2(
            interaction,
            container,
            _prompt_container(prompt_line),
            _action_row_nav(nonce, 0, len(shown_groups)),
            _action_row_confirm(nonce),
        )
    else:
        confirm_container = {
            "type": 17,
            "accent_color": TAG_ACCENT,
            "spoiler": False,
            "components": [
                {"type": 10, "content": "Confirm"},
                {"type": 14, "spacing": 1, "divider": True},
                {"type": 10, "content": prompt_line},
            ],
        }
        await _edit_interaction_v2(
            interaction,
            confirm_container,
            _action_row_confirm(nonce),
        )


async def _handle_tag_confirm(interaction: discord.Interaction, nonce: str, action: str):
    state = _pending_tags.get(nonce)
    if not state:
        await _ack_component_edit(
            interaction,
            _container(0xE63F3F, "This confirmation has expired."),
        )
        return

    if interaction.user.id != state["initiator_id"]:
        # Silent reject via ephemeral followup after ack
        payload = {
            "type": 4,
            "data": {
                "content": "Only the command initiator can confirm this.",
                "flags": 64,
            },
        }
        url = f"https://discord.com/api/v10/interactions/{interaction.id}/{interaction.token}/callback"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload):
                pass
        return

    if action == "cancel":
        _pending_tags.pop(nonce, None)
        await _ack_component_edit(
            interaction,
            _container(0x5C5C6E, "Tag Cancelled", "No changes were made."),
        )
        return

    # confirm
    _pending_tags.pop(nonce, None)
    roblox       = state["roblox"]
    uid          = state["uid"]
    display_name = state["display_name"]
    group        = state["group"]
    role_id      = state["role_id"]
    rank         = state["rank"]
    avatar       = state["avatar"]

    # Ack immediately with a "processing" state so the button click doesn't time out
    await _ack_component_edit(
        interaction,
        _container(0x5C5C6E, "Processing tag..."),
    )

    ok, err = await rbx_set_rank(GROUPS[group], uid, role_id)
    if not ok:
        await _edit_interaction_v2(interaction, _container(0xE63F3F, err))
        return

    await db_set_roblox(bot.db, interaction.user.id, roblox)  # type: ignore[attr-defined]

    card  = make_rank_card(display_name, roblox, rank, group, avatar)
    dfile = discord.File(card, filename="tag.png")
    card_container = _container(
        0x3F3FE6,
        "Tag Changed",
        f"> Gave @{roblox} ({display_name}) **{rank}**\n"
        f"> Group: {group}\n"
        f"> Moderator: {interaction.user.mention}",
    )

    await _edit_interaction_v2(interaction, card_container, file=dfile)

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0x3F3FE6,
            "Tag Update",
            f"Roblox: [{display_name}](<https://www.roblox.com/users/{uid}/profile>) "
            f"([{roblox}](<https://www.roblox.com/users/{uid}/profile>)) has been given the ``{rank}``\n"
            f"Moderator: {interaction.user.mention} ``{interaction.user.id}``",
        ),
    )


async def _handle_tag_nav(interaction: discord.Interaction, nonce: str, action: str):
    state = _pending_tags.get(nonce)
    if not state:
        await _ack_component_edit(
            interaction,
            _container(0xE63F3F, "This confirmation has expired."),
        )
        return

    if interaction.user.id != state["initiator_id"]:
        payload = {
            "type": 4,
            "data": {"content": "Only the command initiator can page.", "flags": 64},
        }
        url = f"https://discord.com/api/v10/interactions/{interaction.id}/{interaction.token}/callback"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload):
                pass
        return

    groups: list[dict] = state["groups"]
    total = len(groups)
    page  = state["page"]
    if action == "prev":
        page = max(0, page - 1)
    elif action == "next":
        page = min(total - 1, page + 1)
    state["page"] = page

    icon_url = await rbx_fetch_group_icon(groups[page]["id"]) if groups else None
    container = _groupcheck_container(
        roblox_username=state["roblox"],
        uid=state["uid"],
        groups=groups,
        page=page,
        group_icon_url=icon_url,
    )

    await _ack_component_edit(
        interaction,
        container,
        _prompt_container(state["prompt"]),
        _action_row_nav(nonce, page, total),
        _action_row_confirm(nonce),
    )


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    data = interaction.data or {}
    custom_id = data.get("custom_id", "")
    parts = custom_id.split(":")
    if len(parts) != 3:
        return
    prefix, nonce, action = parts
    if prefix == "tagconf":
        await _handle_tag_confirm(interaction, nonce, action)
    elif prefix == "tagnav":
        await _handle_tag_nav(interaction, nonce, action)

# /fa


TIER_CHOICES = [
    app_commands.Choice(name="Owner", value="owner"),
    app_commands.Choice(name="Staff", value="staff"),
]


@tree.command(name="fa", description="Add or remove a user from a group's whitelist")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(
    user="Discord user",
    group="Which group",
    tier="Owner (can tag + manage Staff) or Staff (can tag only)",
)
@app_commands.choices(group=GROUP_CHOICES, tier=TIER_CHOICES)
async def fa_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    group: str,
    tier: str,
):
    reason = await db_cmd_disabled_reason(bot.db, "fa")  # type: ignore[attr-defined]
    if reason and not is_botdev(interaction.user.id):
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if not await can_fa(bot.db, interaction.user.id, group):  # type: ignore[attr-defined]
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    if tier == "owner" and not is_botdev(interaction.user.id):
        await interaction.response.send_message("Bot Developer only.", ephemeral=True)
        return

    if await db_bl_check(bot.db, user.id, "whitelist"):  # type: ignore[attr-defined]
        await interaction.response.send_message("That user is blacklisted.", ephemeral=True)
        return

    existing = await db_wl_get_tier(bot.db, user.id, group)  # type: ignore[attr-defined]

    if existing == tier:
        await db_wl_remove(bot.db, user.id, group)  # type: ignore[attr-defined]
        action = f"removed from {group}"
    else:
        await db_wl_set(bot.db, user.id, group, tier)  # type: ignore[attr-defined]
        action = f"set to {tier.capitalize()} in {group}"

    await interaction.response.send_message(f"{user.mention} {action}.", ephemeral=True)

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0xF0A500,
            "Whitelist Updated",
            f"> User: {user.mention}\n"
            f"> Group: {group}\n"
            f"> Action: {action}\n"
            f"> By: {interaction.user.mention}",
        ),
    )

# ,rl #channel

@tree.command(
    name="cleartags",
    description="Remove everyone from a specific Roblox rank (Founder only)"
)
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(
    group="Which group",
    rank="Rank to clear"
)
@app_commands.choices(group=GROUP_CHOICES)
@app_commands.autocomplete(rank=rank_autocomplete)
async def cleartags_cmd(
    interaction: discord.Interaction,
    group: str,
    rank: str,
):
    if not is_founder(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    roles = _group_roles.get(group, [])
    target_role = next((rid for rid, name in roles if name == rank), None)

    if target_role is None:
        await interaction.followup.send("Rank not found.")
        return

    lowest_role = roles[0][0] if roles else None
    if lowest_role is None:
        await interaction.followup.send("No ranks found.")
        return

    token = await _xcsrf()

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        # Get every member in the group
        async with session.get(
            f"https://groups.roblox.com/v1/groups/{GROUPS[group]}/users?limit=100",
            headers={"Cookie": ROBLOX_COOKIE},
        ) as r:
            if r.status != 200:
                await interaction.followup.send("Failed to fetch group members.")
                return

            data = await r.json()

    moved = 0

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        for member in data.get("data", []):
            if member["role"]["id"] != target_role:
                continue

            uid = member["user"]["userId"]

            async with session.patch(
                f"https://groups.roblox.com/v1/groups/{GROUPS[group]}/users/{uid}",
                json={"roleId": lowest_role},
                headers=_rbx_headers(token),
            ) as r:
                if r.status == 200:
                    moved += 1

    await interaction.followup.send(
        f"Removed **{moved}** users from **{rank}** in **{group}**."
    )

    await post_log(
        bot.db,
        _container(
            0xE63F3F,
            "Tags Cleared",
            f"> Group: {group}\n"
            f"> Rank: {rank}\n"
            f"> Users affected: {moved}\n"
            f"> By: {interaction.user.mention}",
        ),
    )
@bot.command(name="rl")
async def rl_cmd(ctx: commands.Context, channel: discord.TextChannel):
    if not is_botdev(ctx.author.id):
        return
    await db_set_config(bot.db, "log_channel", str(channel.id))  # type: ignore[attr-defined]
    await ctx.reply(f"logs → {channel.mention}")


@bot.command(name="rw")
async def rw_cmd(ctx: commands.Context, group: str, role: discord.Role):
    if not is_botdev(ctx.author.id):
        return
    if group not in GROUPS:
        await ctx.reply(f"unknown group. options: {', '.join(GROUP_KEYS)}")
        return
    added = await db_rwl_toggle(bot.db, role.id, group)  # type: ignore[attr-defined]
    if added:
        await ctx.reply(f"added {role.mention} to {group} whitelist")
    else:
        await ctx.reply(f"removed {role.mention} from {group} whitelist")


# /remove

async def current_rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    group_key = interaction.namespace.group
    roblox    = interaction.namespace.roblox
    if not group_key or not roblox:
        return []
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        user_data = await rbx_user(session, roblox)
        if not user_data:
            return []
        uid    = user_data["id"]
        result = await rbx_get_role(GROUPS[group_key], uid)
        if not result:
            return []
        _, name = result
        if current.lower() in name.lower():
            return [app_commands.Choice(name=name, value=name)]
    return []


@tree.command(name="remove", description="Remove someone's rank from a Roblox group")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(roblox="Their Roblox username", group="Which group", rank="Their current rank (autofilled)")
@app_commands.choices(group=GROUP_CHOICES)
@app_commands.autocomplete(rank=current_rank_autocomplete)
async def remove_cmd(
    interaction: discord.Interaction,
    roblox: str,
    group: str,
    rank: str,
):
    reason = await db_cmd_disabled_reason(bot.db, "remove")  # type: ignore[attr-defined]
    if reason and not is_botdev(interaction.user.id):
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Server only.", ephemeral=True)
        return

    if not await can_tag(bot.db, interaction.user, group):  # type: ignore[attr-defined]
        await interaction.response.send_message("Not whitelisted.", ephemeral=True)
        return

    await interaction.response.defer()

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        user_data = await rbx_user(session, roblox)
        if not user_data:
            await interaction.followup.send("User not found.")
            return

    uid          = user_data["id"]
    display_name = user_data.get("displayName", roblox)

    roles       = _group_roles.get(group, [])
    lowest_id   = roles[0][0] if roles else None
    if lowest_id is None:
        await interaction.followup.send("No ranks found for group.")
        return

    ok, err = await rbx_set_rank(GROUPS[group], uid, lowest_id)
    if not ok:
        await interaction.followup.send(err)
        return

    tag_container = _container(
        0xE63F3F,
        "Rank Removed",
        f"> Removed **{rank}** from @{roblox} ({display_name})\n"
        f"> Group: {group}\n"
        f"> Moderator: {interaction.user.mention}",
    )
    await reply_v2(interaction, tag_container)

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0xE63F3F,
            "Remove Log",
            f"> Roblox: @{roblox} ({display_name})\n"
            f"> Rank removed: {rank}\n"
            f"> Group: {group}\n"
            f"> By: {interaction.user.mention}",
        ),
    )


# /blacklist


BL_CHOICES = [
    app_commands.Choice(name="Group", value="group"),
    app_commands.Choice(name="Whitelist", value="whitelist"),
]


@tree.command(name="blacklist", description="Blacklist a user from a group or the whitelist system")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(
    user="Discord user to blacklist",
    type="Group = exile from Roblox group. Whitelist = block from tagging/being whitelisted.",
    group="Required when type is Group",
    roblox="Roblox username — required when type is Group",
)
@app_commands.choices(type=BL_CHOICES, group=GROUP_CHOICES)
async def blacklist_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    type: str,
    group: str | None = None,
    roblox: str | None = None,
):
    reason = await db_cmd_disabled_reason(bot.db, "blacklist")  # type: ignore[attr-defined]
    if reason and not is_botdev(interaction.user.id):
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    if type == "group":
        if not group or not roblox:
            await interaction.response.send_message("Provide group and roblox when using Group.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
            user_data = await rbx_user(session, roblox)
            if not user_data:
                await interaction.followup.send("Roblox user not found.")
                return

        uid          = user_data["id"]
        display_name = user_data.get("displayName", roblox)

        ok, err = await rbx_exile(GROUPS[group], uid)
        if not ok:
            await interaction.followup.send(err)
            return

        await db_bl_add(bot.db, user.id, "group", group)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Exiled @{roblox} from {group} and recorded.")

        await post_log(
            bot.db,  # type: ignore[attr-defined]
            _container(
                0xE63F3F,
                "Group Blacklist",
                f"> Discord: {user.mention}\n"
                f"> Roblox: @{roblox} ({display_name})\n"
                f"> Group: {group}\n"
                f"> By: {interaction.user.mention}",
            ),
        )

    else:  # whitelist
        already = await db_bl_check(bot.db, user.id, "whitelist")  # type: ignore[attr-defined]
        if already:
            await db_bl_remove(bot.db, user.id, "whitelist")  # type: ignore[attr-defined]
            await interaction.response.send_message(f"{user.mention} removed from whitelist blacklist.", ephemeral=True)
            action = "removed from whitelist blacklist"
        else:
            await db_bl_add(bot.db, user.id, "whitelist")  # type: ignore[attr-defined]
            await interaction.response.send_message(f"{user.mention} blacklisted from whitelist.", ephemeral=True)
            action = "blacklisted from whitelist"

        await post_log(
            bot.db,  # type: ignore[attr-defined]
            _container(
                0xE63F3F,
                "Whitelist Blacklist",
                f"> Discord: {user.mention}\n"
                f"> Action: {action}\n"
                f"> By: {interaction.user.mention}",
            ),
        )


# /crewblacklist

@tree.command(name="crewblacklist", description="Block a Roblox group from being tagged (Founder only)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(group_id="Roblox group ID to block/unblock")
async def crewblacklist_cmd(interaction: discord.Interaction, group_id: str):
    if not is_founder(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    try:
        gid = int(group_id)
    except ValueError:
        await interaction.response.send_message("Group ID must be a number.", ephemeral=True)
        return

    added = await db_crewbl_toggle(bot.db, gid, interaction.user.id)  # type: ignore[attr-defined]
    action = "added to" if added else "removed from"

    await interaction.response.send_message(
        f"Group `{gid}` {action} crew blacklist.", ephemeral=True
    )

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0xE63F3F,
            "Crew Blacklist Updated",
            f"> Group ID: `{gid}`\n"
            f"> Action: {action} crew blacklist\n"
            f"> By: {interaction.user.mention} (`{interaction.user.id}`)",
        ),
    )


# /unblacklist

@tree.command(name="unblacklist", description="Remove a user from the blacklist")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(
    user="Discord user to unblacklist",
    type="Group = remove group blacklist record. Whitelist = restore whitelist access.",
    group="Required when type is Group",
)
@app_commands.choices(type=BL_CHOICES, group=GROUP_CHOICES)
async def unblacklist_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    type: str,
    group: str | None = None,
):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    if type == "group":
        if not group:
            await interaction.response.send_message("Provide group when using Group.", ephemeral=True)
            return
        exists = await db_bl_check(bot.db, user.id, "group", group)  # type: ignore[attr-defined]
        if not exists:
            await interaction.response.send_message("Not blacklisted from that group.", ephemeral=True)
            return
        await db_bl_remove(bot.db, user.id, "group", group)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"{user.mention} removed from {group} blacklist.", ephemeral=True)
        action = f"removed from {group} blacklist"
    else:
        exists = await db_bl_check(bot.db, user.id, "whitelist")  # type: ignore[attr-defined]
        if not exists:
            await interaction.response.send_message("Not on whitelist blacklist.", ephemeral=True)
            return
        await db_bl_remove(bot.db, user.id, "whitelist")  # type: ignore[attr-defined]
        await interaction.response.send_message(f"{user.mention} removed from whitelist blacklist.", ephemeral=True)
        action = "removed from whitelist blacklist"

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0x3FE63F,
            "Blacklist Removed",
            f"> Discord: {user.mention}\n"
            f"> Action: {action}\n"
            f"> By: {interaction.user.mention}",
        ),
    )


# /accept

@tree.command(name="accept", description="Accept a Roblox group join request")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(roblox="Their Roblox username", group="Which group")
@app_commands.choices(group=GROUP_CHOICES)
async def accept_cmd(
    interaction: discord.Interaction,
    roblox: str,
    group: str,
):
    reason = await db_cmd_disabled_reason(bot.db, "accept")  # type: ignore[attr-defined]
    if reason and not is_botdev(interaction.user.id):
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Server only.", ephemeral=True)
        return

    tier = await get_group_tier(bot.db, interaction.user.id, group)  # type: ignore[attr-defined]
    if tier not in ("owner", "staff"):
        await interaction.response.send_message("Not whitelisted.", ephemeral=True)
        return

    await interaction.response.defer()

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        user_data = await rbx_user(session, roblox)
        if not user_data:
            await interaction.followup.send("User not found.")
            return

    uid          = user_data["id"]
    display_name = user_data.get("displayName", roblox)

    ok, err = await rbx_accept(GROUPS[group], uid)
    if not ok:
        await interaction.followup.send(err)
        return

    accept_container = _container(
        0x3FE63F,
        "Join Request Accepted",
        f"> Accepted @{roblox} ({display_name}) into **{group}**\n"
        f"> Moderator: {interaction.user.mention}",
    )
    await reply_v2(interaction, accept_container)

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0x3FE63F,
            "Accept Log",
            f"> Roblox: @{roblox} ({display_name})\n"
            f"> Group: {group}\n"
            f"> By: {interaction.user.mention}",
        ),
    )

# /toggle

CMD_CHOICES = [
    app_commands.Choice(name="tag",         value="tag"),
    app_commands.Choice(name="remove",      value="remove"),
    app_commands.Choice(name="accept",      value="accept"),
    app_commands.Choice(name="fa",          value="fa"),
    app_commands.Choice(name="blacklist",   value="blacklist"),
    app_commands.Choice(name="unblacklist", value="unblacklist"),
]


TOGGLE_ACTION_CHOICES = [
    app_commands.Choice(name="Disable", value="disable"),
    app_commands.Choice(name="Enable",  value="enable"),
]


@tree.command(name="toggle", description="Enable or disable a command for regular users")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(
    command="Command to toggle",
    action="Disable or enable",
    reason="What users see when disabled (required when disabling)",
)
@app_commands.choices(command=CMD_CHOICES, action=TOGGLE_ACTION_CHOICES)
async def toggle_cmd(
    interaction: discord.Interaction,
    command: str,
    action: str,
    reason: str = "",
):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    if action == "disable":
        if not reason:
            await interaction.response.send_message("Provide a reason so users know why it's disabled.", ephemeral=True)
            return
        await db_cmd_disable(bot.db, command, reason)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"`/{command}` disabled. Users see: \"{reason}\"")
    else:
        await db_cmd_enable(bot.db, command)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"`/{command}` enabled.")


# /info

@tree.command(name="info", description="Show a Roblox user's rank in all groups")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(roblox="Their Roblox username")
async def info_cmd(interaction: discord.Interaction, roblox: str):
    await interaction.response.defer()

    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        user_data = await rbx_user(session, roblox)
        if not user_data:
            await interaction.followup.send("User not found.")
            return

    uid          = user_data["id"]
    display_name = user_data.get("displayName", roblox)

    lines: list[str] = []
    for key, gid in GROUPS.items():
        result = await rbx_get_role(gid, uid)
        rank   = result[1] if result else "Not in group"
        lines.append(f"> **{key}:** {rank}")

    await reply_v2(
        interaction,
        _container(
            0x3F3FE6,
            f"@{roblox} ({display_name})",
            "\n".join(lines),
        ),
    )

# /whitelist

@tree.command(name="whitelist", description="List owners and staff for a group")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(group="Which group")
@app_commands.choices(group=GROUP_CHOICES)
async def whitelist_cmd(interaction: discord.Interaction, group: str):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer()

    entries = await db_wl_list(bot.db, group)  # type: ignore[attr-defined]

    owners = [f"> <@{uid}>" for uid, tier in entries if tier == "owner"]
    staff  = [f"> <@{uid}>" for uid, tier in entries if tier == "staff"]

    owner_block = "\n".join(owners) if owners else "> none"
    staff_block = "\n".join(staff)  if staff  else "> none"

    await reply_v2(
        interaction,
        _container(
            0x5C5C6E,
            f"{group} Whitelist",
            f"**Owners**\n{owner_block}",
            f"**Staff**\n{staff_block}",
        ),
    )

# /blacklistview

@tree.command(name="blacklistview", description="Show everyone currently on the blacklist")
@app_commands.guilds(*GUILD_OBJECTS)
async def blacklistview_cmd(interaction: discord.Interaction):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer()

    entries = await db_bl_list(bot.db)  # type: ignore[attr-defined]

    group_lines     = [f"> <@{uid}> — {gk}" for uid, t, gk in entries if t == "group"]
    whitelist_lines = [f"> <@{uid}>"         for uid, t, _  in entries if t == "whitelist"]

    group_block     = "\n".join(group_lines)     if group_lines     else "> none"
    whitelist_block = "\n".join(whitelist_lines) if whitelist_lines else "> none"

    await reply_v2(
        interaction,
        _container(
            0xE63F3F,
            "Blacklist",
            f"**Group Bans**\n{group_block}",
            f"**Whitelist Bans**\n{whitelist_block}",
        ),
    )

# /status

@tree.command(name="status", description="Show which commands are currently disabled")
@app_commands.guilds(*GUILD_OBJECTS)
async def status_cmd(interaction: discord.Interaction):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer()

    disabled: list[str] = []
    for cmd in [c.value for c in CMD_CHOICES]:
        reason = await db_cmd_disabled_reason(bot.db, cmd)  # type: ignore[attr-defined]
        if reason:
            disabled.append(f"> `/{cmd}` — {reason}")

    body = "\n".join(disabled) if disabled else "> All commands enabled."
    await reply_v2(interaction, _container(0xF0A500, "Command Status", body))

# /about

ABOUT_LOGO_URL = "https://cdn.discordapp.com/attachments/1530026213572087859/1531815972225286284/021b7561fc5220c5e70352f5e04e0580.jpg?ex=6a6a964b&is=6a6944cb&hm=c2c7071052887b6a9132df22cb426b47eb43d635adcedce8f7aebc37784e7057&"


def _format_uptime(delta: datetime.timedelta) -> str:
    total = int(delta.total_seconds())
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, _   = divmod(rem, 60)
    parts: list[str] = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


@tree.command(name="about", description="About this bot")
@app_commands.guilds(*GUILD_OBJECTS)
async def about_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    started_at: datetime.datetime = getattr(bot, "started_at", datetime.datetime.now(datetime.timezone.utc))
    uptime      = datetime.datetime.now(datetime.timezone.utc) - started_at
    uptime_str  = _format_uptime(uptime)
    latency_ms  = round(bot.latency * 1000)
    servers     = len(bot.guilds)
    groups      = len(GROUPS)
    tracked     = await db_tracked_count(bot.db)  # type: ignore[attr-defined]

    client_id   = bot.user.id if bot.user else 0
    invite_url  = (
        f"https://discord.com/oauth2/authorize?client_id={client_id}"
        f"&permissions=8&scope=bot+applications.commands"
    )

    stats_text = (
        f"Groups managed » `{groups}`\n"
        f"Servers » `{servers}`\n"
        f"Tracked members » `{tracked}`\n"
        f"Latency » `{latency_ms}ms`\n"
        f"Uptime » `{uptime_str}`"
    )

    stats_section = {
        "type": 9,
        "components": [{"type": 10, "content": stats_text}],
        "accessory": {"type": 11, "media": {"url": ABOUT_LOGO_URL}},
    }

    container = {
        "type": 17,
        "accent_color": 0x3F3FE6,
        "spoiler": False,
        "components": [
            {"type": 10, "content": "## Memory"},
            {"type": 10, "content": "Roblox group management for Rangers"},
            {"type": 10, "content": "Developed by [trent](<https://discord.com/users/878416460924465193>)"},
            {"type": 14, "spacing": 1, "divider": True},
            stats_section,
        ],
    }

    button_row = {
        "type": 1,
        "components": [
            {"type": 2, "style": 5, "label": "Add to server", "url": invite_url},
        ],
    }

    await _edit_interaction_v2(interaction, container, button_row)

# ,refresh

@bot.command(name="refresh")
async def refresh_cmd(ctx: commands.Context):
    if not is_botdev(ctx.author.id):
        return
    await refresh_group_roles()
    await ctx.reply("Group roles refreshed.")


# /refreshranks

@tree.command(name="refreshranks", description="Refresh cached group ranks from Roblox")
@app_commands.guilds(*GUILD_OBJECTS)
async def refreshranks_cmd(interaction: discord.Interaction):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    await refresh_group_roles()

    summary = "\n".join(
        f"> {key}: {len(_group_roles.get(key, []))} ranks" for key in GROUP_KEYS
    )
    await interaction.followup.send(f"Group ranks refreshed.\n{summary}")


# /locktag

@tree.command(name="locktag", description="Lock or unlock a rank so it can't be given out via /tag")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(group="Which group", rank="Rank to lock/unlock")
@app_commands.choices(group=GROUP_CHOICES)
@app_commands.autocomplete(rank=rank_autocomplete)
async def locktag_cmd(interaction: discord.Interaction, group: str, rank: str):
    if not is_botdev(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    locked = await db_rank_lock_toggle(bot.db, group, rank)  # type: ignore[attr-defined]

    await interaction.response.send_message(
        f"{rank} in {group} is now {'locked' if locked else 'unlocked'}."
    )


# /clearwhitelist

CLEARWL_GROUP_CHOICES = GROUP_CHOICES + [app_commands.Choice(name="All", value="all")]


@tree.command(name="clearwhitelist", description="Clear the whitelist for a group (Founder only)")
@app_commands.guilds(*GUILD_OBJECTS)
@app_commands.describe(group="Which group (or All)", keepowners="Keep owners and only remove staff?")
@app_commands.choices(group=CLEARWL_GROUP_CHOICES)
async def clearwhitelist_cmd(
    interaction: discord.Interaction,
    group: str,
    keepowners: bool,
):
    if not is_founder(interaction.user.id):
        await interaction.response.send_message("No perms.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    targets = list(GROUP_KEYS) if group == "all" else [group]
    total   = 0
    for g in targets:
        total += await db_wl_clear(bot.db, g, keepowners)  # type: ignore[attr-defined]

    label = "All groups" if group == "all" else group
    kept  = "owners kept" if keepowners else "all entries removed"
    await interaction.followup.send(f"{label} whitelist cleared — {total} removed ({kept}).")

    await post_log(
        bot.db,  # type: ignore[attr-defined]
        _container(
            0xE63F3F,
            "Whitelist Cleared",
            f"> Group: {label}\n"
            f"> Owners kept: {'yes' if keepowners else 'no'}\n"
            f"> Entries removed: {total}\n"
            f"> By: {interaction.user.mention}",
        ),
    )


bot.run(BOT_TOKEN)
