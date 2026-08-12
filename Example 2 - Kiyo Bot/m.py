import asyncio
import os
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncpg


TOKEN        = os.environ["DISCORD_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
USER_TOKEN   = os.environ.get("USER_TOKEN", "").strip()
GUILD_ID     = 1511221374042243122

intents = discord.Intents.default()
intents.members         = True
intents.bans            = True
intents.message_content = True
intents.presences       = True

bot  = commands.Bot(command_prefix=">", intents=intents, help_command=None,
                    allowed_mentions=discord.AllowedMentions.none())
tree = bot.tree


db = None

FOUNDER_IDS          = {878416460924465193, 719163504745250911, 1320827552759287903}
OWNER_IDS            = set()
STAFF_IDS            = set()
TEST_SUBJECT_IDS     = set()
HARDBAN_IDS          = set()
TEST_SUBJECT_CMDS    = set()
FILTERED_WORDS       = set()

ROLE_RANK = {"founder": 3, "owner": 2, "staff": 1, "test_subject": 0}


EVERYWHERE = dict(
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
)

RANK_OPTIONS = [
    {"label": "Founder",      "value": "founder"},
    {"label": "Owner",        "value": "owner"},
    {"label": "Staff",        "value": "staff"},
    {"label": "Test Subject", "value": "test_subject"},
]

SELECT_ROW = {
    "type": 1,
    "components": [{
        "type": 3,
        "custom_id": "whitelist_list_select",
        "placeholder": "Select a rank...",
        "options": RANK_OPTIONS,
    }],
}

DOTS = ["", ".", "..", "..."]

PARTYBOY_ID       = 878416460924465193
BOOM_GIF          = "https://tenor.com/view/chicken-chicken-bro-destroy-boom-explosion-gif-14109606"
_ping_times: list = []
_overstim_active  = False
_hide_mode        = False


def make_view(*items, accent_color=0):
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(*items, accent_color=accent_color))
    return view


def sep():
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.small)


def _clean_bio(text: str) -> str:
    import re
    text = re.sub(r'\*{1,3}', '', text)
    text = re.sub(r'_{1,2}', '', text)
    text = re.sub(r'~~', '', text)
    text = re.sub(r'`{1,3}', '', text)
    return text.strip()


def wl_container(*text_items):
    components = []
    for i, content in enumerate(text_items):
        components.append({"type": 10, "content": content})
        if i < len(text_items) - 1:
            components.append({"type": 14, "spacing": 1, "divider": True})
    return {"type": 17, "accent_color": 5631, "spoiler": False, "components": components}


async def raw_respond(interaction: discord.Interaction, callback_type: int, data: dict):
    await interaction.client.http.request(
        discord.http.Route(
            "POST", "/interactions/{iid}/{token}/callback",
            iid=interaction.id, token=interaction.token,
        ),
        json={"type": callback_type, "data": data},
    )


async def user_get(path: str, params: dict = None) -> dict:
    headers = {"Authorization": USER_TOKEN, "Content-Type": "application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"https://discord.com/api/v10{path}", params=params) as resp:
            return await resp.json()


BADGE_MAP = {
    # standard badges
    "DISCORD_EMPLOYEE":              "Discord Staff",
    "PARTNERED_SERVER_OWNER":        "Partner",
    "HYPESQUAD_EVENTS":              "HypeSquad Events",
    "BUG_HUNTER_LEVEL_1":            "Bug Hunter",
    "BUG_HUNTER_LEVEL_2":            "Bug Hunter Gold",
    "HYPESQUAD_ONLINE_HOUSE_1":      "HypeSquad Bravery",
    "HYPESQUAD_ONLINE_HOUSE_2":      "HypeSquad Brilliance",
    "HYPESQUAD_ONLINE_HOUSE_3":      "HypeSquad Balance",
    "EARLY_SUPPORTER":               "Early Supporter",
    "VERIFIED_BOT_DEVELOPER":        "Early Verified Bot Dev",
    "ACTIVE_DEVELOPER":              "Active Developer",
    "CERTIFIED_MODERATOR":           "Discord Moderator",
    "PREMIUM_EARLY_SUPPORTER":       "Early Nitro Supporter",
    # nitro / boost tenure (lowercase IDs from profile API)
    "premium":                       "Nitro",
    "premium_tenure_1_month_v2":     "Nitro 1 Month",
    "premium_tenure_3_month_v2":     "Nitro 3 Months",
    "premium_tenure_6_month_v2":     "Nitro 6 Months",
    "premium_tenure_12_month_v2":    "Nitro 1 Year",
    "premium_tenure_24_month_v2":    "Nitro 2 Years",
    "premium_tenure_36_month_v2":    "Nitro 3 Years",
    "premium_tenure_48_month_v2":    "Nitro 4 Years",
    "premium_tenure_60_month_v2":    "Nitro 5 Years",
    # server boost level badges
    "guild_booster_lvl1":            "Server Booster L1",
    "guild_booster_lvl2":            "Server Booster L2",
    "guild_booster_lvl3":            "Server Booster L3",
    "guild_booster_lvl4":            "Server Booster L4",
    "guild_booster_lvl5":            "Server Booster L5",
    "guild_booster_lvl6":            "Server Booster L6",
    "guild_booster_lvl7":            "Server Booster L7",
    "guild_booster_lvl8":            "Server Booster L8",
    "guild_booster_lvl9":            "Server Booster L9",
    # quest / achievement badges
    "quest_completed":               "Quest Completed",
    "legacy_username":               "Legacy Username",
    "bot_commands":                  "Supports Commands",
    "verified_bot":                  "Verified Bot",
}

CONNECTED_ICONS = {
    "spotify":  "Spotify",
    "steam":    "Steam",
    "xbox":     "Xbox",
    "twitch":   "Twitch",
    "youtube":  "YouTube",
    "twitter":  "Twitter/X",
    "github":   "GitHub",
    "reddit":   "Reddit",
    "tiktok":   "TikTok",
    "instagram":"Instagram",
    "facebook": "Facebook",
    "epicgames":"Epic Games",
    "roblox":   "Roblox",
    "playstation": "PlayStation",
    "leagueoflegends": "League of Legends",
    "battlenet": "Battle.net",
}

NITRO_TYPES = {0: "None", 1: "Nitro Classic", 2: "Nitro", 3: "Nitro Basic"}


def get_role(user_id):
    if user_id in FOUNDER_IDS:
        return "founder"
    if user_id in OWNER_IDS:
        return "owner"
    if user_id in STAFF_IDS:
        return "staff"
    if user_id in TEST_SUBJECT_IDS:
        return "test_subject"
    return None


def is_whitelisted(user_id):
    return get_role(user_id) is not None


def whitelist_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_whitelisted(interaction.user.id):
            await interaction.response.send_message("You are not whitelisted to use this bot.")
            return False
        return True
    return app_commands.check(predicate)


def min_role_check(min_role):
    async def predicate(interaction: discord.Interaction) -> bool:
        role = get_role(interaction.user.id)
        if role is None or ROLE_RANK.get(role, 0) < ROLE_RANK[min_role]:
            await interaction.response.send_message(f"You need **{min_role}** or higher to use this command.")
            return False
        return True
    return app_commands.check(predicate)


def test_subject_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        role = get_role(interaction.user.id)
        if role is None:
            await interaction.response.send_message("You are not whitelisted to use this bot.")
            return False
        if role == "test_subject":
            cmd = interaction.command.qualified_name if interaction.command else ""
            if cmd not in TEST_SUBJECT_CMDS:
                await interaction.response.send_message("You don't have access to this command.")
                return False
        return True
    return app_commands.check(predicate)


def founder_only():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id not in FOUNDER_IDS:
            await ctx.message.delete()
            return False
        return True
    return commands.check(predicate)


def prefix_min_role_check(min_role):
    async def predicate(ctx: commands.Context) -> bool:
        role = get_role(ctx.author.id)
        if role is None or ROLE_RANK.get(role, 0) < ROLE_RANK[min_role]:
            await ctx.message.delete()
            return False
        return True
    return commands.check(predicate)


async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)
    async with db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id BIGINT PRIMARY KEY,
                role    TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hardbans (
                user_id BIGINT PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gifs (
                name TEXT PRIMARY KEY,
                url  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_subject_commands (
                command TEXT PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_counter (
                id      INT PRIMARY KEY DEFAULT 1,
                counter INT NOT NULL DEFAULT 0,
                CHECK (id = 1)
            )
        """)
        await conn.execute("INSERT INTO ticket_counter (id, counter) VALUES (1, 0) ON CONFLICT DO NOTHING")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS filtered_words (
                word TEXT PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                user_id      BIGINT PRIMARY KEY,
                roblox_name  TEXT NOT NULL
            )
        """)
        for row in await conn.fetch("SELECT word FROM filtered_words"):
            FILTERED_WORDS.add(row["word"])
        for row in await conn.fetch("SELECT command FROM test_subject_commands"):
            TEST_SUBJECT_CMDS.add(row["command"])
        for row in await conn.fetch("SELECT user_id, role FROM whitelist"):
            if row["role"] == "founder":
                FOUNDER_IDS.add(row["user_id"])
            elif row["role"] == "owner":
                OWNER_IDS.add(row["user_id"])
            elif row["role"] == "staff":
                STAFF_IDS.add(row["user_id"])
            elif row["role"] == "test_subject":
                TEST_SUBJECT_IDS.add(row["user_id"])
        for row in await conn.fetch("SELECT user_id FROM hardbans"):
            HARDBAN_IDS.add(row["user_id"])


async def db_set_whitelist(user_id, role):
    await db.execute(
        "INSERT INTO whitelist (user_id, role) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET role = $2",
        user_id, role,
    )


async def db_remove_whitelist(user_id):
    await db.execute("DELETE FROM whitelist WHERE user_id = $1", user_id)


async def db_add_hardban(user_id):
    await db.execute("INSERT INTO hardbans (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)


async def db_remove_hardban(user_id):
    await db.execute("DELETE FROM hardbans WHERE user_id = $1", user_id)


async def db_set_verification(user_id, roblox_name):
    await db.execute(
        "INSERT INTO verifications (user_id, roblox_name) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET roblox_name = $2",
        user_id, roblox_name,
    )


async def db_get_verification(user_id):
    return await db.fetchrow("SELECT roblox_name FROM verifications WHERE user_id = $1", user_id)


async def db_delete_verification(user_id):
    await db.execute("DELETE FROM verifications WHERE user_id = $1", user_id)


class WhitelistGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="whitelist",
            description="Manage the bot whitelist",
            **EVERYWHERE,
        )

    @app_commands.command(name="add", description="Add a user to the whitelist (owner+)")
    @app_commands.describe(user="User to add", role="Role to assign: staff or owner")
    @min_role_check("owner")
    async def add(self, interaction: discord.Interaction, user: discord.User, role: str):
        role = role.lower()

        allowed_roles = ("staff", "owner", "test_subject", "founder") if interaction.user.id == 878416460924465193 else ("staff", "owner", "test_subject")
        if role not in allowed_roles:
            await interaction.response.send_message(f"Invalid role. Choose: {', '.join(f'`{r}`' for r in allowed_roles)}.")
            return

        caller_role = get_role(interaction.user.id)
        if ROLE_RANK.get(caller_role, 0) <= ROLE_RANK.get(role, 0) and caller_role != "founder":
            await interaction.response.send_message("You can only assign roles below your own.")
            return

        OWNER_IDS.discard(user.id)
        STAFF_IDS.discard(user.id)
        TEST_SUBJECT_IDS.discard(user.id)
        if role == "founder":
            FOUNDER_IDS.add(user.id)
        elif role == "owner":
            OWNER_IDS.add(user.id)
        elif role == "staff":
            STAFF_IDS.add(user.id)
        else:
            TEST_SUBJECT_IDS.add(user.id)

        await db_set_whitelist(user.id, role)
        await interaction.response.send_message(f"Added {user.mention} as **{role}**.")

    @app_commands.command(name="remove", description="Remove a user from the whitelist (owner+)")
    @app_commands.describe(user="User to remove")
    @min_role_check("owner")
    async def remove(self, interaction: discord.Interaction, user: discord.User):
        if user.id in FOUNDER_IDS:
            await interaction.response.send_message("Cannot remove a founder.")
            return

        caller_role = get_role(interaction.user.id)
        target_role = get_role(user.id)
        if target_role and ROLE_RANK.get(caller_role, 0) <= ROLE_RANK.get(target_role, 0) and caller_role != "founder":
            await interaction.response.send_message("You can only remove users with a lower role than yours.")
            return

        OWNER_IDS.discard(user.id)
        STAFF_IDS.discard(user.id)
        TEST_SUBJECT_IDS.discard(user.id)
        await db_remove_whitelist(user.id)
        await interaction.response.send_message(f"Removed {user.mention} from the whitelist.")

    @app_commands.command(name="list", description="List all whitelisted users (staff+)")
    @min_role_check("staff")
    async def list(self, interaction: discord.Interaction):
        data = {
            "components": [
                wl_container(
                    "**Whitelist List**",
                    "> Please select the rank you want to view!",
                    "-# to be whitelisted dm trent",
                ),
                SELECT_ROW,
            ],
            "flags": 32768,
        }
        await raw_respond(interaction, 4, data)


tree.add_command(WhitelistGroup())


class TestCommandsGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="testcommands",
            description="Manage commands available to test subjects",
            **EVERYWHERE,
        )

    @app_commands.command(name="enable", description="Allow test subjects to use a command (founder only)")
    @app_commands.describe(command="Command name to enable (e.g. groupcheck, gif send)")
    @min_role_check("founder")
    async def enable(self, interaction: discord.Interaction, command: str):
        command = command.lower().strip()
        TEST_SUBJECT_CMDS.add(command)
        await db.execute("INSERT INTO test_subject_commands (command) VALUES ($1) ON CONFLICT DO NOTHING", command)
        await interaction.response.send_message(f"Test subjects can now use `/{command}`.")

    @app_commands.command(name="disable", description="Remove a command from test subjects (founder only)")
    @app_commands.describe(command="Command name to disable")
    @min_role_check("founder")
    async def disable(self, interaction: discord.Interaction, command: str):
        command = command.lower().strip()
        TEST_SUBJECT_CMDS.discard(command)
        await db.execute("DELETE FROM test_subject_commands WHERE command = $1", command)
        await interaction.response.send_message(f"Test subjects can no longer use `/{command}`.")

    @disable.autocomplete("command")
    async def disable_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=c, value=c)
            for c in sorted(TEST_SUBJECT_CMDS)
            if current.lower() in c
        ][:25]

    @app_commands.command(name="list", description="List commands test subjects can use (founder only)")
    @min_role_check("founder")
    async def list(self, interaction: discord.Interaction):
        if not TEST_SUBJECT_CMDS:
            await interaction.response.send_message("No commands enabled for test subjects.")
            return
        cmds = "\n".join(f"> `/{c}`" for c in sorted(TEST_SUBJECT_CMDS))
        await interaction.response.send_message(f"**Test subject commands:**\n{cmds}")


tree.add_command(TestCommandsGroup())


class GifGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="gif",
            description="Manage and send stored GIFs",
            **EVERYWHERE,
        )

    @app_commands.command(name="send", description="Send a stored GIF (owner+)")
    @app_commands.describe(name="GIF to send")
    @min_role_check("owner")
    async def send(self, interaction: discord.Interaction, name: str):
        row = await db.fetchrow("SELECT url FROM gifs WHERE name = $1", name)
        if not row:
            await interaction.response.send_message(f"No GIF named **{name}**.")
            return
        await interaction.response.send_message(row["url"])

    @send.autocomplete("name")
    async def send_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await db.fetch(
            "SELECT name FROM gifs WHERE name ILIKE $1 ORDER BY name LIMIT 25",
            f"{current}%",
        )
        return [app_commands.Choice(name=r["name"], value=r["name"]) for r in rows]

    @app_commands.command(name="add", description="Add a GIF to the list (owner+)")
    @app_commands.describe(name="Name for the GIF", url="GIF URL")
    @min_role_check("owner")
    async def add(self, interaction: discord.Interaction, name: str, url: str):
        await db.execute(
            "INSERT INTO gifs (name, url) VALUES ($1, $2) ON CONFLICT (name) DO UPDATE SET url = $2",
            name, url,
        )
        await interaction.response.send_message(f"Saved GIF **{name}**.")

    @app_commands.command(name="remove", description="Remove a GIF from the list (owner+)")
    @app_commands.describe(name="GIF to remove")
    @min_role_check("owner")
    async def remove(self, interaction: discord.Interaction, name: str):
        result = await db.execute("DELETE FROM gifs WHERE name = $1", name)
        if result == "DELETE 0":
            await interaction.response.send_message(f"No GIF named **{name}**.")
        else:
            await interaction.response.send_message(f"Removed GIF **{name}**.")

    @remove.autocomplete("name")
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await db.fetch(
            "SELECT name FROM gifs WHERE name ILIKE $1 ORDER BY name LIMIT 25",
            f"{current}%",
        )
        return [app_commands.Choice(name=r["name"], value=r["name"]) for r in rows]


tree.add_command(GifGroup())


@bot.command(name="fadd")
@prefix_min_role_check("owner")
async def fadd(ctx: commands.Context, *, word: str):
    await ctx.message.delete()
    word = word.lower().strip()
    FILTERED_WORDS.add(word)
    await db.execute("INSERT INTO filtered_words (word) VALUES ($1) ON CONFLICT DO NOTHING", word)
    await ctx.send(f"Added `{word}` to the filter.", delete_after=5)


@bot.command(name="fremove")
@prefix_min_role_check("owner")
async def fremove(ctx: commands.Context, *, word: str):
    await ctx.message.delete()
    word = word.lower().strip()
    if word not in FILTERED_WORDS:
        await ctx.send(f"`{word}` is not in the filter.", delete_after=5)
        return
    FILTERED_WORDS.discard(word)
    await db.execute("DELETE FROM filtered_words WHERE word = $1", word)
    await ctx.send(f"Removed `{word}` from the filter.", delete_after=5)


@bot.command(name="flist")
@prefix_min_role_check("owner")
async def flist(ctx: commands.Context):
    await ctx.message.delete()
    if not FILTERED_WORDS:
        await ctx.send("No words in the filter.", delete_after=5)
        return
    words = "\n".join(f"> `{w}`" for w in sorted(FILTERED_WORDS))
    await ctx.send(f"**Filtered words:**\n{words}", delete_after=15)


@bot.event
async def on_ready():
    try:
        await init_db()
        print("Database connected successfully.")
    except Exception as e:
        print(f"Database connection failed: {e}")

    for g in bot.guilds:
        tree.clear_commands(guild=g)
        await tree.sync(guild=g)
    synced = await tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Synced {len(synced)} commands globally:")
    for cmd in synced:
        print(f"  /{cmd.name}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    if user.id in HARDBAN_IDS:
        await guild.ban(user, reason="hardban", delete_message_seconds=0)


@bot.event
async def on_message(message: discord.Message):
    global _overstim_active, _hide_mode

    if message.author.bot:
        await bot.process_commands(message)
        return

    if _hide_mode and message.author.id not in FOUNDER_IDS:
        return

    if FILTERED_WORDS and message.content and not message.content.startswith(">"):
        content_lower = message.content.lower()
        if any(word in content_lower for word in FILTERED_WORDS):
            await message.delete()
            warn = await message.channel.send(view=make_view(
                discord.ui.TextDisplay(f"{message.author.mention} thats a bad word."),
                accent_color=5631,
            ))
            await asyncio.sleep(5)
            await warn.delete()
            return

    if bot.user in message.mentions and not message.reference:
        if message.author.id in FOUNDER_IDS and "summon" in message.content.lower():
            await message.reply("https://tenor.com/view/jinichi-zenin-toji-fushiguro-brother-naobito-cousin-vs-gif-11450150015512570644", mention_author=False)
            await bot.process_commands(message)
            return

        now = asyncio.get_event_loop().time()
        _ping_times.append(now)
        while _ping_times and now - _ping_times[0] > 10:
            _ping_times.pop(0)

        if len(_ping_times) >= 5 and not _overstim_active:
            _overstim_active = True
            _ping_times.clear()

            yes_btn = discord.ui.Button(label="yes", style=discord.ButtonStyle.danger,    custom_id="overstim_yes")
            no_btn  = discord.ui.Button(label="no",  style=discord.ButtonStyle.secondary, custom_id="overstim_no")

            view = discord.ui.LayoutView()
            view.add_item(discord.ui.Container(
                discord.ui.TextDisplay(f"daddyyy <@{PARTYBOY_ID}>. im overstimulatedddd  can i self destruct? 🥺"),
                accent_color=16711927,
            ))
            view.add_item(discord.ui.ActionRow(yes_btn, no_btn))

            await message.channel.send(view=view)
            await bot.process_commands(message)
            return

        if not is_whitelisted(message.author.id):
            yes_btn = discord.ui.Button(label="yes ban him", style=discord.ButtonStyle.danger,    custom_id=f"pingban_yes_{message.author.id}")
            no_btn  = discord.ui.Button(label="nah.",        style=discord.ButtonStyle.secondary, custom_id=f"pingban_no_{message.author.id}")

            view = discord.ui.LayoutView()
            view.add_item(discord.ui.Container(
                discord.ui.TextDisplay(f"why did u ping me... <@{PARTYBOY_ID}> do i ban this guy??"),
                accent_color=5631,
            ))
            view.add_item(discord.ui.ActionRow(yes_btn, no_btn))

            await message.reply(view=view, mention_author=False, allowed_mentions=discord.AllowedMentions(replied_user=False))

    await bot.process_commands(message)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    is_component = interaction.type == discord.InteractionType.component
    custom_id    = (interaction.data or {}).get("custom_id", "")

    if is_component and custom_id in ("overstim_yes", "overstim_no"):
        global _overstim_active
        if interaction.user.id not in FOUNDER_IDS:
            await interaction.response.send_message("you're not a founder lol", ephemeral=True)
            return

        if custom_id == "overstim_no":
            _overstim_active = False
            await interaction.response.edit_message(view=make_view(discord.ui.TextDisplay("fine. ill hold it together 😤")))
            return

        await interaction.response.defer()
        channel = interaction.channel

        countdown_view = discord.ui.LayoutView()
        countdown_view.add_item(discord.ui.Container(
            discord.ui.TextDisplay("self destructing in **3**..."),
            accent_color=16711927,
        ))
        msg = await channel.send(view=countdown_view)

        for i in (2, 1):
            await asyncio.sleep(1)
            v = discord.ui.LayoutView()
            v.add_item(discord.ui.Container(
                discord.ui.TextDisplay(f"self destructing in **{i}**..."),
                accent_color=16711927,
            ))
            await msg.edit(view=v)

        await asyncio.sleep(1)
        await msg.delete()
        await channel.send(BOOM_GIF)
        _overstim_active = False
        return

    if is_component and custom_id.startswith("pingban_"):
        if interaction.user.id not in FOUNDER_IDS:
            await interaction.response.send_message("you're not a founder lol", ephemeral=True)
            return

        _, action, uid_str = custom_id.split("_", 2)
        uid = int(uid_str)

        await interaction.response.defer()
        if action == "yes":
            if uid == 878416460924465193:
                await interaction.followup.send("LMAOOO U TRIED")
                return
            try:
                await interaction.guild.ban(discord.Object(id=uid), reason="bot mention ban", delete_message_seconds=0)
                await interaction.followup.send(view=make_view(discord.ui.TextDisplay(f"<@{uid}> got banned lol")))
            except discord.Forbidden:
                await interaction.followup.send(view=make_view(discord.ui.TextDisplay("ban failed: hierachy")))
            except discord.HTTPException:
                await interaction.followup.send(view=make_view(discord.ui.TextDisplay("ban failed: unknown error")))
        else:
            view = discord.ui.LayoutView()
            view.add_item(discord.ui.Container(
                discord.ui.TextDisplay(f"<@{uid}> canceled ig, be a good boy next time and don't ping me?"),
                accent_color=5631,
            ))
            await interaction.followup.send(view=view)
        return

    if is_component and custom_id == "sp_topic_select":
        topic = interaction.data["values"][0]

        if topic == "Admin Aboose":
            modal = discord.ui.Modal(title="Admin Aboose", custom_id="sp_modal_adminaboose")
            modal.add_item(discord.ui.TextInput(label="who da one aboosing on u loll", custom_id="answer", style=discord.TextStyle.paragraph))
            await interaction.response.send_modal(modal)
            return

        if topic == "Tag":
            modal = discord.ui.Modal(title="Tag", custom_id="sp_modal_tag")
            modal.add_item(discord.ui.TextInput(label="roblox user", custom_id="answer", style=discord.TextStyle.short))
            await interaction.response.send_modal(modal)
            return

        await _create_support_thread(interaction, topic, None)
        return

    if interaction.type == discord.InteractionType.modal_submit and custom_id.startswith("sp_modal_"):
        topic_key = custom_id[len("sp_modal_"):]
        topic     = "Admin Aboose" if topic_key == "adminaboose" else "Tag"
        answer    = interaction.data["components"][0]["components"][0]["value"]
        await _create_support_thread(interaction, topic, answer)
        return

    if is_component and custom_id == "verify_select":
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        member_roles = {r.id for r in member.roles} if member else set()
        already_verified = VERIFIED_ROLE_ID in member_roles
        is_founder = interaction.user.id in FOUNDER_IDS
        if already_verified and not is_founder:
            await interaction.response.send_message("you're already verified.", ephemeral=True)
            return
        modal = discord.ui.Modal(title="Verify", custom_id="verify_modal")
        modal.add_item(discord.ui.TextInput(label="Roblox username", custom_id="roblox_name", style=discord.TextStyle.short, placeholder="e.g. Builderman"))
        await interaction.response.send_modal(modal)
        return

    if interaction.type == discord.InteractionType.modal_submit and custom_id == "verify_modal":
        roblox_name = interaction.data["components"][0]["components"][0]["value"].strip()
        if db is None:
            await interaction.response.send_message("Database is not connected.", ephemeral=True)
            return
        await db_set_verification(interaction.user.id, roblox_name)
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(VERIFY_CHANNEL_ID)
        requester = interaction.guild.get_member(interaction.user.id) or interaction.user
        if channel is not None:
            thread = await channel.create_thread(
                name=f"verify - {interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False,
            )
            try:
                await thread.add_user(requester)
            except discord.Forbidden:
                pass
            await interaction.followup.send(
                view=make_view(discord.ui.TextDisplay(f"got it — your Roblox username **{roblox_name}** has been submitted. head to your ticket: {thread.mention}")),
                ephemeral=True,
            )
            staff_roles   = [interaction.guild.get_role(rid) for rid in SUPPORT_ROLE_IDS]
            staff_roles   = [r for r in staff_roles if r]
            role_mentions = " ".join(r.mention for r in staff_roles) + " <@878416460924465193>"
            await thread.send(
                view=make_view(
                    discord.ui.TextDisplay(f"**Verification Request**"),
                    sep(),
                    discord.ui.TextDisplay(f"> {interaction.user.mention} wants to verify as Roblox user **{roblox_name}**\n> run `>v {interaction.user.mention}` to verify them."),
                    accent_color=0x5865F2,
                )
            )
            await thread.send(role_mentions, allowed_mentions=discord.AllowedMentions(roles=True))

            async with aiohttp.ClientSession() as session:
                roblox_user = await fetch_roblox_user(session, roblox_name)
                if roblox_user:
                    user_id    = roblox_user["id"]
                    raw_groups = await fetch_user_groups(session, user_id)
                    if raw_groups:
                        group_ids = [e["group"]["id"] for e in raw_groups]
                        icons, created_dates = await asyncio.gather(
                            fetch_group_icons(session, group_ids),
                            fetch_group_created_dates(session, group_ids),
                        )
                        groups = [
                            {
                                "id":                 e["group"]["id"],
                                "name":               e["group"]["name"],
                                "description":        e["group"].get("description", ""),
                                "memberCount":        e["group"].get("memberCount", 0),
                                "publicEntryAllowed": e["group"].get("publicEntryAllowed", False),
                                "role":               e["role"],
                                "iconUrl":            icons.get(e["group"]["id"], ""),
                                "created":            created_dates.get(e["group"]["id"], "Unknown"),
                            }
                            for e in raw_groups
                        ]
                        await thread.send(view=GroupView(groups, roblox_user["name"]))
                    else:
                        await thread.send(view=make_view(discord.ui.TextDisplay(f"**{roblox_user['name']}** is not in any Roblox groups.")))
                else:
                    await thread.send(view=make_view(discord.ui.TextDisplay(f"could not find Roblox user **{roblox_name}** — may be a typo.")))
        return

    if is_component and custom_id == "help_section_select":
        section = interaction.data["values"][0]
        await interaction.response.edit_message(view=_help_section_view(section))
        return

    if is_component and custom_id == "botlist_select":
        if interaction.user.id not in FOUNDER_IDS:
            await interaction.response.defer()
            return
        selected_id = int(interaction.data["values"][0])
        guild       = interaction.guild
        bots        = sorted([m for m in guild.members if m.bot], key=lambda m: m.joined_at or discord.utils.utcnow())
        await interaction.response.edit_message(view=_botlist_bot_view(bots, selected_id))
        return

    if is_component and custom_id == "whitelist_list_select":
        rank      = interaction.data["values"][0]
        rank_sets = {"founder": FOUNDER_IDS, "owner": OWNER_IDS, "staff": STAFF_IDS, "test_subject": TEST_SUBJECT_IDS}
        uids      = rank_sets.get(rank, set())

        users_text = "\n".join(f"> <@{uid}>" for uid in uids) if uids else "> *No users in this rank.*"

        data = {
            "components": [
                wl_container(
                    "**Whitelist List**",
                    f"**{rank.capitalize()}** Rank\n{users_text}",
                    "-# to be whitelisted dm trent",
                ),
                SELECT_ROW,
            ],
            "flags": 32768,
        }
        await raw_respond(interaction, 7, data)
        return


async def fetch_roblox_user(session, username):
    async with session.post(
        "https://users.roblox.com/v1/usernames/users",
        json={"usernames": [username], "excludeBannedUsers": False},
    ) as resp:
        data = await resp.json()
    users = data.get("data", [])
    return users[0] if users else None


async def fetch_user_groups(session, user_id):
    async with session.get(f"https://groups.roblox.com/v2/users/{user_id}/groups/roles") as resp:
        data = await resp.json()
    return data.get("data", [])


async def fetch_group_icons(session, group_ids):
    ids = ",".join(str(g) for g in group_ids)
    async with session.get(
        "https://thumbnails.roblox.com/v1/groups/icons",
        params={"groupIds": ids, "size": "150x150", "format": "Png"},
    ) as resp:
        data = await resp.json()
    return {
        entry["targetId"]: entry["imageUrl"]
        for entry in data.get("data", [])
        if entry.get("state") == "Completed"
    }


async def fetch_group_created_dates(session, group_ids):
    results = {}
    for group_id in group_ids:
        async with session.get(f"https://groups.roblox.com/v1/groups/{group_id}") as resp:
            data = await resp.json()
        created = data.get("created", "")
        if created:
            results[group_id] = created[:10]
    return results


class GroupView(discord.ui.LayoutView):
    def __init__(self, groups, roblox_display):
        super().__init__()
        self.groups         = groups
        self.roblox_display = roblox_display
        self.page           = 0
        self._render()

    def _render(self):
        self.clear_items()
        group     = self.groups[self.page]
        max_pages = len(self.groups)
        group_id  = group["id"]
        icon_url  = group.get("iconUrl", "")
        group_url = f"https://www.roblox.com/groups/{group_id}"

        title = discord.ui.TextDisplay(
            f"[{group['name']}]({group_url})\n"
            f"-# **{self.roblox_display}**'s Joined groups\n"
            f"-# Group Made: {group.get('created', 'Unknown')}  •  {group.get('description') or 'No description'}"
        )

        top = (
            discord.ui.Section(title, accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=icon_url)))
            if icon_url else title
        )

        self.add_item(discord.ui.Container(
            top,
            sep(),
            discord.ui.TextDisplay(
                f"> Members: {group['memberCount']}\n"
                f"> Public: {'True' if group.get('publicEntryAllowed') else 'False'}\n"
                f"> Rank: {group.get('role', {}).get('name', 'Unknown')}\n"
                f"> Group Id: `{group_id}`"
            ),
            sep(),
            discord.ui.TextDisplay(f"-# Page {self.page + 1}/{max_pages}"),
            accent_color=0x15FF,
        ))

        self.add_item(discord.ui.ActionRow(
            discord.ui.Button(label="◄", style=discord.ButtonStyle.secondary, custom_id="prev", disabled=self.page == 0),
            discord.ui.Button(label="►", style=discord.ButtonStyle.secondary, custom_id="next", disabled=self.page == max_pages - 1),
        ))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "prev":
            self.page -= 1
        else:
            self.page += 1
        self._render()
        await interaction.response.edit_message(view=self)
        return False


def loading_view(text):
    return make_view(discord.ui.TextDisplay(text))


@tree.command(name="groupcheck", description="Check a Roblox users groups")
@app_commands.describe(roblox_username="The Roblox username to look up")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@test_subject_check()
async def groupcheck(interaction: discord.Interaction, roblox_username: str):
    profile_url   = f"https://www.roblox.com/users/profile?username={roblox_username}"
    username_link = f"[{roblox_username}]({profile_url})"

    await interaction.response.send_message(
        view=loading_view(f"{interaction.user.mention} loading {username_link} groups")
    )

    stop_anim = asyncio.Event()

    async def animate():
        i = 0
        while not stop_anim.is_set():
            await asyncio.sleep(0.8)
            if stop_anim.is_set():
                break
            i = (i + 1) % len(DOTS)
            try:
                await interaction.edit_original_response(
                    view=loading_view(f"{interaction.user.mention} loading {username_link} groups{DOTS[i]}")
                )
            except (discord.HTTPException, discord.NotFound):
                break

    anim_task = asyncio.create_task(animate())

    async def stop_animation():
        stop_anim.set()
        await asyncio.sleep(0.1)
        anim_task.cancel()
        try:
            await anim_task
        except asyncio.CancelledError:
            pass

    async with aiohttp.ClientSession() as session:
        user = await fetch_roblox_user(session, roblox_username)
        if not user:
            await stop_animation()
            await interaction.edit_original_response(
                view=make_view(discord.ui.TextDisplay(f"Could not find Roblox user **{roblox_username}**."))
            )
            return

        user_id        = user["id"]
        roblox_display = user["name"]
        raw_groups     = await fetch_user_groups(session, user_id)

        if not raw_groups:
            await stop_animation()
            await interaction.edit_original_response(
                view=make_view(discord.ui.TextDisplay(f"**{roblox_display}** is not in any groups."))
            )
            return

        group_ids = [entry["group"]["id"] for entry in raw_groups]
        icons, created_dates = await asyncio.gather(
            fetch_group_icons(session, group_ids),
            fetch_group_created_dates(session, group_ids),
        )

    await stop_animation()

    groups = [
        {
            "id":                 entry["group"]["id"],
            "name":               entry["group"]["name"],
            "description":        entry["group"].get("description", ""),
            "memberCount":        entry["group"].get("memberCount", 0),
            "publicEntryAllowed": entry["group"].get("publicEntryAllowed", False),
            "role":               entry["role"],
            "iconUrl":            icons.get(entry["group"]["id"], ""),
            "created":            created_dates.get(entry["group"]["id"], "Unknown"),
        }
        for entry in raw_groups
    ]

    await interaction.edit_original_response(view=GroupView(groups, roblox_display))


@tree.command(name="hb", description="Hardban a user (owner+)")
@app_commands.describe(user="User to hardban", reason="Reason for the hardban")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@min_role_check("owner")
async def hb(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
    await interaction.response.defer()

    if user.id == interaction.user.id:
        await interaction.followup.send("you cant ban yourself lol")
        return
    if user.id == 878416460924465193:
        await interaction.followup.send("LMAOOO U TRIED")
        return
    if db is None:
        await interaction.followup.send("Database is not connected. Contact the bot owner.")
        return

    HARDBAN_IDS.add(user.id)
    await db_add_hardban(user.id)

    try:
        await interaction.guild.ban(user, reason=f"hardban | {reason}", delete_message_seconds=0)
    except discord.Forbidden:
        HARDBAN_IDS.discard(user.id)
        await db_remove_hardban(user.id)
        await interaction.followup.send("ban failed: hierarchy")
        return
    except discord.HTTPException:
        HARDBAN_IDS.discard(user.id)
        await db_remove_hardban(user.id)
        await interaction.followup.send("ban failed: unknown error")
        return

    try:
        await user.send(view=make_view(
            discord.ui.TextDisplay(f"hey bitch ass nigga you got hardbanned from **{interaction.guild.name}**"),
            sep(),
            discord.ui.TextDisplay(f"> Moderator: {interaction.user.mention}\n> Reason: {reason}"),
            sep(),
            discord.ui.TextDisplay("-# please note you cant get unhardbanned unless the owner unbans you"),
        ))
    except (discord.Forbidden, discord.HTTPException):
        pass

    await interaction.followup.send(view=make_view(
        discord.ui.TextDisplay(f"Successfully banned {user.mention}"),
        sep(),
        discord.ui.TextDisplay(f"> Moderator: {interaction.user.mention}\n> Reason: {reason}"),
        sep(),
        discord.ui.TextDisplay("-# please note if you are not the owner you cannot unban"),
    ))


@tree.command(name="unhb", description="Remove a hardban (owner+)")
@app_commands.describe(user_id="The user ID to remove from the hardban list")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@min_role_check("owner")
async def unhb(interaction: discord.Interaction, user_id: str):
    try:
        uid = int(user_id)
    except ValueError:
        await interaction.response.send_message("Invalid user ID.")
        return

    if uid not in HARDBAN_IDS:
        await interaction.response.send_message("That user is not hardbanned.")
        return

    HARDBAN_IDS.discard(uid)
    await db_remove_hardban(uid)

    try:
        await interaction.guild.unban(discord.Object(id=uid), reason="hardban lifted by owner+")
    except discord.NotFound:
        pass

    await interaction.response.send_message(
        f"<@{uid}> (`{uid}`) has been removed from the hardban list and unbanned."
    )


@tree.command(name="unbanall", description="Unban all banned users (owner+)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@min_role_check("owner")
async def unbanall(interaction: discord.Interaction):
    bans  = [entry async for entry in interaction.guild.bans()]
    count = len(bans)

    confirmed = asyncio.Event()
    cancelled = asyncio.Event()

    yes_btn = discord.ui.Button(label="Yes", style=discord.ButtonStyle.danger,    custom_id="unbanall_yes")
    no_btn  = discord.ui.Button(label="No",  style=discord.ButtonStyle.secondary, custom_id="unbanall_no")

    async def yes_callback(i: discord.Interaction):
        if i.user.id != interaction.user.id:
            await i.response.send_message("This is not your confirmation.", ephemeral=True)
            return
        confirmed.set()
        await i.response.defer()

    async def no_callback(i: discord.Interaction):
        if i.user.id != interaction.user.id:
            await i.response.send_message("This is not your confirmation.", ephemeral=True)
            return
        cancelled.set()
        await i.response.edit_message(view=make_view(discord.ui.TextDisplay("Unban all cancelled.")))

    yes_btn.callback = yes_callback
    no_btn.callback  = no_callback

    confirm_view = discord.ui.LayoutView()
    confirm_view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("Unban all"),
        sep(),
        discord.ui.TextDisplay(f"this command will unban all **{count}** banned users, are you sure?"),
        accent_color=0x7536FF,
    ))
    confirm_view.add_item(discord.ui.ActionRow(yes_btn, no_btn))

    await interaction.response.send_message(view=confirm_view)
    msg = await interaction.original_response()

    await asyncio.wait(
        [asyncio.create_task(confirmed.wait()), asyncio.create_task(cancelled.wait())],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=30,
    )

    if not confirmed.is_set():
        return

    unbanned = 0
    for entry in bans:
        try:
            await interaction.guild.unban(entry.user, reason=f"unbanall by {interaction.user}")
            unbanned += 1
        except discord.HTTPException:
            pass

    hbs_cleared = 0
    if db is not None:
        result = await db.execute("DELETE FROM hardbans")
        hbs_cleared = int(result.split()[-1]) if result else 0
    HARDBAN_IDS.clear()

    await msg.edit(view=make_view(
        discord.ui.TextDisplay("Success"),
        sep(),
        discord.ui.TextDisplay(
            f"> Unbanned all **{unbanned}** users!\n"
            f"> Cleared **{hbs_cleared}** hbs from db"
        ),
        sep(),
        accent_color=0x40FF,
    ))


@tree.command(name="sync", description="Force re-sync commands (founder only)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@min_role_check("founder")
async def sync_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    for g in interaction.client.guilds:
        tree.clear_commands(guild=g)
        await tree.sync(guild=g)
    synced = await tree.sync()
    names = ", ".join(f"`/{c.name}`" for c in synced)
    await interaction.followup.send(f"Synced {len(synced)} commands globally: {names}")


@bot.command(name="ban")
@founder_only()
async def prefix_ban(ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
    if user.id == ctx.author.id:
        await ctx.send("you cant ban yourself lol")
        return
    if user.id == 878416460924465193:
        await ctx.send("LMAOOO U TRIED")
        return
    try:
        await ctx.guild.ban(user, reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        await ctx.send("ban failed: hierachy")
        return
    except discord.HTTPException:
        await ctx.send("ban failed: unknown error")
        return

    try:
        await user.send(view=make_view(
            discord.ui.TextDisplay(f"hey bitch ass nigga you got banned from **{ctx.guild.name}**"),
            sep(),
            discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}\n> Reason: {reason}"),
            sep(),
        ))
    except (discord.Forbidden, discord.HTTPException):
        pass

    await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"{user.mention} has been exiled"),
        sep(),
        discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}\n> Reason: {reason}"),
        sep(),
        accent_color=0x20209,
    ))


@bot.command(name="unban")
@founder_only()
async def prefix_unban(ctx: commands.Context, user_id: str, *, reason: str = "No reason provided"):
    try:
        uid = int(user_id)
    except ValueError:
        await ctx.send("Invalid user ID.")
        return

    try:
        await ctx.guild.unban(discord.Object(id=uid), reason=reason)
        HARDBAN_IDS.discard(uid)
        if db is not None:
            await db_remove_hardban(uid)
    except discord.NotFound:
        await ctx.send("That user is not banned.")
        return
    except discord.Forbidden:
        await ctx.send("I do not have permission to unban that user.")
        return

    await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"<@{uid}> has been unbanned"),
        sep(),
        discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}\n> Reason: {reason}"),
        sep(),
        accent_color=0x20209,
    ))


@bot.command(name="hb")
@prefix_min_role_check("owner")
async def prefix_hb(ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
    if user.id == ctx.author.id:
        await ctx.send("you cant ban yourself lol")
        return
    if user.id == 878416460924465193:
        await ctx.send("LMAOOO U TRIED")
        return
    if db is None:
        await ctx.send("Database is not connected. Contact the bot owner.")
        return

    HARDBAN_IDS.add(user.id)
    await db_add_hardban(user.id)

    try:
        await ctx.guild.ban(user, reason=f"hardban | {reason}", delete_message_seconds=0)
    except discord.Forbidden:
        HARDBAN_IDS.discard(user.id)
        await db_remove_hardban(user.id)
        await ctx.send("ban failed: hierachy")
        return
    except discord.HTTPException:
        HARDBAN_IDS.discard(user.id)
        await db_remove_hardban(user.id)
        await ctx.send("ban failed: unknown error")
        return

    try:
        await user.send(view=make_view(
            discord.ui.TextDisplay(f"hey bitch ass nigga you got hardbanned from **{ctx.guild.name}**"),
            sep(),
            discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}\n> Reason: {reason}"),
            sep(),
            discord.ui.TextDisplay("-# please note you cant get unhardbanned unless the owner unbans you"),
        ))
    except (discord.Forbidden, discord.HTTPException):
        pass

    await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"Successfully banned {user.mention}"),
        sep(),
        discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}\n> Reason: {reason}"),
        sep(),
        discord.ui.TextDisplay("-# please note if you are not the owner you cannot unban"),
    ))


@bot.command(name="unhb")
@prefix_min_role_check("owner")
async def prefix_unhb(ctx: commands.Context, user_id: str):
    try:
        uid = int(user_id)
    except ValueError:
        await ctx.send("Invalid user ID.")
        return

    if uid not in HARDBAN_IDS:
        await ctx.send("That user is not hardbanned.")
        return

    HARDBAN_IDS.discard(uid)
    await db_remove_hardban(uid)

    try:
        await ctx.guild.unban(discord.Object(id=uid), reason="hardban lifted by owner+")
    except discord.NotFound:
        pass

    await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"<@{uid}> (`{uid}`) has been removed from the hardban list and unbanned."),
        sep(),
        discord.ui.TextDisplay(f"> Moderator: {ctx.author.mention}"),
        sep(),
        accent_color=0x20209,
    ))


SUPPORT_CHANNEL_ID = 1512997168141832253
SUPPORT_ROLE_IDS   = {1511643299352412230, 1506847827907838053, 1510847135745310790, 1498918197791948840}

VERIFIED_ROLE_ID  = 1498932476268249158
VERIFY_CHANNEL_ID = 1515198194374545499


async def _create_support_thread(interaction: discord.Interaction, topic: str, answer):
    counter     = await db.fetchval("UPDATE ticket_counter SET counter = counter + 1 WHERE id = 1 RETURNING counter")
    thread_name = f"{topic} - {counter:04d}"

    channel = interaction.guild.get_channel(SUPPORT_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("Support channel not found.", ephemeral=True)
        return

    thread = await channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.private_thread,
        invitable=False,
    )

    await thread.add_user(interaction.user)

    support_roles = [interaction.guild.get_role(rid) for rid in SUPPORT_ROLE_IDS]
    support_roles = [r for r in support_roles if r]
    role_mentions = " ".join(r.mention for r in support_roles) + f" <@{PARTYBOY_ID}>"
    extra = f"\n> {answer}" if answer else ""

    await thread.send(
        view=make_view(
            discord.ui.TextDisplay(f"**{thread_name}**"),
            sep(),
            discord.ui.TextDisplay(f"> Opened by {interaction.user.mention}{extra}"),
        ),
    )
    await thread.send(role_mentions, allowed_mentions=discord.AllowedMentions(roles=True, users=True))
    await interaction.response.send_message(f"Your thread has been opened: {thread.mention}", ephemeral=True)


def _sp_view():
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("Hello this is **Kiyo** support."),
        sep(),
        discord.ui.TextDisplay("> please select a forum to open for support."),
        accent_color=5631,
    ))
    view.add_item(discord.ui.ActionRow(discord.ui.Select(
        custom_id="sp_topic_select",
        placeholder="please select a forum to open for support.",
        options=[
            discord.SelectOption(label="Support",      value="Support"),
            discord.SelectOption(label="Admin Aboose", value="Admin Aboose"),
            discord.SelectOption(label="Tag",          value="Tag"),
        ],
    )))
    return view


@bot.command(name="sp")
@prefix_min_role_check("owner")
async def sp(ctx: commands.Context):
    await ctx.message.delete()
    channel = ctx.guild.get_channel(SUPPORT_CHANNEL_ID)
    if channel is None:
        await ctx.send("Support channel not found.", delete_after=5)
        return
    await channel.send(view=_sp_view())


def _vp_view():
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("**Verification**"),
        sep(),
        discord.ui.TextDisplay("> select **Verify** from the dropdown below and enter your Roblox username.\n> a staff member will review and verify you."),
        accent_color=0x5865F2,
    ))
    view.add_item(discord.ui.ActionRow(discord.ui.Select(
        custom_id="verify_select",
        placeholder="click here to verify",
        options=[
            discord.SelectOption(label="Verify", value="verify", description="Submit your Roblox username for verification"),
        ],
    )))
    return view


@bot.command(name="vp")
@prefix_min_role_check("owner")
async def vp(ctx: commands.Context):
    await ctx.message.delete()
    await ctx.channel.send(view=_vp_view())


@bot.command(name="v")
async def verify_user(ctx: commands.Context, member: discord.Member):
    member_role_ids = {r.id for r in ctx.author.roles}
    if ctx.author.id not in FOUNDER_IDS and not member_role_ids & SUPPORT_ROLE_IDS:
        await ctx.message.delete()
        return
    if db is None:
        await ctx.send("Database is not connected.")
        return

    row = await db_get_verification(member.id)
    if row is None:
        await ctx.send(f"{member.mention} has not submitted a verification request.")
        return

    roblox_name = row["roblox_name"]

    async with aiohttp.ClientSession() as session:
        roblox_user = await fetch_roblox_user(session, roblox_name)

    if not roblox_user:
        await ctx.send(
            view=make_view(discord.ui.TextDisplay(f"could not find Roblox user **{roblox_name}** for {member.mention}. ask them to resubmit with the correct username."))
        )
        return

    role = ctx.guild.get_role(VERIFIED_ROLE_ID)
    if role is None:
        await ctx.send("Verified role not found. Set `VERIFIED_ROLE_ID` in the bot config.")
        return

    try:
        await member.add_roles(role, reason=f"verified by {ctx.author} | roblox: {roblox_user['name']}")
    except discord.Forbidden:
        await ctx.send("Missing permissions to assign the verified role.")
        return

    await db_delete_verification(member.id)
    await ctx.send(
        view=make_view(
            discord.ui.TextDisplay(f"{member.mention} has been verified as **{roblox_user['name']}** on Roblox."),
            accent_color=0x57F287,
        )
    )

    try:
        await member.send(
            view=make_view(discord.ui.TextDisplay(f"you have been verified as **{roblox_user['name']}** in **{ctx.guild.name}**."))
        )
    except discord.HTTPException:
        pass

    if isinstance(ctx.channel, discord.Thread) and ctx.channel.parent_id == VERIFY_CHANNEL_ID:
        await ctx.channel.delete()


@bot.command(name="close")
async def close_thread(ctx: commands.Context):
    if not isinstance(ctx.channel, discord.Thread):
        await ctx.message.delete()
        return
    member_role_ids = {r.id for r in ctx.author.roles}
    if ctx.author.id not in FOUNDER_IDS and not member_role_ids & SUPPORT_ROLE_IDS:
        await ctx.message.delete()
        return
    await ctx.channel.delete()


@bot.command(name="delete")
async def delete_channel(ctx: commands.Context):
    if not isinstance(ctx.channel, discord.Thread):
        await ctx.message.delete()
        return
    member_role_ids = {r.id for r in ctx.author.roles}
    if not member_role_ids & SUPPORT_ROLE_IDS and ctx.author.id not in FOUNDER_IDS:
        await ctx.message.delete()
        return
    await ctx.message.delete()
    await ctx.channel.delete()


HELP_SECTIONS = {
    "moderation": (
        "**Moderation**\n"
        "> `/hb <user> [reason]` — hardban a user (owner+)\n"
        "> `/unhb <user_id>` — remove a hardban (owner+)\n"
        "> `/unbanall` — unban all users (owner+)\n"
        "> `>ban <user> [reason]` — ban a user (founder)\n"
        "> `>unban <id> [reason]` — unban a user (founder)\n"
        "> `>hb <user> [reason]` — hardban a user (owner+)\n"
        "> `>unhb <id>` — remove a hardban (owner+)"
    ),
    "whitelist": (
        "**Whitelist**\n"
        "> `/whitelist add <user> <role>` — add a user (owner+)\n"
        "> `/whitelist remove <user>` — remove a user (owner+)\n"
        "> `/whitelist list` — view whitelisted users (staff+)\n"
        "> `/testcommands enable/disable/list` — manage test subject commands (founder)"
    ),
    "utility": (
        "**Utility**\n"
        "> `/groupcheck <username>` — check a Roblox user's groups\n"
        "> `/gif send <name>` — send a stored gif (owner+)\n"
        "> `/gif add <name> <url>` — add a gif (owner+)\n"
        "> `/gif remove <name>` — remove a gif (owner+)\n"
        "> `>fadd <word>` — add a filtered word (owner+)\n"
        "> `>fremove <word>` — remove a filtered word (owner+)\n"
        "> `>flist` — list filtered words (owner+)\n"
        "> `/sync` — re-sync commands (founder)"
    ),
    "support": (
        "**Support**\n"
        "> `>sp` — send support panel (owner+)\n"
        "> `>delete` — delete current thread (support roles)\n"
        "> `>vp` — send verification panel (owner+)\n"
        "> `>v <user>` — verify a user's Roblox account (staff+)"
    ),
}

HELP_OPTIONS = [
    discord.SelectOption(label="Moderation", value="moderation"),
    discord.SelectOption(label="Whitelist",  value="whitelist"),
    discord.SelectOption(label="Utility",    value="utility"),
    discord.SelectOption(label="Support",    value="support"),
]


def _help_welcome_view():
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("**Kiyo**"),
        sep(),
        discord.ui.TextDisplay("> select a category below to view commands."),
        accent_color=5631,
    ))
    view.add_item(discord.ui.ActionRow(discord.ui.Select(
        custom_id="help_section_select",
        placeholder="Select a category...",
        options=HELP_OPTIONS,
    )))
    return view


def _help_section_view(section: str):
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("**Kiyo**"),
        sep(),
        discord.ui.TextDisplay(HELP_SECTIONS[section]),
        accent_color=5631,
    ))
    view.add_item(discord.ui.ActionRow(discord.ui.Select(
        custom_id="help_section_select",
        placeholder="Select a category...",
        options=HELP_OPTIONS,
    )))
    return view


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    await ctx.message.delete()
    await ctx.send(view=_help_welcome_view())


# Intelligence Commands


@bot.command(name="profile")
@founder_only()
async def cmd_profile(ctx: commands.Context, user: discord.User):
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/users/{user.id}/profile", {"with_mutual_guilds": "true", "with_mutual_friends_count": "true"})

    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    u           = data.get("user", {})
    badges      = [BADGE_MAP.get(b["id"], b["id"]) for b in data.get("badges", [])]
    connections = data.get("connected_accounts", [])
    mutuals     = data.get("mutual_guilds", [])
    bio         = _clean_bio(data.get("user_profile", {}).get("bio") or "") or "no bio set"
    nitro_type  = NITRO_TYPES.get(u.get("premium_type", 0), "None")

    display     = u.get("global_name") or user.name
    created_ts  = discord.utils.snowflake_time(user.id)
    created_str = f"<t:{int(created_ts.timestamp())}:D>"

    badge_line  = "  ".join(f"`{b}`" for b in badges) if badges else "`none`"

    connected_lines = "\n".join(
        f"> {CONNECTED_ICONS.get(c['type'], c['type'].title())} — **{c['name']}**"
        for c in connections
    ) or "> none linked"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {display}\n"
                f"-# {user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"> created {created_str}  •  nitro {nitro_type}  •  {len(mutuals)} mutual servers\n"
            f"> badges — {badge_line}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**bio**\n> {bio}"),
        sep(),
        discord.ui.TextDisplay(f"**accounts**\n{connected_lines}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="stalk")
@founder_only()
async def cmd_stalk(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()

    member = ctx.guild.get_member(user.id)
    if not member:
        await ctx.send("User not in this server.", delete_after=5)
        return

    status     = str(member.status)
    activities = member.activities
    now        = discord.utils.utcnow()

    activity_lines = []
    for act in activities:
        if isinstance(act, discord.Spotify):
            activity_lines.append(f"> Spotify: **{act.title}** by {act.artist}")
        elif isinstance(act, discord.Game):
            elapsed = now - act.start if act.start else None
            duration = f" ({int(elapsed.total_seconds()//3600)}h {int((elapsed.total_seconds()%3600)//60)}m)" if elapsed else ""
            activity_lines.append(f"> Playing: **{act.name}**{duration}")
        elif isinstance(act, discord.Streaming):
            activity_lines.append(f"> Streaming: **{act.name}** on {act.platform}")
        elif isinstance(act, discord.CustomActivity):
            activity_lines.append(f"> Status: {act.emoji or ''} {act.name or ''}")
        elif act:
            activity_lines.append(f"> {act.type.name.title()}: **{act.name}**")

    activity_text = "\n".join(activity_lines) or "> nothing detected"

    joined_ts  = int(member.joined_at.timestamp()) if member.joined_at else None
    joined_str = f"<t:{joined_ts}:R>" if joined_ts else "unknown"
    created_ts = int(discord.utils.snowflake_time(user.id).timestamp())
    roles      = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    roles_str  = " ".join(roles[:6]) if roles else "`none`"

    STATUS_COLORS = {"online": 0x2ECC71, "idle": 0xF1C40F, "dnd": 0xE74C3C, "offline": 0x747F8D}
    color         = STATUS_COLORS.get(status, 0x5865F2)

    # pull custom status text if present
    custom_status = ""
    for act in activities:
        if isinstance(act, discord.CustomActivity) and act.name:
            custom_status = f' — "{act.name}"'
            break

    boost_str = f"boosting since <t:{int(member.premium_since.timestamp())}:R>" if member.premium_since else None
    nick_str  = f"`{member.nick}`" if member.nick and member.nick != member.name else None

    # build status line: DND - "custom status"
    status_line = f"> **{status.upper()}**{custom_status}"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {member.display_name}\n"
                f"-# @{user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=member.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Status**\n"
            f"{status_line}"
            + (f"\n> Nickname — {nick_str}" if nick_str else "")
            + (f"\n> {boost_str}" if boost_str else "")
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Timestamps**\n"
            f"> Joined — {joined_str} (<t:{joined_ts}:D>)\n"
            f"> Account — <t:{created_ts}:R> (<t:{created_ts}:D>)"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Activity**\n{activity_text}"),
        sep(),
        discord.ui.TextDisplay(f"**Roles** ({len(roles)})\n> {roles_str}"),
        accent_color=color,
    ))
    await ctx.send(view=view)


@bot.command(name="search")
@founder_only()
async def cmd_search(ctx: commands.Context, *, query: str):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/guilds/{ctx.guild.id}/messages/search", {
        "content": query,
        "limit": "10",
    })

    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    messages = [m for group in data.get("messages", []) for m in group if not m.get("hit") is False]
    hits     = [m for m in messages if m.get("hit")]

    if not hits:
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"No results for `{query}`.")))
        return

    lines = []
    for m in hits[:8]:
        author   = m.get("author", {})
        username = author.get("global_name") or author.get("username", "Unknown")
        content  = m.get("content", "")[:80].replace("\n", " ")
        channel_id = m.get("channel_id", "")
        msg_id     = m.get("id", "")
        jump       = f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{msg_id}"
        lines.append(f"> **{username}**: {content} — [jump]({jump})")

    total = data.get("total_results", len(hits))
    view  = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## search: {query}\n-# {total} results"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="analytics")
@founder_only()
async def cmd_analytics(ctx: commands.Context):
    await ctx.message.delete()
    msg = await ctx.send(view=make_view(discord.ui.TextDisplay("scanning messages...")))

    user_counts  = {}
    total        = 0
    limit        = 500

    async for message in ctx.channel.history(limit=limit):
        if message.author.bot:
            continue
        uid = message.author.id
        user_counts[uid] = user_counts.get(uid, {"name": message.author.display_name, "count": 0})
        user_counts[uid]["count"] += 1
        total += 1

    if total == 0:
        await msg.edit(view=make_view(discord.ui.TextDisplay("No messages found.")))
        return

    top_users = sorted(user_counts.values(), key=lambda x: x["count"], reverse=True)[:10]
    top_lines = "\n".join(f"> `{i:02d}` **{u['name']}** — {u['count']} msgs" for i, u in enumerate(top_users, 1))

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## #{ctx.channel.name}\n-# {total} msgs • {len(user_counts)} chatters"),
        sep(),
        discord.ui.TextDisplay(top_lines),
        accent_color=0x9B9B9B,
    ))
    await msg.edit(view=view)


@bot.command(name="joined")
@founder_only()
async def cmd_joined(ctx: commands.Context):
    await ctx.message.delete()
    members = sorted(
        [m for m in ctx.guild.members if not m.bot and m.joined_at],
        key=lambda m: m.joined_at,
    )

    lines = []
    for i, m in enumerate(members[:20], 1):
        ts = int(m.joined_at.timestamp())
        lines.append(f"> `{i:02d}` **{m.display_name}** — <t:{ts}:D>")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## oldest members\n-# {ctx.guild.name} • {ctx.guild.member_count} total"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="audit")
@founder_only()
async def cmd_audit(ctx: commands.Context, action: str = None):
    await ctx.message.delete()

    action_filter = None
    action_map = {
        "ban":    discord.AuditLogAction.ban,
        "unban":  discord.AuditLogAction.unban,
        "kick":   discord.AuditLogAction.kick,
        "role":   discord.AuditLogAction.member_role_update,
        "invite": discord.AuditLogAction.invite_create,
        "delete": discord.AuditLogAction.message_delete,
        "edit":   discord.AuditLogAction.message_pin,
    }
    if action and action.lower() in action_map:
        action_filter = action_map[action.lower()]

    entries = []
    async for entry in ctx.guild.audit_logs(limit=15, action=action_filter):
        entries.append(entry)

    if not entries:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No audit log entries found.")))
        return

    lines = []
    for e in entries:
        when   = e.created_at.strftime("%m/%d %H:%M")
        action_name = e.action.name.replace("_", " ")
        target = str(e.target) if e.target else "?"
        user   = str(e.user) if e.user else "?"
        reason = f" — {e.reason}" if e.reason else ""
        lines.append(f"> `{when}` **{action_name}** by {user} → {target}{reason}")

    filter_label = f"filter: `{action}`" if action else "all actions"
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## audit log\n-# {ctx.guild.name} • {filter_label}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="invites")
@founder_only()
async def cmd_invites(ctx: commands.Context):
    await ctx.message.delete()
    invites = await ctx.guild.invites()

    if not invites:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No active invites.")))
        return

    invites.sort(key=lambda i: i.uses or 0, reverse=True)

    lines = []
    for inv in invites[:15]:
        creator = inv.inviter.display_name if inv.inviter else "Unknown"
        uses    = inv.uses or 0
        max_u   = inv.max_uses or "∞"
        channel = f"#{inv.channel.name}" if inv.channel else "?"
        expiry  = inv.expires_at.strftime("%m/%d/%Y") if inv.expires_at else "Never"
        lines.append(f"> `{inv.code}` by **{creator}** — {uses}/{max_u} uses — {channel} — expires {expiry}")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## invites\n-# {ctx.guild.name} • {len(invites)} active"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="tokens")
@founder_only()
async def cmd_tokens(ctx: commands.Context, limit: int = 200):
    await ctx.message.delete()
    import re
    token_pattern = re.compile(r"[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}")

    found = []
    async for message in ctx.channel.history(limit=limit):
        matches = token_pattern.findall(message.content)
        for match in matches:
            jump = message.jump_url
            found.append((message.author.display_name, match[:20] + "...", jump))

    if not found:
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"No tokens found in last {limit} messages.")), delete_after=10)
        return

    lines = [f"> **{author}**: `{tok}` — [jump]({url})" for author, tok, url in found[:10]]
    view  = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## leaked tokens\n-# {len(found)} found in #{ctx.channel.name}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="ghost")
@founder_only()
async def cmd_ghost(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/users/{user.id}/profile", {"with_mutual_guilds": "true"})

    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    mutuals    = data.get("mutual_guilds", [])
    mutual_ids = {int(g["id"]) for g in mutuals}
    shared     = [g for g in bot.guilds if g.id in mutual_ids]

    lines = [f"> **{g.name}** (`{g.id}`)" for g in shared] or ["> no mutual servers with this bot"]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## Ghost Check\n"
                f"-# {user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"**mutual servers ({len(shared)})**\n" + "\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="serverinfo")
@founder_only()
async def cmd_serverinfo(ctx: commands.Context):
    await ctx.message.delete()
    g = ctx.guild

    bots    = sum(1 for m in g.members if m.bot)
    humans  = g.member_count - bots
    tier     = g.premium_tier

    channels = g.channels
    text_ch  = sum(1 for c in channels if isinstance(c, discord.TextChannel))
    voice_ch = sum(1 for c in channels if isinstance(c, discord.VoiceChannel))

    owner    = g.owner.mention if g.owner else "Unknown"
    vanity   = f"discord.gg/{g.vanity_url_code}" if g.vanity_url_code else "None"
    features = ", ".join(f.replace("_", " ").title() for f in g.features) or "None"

    emojis   = len(g.emojis)
    stickers = len(g.stickers)
    roles    = len(g.roles) - 1

    created_ts = int(g.created_at.timestamp())
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {g.name}\n"
                f"-# `{g.id}` • created <t:{created_ts}:D>"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=g.icon.url if g.icon else "https://cdn.discordapp.com/embed/avatars/0.png")),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"> owner {owner}  •  vanity {vanity}  •  boost lvl {tier}\n"
            f"> {humans} humans  {bots} bots  •  {text_ch} text  {voice_ch} voice\n"
            f"> {roles} roles  •  {emojis} emojis  •  {stickers} stickers"
        ),
        sep(),
        discord.ui.TextDisplay(f"-# {features}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="servers")
@founder_only()
async def cmd_servers(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    # fetch every server the user token is in
    import aiohttp as _aiohttp
    headers = {"Authorization": USER_TOKEN, "Content-Type": "application/json"}
    async with _aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://discord.com/api/v10/users/@me/guilds") as resp:
            all_guilds = await resp.json()

    if isinstance(all_guilds, dict):
        await ctx.send(f"API error: {all_guilds.get('message', '?')}", delete_after=5)
        return

    found = []
    for g in all_guilds:
        guild_id  = int(g["id"])
        guild_name = g.get("name", f"`{guild_id}`")

        # check if target user is in this server via user token
        async with _aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user.id}") as resp:
                member_data = await resp.json() if resp.status == 200 else None

        if not member_data:
            continue

        joined_at = member_data.get("joined_at")
        if joined_at:
            import datetime
            ts = int(datetime.datetime.fromisoformat(joined_at.rstrip("Z")).timestamp())
            joined_str = f"<t:{ts}:D>"
        else:
            joined_str = "?"

        approx_members = g.get("approximate_member_count", "?")
        found.append(f"> **{guild_name}** — joined {joined_str}")

    if not found:
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"{user.name} is not in any servers the token can see.")), delete_after=5)
        return

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## servers\n"
                f"-# @{user.name} • `{user.id}` • {len(found)} found"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay("\n".join(found[:20])),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


HELP_SECTIONS["intelligence"] = (
    "**WIP**\n"
    "> `>profile @user` — Discord profile + badges + bio\n"
    "> `>harvest @user` — deep profile dump (flags, nitro, banner, connections)\n"
    "> `>stalk @user` — live status, activity, roles\n"
    "> `>activity @user` — raw rich presence data\n"
    "> `>dmhistory @user` — pull DM history\n"
    "> `>msgscan @user` — behavioral profile from message history\n"
    "> `>altscan @user` — alt account detection with risk score\n"
    "> `>lookup <id>` — info on any user ID\n"
    "> `>servers @user` — mutual servers with bot\n"
    "> `>presence @user` — raw gateway presence\n"
    "> `>notes @user` — your Discord note on a user\n"
    "> `>dossier @user` — everything on a user in one embed\n"
    "-# ──\n"
    "> `>voicespy` — all voice channels + who's in them\n"
    "> `>webhooks` — all webhooks with URLs\n"
    "> `>botlist` — all bots + dangerous perms\n"
    "> `>recentjoins` — newest members with alt flags\n"
    "> `>nitrocheck` — all server boosters\n"
    "> `>permaudit` — dangerous permission audit\n"
    "> `>inviteaudit` — invite pattern analysis\n"
    "> `>mutecheck` — all muted/timed-out members\n"
    "-# ──\n"
    "> `>guildinfo` — raw server data\n"
    "> `>channelinfo [#ch]` — raw channel data\n"
    "> `>roleinfo @role` — role perms + metadata\n"
    "> `>perms [@user]` — full permission breakdown\n"
    "> `>inviteinfo <code>` — full invite metadata\n"
    "> `>vanity <code>` — deep vanity URL lookup\n"
    "> `>appinfo <id>` — any app via public endpoint\n"
    "> `>guildwidget <id>` — public widget data\n"
    "> `>snowflake <id>` — decode any snowflake\n"
    "> `>flagdecode <int>` — decode any flags integer\n"
    "> `>tokenchecker <token>` — decode + validate token\n"
    "> `>gateway` — live WebSocket session info\n"
    "-# ──\n"
    "> `>search <query>` — search server messages\n"
    "> `>audit [action]` — audit log\n"
    "> `>rawaudit [id]` — raw audit with undocumented types\n"
    "> `>experiments` — Discord A/B experiment buckets\n"
    "> `>readstate` — unread counts across all channels\n"
    "> `>membersearch <query>` — undocumented member search\n"
    "> `>typing` — live typing event log\n"
    "> `>tokens [limit]` — scan for leaked tokens\n"
    "-# ──\n"
    "> `>selfpurge [n]` — delete your last N messages\n"
    "> `>ghostping @user` — ping then instantly delete\n"
    "> `>hide` — toggle bot invisible to non-founders\n"
    "> `>tokenlog [n]` — command audit log\n"
    "> `>analytics` — top chatters in channel\n"
    "> `>joined` — oldest members\n"
    "> `>invites` — active invites\n"
    "> `>serverinfo` — server stats\n"
    "-# all commands are founder only"
)

HELP_OPTIONS.append(discord.SelectOption(label="WIP", value="intelligence"))


# Deep Reverse Engineering

# 1. RAW GATEWAY HOOK — intercept raw websocket events before discord.py strips them
_raw_presence_log: dict = {}   # uid -> last raw payload
_typing_log: list       = []   # last 50 typing events


@bot.event
async def on_socket_raw_receive(msg):
    import json
    try:
        data = json.loads(msg) if isinstance(msg, str) else json.loads(msg.decode())
    except Exception:
        return

    op = data.get("op")
    t  = data.get("t")
    d  = data.get("d") or {}

    if t == "PRESENCE_UPDATE":
        uid = int(d.get("user", {}).get("id", 0))
        if uid:
            _raw_presence_log[uid] = d

    if t == "TYPING_START":
        _typing_log.append({
            "user_id":    d.get("user_id"),
            "channel_id": d.get("channel_id"),
            "guild_id":   d.get("guild_id"),
            "timestamp":  d.get("timestamp"),
            "member":     d.get("member", {}).get("nick") or (d.get("member", {}).get("user") or {}).get("username"),
        })
        if len(_typing_log) > 50:
            _typing_log.pop(0)


@bot.command(name="presence")
@founder_only()
async def cmd_presence(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()
    raw = _raw_presence_log.get(user.id)
    if not raw:
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"No presence data cached for {user.mention} yet. They need to change status/activity first.")), delete_after=8)
        return

    activities = raw.get("activities", [])
    client_status = raw.get("client_status", {})
    status = raw.get("status", "unknown")

    act_lines = []
    for a in activities:
        atype  = {0: "Playing", 1: "Streaming", 2: "Listening", 3: "Watching", 4: "Custom", 5: "Competing"}.get(a.get("type"), "Unknown")
        name   = a.get("name", "?")
        state  = a.get("state", "")
        detail = a.get("details", "")
        app_id = a.get("application_id", "")
        flags  = a.get("flags", 0)
        ts     = a.get("timestamps", {})
        start  = ts.get("start")
        start_str = f"<t:{start//1000}:R>" if start else ""

        extras = []
        if detail: extras.append(f"detail: {detail}")
        if state:  extras.append(f"state: {state}")
        if app_id: extras.append(f"app_id: `{app_id}`")
        if flags:  extras.append(f"flags: `{flags}`")
        if start_str: extras.append(f"started {start_str}")

        act_lines.append(f"> **{atype}** {name}" + (f"\n> -# {' • '.join(extras)}" if extras else ""))

    clients = "\n".join(f"> {k}: **{v}**" for k, v in client_status.items()) or "> unknown"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## raw presence — {user.name}\n-# `{user.id}` • status: **{status}**"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay("**Activities (raw gateway data)**\n" + ("\n".join(act_lines) or "> none")),
        sep(),
        discord.ui.TextDisplay(f"**Client Platforms**\n{clients}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="typing")
@founder_only()
async def cmd_typing(ctx: commands.Context):
    await ctx.message.delete()
    if not _typing_log:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No typing events logged yet.")), delete_after=5)
        return

    lines = []
    for e in reversed(_typing_log[-15:]):
        uid     = e["user_id"]
        name    = e["member"] or f"`{uid}`"
        ch_id   = e["channel_id"]
        ts      = e["timestamp"]
        ts_str  = f"<t:{ts}:R>" if ts else "?"
        lines.append(f"> **{name}** typed in <#{ch_id}> {ts_str}")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## typing log\n-# last {len(_typing_log)} events intercepted from gateway"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


# 2. UNDOCUMENTED ENDPOINTS

@bot.command(name="notes")
@founder_only()
async def cmd_notes(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/users/@me/notes/{user.id}")
    note = data.get("note", "").strip() if isinstance(data, dict) else ""

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## your note — {user.name}\n-# `{user.id}`"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"> {note}" if note else "> no note set on this user"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="readstate")
@founder_only()
async def cmd_readstate(ctx: commands.Context):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get("/users/@me/read-states")
    entries = data if isinstance(data, list) else data.get("entries", [])

    unread = [e for e in entries if e.get("mention_count", 0) > 0]
    unread.sort(key=lambda e: e.get("mention_count", 0), reverse=True)

    lines = []
    for e in unread[:15]:
        ch_id   = e.get("id", "?")
        mentions = e.get("mention_count", 0)
        last_id  = e.get("last_message_id")
        lines.append(f"> <#{ch_id}> — **{mentions}** unread mention(s)")

    if not lines:
        lines = ["> no unread mentions across any channel"]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## read states\n-# {len(unread)} channels with unread mentions"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="experiments")
@founder_only()
async def cmd_experiments(ctx: commands.Context):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get("/experiments")
    assignments = data.get("assignments", [])

    lines = []
    for exp in assignments[:20]:
        if not exp:
            continue
        # format: [hash, bucket, revision, population, overrides, ...]
        exp_hash   = exp[0] if len(exp) > 0 else "?"
        bucket     = exp[1] if len(exp) > 1 else "?"
        revision   = exp[2] if len(exp) > 2 else "?"
        lines.append(f"> hash `{exp_hash}` — bucket **{bucket}** — rev `{revision}`")

    fingerprint = data.get("fingerprint", "unknown")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## a/b experiments\n-# fingerprint: `{fingerprint}` • {len(assignments)} assignments"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines) if lines else "> no experiment assignments"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="membersearch")
@founder_only()
async def cmd_membersearch(ctx: commands.Context, *, query: str):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/guilds/{ctx.guild.id}/members/search", {
        "query": query,
        "limit": "20",
    })

    members_raw = data if isinstance(data, list) else data.get("members", [])
    if not members_raw:
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"No members found matching `{query}`.")), delete_after=5)
        return

    lines = []
    for entry in members_raw[:15]:
        m    = entry if isinstance(entry, dict) and "user" in entry else entry
        user = m.get("user", {})
        nick = m.get("nick") or user.get("global_name") or user.get("username", "?")
        uid  = user.get("id", "?")
        roles = m.get("roles", [])
        role_str = " ".join(f"<@&{r}>" for r in roles[:3]) if roles else "`no roles`"
        lines.append(f"> **{nick}** `{uid}` — {role_str}")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## member search — `{query}`\n-# {len(members_raw)} result(s) in {ctx.guild.name}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


# 3. RAW AUDIT LOG — action IDs discord.py has no constants for

RAW_AUDIT_ACTIONS = {
    1:   "Server Update", 10: "Channel Create", 11: "Channel Update", 12: "Channel Delete",
    13: "Channel Overwrite Create", 14: "Channel Overwrite Update", 15: "Channel Overwrite Delete",
    20: "Member Kick", 21: "Member Prune", 22: "Member Ban", 23: "Member Unban",
    24: "Member Update", 25: "Member Role Update", 26: "Member Move", 27: "Member Disconnect",
    28: "Bot Add", 30: "Role Create", 31: "Role Update", 32: "Role Delete",
    40: "Invite Create", 41: "Invite Update", 42: "Invite Delete",
    50: "Webhook Create", 51: "Webhook Update", 52: "Webhook Delete",
    60: "Emoji Create", 61: "Emoji Update", 62: "Emoji Delete",
    72: "Message Delete", 73: "Message Bulk Delete", 74: "Message Pin", 75: "Message Unpin",
    80: "Integration Create", 81: "Integration Update", 82: "Integration Delete",
    83: "Stage Instance Create", 84: "Stage Instance Update", 85: "Stage Instance Delete",
    90: "Sticker Create", 91: "Sticker Update", 92: "Sticker Delete",
    100: "Guild Scheduled Event Create", 101: "Guild Scheduled Event Update", 102: "Guild Scheduled Event Delete",
    110: "Thread Create", 111: "Thread Update", 112: "Thread Delete",
    121: "Application Command Permission Update",
    140: "Auto Moderation Rule Create", 141: "Auto Moderation Rule Update", 142: "Auto Moderation Rule Delete",
    143: "Auto Moderation Block Message", 144: "Auto Moderation Flag to Channel", 145: "Auto Moderation User Communication Disabled",
    150: "Creator Monetization Request Created", 151: "Creator Monetization Terms Accepted",
    163: "Onboarding Question Create", 164: "Onboarding Question Update",
    167: "Onboarding Update", 190: "Home Settings Create", 191: "Home Settings Update",
}


@bot.command(name="rawaudit")
@founder_only()
async def cmd_rawaudit(ctx: commands.Context, action_id: int = None):
    await ctx.message.delete()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    params = {"limit": "15"}
    if action_id:
        params["action_type"] = str(action_id)

    data = await user_get(f"/guilds/{ctx.guild.id}/audit-logs", params)

    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    entries = data.get("audit_log_entries", [])
    users   = {u["id"]: u.get("global_name") or u.get("username", "?") for u in data.get("users", [])}

    if not entries:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No audit log entries found.")), delete_after=5)
        return

    lines = []
    for e in entries:
        act_id   = e.get("action_type", 0)
        act_name = RAW_AUDIT_ACTIONS.get(act_id, f"Unknown ({act_id})")
        user_id  = e.get("user_id", "?")
        uname    = users.get(user_id, f"`{user_id}`")
        target   = e.get("target_id", "")
        reason   = f" — _{e['reason']}_" if e.get("reason") else ""
        changes  = e.get("changes", [])
        ch_str   = f" `{len(changes)} changes`" if changes else ""
        lines.append(f"> `{act_id}` **{act_name}** by {uname}{ch_str}{reason}")

    filter_label = f"action `{action_id}` ({RAW_AUDIT_ACTIONS.get(action_id, '?')})" if action_id else "all actions"
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## raw audit log\n-# {ctx.guild.name} • {filter_label}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)




# Reverse Engineering Commands

@bot.command(name="harvest")
@founder_only()
async def cmd_harvest(ctx: commands.Context, user: discord.User):
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/users/{user.id}/profile", {
        "with_mutual_guilds": "true",
        "with_mutual_friends_count": "true",
        "with_premium_since": "true",
    })
    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    u           = data.get("user", {})
    profile     = data.get("user_profile", {}) or {}
    badges      = data.get("badges", [])
    connections = data.get("connected_accounts", [])
    mutuals     = data.get("mutual_guilds", [])
    guild_prof  = data.get("guild_member_profile", {}) or {}
    premium_since = data.get("premium_since")

    display      = u.get("global_name") or u.get("username", str(user.id))
    bio          = _clean_bio(profile.get("bio") or "") or "none"
    pronouns     = profile.get("pronouns") or "none"
    accent_color = profile.get("accent_color")
    banner_hash  = u.get("banner")
    nitro_type   = NITRO_TYPES.get(u.get("premium_type", 0), "None")
    flags        = u.get("public_flags", 0)
    created_ts   = int(discord.utils.snowflake_time(user.id).timestamp())

    # decode public flags manually
    FLAG_NAMES = {
        1: "Discord Staff", 2: "Partner", 4: "HypeSquad Events", 8: "Bug Hunter L1",
        64: "HypeSquad Bravery", 128: "HypeSquad Brilliance", 256: "HypeSquad Balance",
        512: "Early Supporter", 1024: "Team User", 4096: "Bug Hunter L2",
        16384: "Verified Bot", 32768: "Early Verified Bot Dev", 65536: "Certified Moderator",
        131072: "Bot HTTP Interactions", 4194304: "Active Developer",
    }
    flag_list = [name for bit, name in FLAG_NAMES.items() if flags & bit] or ["none"]

    badge_names  = [BADGE_MAP.get(b["id"], b["id"]) for b in badges]
    conn_lines   = "\n".join(f"> {CONNECTED_ICONS.get(c['type'], '🔗')} **{c['name']}** ({c['type']})" for c in connections) or "> none"
    mutual_names = ", ".join(f"`{g.get('nick') or g['id']}`" for g in mutuals[:8]) or "none"
    guild_bio    = _clean_bio(guild_prof.get("bio") or "") or "none"

    banner_url = f"https://cdn.discordapp.com/banners/{user.id}/{banner_hash}.{'gif' if banner_hash and banner_hash.startswith('a_') else 'png'}?size=512" if banner_hash else None
    accent_str = f"#{accent_color:06X}" if accent_color else "none"
    premium_str = f"<t:{int(__import__('datetime').datetime.fromisoformat(premium_since.rstrip('Z')).timestamp())}:R>" if premium_since else "none"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {display}\n"
                f"-# `{user.id}` • `{user.name}` • flags `{flags}`"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Account**\n"
            f"> Created — <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"> Nitro — {nitro_type}\n"
            f"> Nitro since — {premium_str}\n"
            f"> Accent color — {accent_str}\n"
            f"> Pronouns — {pronouns}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Public Flags** ({flags})\n> " + "\n> ".join(flag_list)),
        sep(),
        discord.ui.TextDisplay(f"**Badges**\n> " + ("  ".join(f"`{b}`" for b in badge_names) or "none")),
        sep(),
        discord.ui.TextDisplay(f"**Bio**\n> {bio}"),
        *(
            [sep(), discord.ui.TextDisplay(f"**Server Bio**\n> {guild_bio}")]
            if guild_bio != "none" else []
        ),
        sep(),
        discord.ui.TextDisplay(f"**Connected Accounts**\n{conn_lines}"),
        sep(),
        discord.ui.TextDisplay(f"**Mutual Servers** ({len(mutuals)})\n> {mutual_names}"),
        *(
            [sep(), discord.ui.TextDisplay(f"**Banner**\n> [view]({banner_url})")]
            if banner_url else []
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="dmhistory")
@founder_only()
async def cmd_dmhistory(ctx: commands.Context, user: discord.User, limit: int = 20):
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return
    limit = min(max(limit, 1), 50)

    # open DM then fetch via user token
    import aiohttp as _aiohttp
    headers = {"Authorization": USER_TOKEN, "Content-Type": "application/json"}
    async with _aiohttp.ClientSession(headers=headers) as session:
        # create DM
        async with session.post("https://discord.com/api/v10/users/@me/channels",
                                json={"recipient_id": str(user.id)}) as resp:
            dm = await resp.json()
        if "code" in dm:
            await ctx.send(f"Could not open DM: {dm.get('message', dm['code'])}", delete_after=5)
            return
        channel_id = dm["id"]

        # fetch messages
        async with session.get(f"https://discord.com/api/v10/channels/{channel_id}/messages",
                               params={"limit": str(limit)}) as resp:
            messages = await resp.json()

    if isinstance(messages, dict) and "code" in messages:
        await ctx.send(f"API error: {messages.get('message', messages['code'])}", delete_after=5)
        return

    if not messages:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No DM history found.")), delete_after=5)
        return

    lines = []
    for m in messages:
        author = m.get("author", {})
        name   = author.get("global_name") or author.get("username", "?")
        ts     = int(__import__('datetime').datetime.fromisoformat(m["timestamp"].rstrip("Z")).timestamp())
        content = (m.get("content") or "*(no text)*")[:80]
        attachments = f" 📎×{len(m['attachments'])}" if m.get("attachments") else ""
        lines.append(f"> `<t:{ts}:t>` **{name}**: {content}{attachments}")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## dm history\n-# with {user.name} • last {len(lines)} messages"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="activity")
@founder_only()
async def cmd_activity(ctx: commands.Context, user: discord.User):
    cached = _raw_presence_log.get(user.id)
    if not cached:
        await ctx.send(
            view=make_view(discord.ui.TextDisplay(f"No presence cached for {user.mention} yet — they need to change status/activity once after bot starts.")),
            delete_after=8,
        )
        return

    activities = cached.get("activities", [])
    client_status = cached.get("client_status", {})
    status = cached.get("status", "unknown")

    if not activities:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No activities in cached presence.")), delete_after=5)
        return

    blocks = []
    for act in activities:
        atype  = act.get("type", 0)
        aname  = act.get("name", "?")
        app_id = act.get("application_id")
        state  = act.get("state", "")
        detail = act.get("details", "")
        session= act.get("session_id", "")
        party  = act.get("party", {})
        assets = act.get("assets", {})
        ts     = act.get("timestamps", {})
        flags  = act.get("flags", 0)
        sync_id= act.get("sync_id", "")
        emoji  = act.get("emoji") or {}

        TYPE_NAMES = {0: "Playing", 1: "Streaming", 2: "Listening", 3: "Watching", 4: "Custom", 5: "Competing"}
        type_str = TYPE_NAMES.get(atype, f"Type {atype}")

        lines = [f"**{type_str}: {aname}**"]
        if detail:  lines.append(f"> Details — {detail}")
        if state:   lines.append(f"> State — {state}")
        if app_id:  lines.append(f"> App ID — `{app_id}`")
        if session: lines.append(f"> Session — `{session}`")
        if sync_id: lines.append(f"> Sync ID — `{sync_id}`")
        if flags:   lines.append(f"> Flags — `{flags}`")
        if party:
            size = party.get("size", [])
            lines.append(f"> Party — `{party.get('id', '?')}` {f'({size[0]}/{size[1]})' if len(size)==2 else ''}")
        if assets:
            lines.append(f"> Large image — `{assets.get('large_image', 'none')}`")
            lines.append(f"> Large text — {assets.get('large_text', 'none')}")
        if ts:
            if ts.get("start"): lines.append(f"> Started — <t:{ts['start']//1000}:R>")
            if ts.get("end"):   lines.append(f"> Ends — <t:{ts['end']//1000}:R>")
        if emoji:
            lines.append(f"> Emoji — {emoji.get('name','')} (`{emoji.get('id','builtin')}`)")
        blocks.append("\n".join(lines))

    platform_str = "  ".join(f"`{k}:{v}`" for k, v in client_status.items()) or "unknown"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## activity intel\n-# {user.name} • status `{status}`"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"**Platforms**\n> {platform_str}"),
        sep(),
        *[item for block in blocks for item in [discord.ui.TextDisplay(block), sep()]],
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="voicespy")
@founder_only()
async def cmd_voicespy(ctx: commands.Context):
    lines = []
    total_users = 0

    for vc in sorted(ctx.guild.voice_channels, key=lambda c: c.position):
        members = vc.members
        if not members:
            continue
        total_users += len(members)
        lines.append(f"**#{vc.name}** ({len(members)})")
        for m in members:
            flags = []
            if m.voice.self_mute or m.voice.mute:   flags.append("🔇")
            if m.voice.self_deaf or m.voice.deaf:   flags.append("🔕")
            if m.voice.self_stream:                  flags.append("📡")
            if m.voice.self_video:                   flags.append("📷")
            flag_str = " ".join(flags)

            # calculate time in vc if we have join time (not directly available, use bot's internal cache)
            roles = [r for r in m.roles if r.name != "@everyone"]
            top_role = roles[-1].name if roles else "none"
            lines.append(f"> `{m.name}` {flag_str} — top role: `{top_role}`")

    if not lines:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No one is in voice right now.")), delete_after=5)
        return

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## voice spy\n-# {ctx.guild.name} • {total_users} users in voice"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="lookup")
@founder_only()
async def cmd_lookup(ctx: commands.Context, user_id: str):
    try:
        uid = int(user_id)
    except ValueError:
        await ctx.send("Invalid ID.", delete_after=5)
        return

    # snowflake decode
    epoch      = 1420070400000
    ts_ms      = (uid >> 22) + epoch
    worker_id  = (uid & 0x3E0000) >> 17
    process_id = (uid & 0x1F000) >> 12
    increment  = uid & 0xFFF
    created_ts = ts_ms // 1000

    # hit undocumented user endpoint (works with user token)
    if USER_TOKEN:
        data = await user_get(f"/users/{uid}/profile", {"with_mutual_guilds": "true"})
    else:
        data = {}

    u           = data.get("user", {}) if "code" not in data else {}
    username    = u.get("username") or "unknown"
    global_name = u.get("global_name") or username
    avatar_hash = u.get("avatar")
    avatar_url  = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.{'gif' if avatar_hash and avatar_hash.startswith('a_') else 'png'}" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
    bot_flag    = u.get("bot", False)
    flags       = u.get("public_flags", 0)
    nitro       = NITRO_TYPES.get(u.get("premium_type", 0), "None") if u else "unknown"
    mutuals     = data.get("mutual_guilds", [])
    badges      = [BADGE_MAP.get(b["id"], b["id"]) for b in data.get("badges", [])]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {global_name}\n"
                f"-# `{uid}` • @{username}{' • 🤖 Bot' if bot_flag else ''}"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=avatar_url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Snowflake Decode**\n"
            f"> Created — <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"> Worker ID — `{worker_id}`\n"
            f"> Process ID — `{process_id}`\n"
            f"> Increment — `{increment}`\n"
            f"> Raw timestamp — `{ts_ms}ms`"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Profile**\n"
            f"> Nitro — {nitro}\n"
            f"> Public flags — `{flags}`\n"
            f"> Badges — {('  '.join(f'`{b}`' for b in badges)) or 'none'}\n"
            f"> Mutual servers — {len(mutuals)}"
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="inviteinfo")
@founder_only()
async def cmd_inviteinfo(ctx: commands.Context, code: str):
    code = code.split("/")[-1].strip()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/invites/{code}", {
        "with_counts": "true",
        "with_expiration": "true",
        "inputValue": code,
    })

    if "code" in data and data.get("code") != code:
        await ctx.send(f"API error: {data.get('message', str(data.get('code')))}", delete_after=5)
        return

    guild      = data.get("guild", {}) or {}
    channel    = data.get("channel", {}) or {}
    inviter    = data.get("inviter", {}) or {}

    guild_name     = guild.get("name", "unknown")
    guild_id       = guild.get("id", "?")
    guild_desc     = (guild.get("description") or "none")[:80]
    features       = guild.get("features", [])
    nsfw_level     = {0:"Default",1:"Explicit",2:"Safe",3:"Age Restricted"}.get(guild.get("nsfw_level",0),"?")
    verification   = {0:"None",1:"Low",2:"Medium",3:"High",4:"Highest"}.get(guild.get("verification_level",0),"?")
    premium_tier   = guild.get("premium_tier", 0)
    approx_members = data.get("approximate_member_count", "?")
    approx_online  = data.get("approximate_presence_count", "?")
    channel_name   = channel.get("name", "?")
    channel_type   = {0:"#",2:"🔊",4:"📁",5:"📢",13:"🎙️",15:"🏛️"}.get(channel.get("type",0),"?")
    inviter_name   = inviter.get("global_name") or inviter.get("username", "unknown")
    inviter_id     = inviter.get("id", "?")
    expires        = data.get("expires_at")
    expires_str    = f"<t:{int(__import__('datetime').datetime.fromisoformat(expires.rstrip('Z')).timestamp())}:R>" if expires else "never"
    max_uses       = data.get("max_uses") or "unlimited"
    uses           = data.get("uses", "?")
    max_age        = data.get("max_age", 0)
    temp           = data.get("temporary", False)
    vanity         = guild.get("vanity_url_code")

    features_str = "  ".join(f"`{f}`" for f in features[:8]) if features else "none"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## invite: discord.gg/{code}\n-# guild `{guild_id}`"),
        sep(),
        discord.ui.TextDisplay(
            f"**Server**\n"
            f"> Name — {guild_name}\n"
            f"> Description — {guild_desc}\n"
            f"> Members — **{approx_members}** ({approx_online} online)\n"
            f"> Boost tier — `{premium_tier}`\n"
            f"> Verification — `{verification}`\n"
            f"> NSFW level — `{nsfw_level}`\n"
            f"> Vanity — {f'`discord.gg/{vanity}`' if vanity else 'none'}"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Invite Details**\n"
            f"> Channel — {channel_type}{channel_name}\n"
            f"> Created by — {inviter_name} (`{inviter_id}`)\n"
            f"> Uses — {uses} / {max_uses}\n"
            f"> Expires — {expires_str}\n"
            f"> Max age — {f'{max_age}s' if max_age else 'permanent'}\n"
            f"> Temporary — {temp}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Guild Features** ({len(features)})\n> {features_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="webhooks")
@founder_only()
async def cmd_webhooks(ctx: commands.Context):
    try:
        hooks = await ctx.guild.webhooks()
    except discord.Forbidden:
        await ctx.send("Missing Manage Webhooks permission.", delete_after=5)
        return

    if not hooks:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No webhooks in this server.")), delete_after=5)
        return

    lines = []
    for h in hooks:
        channel_name = h.channel.name if h.channel else "deleted-channel"
        creator      = h.user.name if h.user else "unknown"
        hook_type    = {discord.WebhookType.incoming: "Incoming", discord.WebhookType.channel_follower: "Follower", discord.WebhookType.application: "Application"}.get(h.type, "?")
        lines.append(
            f"**{h.name}** — #{channel_name}\n"
            f"> ID `{h.id}` • type `{hook_type}` • created by `{creator}`\n"
            f"> URL: `{h.url}`"
        )

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## webhooks\n-# {ctx.guild.name} • {len(hooks)} webhook{'s' if len(hooks)!=1 else ''}"),
        sep(),
        discord.ui.TextDisplay("\n\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="guildinfo")
@founder_only()
async def cmd_guildinfo(ctx: commands.Context):
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/guilds/{ctx.guild.id}", {"with_counts": "true"})
    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    g = ctx.guild
    features     = data.get("features", [])
    max_members  = data.get("max_members", "?")
    max_presences= data.get("max_presences") or "default"
    system_flags = data.get("system_channel_flags", 0)
    mfa_level    = {0: "None", 1: "Elevated"}.get(data.get("mfa_level", 0), "?")
    default_notif= {0: "All Messages", 1: "Only Mentions"}.get(data.get("default_message_notifications", 0), "?")
    content_filter={0:"Disabled",1:"Members without roles",2:"All members"}.get(data.get("explicit_content_filter",0),"?")
    hub_type     = data.get("hub_type")
    nsfw_level   = {0:"Default",1:"Explicit",2:"Safe",3:"Age Restricted"}.get(data.get("nsfw_level",0),"?")
    created_ts   = int(discord.utils.snowflake_time(g.id).timestamp())
    locale       = data.get("preferred_locale", "?")
    vanity       = data.get("vanity_url_code")
    safety_alerts= data.get("safety_alerts_channel_id")

    owner        = await bot.fetch_user(g.owner_id) if g.owner_id else None
    owner_str    = f"{owner.name} (`{owner.id}`)" if owner else "unknown"

    features_str = "  ".join(f"`{f}`" for f in features[:10]) if features else "none"

    SYSCHAN_FLAGS = {1:"Suppress join notifs", 2:"Suppress boost notifs", 4:"Suppress tips", 8:"Suppress guild reminder notifs", 16:"Hide wave to new members"}
    syschan_list = [v for bit, v in SYSCHAN_FLAGS.items() if system_flags & bit] or ["none"]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {g.name}\n"
                f"-# `{g.id}` • created <t:{created_ts}:R>"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=g.icon.url if g.icon else "https://cdn.discordapp.com/embed/avatars/0.png")),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Overview**\n"
            f"> Owner — {owner_str}\n"
            f"> Members — {g.member_count} / {max_members}\n"
            f"> Boosts — {g.premium_subscription_count} (tier {g.premium_tier})\n"
            f"> Locale — `{locale}`\n"
            f"> MFA — `{mfa_level}`\n"
            f"> NSFW level — `{nsfw_level}`\n"
            f"> Hub type — `{hub_type}`\n"
            f"> Vanity — {f'`discord.gg/{vanity}`' if vanity else 'none'}"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Settings**\n"
            f"> Default notifications — `{default_notif}`\n"
            f"> Content filter — `{content_filter}`\n"
            f"> Max presences — `{max_presences}`\n"
            f"> Safety alerts channel — {f'<#{safety_alerts}>' if safety_alerts else 'none'}\n"
            f"> System channel flags — {', '.join(syschan_list)}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Features** ({len(features)})\n> {features_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="channelinfo")
@founder_only()
async def cmd_channelinfo(ctx: commands.Context, channel: discord.abc.GuildChannel = None):
    channel = channel or ctx.channel
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/channels/{channel.id}")
    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    created_ts   = int(discord.utils.snowflake_time(channel.id).timestamp())
    ch_type      = {0:"Text",1:"DM",2:"Voice",3:"Group DM",4:"Category",5:"Announcement",10:"Thread",11:"Public Thread",12:"Private Thread",13:"Stage",14:"Directory",15:"Forum",16:"Media"}.get(data.get("type",0),"?")
    topic        = (data.get("topic") or "none")[:100]
    slowmode     = data.get("rate_limit_per_user", 0)
    nsfw         = data.get("nsfw", False)
    position     = data.get("position", "?")
    parent_id    = data.get("parent_id")
    last_msg_id  = data.get("last_message_id")
    perms_count  = len(data.get("permission_overwrites", []))
    flags        = data.get("flags", 0)
    default_thread_slowmode = data.get("default_thread_rate_limit_per_user", 0)
    default_auto_archive = data.get("default_auto_archive_duration")

    last_msg_ts  = int(discord.utils.snowflake_time(int(last_msg_id)).timestamp()) if last_msg_id else None

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(
            f"## #{channel.name}\n"
            f"-# `{channel.id}` • type `{ch_type}` • position `{position}`"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Info**\n"
            f"> Created — <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"> Topic — {topic}\n"
            f"> NSFW — {nsfw}\n"
            f"> Slowmode — {slowmode}s\n"
            f"> Parent — {f'<#{parent_id}>' if parent_id else 'none'}\n"
            f"> Flags — `{flags}`\n"
            f"> Permission overwrites — {perms_count}"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Messages**\n"
            f"> Last message — {f'<t:{last_msg_ts}:R>' if last_msg_ts else 'unknown'}\n"
            f"> Thread auto-archive — {f'{default_auto_archive}m' if default_auto_archive else 'none'}\n"
            f"> Thread slowmode — {default_thread_slowmode}s"
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="roleinfo")
@founder_only()
async def cmd_roleinfo(ctx: commands.Context, *, role: discord.Role):
    created_ts = int(discord.utils.snowflake_time(role.id).timestamp())
    perms      = role.permissions
    perm_names = [name.replace("_", " ").title() for name, val in perms if val]

    PERM_CHUNKS = [perm_names[i:i+4] for i in range(0, len(perm_names), 4)]
    perm_str    = "\n".join("> " + "  ".join(f"`{p}`" for p in chunk) for chunk in PERM_CHUNKS) or "> none"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(
            f"## @{role.name}\n"
            f"-# `{role.id}` • position `{role.position}` • {len(role.members)} members"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Info**\n"
            f"> Created — <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"> Color — `#{role.color.value:06X}`\n"
            f"> Hoisted — {role.hoist}\n"
            f"> Mentionable — {role.mentionable}\n"
            f"> Managed — {role.managed}\n"
            f"> Raw flags — `{role.flags.value}`"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Permissions** ({len(perm_names)})\n{perm_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="snowflake")
@founder_only()
async def cmd_snowflake(ctx: commands.Context, snowflake_id: str):
    try:
        sid = int(snowflake_id)
    except ValueError:
        await ctx.send("Invalid snowflake.", delete_after=5)
        return

    epoch      = 1420070400000
    ts_ms      = (sid >> 22) + epoch
    worker_id  = (sid & 0x3E0000) >> 17
    process_id = (sid & 0x1F000) >> 12
    increment  = sid & 0xFFF
    created_ts = ts_ms // 1000

    import datetime
    dt = datetime.datetime.fromtimestamp(created_ts, tz=datetime.timezone.utc)

    # try to guess what it is based on age
    age_days = (discord.utils.utcnow().timestamp() - created_ts) / 86400

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## snowflake decode\n-# `{sid}`"),
        sep(),
        discord.ui.TextDisplay(
            f"**Timestamp**\n"
            f"> Discord epoch offset — `{ts_ms - epoch}ms`\n"
            f"> Unix timestamp — `{ts_ms}ms`\n"
            f"> Date — <t:{created_ts}:F>\n"
            f"> Relative — <t:{created_ts}:R>\n"
            f"> UTC — `{dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} UTC`"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Internal Fields**\n"
            f"> Worker ID — `{worker_id}`\n"
            f"> Process ID — `{process_id}`\n"
            f"> Increment — `{increment}`\n"
            f"> Age — `{age_days:.1f}` days"
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="perms")
@founder_only()
async def cmd_perms(ctx: commands.Context, member: discord.Member = None):
    member = member or ctx.author
    if not isinstance(member, discord.Member):
        member = ctx.guild.get_member(member.id)
    if not member:
        await ctx.send("Member not in this server.", delete_after=5)
        return

    perms       = member.guild_permissions
    perm_names  = [name.replace("_", " ").title() for name, val in perms if val]
    denied      = [name.replace("_", " ").title() for name, val in perms if not val]
    roles       = [r for r in reversed(member.roles) if r.name != "@everyone"]

    PERM_CHUNKS = [perm_names[i:i+3] for i in range(0, len(perm_names), 3)]
    perm_str    = "\n".join("> " + "  ".join(f"`{p}`" for p in chunk) for chunk in PERM_CHUNKS) or "> none"
    roles_str   = " ".join(r.mention for r in roles[:8]) if roles else "`none`"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## permissions\n"
                f"-# {member.name} • {len(perm_names)} granted • {len(denied)} denied"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=member.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"**Roles**\n> {roles_str}"),
        sep(),
        discord.ui.TextDisplay(f"**Granted ({len(perm_names)})**\n{perm_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


# OPSEC / Extra RE Commands

_cmd_log: list = []  # [(timestamp, user_id, user_name, command, guild)]

@bot.event
async def on_command(ctx):
    _cmd_log.append({
        "ts":      discord.utils.utcnow().timestamp(),
        "uid":     ctx.author.id,
        "name":    ctx.author.name,
        "cmd":     ctx.invoked_with,
        "guild":   ctx.guild.name if ctx.guild else "DM",
        "channel": ctx.channel.name if hasattr(ctx.channel, "name") else "DM",
    })
    if len(_cmd_log) > 200:
        _cmd_log.pop(0)


@bot.command(name="tokenlog")
@founder_only()
async def cmd_tokenlog(ctx: commands.Context, limit: int = 20):
    limit = min(max(limit, 1), 100)
    entries = _cmd_log[-limit:][::-1]
    if not entries:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No commands logged yet.")), delete_after=5)
        return

    lines = []
    for e in entries:
        ts   = int(e["ts"])
        lines.append(f"> <t:{ts}:t> `{e['cmd']}` — **{e['name']}** in #{e['channel']} ({e['guild']})")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## command audit log\n-# last {len(entries)} commands • {len(_cmd_log)} total logged"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="selfpurge")
@founder_only()
async def cmd_selfpurge(ctx: commands.Context, limit: int = 20):
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return
    limit = min(max(limit, 1), 100)

    import aiohttp as _aiohttp
    headers = {"Authorization": USER_TOKEN, "Content-Type": "application/json"}
    deleted = 0

    async with _aiohttp.ClientSession(headers=headers) as session:
        async with session.get(
            f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages",
            params={"limit": "100"},
        ) as resp:
            messages = await resp.json()

        if isinstance(messages, dict):
            await ctx.send(f"API error: {messages.get('message','?')}", delete_after=5)
            return

        me_data = await user_get("/users/@me")
        my_id   = me_data.get("id")

        for m in messages:
            if m.get("author", {}).get("id") == my_id and deleted < limit:
                async with session.delete(
                    f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages/{m['id']}"
                ) as dr:
                    if dr.status in (200, 204):
                        deleted += 1
                await asyncio.sleep(0.4)

    confirm = await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"Purged **{deleted}** of your messages in #{ctx.channel.name}."),
        accent_color=0x9B9B9B,
    ))
    await asyncio.sleep(5)
    await confirm.delete()


@bot.command(name="msgscan")
@founder_only()
async def cmd_msgscan(ctx: commands.Context, user: discord.User):
    member = ctx.guild.get_member(user.id)
    if not member:
        await ctx.send("User not in this server.", delete_after=5)
        return

    status_msg = await ctx.send(view=make_view(discord.ui.TextDisplay(f"Scanning messages for {user.name}...")))

    hour_counts   = [0] * 24
    channel_counts= {}
    word_freq     = {}
    lengths       = []
    total         = 0
    scanned_ch    = 0

    for channel in ctx.guild.text_channels:
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.read_message_history:
            continue
        scanned_ch += 1
        try:
            async for msg in channel.history(limit=200):
                if msg.author.id != user.id:
                    continue
                total += 1
                hour_counts[msg.created_at.hour] += 1
                channel_counts[channel.name] = channel_counts.get(channel.name, 0) + 1
                lengths.append(len(msg.content))
                for word in msg.content.lower().split():
                    if len(word) > 3 and word.isalpha():
                        word_freq[word] = word_freq.get(word, 0) + 1
        except (discord.Forbidden, discord.HTTPException):
            continue

    if total == 0:
        await status_msg.edit(view=make_view(discord.ui.TextDisplay("No messages found.")))
        return

    peak_hour    = hour_counts.index(max(hour_counts))
    avg_len      = int(sum(lengths) / len(lengths)) if lengths else 0
    top_channels = sorted(channel_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_words    = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:8]

    ch_lines   = "\n".join(f"> `#{ch}` — {n} msgs" for ch, n in top_channels)
    word_lines = "  ".join(f"`{w}`×{n}" for w, n in top_words)

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## message profile\n-# {user.name} • {total} msgs across {scanned_ch} channels"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Behavior**\n"
            f"> Total messages — **{total}**\n"
            f"> Avg length — **{avg_len}** chars\n"
            f"> Peak hour — **{peak_hour:02d}:00 UTC**"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Most Active Channels**\n{ch_lines}"),
        sep(),
        discord.ui.TextDisplay(f"**Top Words**\n> {word_lines}"),
        accent_color=0x9B9B9B,
    ))
    await status_msg.edit(view=view)


@bot.command(name="altscan")
@founder_only()
async def cmd_altscan(ctx: commands.Context, user: discord.User):
    member = ctx.guild.get_member(user.id)
    created_ts  = discord.utils.snowflake_time(user.id)
    now         = discord.utils.utcnow()
    age_days    = (now - created_ts).days

    flags = []
    score = 0

    if age_days < 30:
        flags.append(f"🚨 Account only **{age_days}d** old")
        score += 3
    elif age_days < 90:
        flags.append(f"⚠️ Account only **{age_days}d** old")
        score += 1

    if not user.avatar:
        flags.append("🚨 No avatar")
        score += 2

    default_name = user.name.startswith("user") or user.name.replace("_","").isdigit()
    if default_name:
        flags.append("⚠️ Default-style username")
        score += 1

    if member:
        joined_days = (now - member.joined_at).days if member.joined_at else 0
        join_gap    = (member.joined_at - created_ts).days if member.joined_at else 0
        role_count  = len([r for r in member.roles if r.name != "@everyone"])

        if role_count <= 1:
            flags.append(f"⚠️ Only **{role_count}** role(s)")
            score += 1
        if join_gap < 1:
            flags.append("🚨 Joined within minutes of account creation")
            score += 3
        elif join_gap < 7:
            flags.append(f"⚠️ Joined **{join_gap}d** after account creation")
            score += 1

        flags.append(f"ℹ️ In server for **{joined_days}d**")

        # check message count in this channel
        msg_count = 0
        try:
            async for m in ctx.channel.history(limit=500):
                if m.author.id == user.id:
                    msg_count += 1
        except Exception:
            pass
        if msg_count == 0:
            flags.append("⚠️ No messages in this channel")
            score += 1

    if score == 0:
        verdict = "✅ Looks clean"
        color   = 0x2ECC71
    elif score <= 3:
        verdict = "⚠️ Mildly suspicious"
        color   = 0xF1C40F
    elif score <= 6:
        verdict = "🚨 Likely alt"
        color   = 0xE67E22
    else:
        verdict = "🚨 Almost certainly an alt"
        color   = 0xE74C3C

    flag_text = "\n".join(f"> {f}" for f in flags) or "> nothing suspicious"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## alt scanner\n-# {user.name} • `{user.id}`"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url if user.avatar else discord.DefaultAvatar.red.url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"**Verdict: {verdict}**\n-# risk score: {score}/10"),
        sep(),
        discord.ui.TextDisplay(f"**Flags**\n{flag_text}"),
        accent_color=color,
    ))
    await ctx.send(view=view)


@bot.command(name="inviteaudit")
@founder_only()
async def cmd_inviteaudit(ctx: commands.Context):
    try:
        invites = await ctx.guild.invites()
    except discord.Forbidden:
        await ctx.send("Missing Manage Guild permission.", delete_after=5)
        return

    if not invites:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No active invites.")), delete_after=5)
        return

    now = discord.utils.utcnow()
    invites_sorted = sorted(invites, key=lambda i: i.uses or 0, reverse=True)

    suspicious = []
    normal     = []

    for inv in invites_sorted:
        creator  = inv.inviter.name if inv.inviter else "unknown"
        ch       = f"#{inv.channel.name}" if inv.channel else "?"
        uses     = inv.uses or 0
        max_uses = inv.max_uses or "∞"
        expires  = f"<t:{int(inv.expires_at.timestamp())}:R>" if inv.expires_at else "never"
        temp     = " `temp`" if inv.temporary else ""
        age_hrs  = (now - inv.created_at).total_seconds() / 3600 if inv.created_at else 0

        line = f"> `{inv.code}` by **{creator}** in {ch} — {uses}/{max_uses} uses • expires {expires}{temp}"

        # flag suspicious: high use rate, no expiry, temp membership
        sus_score = 0
        if uses > 50 and age_hrs < 24: sus_score += 2
        if inv.temporary: sus_score += 1
        if not inv.max_uses and uses > 100: sus_score += 1
        if inv.inviter is None: sus_score += 2

        if sus_score >= 2:
            suspicious.append(f"⚠️ {line}")
        else:
            normal.append(line)

    blocks = []
    if suspicious:
        blocks.append(discord.ui.TextDisplay(f"**Suspicious ({len(suspicious)})**\n" + "\n".join(suspicious)))
        blocks.append(sep())
    if normal:
        blocks.append(discord.ui.TextDisplay(f"**Normal ({len(normal)})**\n" + "\n".join(normal[:15])))
        blocks.append(sep())

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## invite audit\n-# {ctx.guild.name} • {len(invites)} invites"),
        sep(),
        *blocks,
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="ghostping")
@founder_only()
async def cmd_ghostping(ctx: commands.Context, user: discord.User):
    await ctx.message.delete()
    msg = await ctx.channel.send(f"<@{user.id}>")
    await msg.delete()


@bot.command(name="tokenchecker")
@founder_only()
async def cmd_tokenchecker(ctx: commands.Context, token: str):
    await ctx.message.delete()
    import base64, aiohttp as _aiohttp

    parts = token.strip().split(".")
    if len(parts) != 3:
        await ctx.send(view=make_view(discord.ui.TextDisplay("Invalid token format (expected 3 parts).")), delete_after=8)
        return

    try:
        uid_b64 = parts[0]
        pad     = uid_b64 + "=" * (-len(uid_b64) % 4)
        uid_str = base64.b64decode(pad).decode("utf-8")
        uid     = int(uid_str)
    except Exception:
        await ctx.send(view=make_view(discord.ui.TextDisplay("Could not decode token user ID.")), delete_after=8)
        return

    created_ts = int(discord.utils.snowflake_time(uid).timestamp())

    # validate token via API
    headers = {"Authorization": token.strip()}
    async with _aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            data    = await resp.json()
            valid   = resp.status == 200

    if valid:
        username = data.get("global_name") or data.get("username", "?")
        email    = data.get("email", "hidden")
        phone    = data.get("phone") or "none"
        mfa      = data.get("mfa_enabled", False)
        nitro    = NITRO_TYPES.get(data.get("premium_type", 0), "None")
        locale   = data.get("locale", "?")
        verified = data.get("verified", False)
        status_line = "✅ **VALID** — token is active"
    else:
        username = "unknown"
        email = phone = mfa = nitro = locale = verified = "—"
        status_line = f"❌ **INVALID** — {data.get('message', 'token rejected')}"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## token checker\n-# user ID `{uid}`"),
        sep(),
        discord.ui.TextDisplay(f"**Status**\n> {status_line}"),
        sep(),
        discord.ui.TextDisplay(
            f"**Decoded**\n"
            f"> User ID — `{uid}`\n"
            f"> Created — <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"> Username — {username}\n"
            f"> Nitro — {nitro}\n"
            f"> Email — {email}\n"
            f"> Phone — {phone}\n"
            f"> MFA — {mfa}\n"
            f"> Locale — {locale}\n"
            f"> Verified — {verified}"
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="gateway")
@founder_only()
async def cmd_gateway(ctx: commands.Context):
    ws        = bot.ws
    latency   = round(bot.latency * 1000, 2)
    session   = getattr(ws, "session_id", "unknown")
    seq       = getattr(ws, "sequence", "unknown")

    shard_id  = bot.shard_id
    shard_cnt = bot.shard_count

    resume_url = getattr(ws, "_resume_gateway_url", "hidden")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## gateway session\n-# live WebSocket state"),
        sep(),
        discord.ui.TextDisplay(
            f"**Connection**\n"
            f"> Latency — **{latency}ms**\n"
            f"> Session ID — `{session}`\n"
            f"> Sequence — `{seq}`\n"
            f"> Shard — `{shard_id}` / `{shard_cnt}`\n"
            f"> Resume URL — `{resume_url}`"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Bot**\n"
            f"> User — `{bot.user.name}#{bot.user.discriminator}`\n"
            f"> ID — `{bot.user.id}`\n"
            f"> Guilds — {len(bot.guilds)}\n"
            f"> Users cached — {len(bot.users)}\n"
            f"> Commands — {len(bot.commands)}"
        ),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="appinfo")
@founder_only()
async def cmd_appinfo(ctx: commands.Context, app_id: str):
    try:
        int(app_id)
    except ValueError:
        await ctx.send("Invalid app ID.", delete_after=5)
        return

    import aiohttp as _aiohttp
    async with _aiohttp.ClientSession() as session:
        async with session.get(f"https://discord.com/api/v10/applications/{app_id}/rpc") as resp:
            data = await resp.json()

    if "code" in data:
        await ctx.send(f"API error: {data.get('message', data['code'])}", delete_after=5)
        return

    name        = data.get("name", "?")
    desc        = (data.get("description") or "none")[:200]
    icon_hash   = data.get("icon")
    icon_url    = f"https://cdn.discordapp.com/app-icons/{app_id}/{icon_hash}.png" if icon_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
    flags       = data.get("flags", 0)
    tags        = data.get("tags", [])
    bot_pub     = data.get("bot_public", False)
    bot_req_gco = data.get("bot_require_code_grant", False)
    privacy_url = data.get("privacy_policy_url", "none")
    tos_url     = data.get("terms_of_service_url", "none")
    verify_key  = data.get("verify_key", "?")[:32] + "..."

    APP_FLAGS = {
        1<<6:  "Application Auto Moderation",
        1<<12: "Gateway Presence",
        1<<13: "Gateway Presence Limited",
        1<<14: "Gateway Guild Members",
        1<<15: "Gateway Guild Members Limited",
        1<<16: "Verification Pending",
        1<<17: "Embedded",
        1<<18: "Gateway Message Content",
        1<<19: "Gateway Message Content Limited",
        1<<23: "Application Commands Badge",
    }
    flag_list = [v for bit, v in APP_FLAGS.items() if flags & bit] or ["none"]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(f"## {name}\n-# `{app_id}` • flags `{flags}`"),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=icon_url)),
        ),
        sep(),
        discord.ui.TextDisplay(f"**Description**\n> {desc}"),
        sep(),
        discord.ui.TextDisplay(
            f"**Config**\n"
            f"> Public bot — {bot_pub}\n"
            f"> Requires OAuth grant — {bot_req_gco}\n"
            f"> Tags — {', '.join(f'`{t}`' for t in tags) or 'none'}\n"
            f"> Privacy URL — {privacy_url}\n"
            f"> ToS URL — {tos_url}\n"
            f"> Verify key — `{verify_key}`"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Flags** ({flags})\n> " + "\n> ".join(flag_list)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="guildwidget")
@founder_only()
async def cmd_guildwidget(ctx: commands.Context, guild_id: str):
    try:
        int(guild_id)
    except ValueError:
        await ctx.send("Invalid guild ID.", delete_after=5)
        return

    import aiohttp as _aiohttp
    async with _aiohttp.ClientSession() as session:
        async with session.get(f"https://discord.com/api/v10/guilds/{guild_id}/widget.json") as resp:
            data = await resp.json()

    if "code" in data:
        await ctx.send(f"Widget not enabled or guild not found: {data.get('message', data['code'])}", delete_after=5)
        return

    name         = data.get("name", "?")
    gid          = data.get("id", "?")
    invite_url   = data.get("instant_invite", "none")
    members      = data.get("members", [])
    channels     = data.get("channels", [])
    presence_cnt = data.get("presence_count", len(members))

    member_lines = []
    for m in members[:10]:
        status = m.get("status", "?")
        uname  = m.get("username", "?")
        act    = m.get("game", {}) or {}
        act_str = f" — playing **{act['name']}**" if act.get("name") else ""
        member_lines.append(f"> `{status}` **{uname}**{act_str}")

    ch_lines = "\n".join(f"> `{c['id']}` **{c['name']}**" for c in channels[:8]) or "> none"

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## {name}\n-# guild `{gid}` • {presence_cnt} online"),
        sep(),
        discord.ui.TextDisplay(f"**Invite**\n> {invite_url}"),
        sep(),
        discord.ui.TextDisplay(f"**Online Members ({len(members)})**\n" + ("\n".join(member_lines) or "> none")),
        sep(),
        discord.ui.TextDisplay(f"**Voice Channels ({len(channels)})**\n{ch_lines}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="nitrocheck")
@founder_only()
async def cmd_nitrocheck(ctx: commands.Context):
    boosters = sorted(
        [m for m in ctx.guild.members if m.premium_since],
        key=lambda m: m.premium_since,
    )
    if not boosters:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No boosters in this server.")), delete_after=5)
        return

    lines = []
    for m in boosters:
        ts = int(m.premium_since.timestamp())
        lines.append(f"> **{m.display_name}** (`{m.name}`) — boosting since <t:{ts}:D> (<t:{ts}:R>)")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## boosters\n-# {ctx.guild.name} • {len(boosters)} booster{'s' if len(boosters)!=1 else ''} • tier {ctx.guild.premium_tier}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="vanity")
@founder_only()
async def cmd_vanity(ctx: commands.Context, code: str):
    code = code.split("/")[-1].strip()
    if not USER_TOKEN:
        await ctx.send("USER_TOKEN not set.", delete_after=5)
        return

    data = await user_get(f"/invites/{code}", {"with_counts": "true", "with_expiration": "true"})
    if "code" in data and data.get("code") != code:
        await ctx.send(f"Vanity not found: {data.get('message', '?')}", delete_after=5)
        return

    guild    = data.get("guild", {}) or {}
    g_name   = guild.get("name", "?")
    g_id     = guild.get("id", "?")
    g_desc   = (guild.get("description") or "none")[:100]
    features = guild.get("features", [])
    tier     = guild.get("premium_tier", 0)
    verif    = {0:"None",1:"Low",2:"Medium",3:"High",4:"Highest"}.get(guild.get("verification_level",0),"?")
    online   = data.get("approximate_presence_count", "?")
    members  = data.get("approximate_member_count", "?")
    icon_hash= guild.get("icon")
    icon_url = f"https://cdn.discordapp.com/icons/{g_id}/{icon_hash}.{'gif' if icon_hash and icon_hash.startswith('a_') else 'png'}" if icon_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
    splash   = guild.get("splash")
    banner   = guild.get("banner")
    feat_str = "  ".join(f"`{f}`" for f in features[:8]) if features else "none"

    created_ts = int(discord.utils.snowflake_time(int(g_id)).timestamp()) if g_id != "?" else 0

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## discord.gg/{code}\n"
                f"-# guild `{g_id}` • created <t:{created_ts}:R>"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=icon_url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**{g_name}**\n"
            f"> {g_desc}\n"
            f"> Members — **{members}** ({online} online)\n"
            f"> Boost tier — `{tier}`\n"
            f"> Verification — `{verif}`\n"
            f"> Has splash — {bool(splash)}\n"
            f"> Has banner — {bool(banner)}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Features** ({len(features)})\n> {feat_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="flagdecode")
@founder_only()
async def cmd_flagdecode(ctx: commands.Context, flags: int, flag_type: str = "user"):
    USER_FLAGS = {
        1: "Discord Staff", 2: "Partnered Server Owner", 4: "HypeSquad Events",
        8: "Bug Hunter L1", 64: "HypeSquad Bravery", 128: "HypeSquad Brilliance",
        256: "HypeSquad Balance", 512: "Early Supporter", 1024: "Team User",
        4096: "Bug Hunter L2", 16384: "Verified Bot", 32768: "Early Verified Bot Dev",
        65536: "Discord Certified Moderator", 131072: "Bot HTTP Interactions Only",
        262144: "Spammer", 4194304: "Active Developer",
    }
    GUILD_FLAGS = {
        1: "Unavailable", 2: "Widget Enabled", 4: "Invite Splash",
        8: "VIP Regions", 16: "Vanity URL", 32: "Verified", 64: "Partnered",
        128: "Community", 256: "Commerce", 512: "News", 1024: "Discoverable",
        2048: "Featurable", 4096: "Animated Icon", 8192: "Banner",
        16384: "Staff", 65536: "Member Verification Gate", 131072: "Preview Enabled",
    }
    APP_FLAGS = {
        1<<6: "Auto Mod Rule", 1<<12: "Gateway Presence", 1<<13: "Gateway Presence Limited",
        1<<14: "Gateway Guild Members", 1<<15: "Gateway Guild Members Limited",
        1<<18: "Gateway Message Content", 1<<19: "Gateway Message Content Limited",
        1<<23: "App Commands Badge",
    }
    CHANNEL_FLAGS = {
        1: "Pinned (thread)", 2: "NSFW", 16: "Hide Media Download Options",
        32: "Active Thread", 1<<4: "Require Tag (forum)",
    }

    flag_map = {"user": USER_FLAGS, "guild": GUILD_FLAGS, "app": APP_FLAGS, "channel": CHANNEL_FLAGS}
    table    = flag_map.get(flag_type.lower(), USER_FLAGS)

    matched = [(bit, name) for bit, name in table.items() if flags & bit]
    unknown_bits = flags & ~sum(bit for bit, _ in matched)

    lines = [f"> `{bit}` ({bit.bit_length()-1}) — **{name}**" for bit, name in matched] or ["> no known flags set"]
    if unknown_bits:
        lines.append(f"> `{unknown_bits}` — unknown bits")

    binary_str = f"{flags:032b}"
    chunks     = [binary_str[i:i+8] for i in range(0, 32, 8)]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## flag decode\n-# `{flags}` (0x{flags:08X}) • type: `{flag_type}`"),
        sep(),
        discord.ui.TextDisplay(f"**Binary**\n> `{'  '.join(chunks)}`"),
        sep(),
        discord.ui.TextDisplay(f"**Matched Flags ({len(matched)})**\n" + "\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="recentjoins")
@founder_only()
async def cmd_recentjoins(ctx: commands.Context, limit: int = 15):
    limit   = min(max(limit, 1), 30)
    members = sorted(
        [m for m in ctx.guild.members if not m.bot and m.joined_at],
        key=lambda m: m.joined_at,
        reverse=True,
    )[:limit]

    lines = []
    for m in members:
        ts      = int(m.joined_at.timestamp())
        gap     = (m.joined_at - discord.utils.snowflake_time(m.id)).days
        flag    = " ⚠️" if gap < 7 else ""
        lines.append(f"> **{m.display_name}** — joined <t:{ts}:R> • acc age {gap}d{flag}")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## recent joins\n-# {ctx.guild.name} • last {len(members)} members"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


def _botlist_bot_view(bots: list, selected_id: int):
    b         = next((m for m in bots if m.id == selected_id), bots[0])
    joined_ts = int(b.joined_at.timestamp()) if b.joined_at else 0
    created_ts= int(discord.utils.snowflake_time(b.id).timestamp())
    perms     = b.guild_permissions

    danger = []
    if perms.administrator:   danger.append("`admin`")
    if perms.manage_guild:    danger.append("`manage_guild`")
    if perms.manage_roles:    danger.append("`manage_roles`")
    if perms.manage_webhooks: danger.append("`webhooks`")
    if perms.ban_members:     danger.append("`ban`")
    if perms.kick_members:    danger.append("`kick`")
    if perms.mention_everyone:danger.append("`mention_everyone`")
    if perms.manage_messages: danger.append("`manage_messages`")
    perm_str  = "  ".join(danger) if danger else "`no dangerous perms`"
    roles     = [r for r in b.roles if r.name != "@everyone"]
    roles_str = " ".join(r.mention for r in roles[:6]) if roles else "`none`"

    options = [
        discord.SelectOption(
            label=m.display_name[:25],
            value=str(m.id),
            default=(m.id == selected_id),
        )
        for m in bots[:25]
    ]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {b.display_name}\n"
                f"-# `{b.id}` • joined <t:{joined_ts}:R>"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=b.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"**Info**\n"
            f"> Created — <t:{created_ts}:D>\n"
            f"> Joined server — <t:{joined_ts}:D>\n"
            f"> Nick — `{b.nick or 'none'}`"
        ),
        sep(),
        discord.ui.TextDisplay(f"**Dangerous Perms**\n> {perm_str}"),
        sep(),
        discord.ui.TextDisplay(f"**Roles** ({len(roles)})\n> {roles_str}"),
        accent_color=0x9B9B9B,
    ))
    view.add_item(discord.ui.ActionRow(discord.ui.Select(
        custom_id="botlist_select",
        placeholder="Switch bot...",
        options=options,
    )))
    return view


@bot.command(name="botlist")
@founder_only()
async def cmd_botlist(ctx: commands.Context):
    bots = sorted([m for m in ctx.guild.members if m.bot], key=lambda m: m.joined_at or discord.utils.utcnow())
    if not bots:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No bots in this server.")), delete_after=5)
        return
    await ctx.send(view=_botlist_bot_view(bots, bots[0].id))


@bot.command(name="hide")
@founder_only()
async def cmd_hide(ctx: commands.Context):
    global _hide_mode
    _hide_mode = not _hide_mode
    await ctx.message.delete()
    state = "on" if _hide_mode else "off"
    confirm = await ctx.send(view=make_view(
        discord.ui.TextDisplay(f"Hide mode **{state}** — {'bot is now ignoring all non-founder commands and messages.' if _hide_mode else 'bot is back to normal.'}"),
        accent_color=0x2C2F33 if _hide_mode else 0x9B9B9B,
    ))
    await asyncio.sleep(5)
    await confirm.delete()




@bot.command(name="mutecheck")
@founder_only()
async def cmd_mutecheck(ctx: commands.Context):
    now     = discord.utils.utcnow()
    timed   = [m for m in ctx.guild.members if m.timed_out_until and m.timed_out_until > now]
    if not timed:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No members currently timed out.")), delete_after=5)
        return

    lines = []
    for m in sorted(timed, key=lambda x: x.timed_out_until):
        until_ts = int(m.timed_out_until.timestamp())
        lines.append(f"> **{m.display_name}** — expires <t:{until_ts}:R> (<t:{until_ts}:T>)")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## timed out\n-# {ctx.guild.name} • {len(timed)} member{'s' if len(timed)!=1 else ''}"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="permaudit")
@founder_only()
async def cmd_permaudit(ctx: commands.Context):
    danger_map = {}
    for m in ctx.guild.members:
        if m.bot:
            continue
        p = m.guild_permissions
        flags = []
        if p.administrator:    flags.append("admin")
        if p.ban_members:      flags.append("ban")
        if p.kick_members:     flags.append("kick")
        if p.manage_guild:     flags.append("manage_guild")
        if p.manage_roles:     flags.append("manage_roles")
        if p.manage_webhooks:  flags.append("webhooks")
        if p.mention_everyone: flags.append("mention_all")
        if p.manage_channels:  flags.append("manage_channels")
        if flags:
            danger_map[m] = flags

    if not danger_map:
        await ctx.send(view=make_view(discord.ui.TextDisplay("No members with dangerous permissions.")), delete_after=5)
        return

    sorted_members = sorted(danger_map.items(), key=lambda x: len(x[1]), reverse=True)
    lines = [
        f"> **{m.display_name}** — " + "  ".join(f"`{f}`" for f in flags)
        for m, flags in sorted_members[:20]
    ]

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## perm audit\n-# {ctx.guild.name} • {len(danger_map)} members with elevated perms"),
        sep(),
        discord.ui.TextDisplay("\n".join(lines)),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="dossier")
@founder_only()
async def cmd_dossier(ctx: commands.Context, user: discord.User):
    member     = ctx.guild.get_member(user.id)
    created_ts = int(discord.utils.snowflake_time(user.id).timestamp())
    age_days   = (discord.utils.utcnow() - discord.utils.snowflake_time(user.id)).days

    # profile via user token
    profile_data = {}
    if USER_TOKEN:
        profile_data = await user_get(f"/users/{user.id}/profile", {"with_mutual_guilds": "true"})
        if "code" in profile_data:
            profile_data = {}

    u           = profile_data.get("user", {})
    badges      = [BADGE_MAP.get(b["id"], b["id"]) for b in profile_data.get("badges", [])]
    bio         = _clean_bio(profile_data.get("user_profile", {}).get("bio") or "") or "none"
    nitro       = NITRO_TYPES.get(u.get("premium_type", 0), "None") if u else "unknown"
    mutuals     = profile_data.get("mutual_guilds", [])
    connections = profile_data.get("connected_accounts", [])
    badge_str   = "  ".join(f"`{b}`" for b in badges) if badges else "none"
    conn_str    = ", ".join(CONNECTED_ICONS.get(c["type"], c["type"]) for c in connections) or "none"

    # presence from cache
    cached    = _raw_presence_log.get(user.id, {})
    status    = cached.get("status", "unknown")
    acts      = cached.get("activities", [])
    act_lines = []
    for a in acts:
        if a.get("type") == 2: act_lines.append(f"Spotify: {a.get('details','?')}")
        elif a.get("type") == 0: act_lines.append(f"Playing: {a.get('name','?')}")
        elif a.get("type") == 4 and a.get("state"): act_lines.append(f"Status: {a.get('state')}")

    # member info
    joined_str   = f"<t:{int(member.joined_at.timestamp())}:R>" if member and member.joined_at else "not in server"
    roles        = [r.mention for r in reversed(member.roles) if r.name != "@everyone"] if member else []
    roles_str    = " ".join(roles[:5]) if roles else "none"
    boosting     = f"<t:{int(member.premium_since.timestamp())}:R>" if member and member.premium_since else "no"

    # alt score
    score = 0
    if age_days < 30:  score += 3
    elif age_days < 90: score += 1
    if not user.avatar: score += 2
    if member and member.joined_at:
        gap = (member.joined_at - discord.utils.snowflake_time(user.id)).days
        if gap < 1: score += 3
        elif gap < 7: score += 1
    alt_str = f"`{score}/10`" + (" ⚠️ likely alt" if score >= 4 else "")

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {user.display_name}\n"
                f"-# @{user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(discord.UnfurledMediaItem(url=user.display_avatar.url)),
        ),
        sep(),
        discord.ui.TextDisplay(
            f"> created <t:{created_ts}:D> ({age_days}d ago)  •  nitro {nitro}\n"
            f"> badges — {badge_str}\n"
            f"> connections — {conn_str}"
        ),
        sep(),
        discord.ui.TextDisplay(
            f"> status **{status.upper()}**" + (f"\n> " + "\n> ".join(act_lines) if act_lines else "")
        ),
        sep(),
        discord.ui.TextDisplay(
            f"> joined {joined_str}  •  boosting {boosting}\n"
            f"> {len(mutuals)} mutual servers  •  alt score {alt_str}\n"
            f"> bio — {bio}"
        ),
        sep(),
        discord.ui.TextDisplay(f"**roles**\n> {roles_str}"),
        accent_color=0x9B9B9B,
    ))
    await ctx.send(view=view)


@bot.command(name="r")
@founder_only()
async def give_role(ctx: commands.Context, *, role_name: str):
    await ctx.message.delete()
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if role is None:
        await ctx.send(f"no role found named `{role_name}`", delete_after=5)
        return
    try:
        await ctx.author.add_roles(role)
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"gave you **{role.name}**"), accent_color=0x57F287), delete_after=5)
    except discord.Forbidden:
        await ctx.send("missing permissions to assign that role.", delete_after=5)


@bot.command(name="unr")
@founder_only()
async def remove_role(ctx: commands.Context, *, role_name: str):
    await ctx.message.delete()
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if role is None:
        await ctx.send(f"no role found named `{role_name}`", delete_after=5)
        return
    try:
        await ctx.author.remove_roles(role)
        await ctx.send(view=make_view(discord.ui.TextDisplay(f"removed **{role.name}** from you"), accent_color=0xED4245), delete_after=5)
    except discord.Forbidden:
        await ctx.send("missing permissions to remove that role.", delete_after=5)


@bot.command(name="rf")
async def remove_founder(ctx: commands.Context, user: discord.User):
    if ctx.author.id != 878416460924465193:
        await ctx.message.delete()
        return
    await ctx.message.delete()
    if user.id not in FOUNDER_IDS:
        await ctx.send(f"{user.mention} is not a founder.", delete_after=5)
        return
    if user.id == 878416460924465193:
        await ctx.send("nice try lol", delete_after=5)
        return
    FOUNDER_IDS.discard(user.id)
    await db_remove_whitelist(user.id)
    await ctx.send(view=make_view(discord.ui.TextDisplay(f"removed **{user}** from founder."), accent_color=0xED4245), delete_after=5)


bot.run(TOKEN)
