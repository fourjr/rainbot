import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed
import re


class Tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.group(invoke_without_command=True)
    async def tag(self, ctx, *, name: str = None):
        f"""Create and use custom text responses (tags) for quick replies
        
        **Usage:** `{ctx.prefix}tag [name]` or `{ctx.prefix}tag <subcommand>`
        **Examples:**
        • `{ctx.prefix}tag` (list all tags)
        • `{ctx.prefix}tag rules` (use the 'rules' tag)
        • `{ctx.prefix}tag add welcome Welcome to our server!`
        • `{ctx.prefix}tag edit rules Updated server rules here`
        • `{ctx.prefix}tag delete oldtag`
        
        Tags support variables like {{user}}, {{server}}, {{channel}}.
        """
        if name is None:
            # List all tags
            tags = await self.db.get_tags(ctx.guild.id)

            if not tags:
                embed = create_embed(
                    title="📝 Tags",
                    description="No tags found for this server",
                    color=discord.Color.blue(),
                )
            else:
                tag_list = ", ".join(f"`{tag}`" for tag in tags.keys())
                embed = create_embed(
                    title="📝 Available Tags",
                    description=tag_list,
                    color=discord.Color.blue(),
                )

            await ctx.send(embed=embed)
        else:
            # Use a tag
            tags = await self.db.get_tags(ctx.guild.id)

            if name.lower() not in tags:
                embed = create_embed(
                    title="❌ Tag Not Found",
                    description=f"Tag `{name}` doesn't exist",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            content = tags[name.lower()]

            # Process variables
            from utils.helpers import apply_vars

            content = apply_vars(self.bot, content, ctx.message, "")

            # Increment usage count
            await self.db.increment_tag_usage(ctx.guild.id, name.lower())

            await ctx.send(content)

    @tag.command(name="add", aliases=["create"])
    @has_permissions(level=2)
    async def tag_add(self, ctx, name: str, *, content: str):
        """Create a new tag with the specified name and content"""
        if len(name) > 50:
            embed = create_embed(
                title="❌ Name Too Long",
                description="Tag names must be 50 characters or less",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if len(content) > 2000:
            embed = create_embed(
                title="❌ Content Too Long",
                description="Tag content must be 2000 characters or less",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() in tags:
            embed = create_embed(
                title="❌ Tag Exists",
                description=f"Tag `{name}` already exists",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.db.add_tag(ctx.guild.id, name.lower(), content, ctx.author.id)

        embed = create_embed(
            title="✅ Tag Created",
            description=f"Tag `{name}` has been created",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @tag.command(name="edit", aliases=["update"])
    @has_permissions(level=2)
    async def tag_edit(self, ctx, name: str, *, content: str):
        """Modify the content of an existing tag"""
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = create_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if len(content) > 2000:
            embed = create_embed(
                title="❌ Content Too Long",
                description="Tag content must be 2000 characters or less",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.db.update_tag(ctx.guild.id, name.lower(), content)

        embed = create_embed(
            title="✅ Tag Updated",
            description=f"Tag `{name}` has been updated",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @tag.command(name="delete", aliases=["remove"])
    @has_permissions(level=2)
    async def tag_delete(self, ctx, *, name: str):
        """Permanently delete a tag from the server"""
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = create_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.db.delete_tag(ctx.guild.id, name.lower())

        embed = create_embed(
            title="✅ Tag Deleted",
            description=f"Tag `{name}` has been deleted",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @tag.command(name="info")
    async def tag_info(self, ctx, *, name: str):
        """Show detailed information about a tag (creator, usage count, etc.)"""
        tag_info = await self.db.get_tag_info(ctx.guild.id, name.lower())

        if not tag_info:
            embed = create_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        creator = self.bot.get_user(tag_info["creator_id"])
        creator_name = creator.name if creator else "Unknown User"

        embed = create_embed(title=f"📝 Tag Info: {name}", color=discord.Color.blue())
        embed.add_field(name="Creator", value=creator_name, inline=True)
        embed.add_field(name="Uses", value=str(tag_info.get("uses", 0)), inline=True)
        embed.add_field(
            name="Created", value=tag_info.get("created_at", "Unknown"), inline=True
        )

        await ctx.send(embed=embed)

    @tag.command(name="search")
    async def tag_search(self, ctx, *, query: str):
        """Find tags that contain the specified text in their name"""
        tags = await self.db.get_tags(ctx.guild.id)

        matching_tags = [name for name in tags.keys() if query.lower() in name.lower()]

        if not matching_tags:
            embed = create_embed(
                title="🔍 Search Results",
                description=f"No tags found matching `{query}`",
                color=discord.Color.blue(),
            )
        else:
            tag_list = ", ".join(
                f"`{tag}`" for tag in matching_tags[:20]
            )  # Limit to 20 results
            embed = create_embed(
                title=f"🔍 Search Results for '{query}'",
                description=tag_list,
                color=discord.Color.blue(),
            )

            if len(matching_tags) > 20:
                embed.set_footer(
                    text=f"Showing first 20 of {len(matching_tags)} results"
                )

        await ctx.send(embed=embed)

    @tag.command(name="raw")
    async def tag_raw(self, ctx, *, name: str):
        """Display the raw, unprocessed content of a tag"""
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = create_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        content = tags[name.lower()]

        # Use code block to show raw content
        if len(content) > 1990:  # Account for code block formatting
            content = content[:1990] + "..."

        await ctx.send(f"```\n{content}\n```")

    @commands.group(invoke_without_command=True)
    @has_permissions(level=2)
    async def canned(self, ctx):
        f"""Manage pre-written responses for common moderation situations
        
        **Usage:** `{ctx.prefix}canned [subcommand]`
        **Examples:**
        • `{ctx.prefix}canned` (list all canned responses)
        • `{ctx.prefix}canned add spam Please don't spam in this server`
        • `{ctx.prefix}canned use spam` (send the spam response)
        
        Perfect for consistent moderation messages and warnings.
        """
        canned = await self.db.get_canned_responses(ctx.guild.id)

        if not canned:
            embed = create_embed(
                title="🥫 Canned Responses",
                description="No canned responses configured",
                color=discord.Color.blue(),
            )
        else:
            response_list = ", ".join(f"`{name}`" for name in canned.keys())
            embed = create_embed(
                title="🥫 Available Canned Responses",
                description=response_list,
                color=discord.Color.blue(),
            )

        await ctx.send(embed=embed)

    @canned.command(name="add")
    @has_permissions(level=2)
    async def canned_add(self, ctx, name: str, *, content: str):
        """Create a new canned response for quick moderation use"""
        await self.db.add_canned_response(ctx.guild.id, name.lower(), content)

        embed = create_embed(
            title="✅ Canned Response Added",
            description=f"Canned response `{name}` has been created",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @canned.command(name="use")
    @has_permissions(level=1)
    async def canned_use(self, ctx, *, name: str):
        """Send a canned response by name"""
        canned = await self.db.get_canned_responses(ctx.guild.id)

        if name.lower() not in canned:
            embed = create_embed(
                title="❌ Response Not Found",
                description=f"Canned response `{name}` doesn't exist",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        content = canned[name.lower()]
        content = self._process_variables(content, ctx)

        await ctx.send(content)

    @commands.command()
    @has_permissions(level=2)
    async def addcommand(self, ctx, name: str, *, content: str):
        f"""Create a custom command that responds with text (same as creating a tag)
        
        **Usage:** `{ctx.prefix}addcommand <name> <content>`
        **Examples:**
        • `{ctx.prefix}addcommand discord Join our Discord: discord.gg/example`
        • `{ctx.prefix}addcommand website Visit our website: example.com`
        
        Creates a tag that can be used with `{ctx.prefix}<name>`.
        """
        await self.tag_add(ctx, name, content=content)


async def setup(bot):
    await bot.add_cog(Tags(bot))
