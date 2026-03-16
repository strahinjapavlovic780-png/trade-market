

import discord
from discord.ext import commands
import os
import json
import io
import re
from datetime import datetime, timezone

VOUCH_FILE = "vouches.json"
CONFIG_FILE = "config.json"
PURPLE = discord.Color.purple()
SERVER_NAME = "Trade Hub Official"
LOG_CHANNEL_NAME = "mod-logs"
COOLDOWN = 300

DEFAULT_CONFIG = {
    "MM_ROLE_ID": None,
    "MEMBER_ROLE_ID": None,
    "FOUNDER_ROLE_ID": None,
    "STAFF_CHANNEL_ID": None,
    "MERCY_ROLE_ID": None,
    "TICKET_CATEGORY_ID": None,
    "STAFF_ROLE_ID": None,
    "LEAD_ROLE_ID": None,
    "EXECUTIVE_ROLE_ID": None,
    "VICE_PRESIDENT_ROLE_ID": None,
    "OWNER_ROLE_ID": None,
    "WELCOME_CHANNEL_ID": None,
    "INVITE_LOG_CHANNEL_ID": None,
    "VERIFIED_ROLE_ID": None
}

if not os.path.exists(VOUCH_FILE):
    with open(VOUCH_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)


def load_vouches():
    with open(VOUCH_FILE, "r") as f:
        return json.load(f)


def save_vouches(data):
    with open(VOUCH_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_config():
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)

    changed = False
    for key, value in DEFAULT_CONFIG.items():
        if key not in data:
            data[key] = value
            changed = True

    if changed:
        save_config(data)

    return data


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_cfg(key):
    return load_config().get(key)


def set_cfg(key, value):
    data = load_config()
    data[key] = value
    save_config(data)


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.invites = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

warn_data = {}
invite_cache = {}
ticket_data = {}
command_cooldowns = {}


def role_id(key):
    return get_cfg(key)


def channel_id(key):
    return get_cfg(key)


def has_role_id(member: discord.Member, rid: int | None):
    if rid is None:
        return False
    return any(role.id == rid for role in member.roles)


def has_any_role(member: discord.Member, *role_ids):
    valid_ids = [rid for rid in role_ids if rid is not None]
    return any(role.id in valid_ids for role in member.roles)


def is_owner_bypass(member: discord.Member):
    owner_role_id = role_id("OWNER_ROLE_ID")
    return has_any_role(member, owner_role_id)


def higher_role(ctx, member):
    return member.top_role >= ctx.author.top_role


def check_command_cooldown(user_id: int, command_name: str, seconds: int = 300):
    now = datetime.now(timezone.utc).timestamp()
    key = f"{user_id}:{command_name}"

    last_used = command_cooldowns.get(key)
    if last_used is None:
        command_cooldowns[key] = now
        return True, 0

    remaining = seconds - (now - last_used)
    if remaining > 0:
        return False, int(remaining)

    command_cooldowns[key] = now
    return True, 0


def is_ticket_channel(channel: discord.TextChannel):
    ticket_category_id = channel_id("TICKET_CATEGORY_ID")
    if ticket_category_id is not None and channel.category is not None:
        return channel.category.id == ticket_category_id

    return channel.category is not None and channel.category.name == "══「 🎫 TICKETS 」══"


def extract_member_from_input(guild: discord.Guild, raw_value: str):
    raw_value = raw_value.strip()

    mention_match = re.match(r"<@!?(\d+)>", raw_value)
    if mention_match:
        member = guild.get_member(int(mention_match.group(1)))
        if member:
            return member

    if raw_value.isdigit():
        member = guild.get_member(int(raw_value))
        if member:
            return member

    lowered = raw_value.lower()
    for member in guild.members:
        if member.name.lower() == lowered or member.display_name.lower() == lowered:
            return member

    return None


def founder_or_bootstrap():
    async def predicate(ctx):
        founder_role_id = role_id("FOUNDER_ROLE_ID")

        if founder_role_id is None:
            if ctx.author.id == ctx.guild.owner_id:
                return True
            await ctx.send("❌ Founder role is not set yet. Only the server owner can bootstrap it with `$setfounderrole <id>`.")
            return False

        if founder_role_id not in [role.id for role in ctx.author.roles]:
            await ctx.send("❌ Only Founder can use this command.")
            return False

        return True
    return commands.check(predicate)


def is_mm():
    async def predicate(ctx):
        mm_role_id = role_id("MM_ROLE_ID")
        if mm_role_id is None:
            await ctx.send("❌ MM role is not set. Use `$setmmrole <id>` first.")
            return False

        if mm_role_id not in [role.id for role in ctx.author.roles]:
            await ctx.send("❌ You are not allowed to use this command.")
            return False
        return True
    return commands.check(predicate)


async def get_log_channel(guild):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    if channel is None:
        executive_role_id = role_id("EXECUTIVE_ROLE_ID")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }

        executive_role = guild.get_role(executive_role_id) if executive_role_id else None
        if executive_role:
            overwrites[executive_role] = discord.PermissionOverwrite(view_channel=True)

        channel = await guild.create_text_channel(
            LOG_CHANNEL_NAME,
            overwrites=overwrites
        )

    return channel


async def save_ticket_transcript(channel):
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        created = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{message.author} ({message.author.id})"
        content = message.content if message.content else "[No text content]"

        if message.attachments:
            attachment_urls = "\n".join(att.url for att in message.attachments)
            content += f"\n[Attachments]\n{attachment_urls}"

        messages.append(f"[{created}] {author}: {content}")

    transcript_text = "\n".join(messages) if messages else "No messages in this ticket."
    return io.BytesIO(transcript_text.encode("utf-8"))


async def apply_claim_permissions(channel: discord.TextChannel, claimer: discord.Member):
    data = ticket_data.get(channel.id)
    if not data:
        return False, "❌ Ticket data not found for this channel."

    guild = channel.guild
    mm_role_id = role_id("MM_ROLE_ID")
    mm_role = guild.get_role(mm_role_id) if mm_role_id else None
    creator = guild.get_member(data["creator_id"])
    other_user = guild.get_member(data["other_user_id"]) if data.get("other_user_id") else None

    if data.get("claimer_id"):
        return False, "❌ Ticket already claimed."

    data["claimer_id"] = claimer.id

    if mm_role:
        await channel.set_permissions(mm_role, view_channel=False)

    if creator:
        await channel.set_permissions(
            creator,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    if other_user:
        await channel.set_permissions(
            other_user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    await channel.set_permissions(
        claimer,
        view_channel=True,
        send_messages=True,
        read_message_history=True
    )

    return True, None


async def apply_unclaim_permissions(channel: discord.TextChannel):
    data = ticket_data.get(channel.id)
    if not data:
        return False, "❌ Ticket data not found for this channel."

    guild = channel.guild
    mm_role_id = role_id("MM_ROLE_ID")
    mm_role = guild.get_role(mm_role_id) if mm_role_id else None
    creator = guild.get_member(data["creator_id"])
    other_user = guild.get_member(data["other_user_id"]) if data.get("other_user_id") else None
    claimer = guild.get_member(data["claimer_id"]) if data.get("claimer_id") else None

    if not data.get("claimer_id"):
        return False, "❌ This ticket is not claimed."

    data["claimer_id"] = None

    if mm_role:
        await channel.set_permissions(
            mm_role,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    if creator:
        await channel.set_permissions(
            creator,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    if other_user:
        await channel.set_permissions(
            other_user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    if claimer:
        await channel.set_permissions(claimer, overwrite=None)

    return True, None


def format_target(guild: discord.Guild, value, kind: str):
    if value is None:
        return "`Not Set`"

    if kind == "role":
        role = guild.get_role(value)
        return role.mention if role else f"`{value}` (deleted role)"
    if kind == "channel":
        channel = guild.get_channel(value)
        return channel.mention if channel else f"`{value}` (deleted channel)"
    if kind == "category":
        category = guild.get_channel(value)
        return category.mention if category else f"`{value}` (deleted category)"

    return f"`{value}`"


async def send_set_success(ctx, title: str, key: str, value: int, kind: str):
    set_cfg(key, value)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Setting Updated",
        description=(
            f"**{title}** has been updated successfully.\n\n"
            f"**New Value:** {format_target(ctx.guild, value, kind)}\n"
            f"**Raw ID:** `{value}`"
        ),
        color=PURPLE
    )
    embed.set_footer(text=f"{SERVER_NAME} | Configuration System")
    await ctx.send(embed=embed)


# ================= PANEL SELECT =================

class MMSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🎮In Game Items"),
            discord.SelectOption(label="🪙Crypto"),
            discord.SelectOption(label="💳Paypal"),
        ]

        super().__init__(
            placeholder="Select trade type below",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="mm_select_trade_type"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MMModal(self.values[0]))


class MMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MMSelect())


class MMModal(discord.ui.Modal):
    def __init__(self, trade_type):
        super().__init__(title="Middleman Ticket")

        self.trade_type = trade_type

        self.other_user = discord.ui.TextInput(
            label="Other User (mention or name)",
            required=True
        )

        self.trade_details = discord.ui.TextInput(
            label="Trade Details",
            style=discord.TextStyle.paragraph,
            required=True
        )

        self.agreement = discord.ui.TextInput(
            label="Do both users agree?",
            placeholder="Type YES if both agreed",
            required=True
        )

        self.add_item(self.other_user)
        self.add_item(self.trade_details)
        self.add_item(self.agreement)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        config = load_config()
        ticket_category_id = config.get("TICKET_CATEGORY_ID")

        if ticket_category_id is None:
            category = await guild.create_category("══「 🎫 TICKETS 」══")
            config["TICKET_CATEGORY_ID"] = category.id
            save_config(config)
        else:
            category = guild.get_channel(ticket_category_id)
            if category is None:
                category = await guild.create_category("══「 🎫 TICKETS 」══")
                config["TICKET_CATEGORY_ID"] = category.id
                save_config(config)

        mm_role_id = config.get("MM_ROLE_ID")
        mm_role = guild.get_role(mm_role_id) if mm_role_id else None
        other_member = extract_member_from_input(guild, self.other_user.value)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
        }

        if other_member:
            overwrites[other_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        if mm_role:
            overwrites[mm_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        channel = await guild.create_text_channel(
            name=f"mm-{interaction.user.name}".lower().replace(" ", "-"),
            category=category,
            overwrites=overwrites
        )

        ticket_data[channel.id] = {
            "creator_id": interaction.user.id,
            "other_user_id": other_member.id if other_member else None,
            "claimer_id": None,
            "trade_type": self.trade_type,
            "trade_details": self.trade_details.value,
            "agreement": self.agreement.value
        }

        other_user_text = other_member.mention if other_member else self.other_user.value

        ticket_embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | New Middleman Ticket",
            description=(
                "# New Ticket Created\n"
                "A new **middleman request** has been submitted.\n\n"
                "## Ticket Information\n"
                f"**Trade Type:** {self.trade_type}\n"
                f"**Other User:** {other_user_text}\n"
                f"**Agreement:** {self.agreement.value}\n\n"
                "## Trade Details\n"
                f"{self.trade_details.value}\n\n"
                "## Status\n"
                "**Waiting for a Middleman to claim this ticket.**"
            ),
            color=PURPLE
        )

        ticket_embed.set_footer(text=f"{SERVER_NAME} | Ticket System")

        mention_parts = [interaction.user.mention]
        if other_member:
            mention_parts.append(other_member.mention)
        if mm_role:
            mention_parts.append(mm_role.mention)

        await channel.send(
            content=" ".join(mention_parts),
            embed=ticket_embed,
            view=TicketButtons()
        )

        if other_member:
            await interaction.response.send_message(
                f"✅ Your ticket has been created: {channel.mention}\n✅ {other_member.mention} was automatically added.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Your ticket has been created: {channel.mention}\n⚠️ I could not auto-add the other user. Use a proper mention like `@user` next time.",
                ephemeral=True
            )


# ================= BUTTONS =================

class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✔️Claim", style=discord.ButtonStyle.green, custom_id="ticket_claim_btn")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        mm_role_id = role_id("MM_ROLE_ID")
        if mm_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can claim tickets.",
                ephemeral=True
            )

        success, error = await apply_claim_permissions(interaction.channel, interaction.user)
        if not success:
            return await interaction.response.send_message(error, ephemeral=True)

        claimed_embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Ticket Claimed",
            description=(
                "# Ticket Claimed\n"
                f"This ticket has been claimed by {interaction.user.mention}.\n\n"
                "## Status\n"
                "**Other middlemen can no longer view it.**"
            ),
            color=PURPLE
        )

        claimed_embed.set_footer(text=f"{SERVER_NAME} | Ticket System")
        await interaction.response.send_message(embed=claimed_embed)

    @discord.ui.button(label="🔓Unclaim", style=discord.ButtonStyle.secondary, custom_id="ticket_unclaim_btn")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        mm_role_id = role_id("MM_ROLE_ID")
        owner_role_id = role_id("OWNER_ROLE_ID")

        if mm_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can unclaim tickets.",
                ephemeral=True
            )

        data = ticket_data.get(interaction.channel.id)
        if not data:
            return await interaction.response.send_message(
                "❌ Ticket data not found.",
                ephemeral=True
            )

        if data.get("claimer_id") != interaction.user.id and owner_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "❌ Only the claimer or owner can unclaim this ticket.",
                ephemeral=True
            )

        success, error = await apply_unclaim_permissions(interaction.channel)
        if not success:
            return await interaction.response.send_message(error, ephemeral=True)

        embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Ticket Unclaimed",
            description=(
                "# 🔓 Ticket Unclaimed\n\n"
                f"{interaction.user.mention} has unclaimed this ticket.\n\n"
                "## Status\n"
                "**Another MM can now claim it.**"
            ),
            color=PURPLE
        )
        embed.set_footer(text=f"{SERVER_NAME} | Ticket System")

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="➕Add User", style=discord.ButtonStyle.blurple, custom_id="ticket_add_user_btn")
    async def add_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        mm_role_id = role_id("MM_ROLE_ID")
        if mm_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can use this.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Use command: `$add @user`",
            ephemeral=True
        )

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.gray, custom_id="ticket_remove_user_btn")
    async def remove_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        mm_role_id = role_id("MM_ROLE_ID")
        if mm_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can use this.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Use command: `$remove @user`",
            ephemeral=True
        )

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket_close_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        mm_role_id = role_id("MM_ROLE_ID")
        if mm_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can close tickets.",
                ephemeral=True
            )

        log_channel = await get_log_channel(interaction.guild)
        transcript_file = await save_ticket_transcript(interaction.channel)

        data = ticket_data.get(interaction.channel.id, {})
        creator = interaction.guild.get_member(data.get("creator_id")) if data.get("creator_id") else None

        close_embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Ticket Closed",
            description=(
                f"**Channel:** {interaction.channel.name}\n"
                f"**Closed by:** {interaction.user.mention}\n"
                f"**Created by:** {creator.mention if creator else 'Unknown'}"
            ),
            color=PURPLE
        )
        close_embed.set_footer(text=f"{SERVER_NAME} | Ticket Logs")

        if log_channel:
            await log_channel.send(
                embed=close_embed,
                file=discord.File(transcript_file, filename=f"{interaction.channel.name}-transcript.txt")
            )

        ticket_data.pop(interaction.channel.id, None)

        await interaction.response.send_message("Closing ticket...")
        await interaction.channel.delete()


# ================= FEE SYSTEM =================

class CustomFeeModal(discord.ui.Modal, title="Custom Fee Split"):
    split = discord.ui.TextInput(
        label="Enter split (example: 60-40)",
        placeholder="Example: 70-30",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            parts = self.split.value.replace(" ", "").split("-")
            p1 = int(parts[0])
            p2 = int(parts[1])

            if p1 + p2 != 100:
                await interaction.response.send_message(
                    "Percentages must equal 100.",
                    ephemeral=True
                )
                return

        except Exception:
            await interaction.response.send_message(
                "Invalid format. Use example: 60-40",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Fee Agreement – {p1}/{p2} Split",
            description=(
                "# Middleman Fee Agreement\n\n"
                "Both traders have agreed to split the middleman fee.\n\n"
                f"**User 1 will pay {p1}% of the fee.**\n"
                f"**User 2 will pay {p2}% of the fee.**\n\n"
                "This ensures fairness and equal responsibility between both parties.\n\n"
                "Once payment is completed, the middleman will proceed with the secured transaction."
            ),
            color=PURPLE
        )
        embed.set_footer(text=f"{SERVER_NAME} | Fee System")

        await interaction.response.send_message(embed=embed)


class FeeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="50% / 50%", style=discord.ButtonStyle.primary, custom_id="fee_split_50_50")
    async def split_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Fee Agreement – 50/50 Split",
            description=(
                "# Middleman Fee Agreement\n\n"
                "Both traders have agreed to split the middleman fee equally.\n\n"
                "**Both users will pay 50% of the fee each.**\n\n"
                "This ensures fairness and equal responsibility between both parties.\n\n"
                "Once payment is completed, the middleman will proceed with the secured transaction."
            ),
            color=PURPLE
        )
        embed.set_footer(text=f"{SERVER_NAME} | Fee System")

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="100% One User Pays", style=discord.ButtonStyle.red, custom_id="fee_full_payment")
    async def full_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Fee Agreement – Full Payment",
            description=(
                "# Middleman Fee Agreement\n\n"
                f"{interaction.user.mention} has agreed to cover the full middleman fee.\n\n"
                f"**{interaction.user.mention} will pay 100% of the fees to the middleman.**\n\n"
                "The second trader is not responsible for any service fee in this transaction.\n\n"
                "Once the fee is confirmed, the trade will proceed under full protection."
            ),
            color=PURPLE
        )
        embed.set_footer(text=f"{SERVER_NAME} | Fee System")

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Custom Split", style=discord.ButtonStyle.secondary, custom_id="fee_custom_split")
    async def custom_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomFeeModal())


class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green, emoji="✅", custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        verified_role_id = role_id("VERIFIED_ROLE_ID")
        role = interaction.guild.get_role(verified_role_id) if verified_role_id else None

        if role is None:
            return await interaction.response.send_message(
                "❌ Verified Trader role not found.",
                ephemeral=True
            )

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                "❌ You are already verified.",
                ephemeral=True
            )

        await interaction.user.add_roles(role)

        embed = discord.Embed(
            title=f"💜 {SERVER_NAME} | Verification Complete",
            description=(
                f"**{interaction.user.mention} is now a** **Verified Trader**.\n\n"
                "**You now have access to the server.**"
            ),
            color=PURPLE
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ================= SET COMMANDS =================

@bot.command()
@founder_or_bootstrap()
async def setmmrole(ctx, role: discord.Role):
    await send_set_success(ctx, "MM Role", "MM_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setmemberrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Member Role", "MEMBER_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setfounderrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Founder Role", "FOUNDER_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setstaffchannel(ctx, channel: discord.TextChannel):
    await send_set_success(ctx, "Staff Channel", "STAFF_CHANNEL_ID", channel.id, "channel")


@bot.command()
@founder_or_bootstrap()
async def setmercyrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Mercy Role", "MERCY_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setticketcategory(ctx, category: discord.CategoryChannel):
    await send_set_success(ctx, "Ticket Category", "TICKET_CATEGORY_ID", category.id, "category")


@bot.command()
@founder_or_bootstrap()
async def setstaffrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Staff Role", "STAFF_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setleadrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Lead Role", "LEAD_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setexecutiverole(ctx, role: discord.Role):
    await send_set_success(ctx, "Executive Role", "EXECUTIVE_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setvicepresidentrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Vice President Role", "VICE_PRESIDENT_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setownerrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Owner Role", "OWNER_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setwelcomechannel(ctx, channel: discord.TextChannel):
    await send_set_success(ctx, "Welcome Channel", "WELCOME_CHANNEL_ID", channel.id, "channel")


@bot.command()
@founder_or_bootstrap()
async def setinvitelogchannel(ctx, channel: discord.TextChannel):
    await send_set_success(ctx, "Invite Log Channel", "INVITE_LOG_CHANNEL_ID", channel.id, "channel")


@bot.command()
@founder_or_bootstrap()
async def setverifiedrole(ctx, role: discord.Role):
    await send_set_success(ctx, "Verified Role", "VERIFIED_ROLE_ID", role.id, "role")


@bot.command()
@founder_or_bootstrap()
async def setcheck(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Configuration Check",
        description="Here is the current setup status for the bot.",
        color=PURPLE
    )

    embed.add_field(name="MM Role", value=format_target(ctx.guild, role_id("MM_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Member Role", value=format_target(ctx.guild, role_id("MEMBER_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Founder Role", value=format_target(ctx.guild, role_id("FOUNDER_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Staff Channel", value=format_target(ctx.guild, channel_id("STAFF_CHANNEL_ID"), "channel"), inline=False)
    embed.add_field(name="Mercy Role", value=format_target(ctx.guild, role_id("MERCY_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Ticket Category", value=format_target(ctx.guild, channel_id("TICKET_CATEGORY_ID"), "category"), inline=False)
    embed.add_field(name="Staff Role", value=format_target(ctx.guild, role_id("STAFF_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Lead Role", value=format_target(ctx.guild, role_id("LEAD_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Executive Role", value=format_target(ctx.guild, role_id("EXECUTIVE_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Vice President Role", value=format_target(ctx.guild, role_id("VICE_PRESIDENT_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Owner Role", value=format_target(ctx.guild, role_id("OWNER_ROLE_ID"), "role"), inline=False)
    embed.add_field(name="Welcome Channel", value=format_target(ctx.guild, channel_id("WELCOME_CHANNEL_ID"), "channel"), inline=False)
    embed.add_field(name="Invite Log Channel", value=format_target(ctx.guild, channel_id("INVITE_LOG_CHANNEL_ID"), "channel"), inline=False)
    embed.add_field(name="Verified Role", value=format_target(ctx.guild, role_id("VERIFIED_ROLE_ID"), "role"), inline=False)

    embed.set_footer(text=f"{SERVER_NAME} | Configuration System")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def adminhelp(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Admin Help Menu",
        description=(
            "# Admin Commands\n\n"
            "Below are the configuration and management commands for the bot."
        ),
        color=PURPLE
    )

    embed.add_field(
        name="⚙️ Setup Commands",
        value=(
            "`$setmmrole @role`\n"
            "`$setmemberrole @role`\n"
            "`$setfounderrole @role`\n"
            "`$setstaffchannel #channel`\n"
            "`$setmercyrole @role`\n"
            "`$setticketcategory category`\n"
            "`$setstaffrole @role`\n"
            "`$setleadrole @role`\n"
            "`$setexecutiverole @role`\n"
            "`$setvicepresidentrole @role`\n"
            "`$setownerrole @role`\n"
            "`$setwelcomechannel #channel`\n"
            "`$setinvitelogchannel #channel`\n"
            "`$setverifiedrole @role`"
        ),
        inline=False
    )

    embed.add_field(
        name="📋 Utility",
        value=(
            "`$setcheck` — Shows what is set and what is not\n"
            "`$panel` — Sends the middleman panel\n"
            "`$verify` — Sends verification embed\n"
            "`$help` — Main help menu"
        ),
        inline=False
    )

    embed.set_footer(text=f"{SERVER_NAME} | Admin Help")
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    await ctx.send(embed=embed)


# ================= COMMANDS =================

@bot.command()
async def add(ctx, member: discord.Member):
    if not is_ticket_channel(ctx.channel):
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    mm_role_id = role_id("MM_ROLE_ID")
    if mm_role_id not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can use this command.")

    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)

    data = ticket_data.get(ctx.channel.id)
    if data and not data.get("other_user_id"):
        data["other_user_id"] = member.id

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Added",
        description=(
            "# ✅ User Successfully Added\n\n"
            f"{member.mention} has been added to the ticket and can now participate in the trade."
        ),
        color=PURPLE
    )
    embed.set_footer(text=f"{SERVER_NAME} | Ticket System")

    await ctx.send(embed=embed)


@bot.command()
async def remove(ctx, member: discord.Member):
    if not is_ticket_channel(ctx.channel):
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    mm_role_id = role_id("MM_ROLE_ID")
    if mm_role_id not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can use this command.")

    data = ticket_data.get(ctx.channel.id)
    if data:
        if member.id == data.get("creator_id"):
            return await ctx.send("❌ You cannot remove the ticket creator.")
        if member.id == data.get("claimer_id"):
            return await ctx.send("❌ You cannot remove the current claimer with this command.")

        if member.id == data.get("other_user_id"):
            data["other_user_id"] = None

    await ctx.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Removed",
        description=(
            "# ❌ User Removed\n\n"
            f"{member.mention} has been removed from the ticket."
        ),
        color=PURPLE
    )
    embed.set_footer(text=f"{SERVER_NAME} | Ticket System")

    await ctx.send(embed=embed)

@bot.command()
async def claim(ctx):
    if not is_ticket_channel(ctx.channel):
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    mm_role_id = role_id("MM_ROLE_ID")
    if mm_role_id not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can claim tickets.")

    success, error = await apply_claim_permissions(ctx.channel, ctx.author)

    if not success:
        return await ctx.send(error)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Ticket Claimed",
        description=(
            "# Ticket Claimed\n"
            f"This ticket has been claimed by {ctx.author.mention}.\n\n"
            "## Status\n"
            "**Other middlemen can no longer view it.**"
        ),
        color=PURPLE
    )

    embed.set_footer(text=f"{SERVER_NAME} | Ticket System")

    await ctx.send(embed=embed)


@bot.command()
async def vouch(ctx, member: discord.Member):
    if member == ctx.author:
        return await ctx.send("❌ You cannot vouch for yourself.")

    vouches_data = load_vouches()
    user_id = str(member.id)

    vouches_data[user_id] = vouches_data.get(user_id, 0) + 1
    save_vouches(vouches_data)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | New Vouch",
        description=(
            "# ⭐ New Vouch\n\n"
            f"{ctx.author.mention} vouched for {member.mention}.\n\n"
            "## Current Total\n"
            f"They now have **{vouches_data[user_id]}** vouches."
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{ctx.guild.name} | Vouch System")

    await ctx.send(embed=embed)


@bot.command()
@is_mm()
async def topvouches(ctx):
    vouches_data = load_vouches()

    if not vouches_data:
        return await ctx.send("❌ No vouches found yet.")

    sorted_vouches = sorted(vouches_data.items(), key=lambda x: x[1], reverse=True)[:10]

    lines = []
    for index, (user_id, count) in enumerate(sorted_vouches, start=1):
        member = ctx.guild.get_member(int(user_id))
        name = member.mention if member else f"<@{user_id}>"
        lines.append(f"**{index}.** {name} — **{count}** vouches")

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Top Vouches",
        description="# 🏆 Top Trusted Members\n\n" + "\n".join(lines),
        color=PURPLE
    )

    embed.set_footer(text=f"{ctx.guild.name} | Vouch Leaderboard")
    await ctx.send(embed=embed)


# ================= MODERATION =================

@bot.command()
async def purge(ctx, amount: int):
    lead_role_id = role_id("LEAD_ROLE_ID")
    if not has_role_id(ctx.author, lead_role_id):
        return await ctx.send("❌ Only Lead can use this command.")

    await ctx.channel.purge(limit=amount + 1)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Messages Purged",
        description=(
            f"**Deleted:** {amount} messages\n"
            f"**Channel:** {ctx.channel.mention}\n"
            f"**Moderator:** {ctx.author.mention}"
        ),
        color=PURPLE
    )
    embed.set_footer(text=f"{SERVER_NAME} | Moderation Logs")

    msg = await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=discord.Embed(
            title=f"💜 {SERVER_NAME} | Purge Log",
            description=(
                f"**Moderator:** {ctx.author.mention}\n"
                f"**Messages Deleted:** {amount}\n"
                f"**Channel:** {ctx.channel.mention}"
            ),
            color=PURPLE
        ))

    return msg


@bot.command()
async def warn(ctx, member: discord.Member, *, reason="No reason"):
    lead_role_id = role_id("LEAD_ROLE_ID")
    if not has_role_id(ctx.author, lead_role_id):
        return await ctx.send("❌ Only Lead can use this command.")

    if higher_role(ctx, member):
        return await ctx.send("❌ Cannot warn a user with equal or higher role.")

    time_now = discord.utils.utcnow().strftime("%H:%M")

    warn_data.setdefault(member.id, []).append({
        "reason": reason,
        "mod": str(ctx.author),
        "time": time_now
    })

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Warned",
        description=(
            f"**User:** {member.mention}\n"
            f"**User ID:** {member.id}\n"
            f"**Reason:** {reason}\n"
            f"**Moderator:** {ctx.author.mention}"
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation Logs")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.command()
async def warns(ctx, member: discord.Member):
    lead_role_id = role_id("LEAD_ROLE_ID")
    if not has_role_id(ctx.author, lead_role_id):
        return await ctx.send("❌ Only Lead can use this command.")

    warns_list = warn_data.get(member.id, [])

    if not warns_list:
        description = "**No warnings found**"
    else:
        description = ""
        for i, w in enumerate(warns_list, 1):
            description += f"**{i}.** {w['time']} | {w['mod']} → {w['reason']}\n"

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Warn List",
        description=f"**User:** {member.mention}\n\n{description}",
        color=PURPLE
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation Logs")

    await ctx.send(embed=embed)


@bot.command()
async def unwarn(ctx, member: discord.Member):
    lead_role_id = role_id("LEAD_ROLE_ID")
    if not has_role_id(ctx.author, lead_role_id):
        return await ctx.send("❌ Only Lead can use this command.")

    warn_data.pop(member.id, None)

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Warn Removed",
        description=f"**User:** {member.mention}",
        color=PURPLE
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation Logs")

    await ctx.send(embed=embed)


# ================= INFO COMMANDS =================

@bot.command()
@founder_or_bootstrap()
async def about(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | About Server",
        description=f"""
Welcome to **{SERVER_NAME}** — a place where traders meet, exchange and grow together.

📊 **What we offer**
• Safe and organized **trading channels**  
• Active **moderation team**  
• Friendly and growing **community**  
• Fair and transparent **deals**

🤝 **Our Goal**
Our mission is to create a **trusted trading environment** where everyone can trade safely, meet new people and grow their market experience.

⚡ **Why join us?**
Because here you will find **serious traders**, **fast deals**, and a **community that actually helps each other**.

💡 **Remember**
Always follow the **server rules**, respect other members and enjoy trading.
""",
        color=PURPLE
    )

    embed.set_footer(text=f"{SERVER_NAME} | Official Server")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def rules(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Server Rules",
        description=f"Welcome to **{SERVER_NAME}**! To keep our community safe and fun, please follow these rules:",
        color=PURPLE
    )

    embed.add_field(
        name="1️⃣ Respect Everyone",
        value="Treat all members with **kindness and respect**. No harassment, hate speech, or discrimination allowed. 🙏",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Keep Chat Clean",
        value="Avoid **spamming, excessive caps, or irrelevant messages**. 🧹",
        inline=False
    )

    embed.add_field(
        name="3️⃣ Trade Safely",
        value="Follow **trade guidelines** and avoid scams. 💼",
        inline=False
    )

    embed.add_field(
        name="4️⃣ NSFW Content",
        value="**No NSFW content**. 🚫",
        inline=False
    )

    embed.add_field(
        name="5️⃣ Proper Channels",
        value="Post in the **correct channel**. 📌",
        inline=False
    )

    embed.add_field(
        name="6️⃣ Listen to Moderators",
        value="Moderators have the **final say**. 🛡️",
        inline=False
    )

    embed.set_footer(text=f"{SERVER_NAME} | Official Server")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def mmtos(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Middleman Terms of Service",
        description=f"Welcome to **{SERVER_NAME} MM Services**! To ensure **safe and fair trades**, please read the rules below carefully.",
        color=PURPLE
    )

    embed.add_field(
        name="1️⃣ Use Middleman Services Properly",
        value="Only request a MM in designated channels. 🙏",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Respect MM Decisions",
        value="Middlemen have the **final say** in disputes. 🛡️",
        inline=False
    )

    embed.add_field(
        name="3️⃣ Provide Accurate Info",
        value="Always provide **full and correct trade details**. 📝",
        inline=False
    )

    embed.add_field(
        name="4️⃣ No Bypassing the MM",
        value="**Do not bypass** the middleman. ❌",
        inline=False
    )

    embed.add_field(
        name="5️⃣ Report Issues Responsibly",
        value="Report problems to moderators immediately. ⚠️",
        inline=False
    )

    embed.set_footer(text=f"{SERVER_NAME} | Official Middleman Terms")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def value(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Official Value List",
        description="Here are the official value lists for some popular Roblox games 💜",
        color=PURPLE
    )

    embed.add_field(
        name="🍼 Adopt Me",
        value="[View Adopt Me Value List](https://www.roblox.com/games/920587237/Adopt-Me)",
        inline=False
    )

    embed.add_field(
        name="🔪 Murder Mystery 2",
        value="[View MM2 Value List](https://www.roblox.com/games/142823291/Murder-Mystery-2)",
        inline=False
    )

    embed.add_field(
        name="🗡️ Blade Ball",
        value="[View Blade Ball Value List](https://www.roblox.com/games/6632044412/Blade-Ball)",
        inline=False
    )

    embed.add_field(
        name="🍑 Blox Fruits",
        value="[View Blox Fruits Value List](https://www.roblox.com/games/2753915549/Blox-Fruits)",
        inline=False
    )

    embed.add_field(
        name="🐾 Pet Simulator 99",
        value="[View Pet Simulator 99 Value List](https://www.roblox.com/games/6785889800/Pet-Simulator-99)",
        inline=False
    )

    embed.set_footer(text=f"{ctx.guild.name} | Official Value List")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def marketrules(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Marketplace Rules",
        description=f"Welcome to the **{SERVER_NAME} Marketplace**! To ensure a **safe and fair trading environment**, please follow these rules carefully.",
        color=PURPLE
    )

    embed.add_field(
        name="1️⃣ Respect Traders",
        value="Treat all users with **respect**. No harassment, offensive language, or discrimination is allowed. 🙏",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Use Correct Channels",
        value="Always post trades in the **designated marketplace channels**. Avoid spamming or advertising in other channels. 📌",
        inline=False
    )

    embed.add_field(
        name="3️⃣ No Scams",
        value="Attempting to **trick or scam other traders** is strictly prohibited. Report suspicious activity immediately. ❌",
        inline=False
    )

    embed.add_field(
        name="4️⃣ Middleman Use",
        value="When trading **high-value items**, always use an **official Middleman (MM)** to ensure safety. 🛡️",
        inline=False
    )

    embed.add_field(
        name="5️⃣ Follow Discord Rules",
        value="All general **Discord server rules** still apply while trading. ⚠️",
        inline=False
    )

    embed.set_footer(text=f"{ctx.guild.name} | Official Marketplace Rules")
    await ctx.send(embed=embed)


@bot.command()
@founder_or_bootstrap()
async def staffapp(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Staff Application",
        description=f"""
Interested in becoming a **staff member** at **{SERVER_NAME}**?  

We are looking for **dedicated, responsible, and active members** to help manage and moderate the server.  
If you think you have what it takes, please **DM me directly** to submit your application.  

**When applying, make sure to include the following information:**  
• **Discord Name & Tag**  
• **Previous Experience** in moderation, trading, or community management  
• **Why you want to join our staff team**  
• **Your availability**  
• **Any relevant skills**  

Applications will be **reviewed carefully**, and selected candidates will be contacted for further steps.  
We value honesty, responsibility, and enthusiasm — make sure your application **reflects your dedication**. 💜  

Thank you for your interest in helping make **{SERVER_NAME}** a better and safer community!
""",
        color=PURPLE
    )

    embed.set_footer(text=f"{ctx.guild.name} | Official Staff Application")
    await ctx.send(embed=embed)


@bot.command(name="tos")
@founder_or_bootstrap()
async def tos(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Server TOS",
        description=(
            f"# {SERVER_NAME.upper()}\n"
            "## Server Terms of Service\n\n"
            "### Welcome\n"
            f"Welcome to **{SERVER_NAME}**. Please read the following terms before using the server.\n\n"
            "### Community Rules\n"
            "• Treat every member with **respect**.\n"
            "• **No spam** or flooding channels.\n"
            "• **No harassment, hate speech, or toxicity**.\n"
            "• Follow all **Discord guidelines**.\n\n"
            "### Trading Rules\n"
            "• Be **honest and fair** when trading.\n"
            "• **Scamming is strictly forbidden**.\n"
            "• Report suspicious activity to **staff immediately**.\n\n"
            "### Important Notice\n"
            "By remaining in this server you **agree to follow all rules and terms**.\n"
            "Breaking these rules may result in **warnings, mutes, kicks, or bans**.\n\n"
            "### Enjoy the Server\n"
            f"Trade safely, respect others, and enjoy your time in **{SERVER_NAME}**."
        ),
        color=PURPLE
    )

    embed.set_footer(text=f"{SERVER_NAME} | Administration")
    await ctx.send(embed=embed)


@bot.command(name="support")
@founder_or_bootstrap()
async def support(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Support",
        description=(
            f"# {SERVER_NAME.upper()} SUPPORT\n"
            "## Need Help?\n\n"
            "### Contact Support\n"
            "If you need help with **trades, tickets, or server issues**, please contact our **support team**.\n\n"
            "### What Support Can Help With\n"
            "• **Trade problems or disputes**\n"
            "• **Ticket issues**\n"
            "• **Server questions**\n"
            "• **Reporting scams or suspicious users**\n\n"
            "### Important\n"
            "Please be **patient and respectful** when contacting support.\n"
            "Our staff will respond **as soon as possible**.\n\n"
            "### Thank You\n"
            f"Thank you for using **{SERVER_NAME} Support** 💜"
        ),
        color=PURPLE
    )

    embed.set_footer(text=f"{SERVER_NAME} | Support Team")
    await ctx.send(embed=embed)


# ================= MODERATION ACTIONS =================

@bot.command()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    executive_role_id = role_id("EXECUTIVE_ROLE_ID")
    if not has_any_role(ctx.author, executive_role_id):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "kick", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Kicked",
        description=(
            "# 👢 Kick Executed\n\n"
            f"**User:** {member.mention}\n"
            f"**Username:** {member}\n"
            f"**User ID:** {member.id}\n"
            f"**Moderator:** {ctx.author.mention}\n"
            f"**Moderator ID:** {ctx.author.id}\n"
            f"**Reason:** {reason}\n"
            f"**Account Created:** <t:{int(member.created_at.timestamp())}:F>\n"
            f"**Action Time:** <t:{int(action_time.timestamp())}:F>"
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation System")

    await member.kick(reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    executive_role_id = role_id("EXECUTIVE_ROLE_ID")
    if not has_any_role(ctx.author, executive_role_id):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "ban", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Banned",
        description=(
            "# 🔨 Ban Executed\n\n"
            f"**User:** {member.mention}\n"
            f"**Username:** {member}\n"
            f"**User ID:** {member.id}\n"
            f"**Moderator:** {ctx.author.mention}\n"
            f"**Moderator ID:** {ctx.author.id}\n"
            f"**Reason:** {reason}\n"
            f"**Account Created:** <t:{int(member.created_at.timestamp())}:F>\n"
            f"**Action Time:** <t:{int(action_time.timestamp())}:F>"
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation System")

    await ctx.guild.ban(member, reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.command()
async def unban(ctx, user_id: int, *, reason="No reason provided"):
    executive_role_id = role_id("EXECUTIVE_ROLE_ID")
    if not has_any_role(ctx.author, executive_role_id):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "unban", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    user = await bot.fetch_user(user_id)

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | User Unbanned",
        description=(
            "# ✅ Unban Executed\n\n"
            f"**User:** {user.mention}\n"
            f"**Username:** {user}\n"
            f"**User ID:** {user.id}\n"
            f"**Moderator:** {ctx.author.mention}\n"
            f"**Moderator ID:** {ctx.author.id}\n"
            f"**Reason:** {reason}\n"
            f"**Account Created:** <t:{int(user.created_at.timestamp())}:F>\n"
            f"**Action Time:** <t:{int(action_time.timestamp())}:F>"
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} | Moderation System")

    await ctx.guild.unban(user, reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.event
async def on_member_join(member):
    guild = member.guild

    welcome_channel_id = channel_id("WELCOME_CHANNEL_ID")
    invite_log_channel_id = channel_id("INVITE_LOG_CHANNEL_ID")

    welcome_channel = guild.get_channel(welcome_channel_id) if welcome_channel_id else None
    invite_channel = guild.get_channel(invite_log_channel_id) if invite_log_channel_id else None

    inviter = "Unknown"
    used_invite = "Unknown"

    try:
        new_invites = await guild.invites()
        old_invites = invite_cache.get(guild.id)

        if old_invites:
            for new in new_invites:
                for old in old_invites:
                    if new.code == old.code and new.uses > old.uses:
                        inviter = new.inviter.mention
                        used_invite = new.code

        invite_cache[guild.id] = new_invites
    except Exception:
        pass

    welcome_embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Welcome",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Welcome {member.mention}!**\n\n"
            f"We are happy to have you in **{SERVER_NAME}**.\n\n"
            "**Trade safely, respect others, and enjoy your stay!**\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=PURPLE
    )

    welcome_embed.set_thumbnail(url=member.display_avatar.url)
    welcome_embed.set_footer(text=f"{SERVER_NAME} | Welcome System")

    if welcome_channel:
        await welcome_channel.send(embed=welcome_embed)

    invite_embed = discord.Embed(
        title=f"📈 {SERVER_NAME} | New Member Joined",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**User:** {member.mention}\n"
            f"**User ID:** {member.id}\n\n"
            f"**Invited By:** {inviter}\n"
            f"**Invite Code:** {used_invite}\n\n"
            f"**Account Created:** <t:{int(member.created_at.timestamp())}:F>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=PURPLE
    )

    invite_embed.set_thumbnail(url=member.display_avatar.url)
    invite_embed.set_footer(text=f"{SERVER_NAME} | Invite Tracker")

    if invite_channel:
        await invite_channel.send(embed=invite_embed)


@bot.command()
@founder_or_bootstrap()
async def verify(ctx):
    embed = discord.Embed(
        title=f"💜 {SERVER_NAME} | Verification",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Click the button below to verify.**\n\n"
            "You will receive the **Verified Trader** role.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=PURPLE
    )

    await ctx.send(embed=embed, view=VerifyButton())
    
@bot.command()
@is_mm()
async def howmmworks(ctx):
    embed = discord.Embed(
        title="💜 Trade Hub Official | How a Middleman Works",
        description=(
            "🔐 **How Trade Hub Official's Middleman Service Works**\n\n"
            "Welcome to **Trade Hub Official's Middleman Service**, where your trades are handled with "
            "**maximum security, transparency, and professionalism**.\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ **Why Use a Middleman?**\n"
            "A middleman protects both parties during a trade. Instead of trusting a stranger, "
            "both users trust our verified MM team.\n\n"

            "With our service:\n"
            "• 🚫 No scams\n"
            "• 🔒 No risk of chargebacks\n"
            "• 🤝 Fair trade guarantee\n"
            "• 📜 Proof and documentation of the deal\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📩 **Step-By-Step Process**\n"
            "1️⃣ Both users agree on the trade terms.\n"
            "2️⃣ Open a ticket and select the trade type.\n"
            "3️⃣ Provide clear trade details inside the ticket.\n"
            "4️⃣ An official MM team member will claim the ticket.\n"
            "5️⃣ The buyer sends the payment/item to the MM.\n"
            "6️⃣ After confirmation, the seller delivers their part.\n"
            "7️⃣ Once both sides confirm, the MM safely releases the assets.\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌟 **Trade Hub Official Middleman Service Guarantee**\n"
            "We ensure a **secure, neutral, and protected environment** for every trade."
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Hub Official | Official Middleman System")
    await ctx.send(embed=embed)
    
@bot.command()
@is_mm()
async def fee(ctx):

    embed = discord.Embed(
        title="💜 Trade Hub Official | Middleman Service Fee Confirmation",
        description=(
            "To ensure transparency and fairness, all middleman transactions may include a service fee.\n\n"

            "Please choose how the fee will be handled for this trade:\n\n"

            "🔹 **50% / 50% Split** – Both users share the fee equally.\n"
            "🔹 **100% One User Pays** – One trader covers the entire fee.\n"
            "🔹 **Custom Split** – Choose your own percentage distribution.\n\n"

            "Click one of the buttons below to confirm how the fee will be paid."
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Hub Official | Fee System")

    await ctx.send(embed=embed, view=FeeView(ctx.author))
    
@bot.command()
@is_mm()
async def mmtos(ctx):

    embed = discord.Embed(
        title="💜 Trade Hub Official | Middleman Terms of Service",
        description="Welcome to **Trade Hub Official MM Services**! To ensure **safe and fair trades**, please read the rules below carefully.",
        color=PURPLE
    )

    embed.add_field(
        name="1️⃣ Use Middleman Services Properly",
        value="Only request a MM in designated channels.",
        inline=False
    )

    embed.add_field(
        name="2️⃣ Respect MM Decisions",
        value="Middlemen have the **final say** in disputes.",
        inline=False
    )

    embed.add_field(
        name="3️⃣ Provide Accurate Info",
        value="Always provide **full and correct trade details**.",
        inline=False
    )

    embed.add_field(
        name="4️⃣ No Bypassing the MM",
        value="**Do not bypass** the middleman.",
        inline=False
    )

    embed.add_field(
        name="5️⃣ Report Issues Responsibly",
        value="Report problems to moderators immediately.",
        inline=False
    )

    embed.set_footer(text="Trade Hub Official | Official Middleman Terms")
    await ctx.send(embed=embed)
    
@bot.command()
@is_mm()
async def policy(ctx):

    embed = discord.Embed(
        title="💜 Trade Hub Official | Compensation Policy",
        description=(
            "## Middleman Compensation Policy\n\n"

            "If a mistake happens during a trade handled by our MM team, "
            "Trade Hub Official will review the case and provide compensation if needed.\n\n"

            "### Covered Situations\n"
            "• Middleman mistake\n"
            "• Item loss during MM custody\n"
            "• Confirmed internal error\n\n"

            "### Not Covered\n"
            "• Fake items\n"
            "• Chargebacks\n"
            "• Deals done outside the ticket\n\n"

            "All cases are reviewed by **server executives**."
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Hub Official | Policy System")

    await ctx.send(embed=embed)
    
@bot.command()
@is_mm()
async def confirm(ctx, user1: discord.Member, user2: discord.Member):

    embed = discord.Embed(
        title="💜 Trade Hub Official | Official Trade Confirmation",
        description=(
            "This trade has been officially confirmed under the supervision of our Middleman Team.\n\n"

            "Both parties listed below have agreed to the full trade terms and fee structure.\n\n"

            "**Trade Protection Status: ACTIVE ✅**"
        ),
        color=PURPLE
    )

    embed.add_field(name="Trader 1", value=user1.mention, inline=False)
    embed.add_field(name="Trader 2", value=user2.mention, inline=False)

    embed.set_footer(text="Trade Hub Official | Secure Middleman System")

    await ctx.send(embed=embed)
    
@bot.command()
async def help(ctx):

    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title=f"💜 {ctx.guild.name} | Help Menu",
        description="List of all commands",
        color=PURPLE
    )

    embed.add_field(
        name="Info",
        value="$about\n$tos\n$rules\n$support\n$value\n$marketrules\n$staffapp",
        inline=False
    )

    embed.add_field(
        name="Middleman",
        value="$panel\n$mmtos\n$howmmworks\n$policy\n$fee\n$confirm",
        inline=False
    )

    embed.add_field(
        name="Tickets",
        value="$claim\n$unclaim\n$close\n$add\n$remove",
        inline=False
    )

    embed.add_field(
        name="Vouches",
        value="$vouch\n$vouches\n$topvouches\n$addvouch\n$removevouch",
        inline=False
    )

    embed.add_field(
        name="Moderation",
        value="$purge\n$warn\n$warns\n$unwarn\n$kick\n$ban\n$unban",
        inline=False
    )

    embed.set_footer(text="Trade Hub Official | Official Help Menu")

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    await ctx.send(embed=embed)
    
# ================= PANEL SELECT =================

class MMSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🎮 In Game Items"),
            discord.SelectOption(label="🪙 Crypto"),
            discord.SelectOption(label="💳 PayPal"),
        ]

        super().__init__(
            placeholder="Select trade type below",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="mm_select_trade_type"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MMModal(self.values[0]))


# ================= PANEL VIEW =================

class MMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MMSelect())


# ================= MODAL =================

class MMModal(discord.ui.Modal):
    def __init__(self, trade_type):
        super().__init__(title="Middleman Ticket")

        self.trade_type = trade_type

        self.other_user = discord.ui.TextInput(
            label="Other User (mention or name)",
            required=True
        )

        self.trade_details = discord.ui.TextInput(
            label="Trade Details",
            style=discord.TextStyle.paragraph,
            required=True
        )

        self.agreement = discord.ui.TextInput(
            label="Do both users agree?",
            placeholder="Type YES if both agreed",
            required=True
        )

        self.add_item(self.other_user)
        self.add_item(self.trade_details)
        self.add_item(self.agreement)

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild

        category = guild.get_channel(TICKET_CATEGORY_ID)

        if category is None:
            return await interaction.response.send_message(
                "❌ Ticket category not set. Use `$setticketcategory` first.",
                ephemeral=True
            )

        mm_role = guild.get_role(MM_ROLE_ID)
        other_member = extract_member_from_input(guild, self.other_user.value)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
        }

        if other_member:
            overwrites[other_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        if mm_role:
            overwrites[mm_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        channel = await guild.create_text_channel(
            name=f"mm-{interaction.user.name}".lower().replace(" ", "-"),
            category=category,
            overwrites=overwrites
        )

        ticket_data[channel.id] = {
            "creator_id": interaction.user.id,
            "other_user_id": other_member.id if other_member else None,
            "claimer_id": None,
            "trade_type": self.trade_type,
            "trade_details": self.trade_details.value,
            "agreement": self.agreement.value
        }

        other_user_text = other_member.mention if other_member else self.other_user.value

        ticket_embed = discord.Embed(
            title="💜 Trade Hub Official | New Middleman Ticket",
            description=(
                "# New Ticket Created\n"
                "A new **middleman request** has been submitted.\n\n"
                "## Ticket Information\n"
                f"**Trade Type:** {self.trade_type}\n"
                f"**Other User:** {other_user_text}\n"
                f"**Agreement:** {self.agreement.value}\n\n"
                "## Trade Details\n"
                f"{self.trade_details.value}\n\n"
                "## Status\n"
                "**Waiting for a Middleman to claim this ticket.**"
            ),
            color=PURPLE
        )

        ticket_embed.set_footer(text="Trade Hub Official | Ticket System")

        mention_parts = [interaction.user.mention]

        if other_member:
            mention_parts.append(other_member.mention)

        if mm_role:
            mention_parts.append(mm_role.mention)

        await channel.send(
            content=" ".join(mention_parts),
            embed=ticket_embed,
            view=TicketButtons()
        )

        if other_member:
            await interaction.response.send_message(
                f"✅ Your ticket has been created: {channel.mention}\n"
                f"✅ {other_member.mention} was automatically added.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Your ticket has been created: {channel.mention}",
                ephemeral=True
            )


# ================= PANEL COMMAND =================

@bot.command()
async def panel(ctx):

    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Hub Official | Middleman Service",
        description=(
            "Welcome to our middleman service centre.\n\n"
            "At **Trade Hub Official**, we provide a safe and secure way to exchange your goods.\n\n"
            "Our trusted middleman team ensures both traders receive exactly what they agreed upon.\n\n"
            "**Use the dropdown below to create a ticket.**"
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Hub Official | Official Middleman System")

    await ctx.send(embed=embed, view=MMView())


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    for guild in bot.guilds:
        try:
            invite_cache[guild.id] = await guild.invites()
        except Exception:
            invite_cache[guild.id] = []

    bot.add_view(TicketButtons())
    bot.add_view(MMView())
    bot.add_view(FeeView())
    bot.add_view(VerifyButton())


token = os.getenv("TOKEN")

if not token:
    raise ValueError("TOKEN environment variable not set")

bot.run(token)