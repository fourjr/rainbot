import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import (
    create_embed,
    status_embed,
    update_nested_config,
    remove_nested_config,
)


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command()
    @has_permissions(level=2)
    async def role(self, ctx, member: discord.Member, *, role: discord.Role):
        """Toggles a role for a member (adds if they don't have it, removes if they do).

        **Usage:** `{prefix}role <member> <role>`
        **Examples:**
        - `{prefix}role @user Member`
        - `{prefix}role @user VIP`
        """
        if role in member.roles:
            await member.remove_roles(role, reason=f"Role removed by {ctx.author}")
            action = "removed from"
        else:
            await member.add_roles(role, reason=f"Role added by {ctx.author}")
            action = "added to"

        embed = status_embed(
            title="🎭 Role Updated",
            description=f"{role.mention} has been {action} {member.mention}",
            status="success",
        )
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def selfrole(self, ctx):
        """Manages roles that members can assign to themselves.

        **Usage:** `{prefix}selfrole <subcommand> <role>`
        **Examples:**
        - `{prefix}selfrole add Gamer`
        - `{prefix}selfrole remove Artist`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if not self_roles:
            embed = status_embed(
                title="🎭 Self Roles",
                description="No self-assignable roles configured",
                status="info",
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
        """Makes a role self-assignable.

        **Usage:** `{prefix}selfrole add <role>`
        **Example:** `{prefix}selfrole add Gamer`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if role.id in self_roles:
            embed = status_embed(
                title="❌ Already Added",
                description=f"{role.mention} is already a self-assignable role",
                status="error",
            )
        else:
            self_roles.append(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"self_roles": self_roles})
            embed = status_embed(
                title="✅ Self Role Added",
                description=f"{role.mention} is now self-assignable",
                status="success",
            )
        await ctx.send(embed=embed)

    @selfrole.command(name="remove")
    @has_permissions(level=3)
    async def selfrole_remove(self, ctx, *, role: discord.Role):
        """Removes a role from the self-assignable list.

        **Usage:** `{prefix}selfrole remove <role>`
        **Example:** `{prefix}selfrole remove Artist`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        if role.id not in self_roles:
            embed = status_embed(
                title="❌ Not Found",
                description=f"{role.mention} is not a self-assignable role",
                status="error",
            )
        else:
            self_roles.remove(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"self_roles": self_roles})
            embed = status_embed(
                title="✅ Self Role Removed",
                description=f"{role.mention} is no longer self-assignable",
                status="success",
            )
        await ctx.send(embed=embed)

    @commands.command()
    async def iam(self, ctx, *, role_name: str):
        """Assigns a self-assignable role to you.

        **Usage:** `{prefix}iam <role_name>`
        **Examples:**
        - `{prefix}iam Gamer`
        - `{prefix}iam Artist`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        # Find role by name
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            embed = status_embed(
                title="❌ Role Not Found",
                description=f"Role '{role_name}' not found",
                status="error",
            )
            await ctx.send(embed=embed)
            return
        if role.id not in self_roles:
            embed = status_embed(
                title="❌ Not Self-Assignable",
                description=f"{role.mention} is not self-assignable",
                status="error",
            )
            await ctx.send(embed=embed)
            return
        if role in ctx.author.roles:
            embed = status_embed(
                title="❌ Already Have Role",
                description=f"You already have {role.mention}",
                status="error",
            )
        else:
            await ctx.author.add_roles(role, reason="Self-assigned role")
            embed = status_embed(
                title="✅ Role Assigned",
                description=f"You now have {role.mention}",
                status="success",
            )
        await ctx.send(embed=embed)

    @commands.command()
    async def iamnot(self, ctx, *, role_name: str):
        """Removes a self-assignable role from you.

        **Usage:** `{prefix}iamnot <role_name>`
        **Examples:**
        - `{prefix}iamnot Gamer`
        - `{prefix}iamnot Artist`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        self_roles = config.get("self_roles", [])

        # Find role by name
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            embed = status_embed(
                title="❌ Role Not Found",
                description=f"Role '{role_name}' not found",
                status="error",
            )
            await ctx.send(embed=embed)
            return
        if role.id not in self_roles:
            embed = status_embed(
                title="❌ Not Self-Assignable",
                description=f"{role.mention} is not self-assignable",
                status="error",
            )
            await ctx.send(embed=embed)
            return
        if role not in ctx.author.roles:
            embed = status_embed(
                title="❌ Don't Have Role",
                description=f"You don't have {role.mention}",
                status="error",
            )
        else:
            await ctx.author.remove_roles(role, reason="Self-removed role")
            embed = status_embed(
                title="✅ Role Removed",
                description=f"You no longer have {role.mention}",
                status="success",
            )
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @has_permissions(level=3)
    async def autorole(self, ctx):
        """Manages roles that are automatically assigned to new members.

        **Usage:** `{prefix}autorole <subcommand> <role>`
        **Examples:**
        - `{prefix}autorole add Member`
        - `{prefix}autorole remove Verified`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if not auto_roles:
            embed = status_embed(
                title="🤖 Auto Roles",
                description="No auto roles configured",
                status="info",
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
        """Adds a role to be automatically assigned to new members.

        **Usage:** `{prefix}autorole add <role>`
        **Example:** `{prefix}autorole add Member`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if role.id in auto_roles:
            embed = status_embed(
                title="❌ Already Added",
                description=f"{role.mention} is already an auto role",
                status="error",
            )
        else:
            auto_roles.append(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"auto_roles": auto_roles})
            embed = status_embed(
                title="✅ Auto Role Added",
                description=f"{role.mention} will be given to new members",
                status="success",
            )
        await ctx.send(embed=embed)

    @autorole.command(name="remove")
    @has_permissions(level=3)
    async def autorole_remove(self, ctx, *, role: discord.Role):
        """Removes a role from the autorole list.

        **Usage:** `{prefix}autorole remove <role>`
        **Example:** `{prefix}autorole remove Verified`
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        auto_roles = config.get("auto_roles", [])

        if role.id not in auto_roles:
            embed = status_embed(
                title="❌ Not Found",
                description=f"{role.mention} is not an auto role",
                status="error",
            )
        else:
            auto_roles.remove(role.id)
            await self.db.update_guild_config(ctx.guild.id, {"auto_roles": auto_roles})
            embed = status_embed(
                title="✅ Auto Role Removed",
                description=f"{role.mention} will no longer be given to new members",
                status="success",
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
        """Manages roles that are assigned by reacting to a message.

        **Usage:** `{prefix}reactionrole <subcommand>`
        **Examples:**
        - `{prefix}reactionrole add <message_link> 🎮 @Gamer`
        - `{prefix}reactionrole remove <message_link> 🎮`
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
        """Links a reaction on a message to a role.

        **Usage:** `{prefix}reactionrole add <message_link> <emoji> <role>`
        **Example:** `{prefix}reactionrole add https://discord.com/... 🎮 @Gamer`
        """
        try:
            await message.add_reaction(emoji)
            key = f"{message.id}_{emoji}"
            await update_nested_config(
                self.db, ctx.guild.id, "reaction_roles", key, role.id
            )
            embed = status_embed(
                title="✅ Reaction Role Set",
                description=f"Reacting with {emoji} will give {role.mention}",
                status="success",
            )
            await ctx.send(embed=embed)
        except discord.NotFound:
            embed = status_embed(
                title="❌ Message Not Found",
                description="Could not find the specified message",
                status="error",
            )
            await ctx.send(embed=embed)

    @reactionrole.command(name="remove")
    @has_permissions(level=3)
    async def reactionrole_remove(self, ctx, message: discord.Message, emoji: str):
        """Removes a reaction role from a message.

        **Usage:** `{prefix}reactionrole remove <message_link> <emoji>`
        **Example:** `{prefix}reactionrole remove https://discord.com/... 🎮`
        """
        key = f"{message.id}_{emoji}"
        await remove_nested_config(self.db, ctx.guild.id, "reaction_roles", key)
        embed = status_embed(
            title="✅ Reaction Role Removed",
            description=f"Reaction role for {emoji} on message {message.id} has been removed.",
            status="success",
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


async def setup(bot):
    await bot.add_cog(Roles(bot))
