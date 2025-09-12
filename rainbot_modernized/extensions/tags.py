import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed, status_embed
import re


class Tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.group(invoke_without_command=True)
    async def tag(self, ctx, *, name: str = None):
        """Manages custom text commands (tags).

        Use this command to create, edit, and use custom text responses.

        **Usage:**
        - To list all tags: `{prefix}tag`
        - To use a tag: `{prefix}tag <tag_name>`
        - For subcommands: `{prefix}tag <subcommand>`

        **Examples:**
        - `{prefix}tag` (shows a list of all tags)
        - `{prefix}tag rules` (displays the 'rules' tag)
        - `{prefix}tag add welcome Welcome, {author.mention}, to our server!`

        **Available Variables:**
        - `{{author}}`: The user who invoked the tag.
        - `{{guild}}`: The name of the server.
        - `{{channel}}`: The channel where the tag was invoked.
        """
        if name is None:
            # List all tags
            tags = await self.db.get_tags(ctx.guild.id)

            if not tags:
                embed = status_embed(
                    title="📝 Tags",
                    description="No tags found for this server",
                    status="info",
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
                embed = status_embed(
                    title="❌ Tag Not Found",
                    description=f"Tag `{name}` doesn't exist",
                    status="error",
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
        """Creates a new tag.

        **Usage:** `{prefix}tag add <name> <content>`
        **Example:** `{prefix}tag add welcome Welcome to our server!`
        """
        if len(name) > 50:
            embed = status_embed(
                title="❌ Name Too Long",
                description="Tag names must be 50 characters or less",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        if len(content) > 2000:
            embed = status_embed(
                title="❌ Content Too Long",
                description="Tag content must be 2000 characters or less",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() in tags:
            embed = status_embed(
                title="❌ Tag Exists",
                description=f"Tag `{name}` already exists",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        await self.db.add_tag(ctx.guild.id, name.lower(), content, ctx.author.id)

        embed = status_embed(
            title="✅ Tag Created",
            description=f"Tag `{name}` has been created",
            status="success",
        )
        await ctx.send(embed=embed)

    @tag.command(name="edit", aliases=["update"])
    @has_permissions(level=2)
    async def tag_edit(self, ctx, name: str, *, content: str):
        """Edits an existing tag.

        **Usage:** `{prefix}tag edit <name> <new_content>`
        **Example:** `{prefix}tag edit welcome Welcome to our awesome server!`
        """
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = status_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        if len(content) > 2000:
            embed = status_embed(
                title="❌ Content Too Long",
                description="Tag content must be 2000 characters or less",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        await self.db.update_tag(ctx.guild.id, name.lower(), content)

        embed = status_embed(
            title="✅ Tag Updated",
            description=f"Tag `{name}` has been updated",
            status="success",
        )
        await ctx.send(embed=embed)

    @tag.command(name="delete", aliases=["remove"])
    @has_permissions(level=2)
    async def tag_delete(self, ctx, *, name: str):
        """Deletes a tag.

        **Usage:** `{prefix}tag delete <name>`
        **Example:** `{prefix}tag delete oldtag`
        """
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = status_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        await self.db.delete_tag(ctx.guild.id, name.lower())

        embed = status_embed(
            title="✅ Tag Deleted",
            description=f"Tag `{name}` has been deleted",
            status="success",
        )
        await ctx.send(embed=embed)

    @tag.command(name="info")
    async def tag_info(self, ctx, *, name: str):
        """Shows information about a tag, such as creator and usage count.

        **Usage:** `{prefix}tag info <name>`
        **Example:** `{prefix}tag info welcome`
        """
        tag_info = await self.db.get_tag_info(ctx.guild.id, name.lower())

        if not tag_info:
            embed = status_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                status="error",
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
        """Searches for tags by name.

        **Usage:** `{prefix}tag search <query>`
        **Example:** `{prefix}tag search wel`
        """
        tags = await self.db.get_tags(ctx.guild.id)

        matching_tags = [name for name in tags.keys() if query.lower() in name.lower()]

        if not matching_tags:
            embed = status_embed(
                title="🔍 Search Results",
                description=f"No tags found matching `{query}`",
                status="info",
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
        """Displays the raw, unformatted content of a tag.

        **Usage:** `{prefix}tag raw <name>`
        **Example:** `{prefix}tag raw welcome`
        """
        tags = await self.db.get_tags(ctx.guild.id)

        if name.lower() not in tags:
            embed = status_embed(
                title="❌ Tag Not Found",
                description=f"Tag `{name}` doesn't exist",
                status="error",
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
        """Manages canned responses for moderation.

        **Usage:** `{prefix}canned <subcommand>`
        **Examples:**
        - `{prefix}canned add spam Please do not spam.`
        - `{prefix}canned use spam`
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
        """Adds a new canned response.

        **Usage:** `{prefix}canned add <name> <content>`
        **Example:** `{prefix}canned add spam Please do not spam.`
        """
        await self.db.add_canned_response(ctx.guild.id, name.lower(), content)

        embed = status_embed(
            title="✅ Canned Response Added",
            description=f"Canned response `{name}` has been created",
            status="success",
        )
        await ctx.send(embed=embed)

    @canned.command(name="use")
    @has_permissions(level=1)
    async def canned_use(self, ctx, *, name: str):
        """Uses a canned response.

        **Usage:** `{prefix}canned use <name>`
        **Example:** `{prefix}canned use spam`
        """
        canned = await self.db.get_canned_responses(ctx.guild.id)

        if name.lower() not in canned:
            embed = status_embed(
                title="❌ Response Not Found",
                description=f"Canned response `{name}` doesn't exist",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        content = canned[name.lower()]
        content = self._process_variables(content, ctx)

        await ctx.send(content)

    @commands.command()
    @has_permissions(level=2)
    async def addcommand(self, ctx, name: str, *, content: str):
        """Creates a custom command (alias for `tag add`).

        **Usage:** `{prefix}addcommand <name> <content>`
        **Example:** `{prefix}addcommand discord Join our server: discord.gg/example`

        Note: This creates a tag that must be used with `{prefix}tag <name>`.
        """
        await self.tag_add(ctx, name, content=content)


async def setup(bot):
    await bot.add_cog(Tags(bot))
