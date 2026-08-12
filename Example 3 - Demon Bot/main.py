import asyncio
import io
import os
import random
import re
from urllib.parse import quote

import aiohttp
import asyncpg
import discord
import httpx
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = (os.getenv("DCT") or "").strip()
COMMIT_SHA = os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")[:7]
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/callback")
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
PORT = int(os.getenv("PORT", 8080))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NAVY_API_KEY = (os.getenv("NAVY_API_KEY") or "").strip()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, max_messages=10000)

FOUNDER_ID = 878416460924465193
FOUNDER_IDS = {878416460924465193, 1484390959008583831}

RANKS = {
    "founder": 1,
    "fa": 1,
    "owner": 2,
    "friend": 3,
    "staff": 4,
}

GIF = "https://cdn.discordapp.com/attachments/1510889279231098932/1523601338183716904/4e836835dcb96ed29267dc4d09850e4c.gif?ex=6a4cb3d2&is=6a4b6252&hm=5d481b7e3318cc889f0f0d0f09b48c43bd08e373343221c69413b6e3ca68eafb&"

db: asyncpg.Pool = None
http_client: httpx.AsyncClient = None


# --- db helpers ---

async def get_rank(user_id: int) -> str | None:
    if user_id in FOUNDER_IDS:
        return "founder"
    row = await db.fetchrow("SELECT rank FROM whitelist WHERE user_id = $1", user_id)
    return row["rank"] if row else None


async def load_whitelist() -> dict:
    rows = await db.fetch("SELECT user_id, rank FROM whitelist")
    return {str(r["user_id"]): r["rank"] for r in rows}


async def save_whitelist_entry(user_id: int, rank: str):
    await db.execute(
        "INSERT INTO whitelist (user_id, rank) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET rank = $2",
        user_id, rank
    )


async def delete_whitelist_entry(user_id: int):
    await db.execute("DELETE FROM whitelist WHERE user_id = $1", user_id)


async def load_hardbans() -> dict:
    rows = await db.fetch("SELECT user_id, reason FROM hardbans")
    return {str(r["user_id"]): r["reason"] for r in rows}


async def save_hardban(user_id: int, reason: str):
    await db.execute(
        "INSERT INTO hardbans (user_id, reason) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET reason = $2",
        user_id, reason
    )


async def delete_hardban(user_id: int):
    await db.execute("DELETE FROM hardbans WHERE user_id = $1", user_id)


async def increment_info_uses() -> int:
    row = await db.fetchrow(
        "INSERT INTO stats (key, value) VALUES ('info_uses', 1) ON CONFLICT (key) DO UPDATE SET value = stats.value + 1 RETURNING value"
    )
    return row["value"]


async def get_info_uses() -> int:
    row = await db.fetchrow("SELECT value FROM stats WHERE key = 'info_uses'")
    return row["value"] if row else 0


# --- component helpers ---

async def send_components(ctx, payload):
    await ctx.message.delete()
    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=payload)


def component_msg(lines: list[dict]) -> dict:
    return {
        "flags": 32768,
        "allowed_mentions": {"parse": []},
        "components": [{
            "type": 17,
            "accent_color": 5631,
            "spoiler": False,
            "components": lines
        }]
    }


# --- oauth2 web server ---

async def oauth_callback(request: web.Request) -> web.Response:
    code = request.rel_url.query.get("code")
    if not code:
        return web.Response(text="Missing code.", status=400)

    async with aiohttp.ClientSession() as session:
        token_resp = await session.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_data = await token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return web.Response(text="Failed to get token.", status=400)

        refresh_token = token_data.get("refresh_token")

        user_resp = await session.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_data = await user_resp.json()
        user_id = user_data.get("id")
        if not user_id:
            return web.Response(text="Failed to get user.", status=400)

    await db.execute(
        "INSERT INTO user_tokens (user_id, access_token, refresh_token) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET access_token = $2, refresh_token = $3",
        int(user_id), access_token, refresh_token
    )
    print(f"[callback] saved token for user {user_id}")

    return web.Response(
        text="<html><body style='background:#1a1a2e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0'><h2>You're all set. The bot can now move you when needed. You can close this tab.</h2></body></html>",
        content_type="text/html",
    )


async def start_webserver():
    app = web.Application()
    app.router.add_get("/callback", oauth_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web server running on port {PORT}")


# --- bot events ---

TARGET_GUILD_ID = 1523884556091134083


async def refresh_access_token(refresh_token: str) -> str | None:
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = await resp.json()
        if "access_token" in data:
            return data["access_token"], data.get("refresh_token")
        return None, None


async def auto_pull_task():
    await asyncio.sleep(5)
    while True:
        rows = await db.fetch("SELECT user_id, access_token, refresh_token FROM user_tokens")
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            for row in rows:
                access_token = row["access_token"]
                # refresh token first if we have one
                if row["refresh_token"]:
                    new_access, new_refresh = await refresh_access_token(row["refresh_token"])
                    if new_access:
                        access_token = new_access
                        await db.execute(
                            "UPDATE user_tokens SET access_token = $1, refresh_token = $2 WHERE user_id = $3",
                            new_access, new_refresh, row["user_id"]
                        )
                try:
                    await session.put(
                        f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/members/{row['user_id']}",
                        headers=headers,
                        json={"access_token": access_token},
                    )
                except Exception:
                    pass
        await asyncio.sleep(30 * 24 * 60 * 60)  # 30 days


@bot.event
async def on_ready():
    global db, http_client
    db = await asyncpg.create_pool(DATABASE_URL)
    http_client = httpx.AsyncClient(timeout=15)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (user_id BIGINT PRIMARY KEY, rank TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hardbans (user_id BIGINT PRIMARY KEY, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value BIGINT NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS user_tokens (user_id BIGINT PRIMARY KEY, access_token TEXT NOT NULL, refresh_token TEXT);
        ALTER TABLE user_tokens ADD COLUMN IF NOT EXISTS refresh_token TEXT;
        CREATE TABLE IF NOT EXISTS raid_points (user_id BIGINT PRIMARY KEY, points BIGINT NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS raid_config (key TEXT PRIMARY KEY, value BIGINT NOT NULL);
        CREATE TABLE IF NOT EXISTS roblox_links (discord_id BIGINT PRIMARY KEY, roblox_id BIGINT NOT NULL, roblox_name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS word_filter (word TEXT PRIMARY KEY);
        INSERT INTO stats (key, value) VALUES ('info_uses', 0) ON CONFLICT DO NOTHING;
    """)
    asyncio.create_task(start_webserver())
    asyncio.create_task(auto_pull_task())
    await bot.tree.sync()
    for guild in bot.guilds:
        await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} ({bot.user.id})")

    # post update embed to first available channel in the target guild only
    UPDATE_GUILD_ID = 1511221374042243122
    payload = component_msg([
        {"type": 10, "content": "**Bot Updated**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> Updated to latest commit: `{COMMIT_SHA}`"},
    ])
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    update_guild = bot.get_guild(UPDATE_GUILD_ID)
    if update_guild:
        for channel in update_guild.text_channels:
            try:
                async with aiohttp.ClientSession() as session:
                    resp = await session.post(
                        f"https://discord.com/api/v10/channels/{channel.id}/messages",
                        headers=headers, json=payload
                    )
                if resp.status in (200, 201):
                    break
            except Exception:
                continue


# info

@bot.command(name="info")
@commands.cooldown(1, 10, commands.BucketType.user)
async def info(ctx):
    uses = await increment_info_uses()
    payload = component_msg([
        {"type": 10, "content": f"**Hi, I'm {bot.user.name}**"},
        {"type": 14, "spacing": 2, "divider": True},
        {"type": 10, "content": "**What I do:**\n> Track raid points for every member\n> Handle promotions when **cfrm** approves\n> Manage whitelisted server access"},
        {"type": 12, "items": [{"media": {"url": GIF}, "description": None, "spoiler": False}]},
        {"type": 10, "content": f"-# !info used `{uses}` times"}
    ])
    await send_components(ctx, payload)


@info.error
async def info_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.message.delete()
        await ctx.send(f"Cooldown — try again in `{error.retry_after:.1f}s`.", delete_after=4)


# --- hardban ---

async def has_full_access(ctx) -> bool:
    if ctx.author.id in FOUNDER_IDS:
        return True
    return await get_rank(ctx.author.id) == "fa"


@bot.command(name="hb")
async def hardban(ctx, user: discord.User, *, reason: str = "No reason provided"):
    if not await has_full_access(ctx):
        return
    if user.id == ctx.author.id:
        return await ctx.send("you cant ban yourself", delete_after=4)
    if user.id in FOUNDER_IDS:
        return await ctx.send("you cant ban the owner", delete_after=4)
    target_rank = await get_rank(user.id)
    if target_rank == "founder":
        return await ctx.send("you cant ban a founder", delete_after=4)
    author_rank = await get_rank(ctx.author.id)
    if target_rank and RANKS.get(target_rank, 99) < RANKS.get(author_rank or "staff", 99):
        return await ctx.send("you cant ban someone with a higher rank", delete_after=4)
    await save_hardban(user.id, reason)
    try:
        await ctx.guild.ban(user, reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        await ctx.message.delete()
        return await ctx.send("error - no perms", delete_after=4)
    payload = component_msg([
        {"type": 10, "content": "Hardbanned"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> {user.mention} has been **hardbanned** and added to the db\n> reason: {reason}"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": "-# u have to be whitelisted as **founder** to unban"}
    ])
    await send_components(ctx, payload)


@bot.command(name="unhb")
async def unhardban(ctx, user: discord.User, *, reason: str = "No reason provided"):
    if not await has_full_access(ctx):
        return
    hb = await load_hardbans()
    was_hardbanned = str(user.id) in hb
    if was_hardbanned:
        await delete_hardban(user.id)
    try:
        await ctx.guild.unban(user, reason=reason)
    except discord.NotFound:
        if not was_hardbanned:
            await ctx.message.delete()
            return await ctx.send(f"**{user}** isn't banned.", delete_after=4)
    payload = component_msg([
        {"type": 10, "content": "Unbanned"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> {user.mention} has been **unbanned** and removed from the db\n> moderator: {ctx.author.mention}\n> reason: {reason}"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": "-# hardban lifted by founder"}
    ])
    await send_components(ctx, payload)


class UnbanAllView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        rank = await get_rank(interaction.user.id)
        if interaction.user.id not in FOUNDER_IDS and rank != "fa":
            return await interaction.response.defer()
        hb = await load_hardbans()
        count = len(hb)
        unbanned = 0
        for uid in list(hb.keys()):
            try:
                user = await bot.fetch_user(int(uid))
                await interaction.guild.unban(user, reason="mass unban by founder")
                await delete_hardban(int(uid))
                unbanned += 1
            except (discord.NotFound, discord.HTTPException):
                pass
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"unbanned `{unbanned}/{count}` users and cleared the db",
            embed=None,
            view=self
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        rank = await get_rank(interaction.user.id)
        if interaction.user.id not in FOUNDER_IDS and rank != "fa":
            return await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="cancelled", embed=None, view=self)


@bot.command(name="unhball")
async def unban_all(ctx):
    if not await has_full_access(ctx):
        return
    await ctx.message.delete()
    hb = await load_hardbans()
    count = len(hb)
    if count == 0:
        return await ctx.send("no one is hardbanned", delete_after=4)
    embed = discord.Embed(
        description=f"do u wish to unban all `{count}` hardbanned users?",
        color=0x0015FF
    )
    await ctx.send(embed=embed, view=UnbanAllView())


@bot.event
async def on_member_unban(guild, user):
    hb = await load_hardbans()
    if str(user.id) not in hb:
        return
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
        if entry.target.id == user.id:
            if entry.user.id in FOUNDER_IDS or entry.user.id == bot.user.id:
                return
            break
    await guild.ban(user, reason="hardbanned")


# --- whitelist management ---

@bot.command(name="addrank")
async def addrank(ctx, member: discord.Member, rank: str):
    if ctx.author.id not in FOUNDER_IDS:
        return
    rank = rank.lower()
    if rank not in RANKS:
        await ctx.message.delete()
        return await ctx.send("Invalid rank. Choose from: `founder`, `fa`, `owner`, `friend`, `staff`", delete_after=4)
    await save_whitelist_entry(member.id, rank)
    await ctx.send(f"{member.mention} has been set to **{rank}**")


@bot.command(name="removerank")
async def removerank(ctx, member: discord.Member):
    if ctx.author.id not in FOUNDER_IDS:
        return
    wl = await load_whitelist()
    if str(member.id) not in wl:
        await ctx.message.delete()
        return await ctx.send(f"**{member.display_name}** has no rank.", delete_after=4)
    await delete_whitelist_entry(member.id)
    await ctx.send(f"{member.mention} your rank has been removed")


@bot.command(name="rank")
async def rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    r = await get_rank(target.id)
    if r:
        payload = component_msg([{"type": 10, "content": f"> {target.name} is rank **{r}**"}])
    else:
        payload = component_msg([{"type": 10, "content": f"> {target.name} is not whitelisted"}])
    await send_components(ctx, payload)


async def build_rank_page(rank_name: str) -> str:
    wl = await load_whitelist()
    by_rank: dict[str, list[str]] = {}

    founder_user = await bot.fetch_user(FOUNDER_ID)
    by_rank["founder"] = [f"**{founder_user.name}**"]

    for uid, r in wl.items():
        try:
            u = await bot.fetch_user(int(uid))
            name = f"**{u.name}**"
        except discord.NotFound:
            name = f"**{uid}**"
        by_rank.setdefault(r, []).append(name)

    members = by_rank.get(rank_name, [])
    if not members:
        return "> *no one*"
    return "\n".join(f"> {n}" for n in members)


def whitelist_payload(rank_name: str, body: str) -> dict:
    return {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "accent_color": 5631,
                "spoiler": False,
                "components": [
                    {"type": 10, "content": f"**Whitelist — {rank_name.capitalize()}**"},
                    {"type": 14, "spacing": 1, "divider": True},
                    {"type": 10, "content": body},
                ]
            },
            {
                "type": 1,
                "components": [{
                    "type": 3,
                    "custom_id": "wl_select",
                    "placeholder": "Switch rank...",
                    "options": [
                        {"label": "Founder", "value": "founder", "default": rank_name == "founder"},
                        {"label": "Owner", "value": "owner", "default": rank_name == "owner"},
                        {"label": "Friend", "value": "friend", "default": rank_name == "friend"},
                        {"label": "Staff", "value": "staff", "default": rank_name == "staff"},
                    ]
                }]
            }
        ]
    }


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.data.get("custom_id") != "wl_select":
        bot._connection._view_store.dispatch_view(
            interaction.data.get("component_type", 2),
            interaction.data.get("custom_id", ""),
            interaction
        )
        return
    if interaction.user.id not in FOUNDER_IDS:
        return await interaction.response.defer()
    rank_name = interaction.data["values"][0]
    body = await build_rank_page(rank_name)
    url = f"https://discord.com/api/v10/channels/{interaction.channel.id}/messages/{interaction.message.id}"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.patch(url, headers=headers, json=whitelist_payload(rank_name, body))
    await interaction.response.defer()


@bot.command(name="whitelist")
async def whitelist(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    body = await build_rank_page("founder")
    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=whitelist_payload("founder", body))


# --- utility ---

@bot.command(name="invite")
async def invite(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    url = "https://discord.com/oauth2/authorize?client_id=1523598535659098182&permissions=8&scope=bot"
    payload = component_msg([
        {"type": 10, "content": f"**Invite link**\n> {url}"}
    ])
    await send_components(ctx, payload)


FULL_ACCESS_CMDS = "**!info** — bot info\n**!rank @user** — check rank\n**!addrank @user <rank>** — set rank\n**!removerank @user** — remove rank\n**!whitelist** — view whitelist\n**!hb @user** — hardban\n**!unhb @user** — unban\n**!unhball** — unban all\n**!restoreguild** — post authorize embed\n**!pull <guild_id>** — move authorized users to new server\n**!r <role_id>** — set raid role\n**!rl #channel** — set raid log channel\n**/raid @user <pts>** — give raid points\n**/leaderboard** — raid leaderboard\n**!s** — shutdown"


@bot.command(name="help")
async def help_cmd(ctx):
    await ctx.message.delete()

    if ctx.author.id in FOUNDER_IDS:
        label = "Full Access"
        content = FULL_ACCESS_CMDS
    else:
        r = await get_rank(ctx.author.id) or "none"
        cmds = {
            "none":    "**!info** — bot info",
            "staff":   "**!info** — bot info\n**!rank @user** — check someone's rank",
            "friend":  "**!info** — bot info\n**!rank @user** — check someone's rank",
            "owner":   "**!info** — bot info\n**!rank @user** — check someone's rank\n**!whitelist** — view whitelist",
            "founder": FULL_ACCESS_CMDS,
            "fa":      FULL_ACCESS_CMDS,
        }
        label = r
        content = cmds.get(r, cmds["staff"])

    payload = component_msg([
        {"type": 10, "content": f"**Commands** — {label}"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": content},
    ])

    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            dm = await session.post(
                "https://discord.com/api/v10/users/@me/channels",
                headers=headers,
                json={"recipient_id": ctx.author.id}
            )
            dm_data = await dm.json()
            await session.post(
                f"https://discord.com/api/v10/channels/{dm_data['id']}/messages",
                headers=headers,
                json=payload
            )
    except Exception:
        pass


@bot.command(name="u")
async def update(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    await ctx.send("Restarting...", delete_after=3)
    await bot.close()
    os._exit(1)


@bot.command(name="s")
async def shutdown(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    await ctx.send("Shutting down...", delete_after=3)
    await bot.close()


# --- guild restore ---

@bot.command(name="restoreguild")
async def restore_guild(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()

    if not CLIENT_ID or not CLIENT_SECRET:
        return await ctx.send("Missing `CLIENT_ID` or `CLIENT_SECRET` in env.", delete_after=6)

    oauth_url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&scope=identify%20guilds.join"
    )
    print(f"[restoreguild] oauth_url: {oauth_url}")
    print(f"[restoreguild] REDIRECT_URI: {REDIRECT_URI}")
    print(f"[restoreguild] CLIENT_ID: {CLIENT_ID}")

    payload = {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "accent_color": 5631,
                "spoiler": False,
                "components": [
                    {"type": 10, "content": "**Server Restore**"},
                    {"type": 14, "spacing": 1, "divider": True},
                    {"type": 10, "content": "> Authorize the bot so it can move you to the new server if this one ever gets terminated or moved."},
                ]
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 5,
                        "label": "Authorize",
                        "url": oauth_url,
                    }
                ]
            }
        ]
    }

    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=payload)


@bot.command(name="pull")
async def pull(ctx, target_guild_id: int = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()

    if not target_guild_id:
        return await ctx.send("Usage: `!pull <guild_id>`", delete_after=6)

    try:
        target_guild = await bot.fetch_guild(target_guild_id)
    except discord.NotFound:
        return await ctx.send("Bot is not in that guild.", delete_after=6)

    rows = await db.fetch("SELECT user_id, access_token FROM user_tokens")
    if not rows:
        return await ctx.send("No authorized users in the database.", delete_after=6)

    status_msg = await ctx.send(f"Pulling `0/{len(rows)}` users into **{target_guild.name}**...")

    pulled = 0
    failed = 0
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        for i, row in enumerate(rows):
            try:
                resp = await session.put(
                    f"https://discord.com/api/v10/guilds/{target_guild_id}/members/{row['user_id']}",
                    headers=headers,
                    json={"access_token": row["access_token"]},
                )
                body = await resp.json()
                print(f"[pull] user {row['user_id']} status {resp.status}: {body}")
                if resp.status in (201, 204):
                    pulled += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[pull] exception for user {row['user_id']}: {e}")
                failed += 1

            if (i + 1) % 10 == 0:
                try:
                    await status_msg.edit(content=f"Pulling `{i + 1}/{len(rows)}` users into **{target_guild.name}**...")
                except Exception:
                    pass

    await status_msg.delete()
    payload = component_msg([
        {"type": 10, "content": "**Pull Complete**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> Server: **{target_guild.name}**\n> Pulled: `{pulled}`\n> Failed: `{failed}`"},
    ])
    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers={"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}, json=payload)


# --- raid db helpers ---

async def get_raid_config(key: str) -> int | None:
    row = await db.fetchrow("SELECT value FROM raid_config WHERE key = $1", key)
    return row["value"] if row else None


async def set_raid_config(key: str, value: int):
    await db.execute(
        "INSERT INTO raid_config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
        key, value
    )


async def add_raid_points(user_id: int, amount: int) -> int:
    row = await db.fetchrow(
        "INSERT INTO raid_points (user_id, points) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET points = raid_points.points + $2 RETURNING points",
        user_id, amount
    )
    return row["points"]


async def get_top_raiders(limit: int = 10) -> list:
    return await db.fetch("SELECT user_id, points FROM raid_points ORDER BY points DESC LIMIT $1", limit)


async def can_use_raid(interaction: discord.Interaction) -> bool:
    if interaction.user.id in FOUNDER_IDS:
        return True
    rank = await get_rank(interaction.user.id)
    if rank:
        return True
    role_id = await get_raid_config("allowed_role_id")
    if role_id and interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member and any(r.id == role_id for r in member.roles):
            return True
    return False


async def update_leaderboard(fallback_channel_id: int):
    rows = await get_top_raiders(10)
    lines = []
    for i in range(1, 11):
        if i <= len(rows):
            row = rows[i - 1]
            lines.append(f"> **{i}.** <@{row['user_id']}> **{row['points']}** pts")
        else:
            lines.append(f"> **{i}.**")

    payload = {
        "flags": 32768,
        "allowed_mentions": {"parse": []},
        "components": [{
            "type": 17,
            "accent_color": 0x2b2d31,
            "spoiler": False,
            "components": [
                {"type": 10, "content": "**Raid Leaderboard**"},
                {"type": 14, "spacing": 1, "divider": True},
                {"type": 10, "content": "\n".join(lines)},
            ]
        }]
    }
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    lb_msg_id = await get_raid_config("lb_message_id")
    lb_channel_id = await get_raid_config("lb_channel_id")

    async with aiohttp.ClientSession() as session:
        edited = False
        if lb_msg_id and lb_channel_id:
            resp = await session.patch(
                f"https://discord.com/api/v10/channels/{lb_channel_id}/messages/{lb_msg_id}",
                headers=headers, json=payload
            )
            edited = resp.status == 200

        if not edited:
            resp = await session.post(
                f"https://discord.com/api/v10/channels/{fallback_channel_id}/messages",
                headers=headers, json=payload
            )
            if resp.status in (200, 201):
                data = await resp.json()
                await set_raid_config("lb_message_id", int(data["id"]))
                await set_raid_config("lb_channel_id", fallback_channel_id)


# slash commands

@bot.tree.command(name="imagefilter", description="Toggle the AI image filter on or off (founder only)")
async def slash_imagefilter(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if interaction.user.id not in FOUNDER_IDS:
        return await interaction.followup.send("Founder only.", ephemeral=True)

    current = await get_raid_config("image_filter_enabled")
    if current is None:
        current = 1
    new_val = 0 if current else 1
    await set_raid_config("image_filter_enabled", new_val)
    state = "enabled" if new_val else "disabled"
    await interaction.followup.send(f"Image filter {state}.", ephemeral=True)


@bot.tree.command(name="raid", description="Give a user raid points")
@app_commands.describe(user="The user to give points to", points="Amount of points to give")
async def slash_raid(interaction: discord.Interaction, user: discord.Member, points: int):
    await interaction.response.defer(ephemeral=True)

    if not await can_use_raid(interaction):
        return await interaction.followup.send("You don't have permission to use this.", ephemeral=True)

    if user.id == interaction.user.id and interaction.user.id not in FOUNDER_IDS:
        return await interaction.followup.send("You can't give points to yourself.", ephemeral=True)

    if points <= 0:
        return await interaction.followup.send("Points must be a positive number.", ephemeral=True)

    new_total = await add_raid_points(user.id, points)

    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

    confirm_payload = component_msg([
        {"type": 10, "content": "**Raid Points Added**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> {user.mention} +**{points}** pts\n> Total: **{new_total}** pts"},
    ])
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
            headers=headers, json=confirm_payload
        )

    log_channel_id = await get_raid_config("log_channel_id")
    if log_channel_id:
        log_payload = component_msg([
            {"type": 10, "content": "**Raid Log**"},
            {"type": 14, "spacing": 1, "divider": True},
            {"type": 10, "content": f"> Caller: {interaction.user.mention}\n> User: {user.mention}\n> Points given: **{points}**\n> New total: **{new_total}**"},
        ])
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{log_channel_id}/messages",
                headers=headers, json=log_payload
            )

    await update_leaderboard(interaction.channel_id)
    await interaction.followup.send("Done.", ephemeral=True)


@bot.tree.command(name="clearpoints", description="Remove raid points from a user")
@app_commands.describe(user="The user to remove points from", points="Amount of points to remove (omit to remove all)")
async def slash_clearpoints(interaction: discord.Interaction, user: discord.Member, points: int = None):
    await interaction.response.defer(ephemeral=True)

    if not await can_use_raid(interaction):
        return await interaction.followup.send("You don't have permission to use this.", ephemeral=True)

    if points is not None and points <= 0:
        return await interaction.followup.send("Points must be a positive number.", ephemeral=True)

    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

    if points is None:
        await db.execute("DELETE FROM raid_points WHERE user_id = $1", user.id)
        new_total = 0
        desc = f"> {user.mention} points cleared\n> Total: **0** pts"
        log_desc = f"> Caller: {interaction.user.mention}\n> User: {user.mention}\n> All points removed"
    else:
        row = await db.fetchrow(
            "UPDATE raid_points SET points = GREATEST(points - $2, 0) WHERE user_id = $1 RETURNING points",
            user.id, points
        )
        new_total = row["points"] if row else 0
        desc = f"> {user.mention} -**{points}** pts\n> Total: **{new_total}** pts"
        log_desc = f"> Caller: {interaction.user.mention}\n> User: {user.mention}\n> Points removed: **{points}**\n> New total: **{new_total}**"

    confirm_payload = component_msg([
        {"type": 10, "content": "**Raid Points Removed**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": desc},
    ])
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
            headers=headers, json=confirm_payload
        )

    log_channel_id = await get_raid_config("log_channel_id")
    if log_channel_id:
        log_payload = component_msg([
            {"type": 10, "content": "**Raid Log**"},
            {"type": 14, "spacing": 1, "divider": True},
            {"type": 10, "content": log_desc},
        ])
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{log_channel_id}/messages",
                headers=headers, json=log_payload
            )

    await update_leaderboard(interaction.channel_id)
    await interaction.followup.send("Done.", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show the raid points leaderboard")
@app_commands.describe(debug="Show raw DB data to fix display issues (founder only)", clear="Wipe all raid points (founder only)")
async def slash_leaderboard(interaction: discord.Interaction, debug: bool = False, clear: bool = False):
    await interaction.response.defer(ephemeral=True)

    if not await can_use_raid(interaction):
        return await interaction.followup.send("You don't have permission to use this.", ephemeral=True)

    if clear:
        if interaction.user.id not in FOUNDER_IDS:
            return await interaction.followup.send("Clear is founder only.", ephemeral=True)
        log_channel_id = await get_raid_config("log_channel_id")
        await db.execute("DELETE FROM raid_points")
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
        confirm_payload = component_msg([
            {"type": 10, "content": "> Raid leaderboard has been cleared."},
        ])
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
                headers=headers, json=confirm_payload
            )
        if log_channel_id:
            log_payload = component_msg([
                {"type": 10, "content": "**Raid Log**"},
                {"type": 14, "spacing": 1, "divider": True},
                {"type": 10, "content": f"> {interaction.user.mention} cleared the raid leaderboard"},
            ])
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://discord.com/api/v10/channels/{log_channel_id}/messages",
                    headers=headers, json=log_payload
                )
        await update_leaderboard(interaction.channel_id)
        await db.execute("DELETE FROM raid_config WHERE key IN ('lb_message_id', 'lb_channel_id')")
        return await interaction.followup.send("Done.", ephemeral=True)

    if debug:
        if interaction.user.id not in FOUNDER_IDS:
            return await interaction.followup.send("Debug is founder only.", ephemeral=True)
        rows = await db.fetch("SELECT user_id, points FROM raid_points ORDER BY points DESC")
        if not rows:
            return await interaction.followup.send("No raid points in DB.", ephemeral=True)
        lines = "\n".join(f"> `{r['user_id']}` — **{r['points']}** pts" for r in rows)
        payload = component_msg([
            {"type": 10, "content": "**Raid Leaderboard**"},
            {"type": 14, "spacing": 1, "divider": True},
            {"type": 10, "content": lines},
        ])
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
                headers=headers, json=payload
            )
        return await interaction.followup.send("Done.", ephemeral=True)

    rows = await get_top_raiders(10)
    lines = []
    for i in range(1, 11):
        if i <= len(rows):
            row = rows[i - 1]
            lines.append(f"> **{i}.** <@{row['user_id']}> **{row['points']}** pts")
        else:
            lines.append(f"> **{i}.**")

    lb_payload = {
        "flags": 32768,
        "allowed_mentions": {"parse": []},
        "components": [{
            "type": 17,
            "accent_color": 0x2b2d31,
            "spoiler": False,
            "components": [
                {"type": 10, "content": "**Raid Leaderboard**"},
                {"type": 14, "spacing": 1, "divider": True},
                {"type": 10, "content": "\n".join(lines)},
            ]
        }]
    }
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
            headers=headers, json=lb_payload
        )
        if resp.status in (200, 201):
            data = await resp.json()
            await set_raid_config("lb_message_id", int(data["id"]))
            await set_raid_config("lb_channel_id", interaction.channel_id)

    await interaction.followup.send("Done.", ephemeral=True)


# --- raid config prefix commands ---

@bot.command(name="rl")
async def set_log_channel(ctx, channel: discord.TextChannel = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    if not channel:
        return await ctx.send("Usage: `!rl #channel`", delete_after=4)
    await set_raid_config("log_channel_id", channel.id)
    payload = component_msg([
        {"type": 10, "content": "**Raid Log Channel**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> Log channel set to {channel.mention}"},
    ])
    await send_components(ctx, payload)


@set_log_channel.error
async def rl_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.message.delete()
        await ctx.send("Invalid channel. Usage: `!rl #channel`", delete_after=4)


@bot.command(name="r")
async def set_raid_role(ctx, role_id: int = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    if not role_id:
        return await ctx.send("Usage: `!r <role_id>`", delete_after=4)
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send(f"No role found with ID `{role_id}`. Make sure the ID is correct.", delete_after=5)
    await set_raid_config("allowed_role_id", role_id)
    payload = component_msg([
        {"type": 10, "content": "**Raid Role**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> Raid role set to **{role.name}**"},
    ])
    await send_components(ctx, payload)


@set_raid_role.error
async def r_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.message.delete()
        await ctx.send("Invalid role ID. Usage: `!r <role_id>`", delete_after=4)


# --- roblox profile commands ---

async def roblox_get(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url, headers={"Accept": "application/json"}) as r:
        return await r.json() if r.status == 200 else {}


@bot.tree.command(name="set", description="Link a Discord user to their Roblox account")
@app_commands.describe(user="Discord user", roblox_user="Roblox username to search")
async def slash_set(interaction: discord.Interaction, user: discord.Member, roblox_user: str):
    if interaction.user.id not in FOUNDER_IDS:
        rank = await get_rank(interaction.user.id)
        if not rank:
            return await interaction.response.send_message("No permission.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    # roblox_user is the selected value from autocomplete which is "id:username"
    if ":" in roblox_user:
        roblox_id_str, roblox_name = roblox_user.split(":", 1)
        roblox_id = int(roblox_id_str)
        # verify the name is correct by fetching from API
        async with aiohttp.ClientSession() as session:
            profile = await roblox_get(session, f"https://users.roblox.com/v1/users/{roblox_id}")
        if profile.get("name"):
            roblox_name = profile["name"]
    else:
        # fallback: search by username
        async with aiohttp.ClientSession() as session:
            search = await roblox_get(session, f"https://users.roblox.com/v1/users/search?keyword={roblox_user}&limit=5")
        users = search.get("data", [])
        match = next((u for u in users if u["name"].lower() == roblox_user.lower()), users[0] if users else None)
        if not match:
            return await interaction.followup.send("Roblox user not found.", ephemeral=True)
        roblox_id = match["id"]
        roblox_name = match["name"]

    await db.execute(
        "INSERT INTO roblox_links (discord_id, roblox_id, roblox_name) VALUES ($1, $2, $3) ON CONFLICT (discord_id) DO UPDATE SET roblox_id = $2, roblox_name = $3",
        user.id, roblox_id, roblox_name
    )

    payload = component_msg([
        {"type": 10, "content": "**Roblox Linked**"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": f"> {user.mention} linked to **{roblox_name}** (`{roblox_id}`)"},
    ])
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
            headers=headers, json=payload
        )
    await interaction.followup.send("Done.", ephemeral=True)


@slash_set.autocomplete("roblox_user")
async def roblox_user_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not current:
        return []
    try:
        async with aiohttp.ClientSession() as session:
            data = await roblox_get(session, f"https://users.roblox.com/v1/users/search?keyword={current}&limit=10")
        users = data.get("data", [])
        return [
            app_commands.Choice(name=f"{u['name']} (ID: {u['id']})", value=f"{u['id']}:{u['name']}")
            for u in users
        ][:25]
    except Exception:
        return []


@bot.tree.command(name="call", description="Pull up a linked Roblox profile")
@app_commands.describe(user="Discord user to look up")
async def slash_call(interaction: discord.Interaction, user: str):
    await interaction.response.defer(ephemeral=True)

    if ":" not in user:
        return await interaction.followup.send("Invalid selection.", ephemeral=True)

    discord_id_str, roblox_id_str = user.split(":", 1)
    roblox_id = int(roblox_id_str)

    async with aiohttp.ClientSession() as session:
        profile = await roblox_get(session, f"https://users.roblox.com/v1/users/{roblox_id}")
        avatar_data = await roblox_get(session, f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={roblox_id}&size=150x150&format=Png&isCircular=false")
        followers_data = await roblox_get(session, f"https://friends.roblox.com/v1/users/{roblox_id}/followers/count")
        following_data = await roblox_get(session, f"https://friends.roblox.com/v1/users/{roblox_id}/followings/count")
        badges_data = await roblox_get(session, f"https://badges.roblox.com/v1/users/{roblox_id}/badges?limit=1")

    display_name = profile.get("displayName", profile.get("name", "Unknown"))
    username = profile.get("name", "Unknown")
    description = profile.get("description", "") or "/ware"
    created = profile.get("created", "")[:10] if profile.get("created") else "N/A"
    banned = profile.get("isBanned", False)

    followers = followers_data.get("count", 0)
    following = following_data.get("count", 0)
    badge_count = badges_data.get("data") and len(badges_data["data"]) or 0
    badge_total = badges_data.get("total", badge_count)

    avatar_url = None
    try:
        avatar_url = avatar_data["data"][0]["imageUrl"]
    except (KeyError, IndexError, TypeError):
        pass

    discord_member = interaction.guild.get_member(int(discord_id_str)) if interaction.guild else None
    discord_name = discord_member.display_name if discord_member else f"<@{discord_id_str}>"

    profile_line = f"**{display_name}** (@{username})" if display_name != username else f"**{username}**"
    status = " *(banned)*" if banned else ""

    body = (
        f"{profile_line}{status}\n"
        f"{description}\n\n"
        f"**Created**   **Last Online**   **Badges ({badge_total})**\n"
        f"{created}    N/A      {'No badges to show' if badge_total == 0 else f'{badge_total} badges'}\n\n"
        f"**ID**      **Following**   **Followers**\n"
        f"{roblox_id}   {following}       {followers}"
    )

    roblox_profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"
    components = [
        {"type": 10, "content": f"{discord_name} — [View Roblox Profile]({roblox_profile_url})"},
        {"type": 14, "spacing": 1, "divider": True},
        {"type": 10, "content": body},
    ]

    if avatar_url:
        components.insert(1, {
            "type": 12,
            "items": [{"media": {"url": avatar_url}, "description": None, "spoiler": False}]
        })

    payload = {
        "flags": 32768,
        "allowed_mentions": {"parse": []},
        "components": [{
            "type": 17,
            "accent_color": 0x2b2d31,
            "spoiler": False,
            "components": components
        }]
    }

    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{interaction.channel_id}/messages",
            headers=headers, json=payload
        )
    await interaction.followup.send("Done.", ephemeral=True)


@slash_call.autocomplete("user")
async def call_user_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rows = await db.fetch("SELECT discord_id, roblox_id, roblox_name FROM roblox_links")
    choices = []
    for row in rows:
        member = interaction.guild.get_member(row["discord_id"]) if interaction.guild else None
        discord_name = member.display_name if member else str(row["discord_id"])
        label = f"{discord_name} (@{row['roblox_name']})"
        if current.lower() in label.lower():
            choices.append(app_commands.Choice(
                name=label,
                value=f"{row['discord_id']}:{row['roblox_id']}"
            ))
    return choices[:25]


CLEARDB_OPTIONS = {"whitelist", "hardbans", "raid", "user", "roblox", "stats"}

CLEARDB_QUERIES = {
    "whitelist": "DELETE FROM whitelist",
    "hardbans":  "DELETE FROM hardbans",
    "raid":      "DELETE FROM raid_points",
    "user":      "DELETE FROM user_tokens",
    "roblox":    "DELETE FROM roblox_links",
    "stats":     "UPDATE stats SET value = 0",
}

@bot.command(name="cleardb")
async def cleardb(ctx, option: str = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()

    if not option or option.lower() not in CLEARDB_OPTIONS:
        opts = ", ".join(f"`{o}`" for o in CLEARDB_OPTIONS)
        return await ctx.send(f"Error: please pick an option. {opts}", delete_after=6)

    option = option.lower()
    await db.execute(CLEARDB_QUERIES[option])

    payload = component_msg([
        {"type": 10, "content": f"> `{option}` table has been cleared."},
    ])
    await send_components(ctx, payload)


# --- staff help ---

STAFF_HELP_CONTENT = """**Command Reference**

**!info**
> Shows bot info
> Example: `!info`
> Access: everyone

**!rank @user**
> Check someone's whitelist rank
> Example: `!rank @trent`
> Access: staff+

**!addrank @user <rank>**
> Set a user's rank (`founder`, `fa`, `owner`, `friend`, `staff`)
> Example: `!addrank @trent staff`
> Access: founder / fa

**!removerank @user**
> Remove a user's rank
> Example: `!removerank @trent`
> Access: founder / fa

**!whitelist**
> View all whitelisted users by rank
> Example: `!whitelist`
> Access: founder / fa

**!hb @user <reason>**
> Hardban a user — bans + adds to DB (auto-rebans if manually unbanned)
> Example: `!hb @trent breaking rules`
> Access: founder / fa

**!unhb @user <reason>**
> Unban a user and remove from hardban DB
> Example: `!unhb @trent`
> Access: founder / fa

**!unhball**
> Unban all hardbanned users at once
> Example: `!unhball`
> Access: founder / fa

**!restoreguild**
> Post the OAuth2 authorize embed for server restore
> Example: `!restoreguild`
> Access: founder / fa

**!pull <guild_id>**
> Move all authorized users to a new server
> Example: `!pull 123456789`
> Access: founder / fa

**!r <role_id>**
> Set the role allowed to use /raid
> Example: `!r 987654321`
> Access: founder / fa

**!rl #channel**
> Set the raid log channel
> Example: `!rl #raid-logs`
> Access: founder / fa

**!fa <word>**
> Add a word to the filter
> Example: `!fa badword`
> Access: founder / fa

**!fr <word>**
> Remove a word from the filter
> Example: `!fr badword`
> Access: founder / fa

**/raid @user <pts>**
> Give raid points to a user
> Example: `/raid @trent 10`
> Access: raid role / whitelist / founder

**/leaderboard**
> Show the raid leaderboard
> Example: `/leaderboard`
> Access: raid role / whitelist / founder

**!s**
> Shutdown the bot
> Example: `!s`
> Access: founder / fa"""


@bot.command(name="staffhelp")
async def staffhelp(ctx):
    rank = await get_rank(ctx.author.id)
    if ctx.author.id not in FOUNDER_IDS and not rank:
        return
    await ctx.message.delete()
    payload = component_msg([
        {"type": 10, "content": STAFF_HELP_CONTENT},
    ])
    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=payload)


# --- word filter commands ---

@bot.command(name="fa")
async def filter_add(ctx, *, word: str = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    if not word:
        return await ctx.send("Usage: `!fa <word>`", delete_after=4)
    word = word.lower().strip()
    global _word_filter_cache
    await db.execute("INSERT INTO word_filter (word) VALUES ($1) ON CONFLICT DO NOTHING", word)
    _word_filter_cache = None
    await ctx.channel.send("👍", delete_after=3)


@bot.command(name="fr")
async def filter_remove(ctx, *, word: str = None):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    if not word:
        return await ctx.send("Usage: `!fr <word>`", delete_after=4)
    word = word.lower().strip()
    global _word_filter_cache
    result = await db.execute("DELETE FROM word_filter WHERE word = $1", word)
    _word_filter_cache = None
    if result == "DELETE 1":
        await ctx.channel.send("👍", delete_after=3)
    else:
        await ctx.channel.send("Word not in filter.", delete_after=4)


# --- ai image filter ---

async def check_image_nsfw(image_url: str) -> bool:
    if not NAVY_API_KEY:
        return False
    try:
        image_url = re.sub(r"[\s&]+$", "", image_url).strip()
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Does this image contain explicit nudity, sexual content, graphic gore, or graphic violence (e.g. visible wounds, blood)? Normal photos, music videos, dark lighting, and people holding objects do NOT count. Reply with only YES or NO."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
            }],
            "max_tokens": 5,
        }
        client = http_client or httpx.AsyncClient(timeout=15)
        resp = await client.post(
            "https://api.navy/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {NAVY_API_KEY}", "Content-Type": "application/json"},
        )
        data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip().upper()
        print(f"[filter] navy answer: {answer}")
        return answer.startswith("YES")
    except Exception as e:
        print(f"[filter] navy error: {e}")
        return False


_word_filter_cache: set | None = None

LEET_MAP = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
    '7': 't', '@': 'a', '$': 's', '!': 'i',
})

DEFAULT_FILTERED_WORDS = {
    # racial slurs
    "nigger", "nggr", "ncr", "nigr", "kkk", "coon", "chink", "spic",
    "kike", "gook", "wetback", "beaner",
    # homophobic slurs
    "faggot", "fag",
    # csam / exploitation
    "cp", "csam", "pedo", "pedophile", "pedophiles", "loli", "shota", "jailbait",
    "i love cp",
    # doxxing
    "dox", "doxx", "dropping your info", "i will dox", "post your address",
    # self harm / threats
    "kys", "kill yourself", "kill urself", "go die", "end your life",
    "rope yourself", "slit", "764", "cnc",
    # swatting
    "swatting", "swatted", "ima swat you", "i will swat you", "i'm gonna swat you", "gonna swat you",
    # sexual violence
    "rape", "raping", "raped", "rapist",
    # malware / hacking
    "grabify", "ip logger", "ip grab", "ip stresser", "ddos", "rat link",
    "discord token", "token grab", "token logger", "hack discord", "send rat",
    "keylogger", "stealthy rat", "remote access trojan",
    # gore / violent content
    "gore link", "watch him die", "death video", "murder video",
    # piracy / illegal
    "crack download", "pirated software", "nulled software",
    # drug dealing
    "buy coke", "buy meth", "buy weed", "drug plug", "plug link",
    # tranny
    "tranny",
}


def normalize(text: str) -> str:
    # lowercase, apply leet substitutions, then remove all spaces and punctuation
    text = text.lower().translate(LEET_MAP)
    text = re.sub(r"[\s\-_'.!?]+", "", text)
    return text


async def get_filtered_words() -> set:
    global _word_filter_cache
    if _word_filter_cache is None:
        if db is None:
            return DEFAULT_FILTERED_WORDS
        rows = await db.fetch("SELECT word FROM word_filter")
        _word_filter_cache = DEFAULT_FILTERED_WORDS | {r["word"] for r in rows}
    return _word_filter_cache


def contains_filtered_word(text: str, words: set) -> str | None:
    # check original text with word boundaries (handles normal words and phrases)
    text_lower = text.lower()
    for word in words:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text_lower):
            return word

    # normalized check: only runs when text has leet/spacing obfuscation
    # skip if text is already plain alpha (no spaces between letters, no leet chars)
    has_obfuscation = bool(re.search(r"[013457@$!]", text_lower) or re.search(r"\b\w\s+\w\s+\w", text_lower))
    if not has_obfuscation:
        return None

    text_norm = normalize(text)
    for word in words:
        word_norm = normalize(word)
        if word_norm and len(word_norm) >= 5 and word_norm in text_norm:
            return word

    return None


async def scan_message(message: discord.Message) -> bool:
    if message.author.bot:
        return False

    # --- word filter ---
    if message.content:
        filtered_words = await get_filtered_words()
        matched = contains_filtered_word(message.content, filtered_words)
        if matched:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(
                    f"{message.author.mention} please dont send that. Reason - TOS",
                    delete_after=5
                )
            except Exception:
                pass
            return True

    # --- image filter ---
    if db is None:
        return False
    image_filter_on = await get_raid_config("image_filter_enabled")
    if image_filter_on is None:
        image_filter_on = 1
    if not image_filter_on:
        return False

    SCANNABLE = ("image/", "video/gif", "video/mp4", "video/webm")
    image_urls = []
    for attachment in message.attachments:
        ct = attachment.content_type or ""
        if any(ct.startswith(t) for t in SCANNABLE):
            image_urls.append(attachment.url)
    for embed in message.embeds:
        if embed.image and embed.image.url:
            image_urls.append(embed.image.url.rstrip("& \n\r"))
        if embed.thumbnail and embed.thumbnail.url:
            image_urls.append(embed.thumbnail.url.rstrip("& \n\r"))
        if embed.video and embed.video.url:
            image_urls.append(embed.video.url.rstrip("& \n\r"))

    print(f"[filter] scanning {len(image_urls)} image(s), {len(message.embeds)} embed(s), {len(message.attachments)} attachment(s)")
    for url in image_urls:
        print(f"[filter] checking: {url}")
        flagged = await check_image_nsfw(url)
        if flagged:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(
                    f"{message.author.mention} please dont send that. Reason - NSFW",
                    delete_after=5
                )
            except Exception:
                pass
            return True
    return False


ZZZ_TEXT = (
    "hey so we got a bot now\n\n"
    "basically it just keeps track of raid points, so whenever you go on a raid staff will add points to you with `/raid` "
    "and you can see the leaderboard with `/leaderboard`\n\n"
    "it also auto deletes stuff that breaks tos like slurs and flagged images, itll ping you when it does so you know why your message got deleted\n\n"
    "and if the server ever gets termed or whatever, the bot can just move everyone to the new one so we dont lose the whole community\n\n"
    "thats pretty much it, any questions ask staff"
)


@bot.command(name="zzz")
async def zzz(ctx):
    if ctx.author.id not in FOUNDER_IDS:
        return
    await ctx.message.delete()
    payload = component_msg([
        {"type": 10, "content": ZZZ_TEXT},
    ])
    url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=payload)


SUMMON_MESSAGES = [
    "summoned.",
    "who dared",
    "speak their name",
    "the name.",
    "point.",
    "who lives, who dies",
    "make it worth my time",
    "who needs to be erased",
    "i am here",
    "the ritual is complete",
    "you have my attention",
    "let them be nameless",
    "give me a target",
    "who breathes for the last time",
    "summoned from the void",
    "the veil parts",
    "a soul, and quickly",
    "who has angered you",
    "i answer only to you",
    "say the word",
    "shadows follow. who first?",
    "state your victim",
    "the reaping begins",
    "who am i erasing today",
]


@bot.event
async def on_message(message: discord.Message):
    print(f"[msg] id={message.id} author={message.author} content={message.content!r} mentions={[m.id for m in message.mentions]}")
    if (
        not message.author.bot
        and message.author.id in FOUNDER_IDS
        and bot.user in message.mentions
        and not message.mention_everyone
    ):
        try:
            gif_url = "https://media1.tenor.com/m/IKfWNYa-YBkAAAAC/aura-de-insanidade.gif"
            resp = await http_client.get(gif_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                gif_file = discord.File(io.BytesIO(resp.content), filename="summon.gif")
                await message.channel.send(file=gif_file)
                await asyncio.sleep(2)
            await message.channel.send(random.choice(SUMMON_MESSAGES))
        except Exception as e:
            print(f"[summon] error: {e}")

    await scan_message(message)
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    print(f"[edit] embeds before={len(before.embeds)} after={len(after.embeds)} attachments={len(after.attachments)}")
    if before.embeds == after.embeds and before.attachments == after.attachments:
        return
    await scan_message(after)


bot.run(TOKEN)
