import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command()
    @has_permissions(level=2)
    async def role(self, ctx, member: discord.Member, *, role: discord.Role):
        f"""Add or remove a role from a member (toggles if they already have it)
        
        **Usage:** `{ctx.prefix}role <member> <role>`
        **Examples:**
        • `{ctx.prefix}role @user Member` (add Member role)
        • `{ctx.prefix}role @user VIP` (remove VIP role if they have it)
        
        Automatically adds the role if they don't have it, removes if they do.
        """
        if role in member.roles:
            await member.remove_roles(role, reason=f"Role removed by {ctx.author}")
            action = "removed from"
            color = discord.Color.red()
        else:
            await member.add_roles(role, reason=f"Role added by {ctx.author}")
            action = "added to"
            color = discord.Color.green()

        embed = create_embed(
            title="🎭 Role Updated",
            description=f"{role.mention} has been {action} {member.mention}",
            color=color,
        )
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def selfrole(self, ctx):
        f"""Manage roles that members can assign to themselves
        
        **Usage:** `{ctx.prefix}selfrole [add/remove] [role]`
        **Examples:**
        • `{ctx.prefix}selfrole` (list available self-roles)
        • `{ctx.prefix}selfrole add Gamer` (make Gamer self-assignable)
        • `{ctx.prefix}selfrole remove Artist` (remove from self-assignable)
        
        Members can then use `{ctx.prefix}iam <role>` to get these roles.
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if not self_roles:
            embed = create_embed(
                title="🎭 Self Roles",
                description="No self-assignable roles configured",
                color=discord.Color.blue(),
            )
        else:
            roles = [ctx.guild.get_role(role_id) for role_id in self_roles]
            roles = [role for role in roles if role]  # Filter out None values

            embed = create_embed(
                title="🎭 Self Roles",
                description="Available self-assignable roles:",
                color=discord.Color.blue(),
            )

            for role in roles:
                embed.add_field(name=role.name, value=role.mention, inline=True)

        await ctx.send(embed=embed)

    @selfrole.command(name="add")
    @has_permissions(level=3)
    async def selfrole_add(self, ctx, *, role: discord.Role):
        """Make a role self-assignable by members"""
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if role.id in self_roles:
            embed = create_embed(
                title="❌ Already Added",
                description=f"{role.mention} is already a self-assignable role",
                color=discord.Color.red(),
            )
        else:
            self_roles.append(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"self_roles": self_roles})

            embed = create_embed(
                title="✅ Self Role Added",
                description=f"{role.mention} is now self-assignable",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @selfrole.command(name="remove")
    @has_permissions(level=3)
    async def selfrole_remove(self, ctx, *, role: discord.Role):
        """Remove a role from the self-assignable list"""
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if role.id not in self_roles:
            embed = create_embed(
                title="❌ Not Found",
                description=f"{role.mention} is not a self-assignable role",
                color=discord.Color.red(),
            )
        else:
            self_roles.remove(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"self_roles": self_roles})

            embed = create_embed(
                title="✅ Self Role Removed",
                description=f"{role.mention} is no longer self-assignable",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    async def iam(self, ctx, *, role_name: str):
        f"""Give yourself a self-assignable role by name
        
        **Usage:** `{ctx.prefix}iam <role_name>`
        **Examples:**
        • `{ctx.prefix}iam Gamer`
        • `{ctx.prefix}iam Artist`
        • `{ctx.prefix}iam Movie Lover`
        
        Only works with roles that moderators have made self-assignable.
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        # Find role by name
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            embed = create_embed(
                title="❌ Role Not Found",
                description=f"Role '{role_name}' not found",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if role.id not in self_roles:
            embed = create_embed(
                title="❌ Not Self-Assignable",
                description=f"{role.mention} is not self-assignable",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if role in ctx.author.roles:
            embed = create_embed(
                title="❌ Already Have Role",
                description=f"You already have {role.mention}",
                color=discord.Color.red(),
            )
        else:
            await ctx.author.add_roles(role, reason="Self-assigned role")
            embed = create_embed(
                title="✅ Role Assigned",
                description=f"You now have {role.mention}",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    async def iamnot(self, ctx, *, role_name: str):
        f"""Remove a self-assignable role from yourself by name
        
        **Usage:** `{ctx.prefix}iamnot <role_name>`
        **Examples:**
        • `{ctx.prefix}iamnot Gamer`
        • `{ctx.prefix}iamnot Artist`
        • `{ctx.prefix}iamnot Movie Lover`
        
        Only works with self-assignable roles you currently have.
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        # Find role by name
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            embed = create_embed(
                title="❌ Role Not Found",
                description=f"Role '{role_name}' not found",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if role.id not in self_roles:
            embed = create_embed(
                title="❌ Not Self-Assignable",
                description=f"{role.mention} is not self-assignable",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if role not in ctx.author.roles:
            embed = create_embed(
                title="❌ Don't Have Role",
                description=f"You don't have {role.mention}",
                color=discord.Color.red(),
            )
        else:
            await ctx.author.remove_roles(role, reason="Self-removed role")
            embed = create_embed(
                title="✅ Role Removed",
                description=f"You no longer have {role.mention}",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def autorole(self, ctx):
        f"""Manage roles automatically given to new members when they join
        
        **Usage:** `{ctx.prefix}autorole [add/remove] [role]`
        **Examples:**
        • `{ctx.prefix}autorole` (list current auto-roles)
        • `{ctx.prefix}autorole add Member` (give Member to new joiners)
        • `{ctx.prefix}autorole remove Verified` (stop auto-assigning Verified)
        
        New members will automatically receive these roles when they join.
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if not auto_roles:
            embed = create_embed(
                title="🤖 Auto Roles",
                description="No auto roles configured",
                color=discord.Color.blue(),
            )
        else:
            roles = [ctx.guild.get_role(role_id) for role_id in auto_roles]
            roles = [role for role in roles if role]

            embed = create_embed(
                title="🤖 Auto Roles",
                description="Roles automatically given to new members:",
                color=discord.Color.blue(),
            )

            for role in roles:
                embed.add_field(name=role.name, value=role.mention, inline=True)

        await ctx.send(embed=embed)

    @autorole.command(name="add")
    @has_permissions(level=3)
    async def autorole_add(self, ctx, *, role: discord.Role):
        """Add a role to be automatically given to new members"""
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if role.id in auto_roles:
            embed = create_embed(
                title="❌ Already Added",
                description=f"{role.mention} is already an auto role",
                color=discord.Color.red(),
            )
        else:
            auto_roles.append(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"auto_roles": auto_roles})

            embed = create_embed(
                title="✅ Auto Role Added",
                description=f"{role.mention} will be given to new members",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @autorole.command(name="remove")
    @has_permissions(level=3)
    async def autorole_remove(self, ctx, *, role: discord.Role):
        """Stop automatically giving a role to new members"""
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if role.id not in auto_roles:
            embed = create_embed(
                title="❌ Not Found",
                description=f"{role.mention} is not an auto role",
                color=discord.Color.red(),
            )
        else:
            auto_roles.remove(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"auto_roles": auto_roles})

            embed = create_embed(
                title="✅ Auto Role Removed",
                description=f"{role.mention} will no longer be given to new members",
                color=discord.Color.green(),
            )

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Give auto roles to new members"""
        config = await self.db.get_guild_config(member.guild.id)
        auto_roles = config.get("auto_roles", [])

        if auto_roles:
            roles = [member.guild.get_role(role_id) for role_id in auto_roles]
            roles = [role for role in roles if role and role < member.guild.me.top_role]

            if roles:
                await member.add_roles(*roles, reason="Auto role assignment")

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def reactionrole(self, ctx):
        f"""Set up roles that members can get by reacting to messages
        
        **Usage:** `{ctx.prefix}reactionrole add <message_link> <emoji> <role>`
        **Examples:**
        • `{ctx.prefix}reactionrole add [message] 🎮 Gamer`
        • `{ctx.prefix}reactionrole add [message] 🎨 Artist`
        • `{ctx.prefix}reactionrole remove [message] 🎮`
        
        Members get/lose roles by reacting to the message with the emoji.
        """
        embed = create_embed(
            title="⚡ Reaction Roles",
            description=f"Use `{ctx.prefix}reactionrole add` to configure reaction roles",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="add")
    @has_permissions(level=3)
    async def reactionrole_add(
        self, ctx, message: discord.Message, emoji: str, role: discord.Role
    ):
        """Link an emoji reaction to a role on a specific message"""
        try:
            await message.add_reaction(emoji)

            await self.db.update_guild_config(
                ctx.guild.id, {f"reaction_roles.{message.id}_{emoji}": role.id}
            )

            embed = create_embed(
                title="✅ Reaction Role Set",
                description=f"Reacting with {emoji} will give {role.mention}",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

        except discord.NotFound:
            embed = create_embed(
                title="❌ Message Not Found",
                description="Could not find the specified message",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)

    @reactionrole.command(name="remove")
    @has_permissions(level=3)
    async def reactionrole_remove(self, ctx, message: discord.Message, emoji: str):
        """Remove a reaction role from a message"""
        await self.db.update_guild_config(
            ctx.guild.id, {f"$unset": {f"reaction_roles.{message.id}_{emoji}": ""}}
        )

        embed = create_embed(
            title="✅ Reaction Role Removed",
            description=f"Reaction role for {emoji} on message {message.id} has been removed.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction role assignment"""
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        config = await self.db.get_guild_config(guild.id)
        reaction_roles = config.get("reaction_roles", {})
        key = f"{payload.message_id}_{payload.emoji}"

        if key in reaction_roles:
            role_id = reaction_roles[key]
            role = guild.get_role(role_id)
            if role:
                member = guild.get_member(payload.user_id)
                if member and role not in member.roles:
                    await member.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction role removal"""
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        config = await self.bot.db.get_guild_config(guild.id)
        reaction_roles = config.get("reaction_roles", {})
        key = f"{payload.message_id}_{payload.emoji}"

        if key in reaction_roles:
            role_id = reaction_roles[key]
            role = guild.get_role(role_id)
            if role:
                member = guild.get_member(payload.user_id)
                if member and role in member.roles:
                    await member.remove_roles(role, reason="Reaction role removed")

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def reactionrole2(self, ctx):
        """Alternative reaction role setup method"""
        embed = create_embed(
            title="⚡ Reaction Roles",
            description=f"Use `{ctx.prefix}reactionrole setup` to configure reaction roles",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @reactionrole2.command()
    @has_permissions(level=3)
    async def setup(self, ctx, message_id: int, emoji: str, *, role: discord.Role):
        """Set up a reaction role using message ID instead of message object"""
        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.add_reaction(emoji)

            # Store in database
            reaction_roles = await self.db.get_reaction_roles(ctx.guild.id)
            key = f"{message_id}_{emoji}"
            reaction_roles[key] = role.id
            await self.db.update_reaction_roles(ctx.guild.id, reaction_roles)

            embed = create_embed(
                title="✅ Reaction Role Set",
                description=f"Reacting with {emoji} will give {role.mention}",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

        except discord.NotFound:
            embed = create_embed(
                title="❌ Message Not Found",
                description="Could not find the specified message",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle reaction role assignment"""
        if user.bot or not reaction.message.guild:
            return

        reaction_roles = await self.db.get_reaction_roles(reaction.message.guild.id)
        key = f"{reaction.message.id}_{str(reaction.emoji)}"

        if key in reaction_roles:
            role = reaction.message.guild.get_role(reaction_roles[key])
            if role and role not in user.roles:
                await user.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        """Handle reaction role removal"""
        if user.bot or not reaction.message.guild:
            return

        reaction_roles = await self.db.get_reaction_roles(reaction.message.guild.id)
        key = f"{reaction.message.id}_{str(reaction.emoji)}"

        if key in reaction_roles:
            role = reaction.message.guild.get_role(reaction_roles[key])
            if role and role in user.roles:
                await user.remove_roles(role, reason="Reaction role removed")


async def setup(bot):
    await bot.add_cog(Roles(bot))
