import discord
from discord.ext import commands
from core.database import Database
from utils.helpers import create_embed
from utils.paginator import Paginator
import psutil
import time
from datetime import datetime
import platform


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.start_time = time.time()

    @commands.command()
    async def help(self, ctx, *, command: str = None):
        f"""Show available commands or get detailed help for a specific command
        
        **Usage:** `{ctx.prefix}help [command]`
        **Examples:**
        • `{ctx.prefix}help` (show all commands)
        • `{ctx.prefix}help ban` (detailed help for ban command)
        • `{ctx.prefix}help setup` (help for setup commands)
        
        Commands are organized by category for easy browsing.
        """
        if command:
            # Show help for specific command
            cmd = self.bot.get_command(command)
            if not cmd:
                embed = create_embed(
                    title="❌ Command Not Found",
                    description=f"No command named `{command}` found",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            embed = create_embed(
                title=f"Help: {cmd.name}",
                description=cmd.help or "No description available",
                color=discord.Color.blue(),
            )

            if cmd.aliases:
                embed.add_field(
                    name="Aliases",
                    value=", ".join(f"`{alias}`" for alias in cmd.aliases),
                    inline=False,
                )

            if hasattr(cmd, "signature"):
                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}{cmd.name} {cmd.signature}`",
                    inline=False,
                )

            await ctx.send(embed=embed)
        else:
            # Show main help menu - dynamically discover commands
            embed = create_embed(
                title="🤖 Rainbot Help",
                description="A powerful Discord moderation bot",
                color=discord.Color.blue(),
            )

            # Categorize commands by cog
            categories = {
                "🛡️ Moderation": [],
                "⚙️ Setup": [],
                "🎭 Roles": [],
                "📝 Tags": [],
                "🎉 Giveaways": [],
                "📊 Utility": [],
                "🔧 Owner": [],
            }

            # Get all commands and categorize them
            for cmd in self.bot.commands:
                if cmd.hidden:
                    continue

                # Skip subcommands (they'll be shown with their parent)
                if hasattr(cmd, "parent") and cmd.parent:
                    continue

                cog_name = cmd.cog.qualified_name if cmd.cog else "No Category"

                if cog_name == "Moderation":
                    categories["🛡️ Moderation"].append(cmd.name)
                elif cog_name == "Setup":
                    categories["⚙️ Setup"].append(cmd.name)
                elif cog_name == "Roles":
                    categories["🎭 Roles"].append(cmd.name)
                elif cog_name == "Tags":
                    categories["📝 Tags"].append(cmd.name)
                elif cog_name == "Giveaways":
                    categories["🎉 Giveaways"].append(cmd.name)
                elif cog_name == "Utils":
                    # Skip owner-only commands for regular users
                    if any(check.__name__ == "is_owner" for check in cmd.checks):
                        if await self.bot.is_owner(ctx.author):
                            categories["🔧 Owner"].append(cmd.name)
                    else:
                        categories["📊 Utility"].append(cmd.name)
                elif cog_name == "AutoMod":
                    categories["⚙️ Setup"].append(cmd.name)
                elif cog_name == "Notes":
                    categories["🛡️ Moderation"].append(cmd.name)
                else:
                    categories["📊 Utility"].append(cmd.name)

            # Add categories with commands to embed
            for category, cmds in categories.items():
                if cmds:  # Only show categories that have commands
                    cmd_list = ", ".join(f"`{cmd}`" for cmd in sorted(cmds))
                    embed.add_field(name=category, value=cmd_list, inline=False)

            embed.set_footer(text=f"Use {ctx.prefix}help <command> for detailed help")
            await ctx.send(embed=embed)

    @commands.command(aliases=["botinfo"])
    async def about(self, ctx):
        """Display bot information, version, and basic statistics"""
        uptime = time.time() - self.start_time
        uptime_str = str(datetime.utcfromtimestamp(uptime).strftime("%H:%M:%S"))

        embed = create_embed(
            title="🤖 About Rainbot",
            description="A powerful Discord moderation bot",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Made with ❤️ by the Rainbot team")

        await ctx.send(embed=embed)

    @commands.command(aliases=["serverinfo", "si"])
    async def server(self, ctx):
        f"""Show detailed information about the current server
        
        **Usage:** `{ctx.prefix}server`
        **Aliases:** `{ctx.prefix}serverinfo`, `{ctx.prefix}si`
        **Shows:**
        • Server name, owner, creation date
        • Member count, channel count, role count
        • Verification level, boost status
        • Server icon and ID
        
        Great for getting a quick overview of server statistics.
        """
        guild = ctx.guild

        embed = create_embed(title=f"📊 {guild.name}", color=discord.Color.blue())

        embed.add_field(
            name="Owner",
            value=guild.owner.mention if guild.owner else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True
        )
        embed.add_field(
            name="Region",
            value=str(guild.region) if hasattr(guild, "region") else "Unknown",
            inline=True,
        )

        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)

        embed.add_field(
            name="Verification",
            value=str(guild.verification_level).title(),
            inline=True,
        )
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(
            name="Boosts", value=str(guild.premium_subscription_count), inline=True
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text=f"ID: {guild.id}")

        await ctx.send(embed=embed)

    @commands.command(aliases=["userinfo", "ui"])
    async def user(self, ctx, *, user: discord.Member = None):
        f"""Display detailed information about a user or yourself
        
        **Usage:** `{ctx.prefix}user [user]`
        **Examples:**
        • `{ctx.prefix}user` (your own info)
        • `{ctx.prefix}user @someone` (their info)
        • `{ctx.prefix}ui @user` (alias)
        
        Shows join date, account creation, roles, status, and more.
        """
        user = user or ctx.author

        embed = create_embed(
            title=f"👤 {user}",
            color=(
                user.color
                if user.color != discord.Color.default()
                else discord.Color.blue()
            ),
        )

        embed.add_field(name="ID", value=str(user.id), inline=True)
        embed.add_field(
            name="Created", value=user.created_at.strftime("%Y-%m-%d"), inline=True
        )
        embed.add_field(
            name="Joined",
            value=user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "Unknown",
            inline=True,
        )

        embed.add_field(name="Status", value=str(user.status).title(), inline=True)
        embed.add_field(
            name="Activity",
            value=user.activity.name if user.activity else "None",
            inline=True,
        )
        embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)

        if user.roles[1:]:  # Exclude @everyone
            roles = ", ".join(role.mention for role in user.roles[1:][:10])
            if len(user.roles) > 11:
                roles += f" (+{len(user.roles) - 11} more)"
            embed.add_field(name="Roles", value=roles, inline=False)

        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author}")

        await ctx.send(embed=embed)

    @commands.command()
    async def stats(self, ctx):
        """Show comprehensive bot performance and usage statistics"""
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        cpu_usage = process.cpu_percent()

        uptime = time.time() - self.start_time
        uptime_str = str(
            datetime.utcfromtimestamp(uptime).strftime("%d days, %H:%M:%S")
        )

        embed = create_embed(title="📊 Bot Statistics", color=discord.Color.blue())

        # Bot stats
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.commands)), inline=True)

        # System stats
        embed.add_field(
            name="Memory Usage", value=f"{memory_usage:.1f} MB", inline=True
        )
        embed.add_field(name="CPU Usage", value=f"{cpu_usage:.1f}%", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        # Discord stats
        embed.add_field(
            name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True
        )
        embed.add_field(
            name="Shards", value=str(self.bot.shard_count or 1), inline=True
        )
        embed.add_field(name="Version", value=discord.__version__, inline=True)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def eval(self, ctx, *, code: str):
        """Execute Python code for debugging and testing (bot owner only)"""
        import textwrap
        import io
        import contextlib

        code = code.strip("` ")
        if code.startswith("py"):
            code = code[2:]

        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'

        try:
            exec(to_compile, globals())
        except Exception as e:
            embed = create_embed(
                title="❌ Compilation Error",
                description=f"```py\n{e.__class__.__name__}: {e}\n```",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        func = globals()["func"]
        try:
            with contextlib.redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            embed = create_embed(
                title="❌ Runtime Error",
                description=f"```py\n{value}{e.__class__.__name__}: {e}\n```",
                color=discord.Color.red(),
            )
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    embed = create_embed(
                        title="✅ Evaluation Result",
                        description=f"```py\n{value}\n```",
                        color=discord.Color.green(),
                    )
                else:
                    embed = create_embed(
                        title="✅ Evaluation Complete",
                        description="No output",
                        color=discord.Color.green(),
                    )
            else:
                embed = create_embed(
                    title="✅ Evaluation Result",
                    description=f"```py\n{value}{ret}\n```",
                    color=discord.Color.green(),
                )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, *, extension: str):
        """Reload a bot extension/module (bot owner only)"""
        try:
            await self.bot.reload_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Reloaded",
                description=f"Successfully reloaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Reload Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, *, extension: str):
        """Load a new bot extension/module (bot owner only)"""
        try:
            await self.bot.load_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Loaded",
                description=f"Successfully loaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Load Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, *, extension: str):
        """Unload a bot extension/module (bot owner only)"""
        try:
            await self.bot.unload_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Unloaded",
                description=f"Successfully unloaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Unload Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command(aliases=["health"])
    @commands.is_owner()
    async def serverhealth(self, ctx):
        """Display server resource usage and system health (bot owner only)"""
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        cpu_usage = process.cpu_percent()

        uptime = time.time() - self.start_time
        uptime_str = str(
            datetime.utcfromtimestamp(uptime).strftime("%d days, %H:%M:%S")
        )

        embed = create_embed(title="🩺 Server Health", color=discord.Color.green())

        embed.add_field(name="CPU Usage", value=f"{cpu_usage:.1f}%", inline=True)
        embed.add_field(
            name="Memory Usage", value=f"{memory_usage:.1f} MB", inline=True
        )
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)

        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        f"""Test bot responsiveness and show connection latency
        
        **Usage:** `{ctx.prefix}ping`
        **Shows:**
        • Websocket latency to Discord
        • Message response time
        • Database ping time
        • API response time (if available)
        
        Useful for checking if the bot is responding normally.
        """
        import aiohttp
        from config.config import config

        # Websocket latency
        websocket_latency = round(self.bot.latency * 1000)

        # Message response time
        message_start = time.time()
        message = await ctx.send("🏓 Calculating ping...")
        message_latency = round((time.time() - message_start) * 1000)

        # Database latency
        db_latency = "N/A"
        try:
            db_start = time.time()
            await self.db.client.admin.command("ping")
            db_latency = f"{round((time.time() - db_start) * 1000)}ms"
        except Exception:
            db_latency = "Error"

        # API latency (if moderation API is configured)
        api_latency = "N/A"
        if config.api.moderation_api_url:
            try:
                api_start = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{config.api.moderation_api_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            api_latency = f"{round((time.time() - api_start) * 1000)}ms"
                        else:
                            api_latency = "Error"
            except Exception:
                api_latency = "Timeout"

        # Determine overall color based on websocket latency
        color = (
            discord.Color.green()
            if websocket_latency < 100
            else (
                discord.Color.orange()
                if websocket_latency < 300
                else discord.Color.red()
            )
        )

        embed = create_embed(
            title="🏓 Pong!", description="Connection latency measurements", color=color
        )

        embed.add_field(
            name="🌐 Websocket", value=f"{websocket_latency}ms", inline=True
        )
        embed.add_field(name="💬 Message", value=f"{message_latency}ms", inline=True)
        embed.add_field(name="🗄️ Database", value=db_latency, inline=True)
        embed.add_field(name="🔗 API", value=api_latency, inline=True)

        # Add status indicator
        if websocket_latency < 100:
            status = "🟢 Excellent"
        elif websocket_latency < 200:
            status = "🟡 Good"
        elif websocket_latency < 300:
            status = "🟠 Fair"
        else:
            status = "🔴 Poor"

        embed.add_field(name="📊 Status", value=status, inline=True)

        await message.edit(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        f"""Get a link to invite this bot to your own server
        
        **Usage:** `{ctx.prefix}invite`
        **Provides:**
        • Direct invite link with proper permissions
        • All necessary permissions for full functionality
        • Easy one-click setup for your server
        
        Share this with friends who want the bot in their servers!
        """
        embed = create_embed(
            title="📨 Invite rainbot",
            description=f"[Click here to invite me!](https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot&permissions=2013785334)",
            color=discord.Color.blue(),
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def testperms(self, ctx):
        """Check your current permission level in the bot's system"""
        if hasattr(self.bot, "permissions") and self.bot.permissions:
            user_level = await self.bot.permissions.get_user_level(
                ctx.guild, ctx.author
            )
            embed = create_embed(
                title="🔐 Permission Test",
                description=f"Your permission level: **{user_level}**\n"
                f"Bot owners: {list(self.bot.owner_ids) if self.bot.owner_ids else 'None set'}",
                color=discord.Color.blue(),
            )
        else:
            embed = create_embed(
                title="❌ Permission System Error",
                description="Permission system not initialized",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utils(bot))
