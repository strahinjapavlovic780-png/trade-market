import discord
from discord.ext import commands
import os
import json
import io
from datetime import datetime

VOUCH_FILE = "vouches.json"
PURPLE = discord.Color.purple()

if not os.path.exists(VOUCH_FILE):
    with open(VOUCH_FILE, "w") as f:
        json.dump({}, f)


def load_vouches():
    with open(VOUCH_FILE, "r") as f:
        return json.load(f)


def save_vouches(data):
    with open(VOUCH_FILE, "w") as f:
        json.dump(data, f, indent=4)


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

MM_ROLE_ID = 1465699152653455546
MEMBER_ROLE_ID = 1465699188628262963
FOUNDER_ROLE_ID = 1465697938155110411
STAFF_CHANNEL_ID = 1480919385966116916
MERCY_ROLE_ID = 1465699224061743156
TICKET_CATEGORY_ID = 1466889112652087539
STAFF_ROLE_ID = 1465698968439886030
LEAD_ROLE_ID = 1465698723479687387
EXECUTIVE_ROLE_ID = 1465698169672175676
VICE_PRESIDENT_ROLE_ID = 1465697969851601050
OWNER_ROLE_ID = 1465695641320685730
WELCOME_CHANNEL_ID = 1478783015017648259
INVITE_LOG_CHANNEL_ID = 1479054141312471092

LOG_CHANNEL_NAME = "mod-logs"
COOLDOWN = 300
warn_data = {}
invite_cache = {}


def is_mm():
    async def predicate(ctx):
        if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
            await ctx.send("❌ You are not allowed to use this command.")
            return False
        return True
    return commands.check(predicate)


def has_role(ctx, role_id):
    return any(role.id == role_id for role in ctx.author.roles)


def is_owner(ctx):
    return any(role.id == OWNER_ROLE_ID for role in ctx.author.roles)


def higher_role(ctx, member):
    return member.top_role >= ctx.author.top_role


async def get_log_channel(guild):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    if channel is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.get_role(EXECUTIVE_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }

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
    
command_cooldowns = {}

def has_any_role(member, *role_ids):
    return any(role.id in role_ids for role in member.roles)

def is_owner_bypass(member):
    return has_any_role(member, OWNER_ROLE_ID)

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
            options=options
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
        global TICKET_CATEGORY_ID

        if TICKET_CATEGORY_ID is None:
            category = await guild.create_category("══「 🎫 TICKETS 」══")
            TICKET_CATEGORY_ID = category.id
        else:
            category = guild.get_channel(TICKET_CATEGORY_ID)

            if category is None:
                category = await guild.create_category("══「 🎫 TICKETS 」══")
                TICKET_CATEGORY_ID = category.id

        mm_role = guild.get_role(MM_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
        }

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

        ticket_embed = discord.Embed(
            title="💜 Trade Market | New Middleman Ticket",
            description=(
                "# New Ticket Created\n"
                "A new **middleman request** has been submitted.\n\n"
                "## Ticket Information\n"
                f"**Trade Type:** {self.trade_type}\n"
                f"**Other User:** {self.other_user.value}\n"
                f"**Agreement:** {self.agreement.value}\n\n"
                "## Trade Details\n"
                f"{self.trade_details.value}\n\n"
                "## Status\n"
                "**Waiting for a Middleman to claim this ticket.**"
            ),
            color=PURPLE
        )

        ticket_embed.set_footer(text="Trade Market | Ticket System")

        mention_text = interaction.user.mention
        if mm_role:
            mention_text = f"{interaction.user.mention} {mm_role.mention}"

        await channel.send(
            content=mention_text,
            embed=ticket_embed,
            view=TicketButtons(interaction.user)
        )

        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True
        )


# ================= BUTTONS =================

class TicketButtons(discord.ui.View):
    def __init__(self, creator):
        super().__init__(timeout=None)
        self.creator = creator
        self.claimer = None

    @discord.ui.button(label="✔️Claim", style=discord.ButtonStyle.green)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if MM_ROLE_ID not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can claim tickets.",
                ephemeral=True
            )

        if self.claimer:
            return await interaction.response.send_message(
                "Ticket already claimed.",
                ephemeral=True
            )

        self.claimer = interaction.user
        button.disabled = True

        guild = interaction.guild
        channel = interaction.channel
        mm_role = guild.get_role(MM_ROLE_ID)

        if mm_role:
            await channel.set_permissions(mm_role, view_channel=False)

        await channel.set_permissions(
            self.creator,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        await channel.set_permissions(
            interaction.user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        claimed_embed = discord.Embed(
            title="💜 Trade Market | Ticket Claimed",
            description=(
                "# Ticket Claimed\n"
                f"This ticket has been claimed by {interaction.user.mention}.\n\n"
                "## Status\n"
                f"{self.creator.mention} and {interaction.user.mention} can now access this ticket.\n"
                "**Other middlemen can no longer view it.**"
            ),
            color=PURPLE
        )

        claimed_embed.set_footer(text="Trade Market | Ticket System")

        await interaction.response.edit_message(view=self)
        await channel.send(embed=claimed_embed)

    @discord.ui.button(label="➕Add User", style=discord.ButtonStyle.blurple)
    async def add_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if MM_ROLE_ID not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can use this.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Use command: `!add @user`",
            ephemeral=True
        )

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.gray)
    async def remove_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if MM_ROLE_ID not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message(
                "Only MM team can use this.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Use command: `!remove @user`",
            ephemeral=True
        )

@discord.ui.button(label="Close", style=discord.ButtonStyle.red)
async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
    if MM_ROLE_ID not in [role.id for role in interaction.user.roles]:
        return await interaction.response.send_message(
            "Only MM team can close tickets.",
            ephemeral=True
        )

    log_channel = await get_log_channel(interaction.guild)
    transcript_file = await save_ticket_transcript(interaction.channel)

    close_embed = discord.Embed(
        title="💜 Trade Market | Ticket Closed",
        description=(
            f"**Channel:** {interaction.channel.name}\n"
            f"**Closed by:** {interaction.user.mention}\n"
            f"**Created by:** {self.creator.mention}"
        ),
        color=PURPLE
    )
    close_embed.set_footer(text="Trade Market | Ticket Logs")

    if log_channel:
        await log_channel.send(
            embed=close_embed,
            file=discord.File(transcript_file, filename=f"{interaction.channel.name}-transcript.txt")
        )

    await interaction.response.send_message("Closing ticket...")
    await interaction.channel.delete()


# ================= COMMANDS =================

@bot.command()
async def add(ctx, member: discord.Member):
    if ctx.channel.category is None or ctx.channel.category.name != "══「 🎫 TICKETS 」══":
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can use this command.")

    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)

    embed = discord.Embed(
        title="💜 Trade Market | User Added",
        description=(
            "# ✅ User Successfully Added\n\n"
            f"{member.mention} has been added to the ticket and can now participate in the trade."
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Ticket System")

    await ctx.send(embed=embed)


@bot.command()
async def remove(ctx, member: discord.Member):
    if ctx.channel.category is None or ctx.channel.category.name != "══「 🎫 TICKETS 」══":
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can use this command.")

    await ctx.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        title="💜 Trade Market | User Removed",
        description=(
            "# ❌ User Removed\n\n"
            f"{member.mention} has been removed from the ticket."
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Ticket System")

    await ctx.send(embed=embed)


@bot.command()
async def claim(ctx):
    if ctx.channel.category is None or ctx.channel.category.name != "══「 🎫 TICKETS 」══":
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can claim tickets.")

    embed = discord.Embed(
        title="💜 Trade Market | Ticket Claimed",
        description=(
            "# ✅ Ticket Claimed\n\n"
            f"{ctx.author.mention} has claimed this ticket.\n\n"
            "## Status\n"
            "**Ticket is now private.**"
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Ticket System")

    await ctx.channel.send(embed=embed)


@bot.command()
async def close(ctx):
    if ctx.channel.category is None or ctx.channel.category.name != "══「 🎫 TICKETS 」══":
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can close tickets.")

    log_channel = await get_log_channel(ctx.guild)
    transcript_file = await save_ticket_transcript(ctx.channel)

    close_embed = discord.Embed(
        title="💜 Trade Market | Ticket Closed",
        description=(
            f"**Channel:** {ctx.channel.name}\n"
            f"**Closed by:** {ctx.author.mention}"
        ),
        color=PURPLE
    )
    close_embed.set_footer(text="Trade Market | Ticket Logs")

    if log_channel:
        await log_channel.send(
            embed=close_embed,
            file=discord.File(transcript_file, filename=f"{ctx.channel.name}-transcript.txt")
        )

    await ctx.send("Closing ticket...")
    await ctx.channel.delete()


@bot.command()
async def unclaim(ctx):
    if ctx.channel.category is None or ctx.channel.category.name != "══「 🎫 TICKETS 」══":
        return await ctx.send("❌ This command can only be used inside ticket channels.")

    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only MM team can unclaim tickets.")

    embed = discord.Embed(
        title="💜 Trade Market | Ticket Unclaimed",
        description=(
            "# 🔓 Ticket Unclaimed\n\n"
            f"{ctx.author.mention} has unclaimed this ticket.\n\n"
            "## Status\n"
            "**Another MM can now claim it.**"
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Ticket System")

    await ctx.channel.send(embed=embed)

# ================= SERVER COMMAND =================

@bot.command()
async def server(ctx):
    guild = ctx.guild
    total_members = guild.member_count
    humans = sum(1 for member in guild.members if not member.bot)
    bots = sum(1 for member in guild.members if member.bot)
    channels = len(guild.channels)
    roles = len(guild.roles)
    created = guild.created_at.strftime("%Y-%m-%d")

    embed = discord.Embed(
        title=f"💜 {guild.name} | Server Info",
        description=(
            "# Server Overview\n\n"
            f"**Owner:** <@{guild.owner_id}>\n"
            f"**Created:** {created}\n"
            f"**Members:** {total_members}\n"
            f"**Humans:** {humans}\n"
            f"**Bots:** {bots}\n"
            f"**Channels:** {channels}\n"
            f"**Roles:** {roles}"
        ),
        color=PURPLE
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text=f"{guild.name} | Official Server Information")
    await ctx.send(embed=embed)


# ================= PANEL COMMAND =================

@bot.command()
async def panel(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Market | Middleman Service",
        description=(
            "Welcome to our middleman service centre.\n\n"
            "At **Trade Market**, we provide a safe and secure way to exchange your goods, "
            "whether it's in-game items, crypto or digital assets.\n\n"
            "Our trusted middleman team ensures that both parties receive exactly what they agreed upon "
            "with **zero risk of scams**.\n\n"
            "**If you've found a trade and want to ensure your safety, "
            "you can use our FREE middleman service by following the steps below.**\n\n"
            "*Note: Large trades may include a small service fee.*\n\n"
            "📌 **Usage Conditions**\n"
            "• Find someone to trade with.\n"
            "• Agree on the trade terms.\n"
            "• Click the dropdown below.\n"
            "• Wait for a staff member.\n\n"
            "**Trade Market • Trusted Middleman Service**"
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Official Middleman System")

    await ctx.send(embed=embed, view=MMView())


# ================= HOW MM WORKS =================

@bot.command()
async def howmmworks(ctx):
    embed = discord.Embed(
        title="💜 Trade Market | How a Middleman Works",
        description=(
            "🔐 **How Trade Market's Middleman Service Works**\n\n"
            "Welcome to **Trade Market's Middleman Service**, where your trades are handled with "
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
            "🌟 **Trade Market's Middleman Service Guarantee**\n"
            "We ensure a **secure, neutral, and protected environment** for every trade.\n"
            "Our reputation is built on **trust, safety, and successful transactions**.\n\n"
            "💜 Trade safely. Trade smart. Trade with confidence."
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Market | Official Middleman System")
    await ctx.send(embed=embed)


# ================= POLICY =================

@bot.command()
async def policy(ctx):
    embed = discord.Embed(
        title="💜 Trade Market | Middleman Accountability & Compensation Policy",
        color=PURPLE
    )

    embed.add_field(
        name="1. Middleman Responsibility",
        value=(
            "Official middlemen must remain neutral and handle all assets fairly. "
            "Any misuse of authority or failure to return items is considered internal fraud."
        ),
        inline=False
    )

    embed.add_field(
        name="2. If a Middleman Scams",
        value=(
            "• Both traders will receive full compensation equal to their losses.\n"
            "• Compensation is provided by the Executive Team.\n"
            "• The middleman will be terminated, blacklisted, and permanently banned."
        ),
        inline=False
    )

    embed.add_field(
        name="3. Compensation Requirements",
        value=(
            "• Trade must occur inside our official Discord server.\n"
            "• The middleman must have had the MM role at the time.\n"
            "• Valid proof (screenshots/recordings) must be provided.\n\n"
            "**All official trades are fully protected under this policy.**"
        ),
        inline=False
    )

    embed.set_footer(text="Trade Market | Protection Guaranteed")
    await ctx.send(embed=embed)


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

        except:
            await interaction.response.send_message(
                "Invalid format. Use example: 60-40",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"💜 Trade Market | Fee Agreement – {p1}/{p2} Split",
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
        embed.set_footer(text="Trade Market | Fee System")

        await interaction.response.send_message(embed=embed)


class FeeView(discord.ui.View):
    def __init__(self, requester):
        super().__init__(timeout=None)
        self.requester = requester

    @discord.ui.button(label="50% / 50%", style=discord.ButtonStyle.primary)
    async def split_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="💜 Trade Market | Fee Agreement – 50/50 Split",
            description=(
                "# Middleman Fee Agreement\n\n"
                "Both traders have agreed to split the middleman fee equally.\n\n"
                "**Both users will pay 50% of the fee each.**\n\n"
                "This ensures fairness and equal responsibility between both parties.\n\n"
                "Once payment is completed, the middleman will proceed with the secured transaction."
            ),
            color=PURPLE
        )
        embed.set_footer(text="Trade Market | Fee System")

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="100% One User Pays", style=discord.ButtonStyle.red)
    async def full_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="💜 Trade Market | Fee Agreement – Full Payment",
            description=(
                "# Middleman Fee Agreement\n\n"
                f"{interaction.user.mention} has agreed to cover the full middleman fee.\n\n"
                f"**{interaction.user.mention} will pay 100% of the fees to the middleman.**\n\n"
                "The second trader is not responsible for any service fee in this transaction.\n\n"
                "Once the fee is confirmed, the trade will proceed under full protection."
            ),
            color=PURPLE
        )
        embed.set_footer(text="Trade Market | Fee System")

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Custom Split", style=discord.ButtonStyle.secondary)
    async def custom_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomFeeModal())


@bot.command()
async def fee(ctx):
    embed = discord.Embed(
        title="💜 Trade Market | Middleman Service Fee Confirmation",
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
    embed.set_footer(text="Trade Market | Fee System")

    await ctx.send(embed=embed, view=FeeView(ctx.author))


# ================= CONFIRM SYSTEM =================

@bot.command()
async def confirm(ctx, user1: discord.Member, user2: discord.Member):
    embed = discord.Embed(
        title="💜 Trade Market | Official Trade Confirmation",
        description=(
            "This trade has been officially confirmed under the supervision of our Middleman Team.\n\n"
            "Both parties listed below have agreed to the full trade terms, conditions, "
            "and fee structure associated with this transaction.\n\n"
            "By confirming this trade, both users acknowledge that:\n"
            "• The trade terms are final and mutually accepted.\n"
            "• The middleman will securely hold and transfer assets.\n"
            "• Any attempt of scam or chargeback will result in permanent ban.\n\n"
            "The transaction is now protected and logged under our official policy system.\n\n"
            "**Trade Protection Status: ACTIVE ✅**"
        ),
        color=PURPLE
    )

    embed.add_field(name="Trader 1", value=user1.mention, inline=False)
    embed.add_field(name="Trader 2", value=user2.mention, inline=False)
    embed.set_footer(text="Trade Market | Secure Middleman Protection System")

    await ctx.send(embed=embed)

# ================= HELP =================

@bot.command()
async def help(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title=f"💜 {ctx.guild.name} | Help Menu",
        description=(
            "# Command Categories\n\n"
            "Here is a list of all available commands, sorted by category."
        ),
        color=PURPLE
    )

    embed.add_field(
        name="1️⃣ Info",
        value=(
            "`!about` — About the server 💜\n"
            "`!tos` — Server TOS 💜\n"
            "`!rules` — Server rules 📜\n"
            "`!support` — Server Support 🆘\n"
            "`!value` — Official Value List 🎮\n"
            "`!marketrules` — Marketplace Rules 🛒\n"
            "`!staffapp` — Staff Application 📝"
        ),
        inline=False
    )

    embed.add_field(
        name="2️⃣ Middleman",
        value=(
            "`!panel` — Sends the Middleman panel\n"
            "`!mmtos` — Middleman Terms of Service 🛡️\n"
            "`!howmmworks` — Explains how MM works\n"
            "`!policy` — Shows compensation policy\n"
            "`!fee` — Sends fee agreement\n"
            "`!confirm @user1 @user2` — Confirms trade\n"
            "`!mercy @user` — Offer mercy to a user"
        ),
        inline=False
    )

    embed.add_field(
        name="3️⃣ Ticket System",
        value=(
            "`!claim` — Claim the current ticket\n"
            "`!unclaim` — Unclaim the ticket\n"
            "`!close` — Closes the current ticket\n"
            "`!add @user` — Add user to ticket\n"
            "`!remove @user` — Remove user from ticket"
        ),
        inline=False
    )

    embed.add_field(
        name="4️⃣ Vouch System",
        value=(
            "`!vouch @user` — Add 1 vouch\n"
            "`!vouches [@user]` — Check vouches\n"
            "`!topvouches` — Shows top vouches\n"
            "`!addvouch @user <amount>` — Add vouches (MM ONLY)\n"
            "`!removevouch @user` — Remove vouches (MM ONLY)"
        ),
        inline=False
    )

    embed.add_field(
        name="5️⃣ Moderation",
        value=(
            "`!purge <amount>` — Delete messages\n"
            "`!warn @user <reason>` — Warn a user\n"
            "`!warns @user` — Check warns\n"
            "`!unwarn @user` — Remove warn\n"
            "`!kick @user <reason>` — Kick user\n"
            "`!ban @user <reason>` — Ban user\n"
            "`!unban <user_id> <reason>` — Unban user\n"
            
          
        ),
        inline=False
    )

    embed.add_field(
        name="6️⃣ Extra Information",
        value=(
            "`50/50 Button` — Split fee\n"
            "`100% Button` — One user pays full fee\n"
            "`Custom Split` — Custom fee split\n"
            "`Claim Button` — Claims ticket\n"
            "`Unclaim Button` — Unclaims ticket"
        ),
        inline=False
    )

    embed.set_footer(text=f"{ctx.guild.name} | Official Help Menu")

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    await ctx.send(embed=embed)


# ================= VOUCHES =================

@bot.command()
@is_mm()
async def addvouch(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Please provide a valid positive number.")

    vouches_data = load_vouches()
    user_id = str(member.id)

    vouches_data[user_id] = vouches_data.get(user_id, 0) + amount
    save_vouches(vouches_data)

    embed = discord.Embed(
        title="💜 Trade Market | Vouch Added",
        description=(
            "# ⭐ Vouch Added\n\n"
            f"{member.mention} received **{amount}** vouches.\n\n"
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
async def removevouch(ctx, member: discord.Member):
    vouches_data = load_vouches()
    user_id = str(member.id)

    vouches_data[user_id] = 0
    save_vouches(vouches_data)

    embed = discord.Embed(
        title="💜 Trade Market | Vouches Removed",
        description=(
            "# 🗑️ Vouches Reset\n\n"
            f"{member.mention}'s vouches have been **reset to 0**.\n\n"
            "## Status\n"
            "All previous vouches have been removed."
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{ctx.guild.name} | Vouch System")

    await ctx.send(embed=embed)


@bot.command()
@is_mm()
async def vouches(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    vouches_data = load_vouches()
    count = vouches_data.get(str(member.id), 0)

    embed = discord.Embed(
        title="💜 Trade Market | Vouch Count",
        description=(
            "# ⭐ Vouch Count\n\n"
            f"{member.mention} currently has **{count}** vouches.\n\n"
            "## Reputation Status\n"
            "Vouches represent successful trades and trust."
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{ctx.guild.name} | Vouch System")

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
        title="💜 Trade Market | New Vouch",
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
        title="💜 Trade Market | Top Vouches",
        description="# 🏆 Top Trusted Members\n\n" + "\n".join(lines),
        color=PURPLE
    )

    embed.set_footer(text=f"{ctx.guild.name} | Vouch Leaderboard")
    await ctx.send(embed=embed)


# ================= MERCY =================

class MercyView(discord.ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=60)
        self.target = target

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ You are not allowed to respond to this.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(MERCY_ROLE_ID)
        staff_channel = interaction.guild.get_channel(STAFF_CHANNEL_ID)

        if role:
            await self.target.add_roles(role)

        accept_embed = discord.Embed(
            title="Mercy Accepted",
            description=(
                f"**{self.target.mention} has accepted the offer!**\n\n"
                "**What now?**\n"
                "▸ Check out and read all the staff channels carefully.\n"
                "▸ Once you have read them check your DMs for further guide.\n"
                "▸ Ask other staff for help if needed.\n\n"
                "**Start earning now!**"
            ),
            color=PURPLE
        )
        accept_embed.set_footer(text="Mercy System")

        await interaction.channel.send(embed=accept_embed)

        if staff_channel:
            await staff_channel.send(embed=accept_embed)

        await interaction.response.send_message(
            "✅ Offer accepted.",
            ephemeral=True
        )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        decline_embed = discord.Embed(
            title="Mercy Declined",
            description=(
                f"**{self.target.mention} has declined the offer!**\n\n"
                "**What now?**\n"
                "▸ Staff will review the situation.\n"
                "▸ You will not receive access to the Mercy program.\n\n"
                "**Decision recorded.**"
            ),
            color=PURPLE
        )
        decline_embed.set_footer(text="Mercy System")

        await interaction.channel.send(embed=decline_embed)

        await interaction.response.send_message(
            "❌ Offer declined.",
            ephemeral=True
        )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)


@bot.command()
async def mercy(ctx, member: discord.Member):
    if MM_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only Middleman can use this command.")

    embed = discord.Embed(
        title="Hitting Application",
        description="""• **We regret to inform you that you have been scammed**, and we sincerely apologize for this unfortunate situation.

However, there is a way for you to recover your losses and potentially earn 2x or even 100x if you're active.

• **What is Hitting?**
Hitting is where **you scam other people**, often using fake middlemans.
You can use our fake services that we provide to scam others and get tons of items.

Choose if you want to start hitting with us now.

Please click **accept or decline** to indicate your decision.
You have one minute to respond.

**The decision is yours. Make it count.**
""",
        color=PURPLE
    )
    embed.set_footer(text="Mercy System")

    await ctx.send(embed=embed, view=MercyView(member))


# ================= MODERATION =================

@bot.command()
async def purge(ctx, amount: int):
    if not has_role(ctx, LEAD_ROLE_ID):
        return

    await ctx.channel.purge(limit=amount + 1)

    embed = discord.Embed(
        title="💜 Trade Market | Messages Purged",
        description=(
            f"**Deleted:** {amount} messages\n"
            f"**Channel:** {ctx.channel.mention}\n"
            f"**Moderator:** {ctx.author.mention}"
        ),
        color=PURPLE
    )
    embed.set_footer(text="Trade Market | Moderation Logs")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    await log.send(embed=discord.Embed(
        title="💜 Trade Market | Purge Log",
        description=(
            f"**Moderator:** {ctx.author.mention}\n"
            f"**Messages Deleted:** {amount}\n"
            f"**Channel:** {ctx.channel.mention}"
        ),
        color=PURPLE
    ))


@bot.command()
async def warn(ctx, member: discord.Member, *, reason="No reason"):
    if not has_role(ctx, LEAD_ROLE_ID):
        return

    if higher_role(ctx, member):
        return await ctx.send("❌ Cannot warn a user with equal or higher role.")

    time = discord.utils.utcnow().strftime("%H:%M")

    warn_data.setdefault(member.id, []).append({
        "reason": reason,
        "mod": ctx.author,
        "time": time
    })

    embed = discord.Embed(
        title="💜 Trade Market | User Warned",
        description=(
            f"**User:** {member.mention}\n"
            f"**User ID:** {member.id}\n"
            f"**Reason:** {reason}\n"
            f"**Moderator:** {ctx.author.mention}"
        ),
        color=PURPLE
    )

    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.set_footer(text="Trade Market | Moderation Logs")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    await log.send(embed=embed)


@bot.command()
async def warns(ctx, member: discord.Member):
    if not has_role(ctx, LEAD_ROLE_ID):
        return

    warns = warn_data.get(member.id, [])

    if not warns:
        description = "**No warnings found**"
    else:
        description = ""
        for i, w in enumerate(warns, 1):
            description += f"**{i}.** {w['time']} | {w['mod']} → {w['reason']}\n"

    embed = discord.Embed(
        title="💜 Trade Market | Warn List",
        description=f"**User:** {member.mention}\n\n{description}",
        color=PURPLE
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Trade Market | Moderation Logs")

    await ctx.send(embed=embed)


@bot.command()
async def unwarn(ctx, member: discord.Member):
    if not has_role(ctx, LEAD_ROLE_ID):
        return

    warn_data.pop(member.id, None)

    embed = discord.Embed(
        title="💜 Trade Market | Warn Removed",
        description=f"**User:** {member.mention}",
        color=PURPLE
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Trade Market | Moderation Logs")

    await ctx.send(embed=embed)


# ================= INFO COMMANDS =================

@bot.command()
async def about(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.send("❌ You don't have permission to use this command!")
        return

    embed = discord.Embed(
        title="💜 Trade Market | About Server",
        description="""
Welcome to **Trade Market** — a place where traders meet, exchange and grow together.

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

    embed.set_footer(text="Trade Market | Official Server")
    await ctx.send(embed=embed)


@bot.command()
async def rules(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.send("❌ You don't have permission to use this command!")
        return

    embed = discord.Embed(
        title="💜 Trade Market | Server Rules",
        description="Welcome to **Trade Market**! To keep our community safe and fun, please follow these rules:",
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

    embed.set_footer(text="Trade Market | Official Server")
    await ctx.send(embed=embed)


@bot.command()
async def mmtos(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.send("❌ You don't have permission to use this command!")
        return

    embed = discord.Embed(
        title="💜 Trade Market | Middleman Terms of Service",
        description="Welcome to **Trade Market MM Services**! To ensure **safe and fair trades**, please read the rules below carefully.",
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

    embed.set_footer(text="Trade Market | Official Middleman Terms")
    await ctx.send(embed=embed)


@bot.command()
async def value(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Market | Official Value List",
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
async def marketrules(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Market | Marketplace Rules",
        description="Welcome to the **Trade Market Marketplace**! To ensure a **safe and fair trading environment**, please follow these rules carefully.",
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
async def staffapp(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Market | Staff Application",
        description="""
Interested in becoming a **staff member** at **Trade Market**?  

We are looking for **dedicated, responsible, and active members** to help manage and moderate the server.  
If you think you have what it takes, please **DM me directly** to submit your application.  

**When applying, make sure to include the following information:**  
• **Discord Name & Tag** (e.g., User#1234)  
• **Previous Experience** in moderation, trading, or community management  
• **Why you want to join our staff team**  
• **Your availability** (how many hours per week you can dedicate)  
• **Any relevant skills** (Discord bots, community support, etc.)  

Applications will be **reviewed carefully**, and selected candidates will be contacted for further steps.  
We value honesty, responsibility, and enthusiasm — make sure your application **reflects your dedication**. 💜  

Thank you for your interest in helping make **Trade Market** a better and safer community!
""",
        color=PURPLE
    )

    embed.set_footer(text=f"{ctx.guild.name} | Official Staff Application")
    await ctx.send(embed=embed)


@bot.command(name="tos")
async def tos(ctx):
    embed = discord.Embed(
        title="💜 Trade Market | Server TOS",
        description=(
            "# TRADE MARKET\n"
            "## Server Terms of Service\n\n"
            "### Welcome\n"
            "Welcome to **Trade Market**. Please read the following terms before using the server.\n\n"
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
            "Trade safely, respect others, and enjoy your time in **Trade Market**."
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Market | Administration")
    await ctx.send(embed=embed)


@bot.command(name="support")
async def support(ctx):
    if FOUNDER_ROLE_ID not in [role.id for role in ctx.author.roles]:
        return await ctx.send("❌ Only the Founder can use this command.")

    embed = discord.Embed(
        title="💜 Trade Market | Support",
        description=(
            "# TRADE MARKET SUPPORT\n"
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
            "Thank you for using **Trade Market Support** 💜"
        ),
        color=PURPLE
    )

    embed.set_footer(text="Trade Market | Support Team")
    await ctx.send(embed=embed)

# ================= MODERATION =================

@bot.command()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    if not has_any_role(ctx.author, EXECUTIVE_ROLE_ID):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "kick", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title="💜 Trade Market | User Kicked",
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
    embed.set_footer(text="Trade Market | Moderation System")

    await member.kick(reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if not has_any_role(ctx.author, EXECUTIVE_ROLE_ID):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "ban", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title="💜 Trade Market | User Banned",
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
    embed.set_footer(text="Trade Market | Moderation System")

    await ctx.guild.ban(member, reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)


@bot.command()
async def unban(ctx, user_id: int, *, reason="No reason provided"):
    if not has_any_role(ctx.author, EXECUTIVE_ROLE_ID):
        return await ctx.send("❌ Only Executive can use this command.")

    if not is_owner_bypass(ctx.author):
        allowed, remaining = check_command_cooldown(ctx.author.id, "unban", 300)
        if not allowed:
            return await ctx.send(f"❌ Cooldown active. Try again in **{remaining}s**.")

    user = await bot.fetch_user(user_id)

    action_time = discord.utils.utcnow()

    embed = discord.Embed(
        title="💜 Trade Market | User Unbanned",
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
    embed.set_footer(text="Trade Market | Moderation System")

    await ctx.guild.unban(user, reason=f"{reason} | By: {ctx.author}")

    await ctx.send(embed=embed)

    log = await get_log_channel(ctx.guild)
    if log:
        await log.send(embed=embed)

@bot.event
async def on_member_join(member):

    guild = member.guild

    welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
    invite_channel = guild.get_channel(INVITE_LOG_CHANNEL_ID)

    inviter = "Unknown"
    used_invite = "Unknown"

    new_invites = await guild.invites()
    old_invites = invite_cache.get(guild.id)

    if old_invites:
        for new in new_invites:
            for old in old_invites:
                if new.code == old.code and new.uses > old.uses:
                    inviter = new.inviter.mention
                    used_invite = new.code

    invite_cache[guild.id] = new_invites

    # ================= WELCOME EMBED =================

    welcome_embed = discord.Embed(
        title="💜 Trade Market | Welcome",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Welcome {member.mention}!**\n\n"
            "We are happy to have you in **Trade Market**.\n\n"
            "**Trade safely, respect others, and enjoy your stay!**\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=PURPLE
    )

    welcome_embed.set_thumbnail(url=member.display_avatar.url)
    welcome_embed.set_footer(text="Trade Market | Welcome System")

    if welcome_channel:
        await welcome_channel.send(embed=welcome_embed)

    # ================= INVITE EMBED =================

    invite_embed = discord.Embed(
        title="📈 Trade Market | New Member Joined",
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
    invite_embed.set_footer(text="Trade Market | Invite Tracker")

    if invite_channel:
        await invite_channel.send(embed=invite_embed)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    for guild in bot.guilds:
        invite_cache[guild.id] = await guild.invites()

    bot.add_view(MercyView(None))


token = os.getenv("TOKEN")

if not token:
    raise ValueError("TOKEN environment variable not set")

bot.run(token)