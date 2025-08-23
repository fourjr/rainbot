"""
Advanced pagination system for Discord embeds and messages
"""

import asyncio
from typing import List, Optional, Union, Callable, Any

import discord
from discord.ext import commands

from .constants import EMOJIS


class Paginator:
    """
    Advanced paginator for Discord messages with navigation controls
    """

    def __init__(
        self,
        ctx: commands.Context,
        pages: List[Union[str, discord.Embed]],
        *,
        timeout: float = 300.0,
        delete_after: bool = False,
        show_page_count: bool = True,
        show_navigation: bool = True,
        per_page: int = 1,
        allowed_mentions: discord.AllowedMentions = None,
    ):
        self.ctx = ctx
        self.pages = pages
        self.timeout = timeout
        self.delete_after = delete_after
        self.show_page_count = show_page_count
        self.show_navigation = show_navigation
        self.per_page = per_page
        self.allowed_mentions = allowed_mentions

        self.current_page = 0
        self.message: Optional[discord.Message] = None

        # Navigation emojis
        self.emojis = {
            "first": "⏮️",
            "previous": "◀️",
            "stop": "⏹️",
            "next": "▶️",
            "last": "⏭️",
            "info": "ℹ️",
        }

    @property
    def total_pages(self) -> int:
        """Get total number of pages"""
        return len(self.pages)

    def get_page_content(self, page_num: int) -> Union[str, discord.Embed]:
        """Get content for a specific page"""
        if not (0 <= page_num < self.total_pages):
            page_num = 0

        content = self.pages[page_num]

        # Add page count to embeds
        if (
            isinstance(content, discord.Embed)
            and self.show_page_count
            and self.total_pages > 1
        ):
            if content.footer.text:
                content.set_footer(
                    text=f"{content.footer.text} • Page {page_num + 1}/{self.total_pages}",
                    icon_url=content.footer.icon_url,
                )
            else:
                content.set_footer(text=f"Page {page_num + 1}/{self.total_pages}")

        return content

    async def start(self) -> Optional[discord.Message]:
        """Start the paginator"""
        if not self.pages:
            return None

        # Send initial message
        content = self.get_page_content(0)

        if isinstance(content, discord.Embed):
            self.message = await self.ctx.send(
                embed=content, allowed_mentions=self.allowed_mentions
            )
        else:
            self.message = await self.ctx.send(
                content, allowed_mentions=self.allowed_mentions
            )

        # Add navigation if needed
        if self.total_pages > 1 and self.show_navigation:
            await self._add_reactions()
            await self._handle_reactions()

        return self.message

    async def _add_reactions(self):
        """Add navigation reactions"""
        if not self.message:
            return

        try:
            if self.total_pages > 2:
                await self.message.add_reaction(self.emojis["first"])

            await self.message.add_reaction(self.emojis["previous"])
            await self.message.add_reaction(self.emojis["stop"])
            await self.message.add_reaction(self.emojis["next"])

            if self.total_pages > 2:
                await self.message.add_reaction(self.emojis["last"])

            await self.message.add_reaction(self.emojis["info"])

        except discord.HTTPException:
            pass

    async def _handle_reactions(self):
        """Handle reaction-based navigation"""

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                user == self.ctx.author
                and reaction.message.id == self.message.id
                and str(reaction.emoji) in self.emojis.values()
            )

        while True:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add", timeout=self.timeout, check=check
                )

                emoji = str(reaction.emoji)

                # Handle navigation
                if emoji == self.emojis["first"]:
                    self.current_page = 0
                elif emoji == self.emojis["previous"]:
                    self.current_page = max(0, self.current_page - 1)
                elif emoji == self.emojis["next"]:
                    self.current_page = min(self.total_pages - 1, self.current_page + 1)
                elif emoji == self.emojis["last"]:
                    self.current_page = self.total_pages - 1
                elif emoji == self.emojis["stop"]:
                    await self._cleanup()
                    break
                elif emoji == self.emojis["info"]:
                    await self._show_info()

                # Update message
                if emoji != self.emojis["stop"] and emoji != self.emojis["info"]:
                    await self._update_message()

                # Remove user's reaction
                try:
                    await reaction.remove(user)
                except discord.HTTPException:
                    pass

            except asyncio.TimeoutError:
                await self._cleanup()
                break

    async def _update_message(self):
        """Update the message with current page content"""
        if not self.message:
            return

        content = self.get_page_content(self.current_page)

        try:
            if isinstance(content, discord.Embed):
                await self.message.edit(
                    embed=content, allowed_mentions=self.allowed_mentions
                )
            else:
                await self.message.edit(
                    content=content, allowed_mentions=self.allowed_mentions
                )
        except discord.HTTPException:
            pass

    async def _show_info(self):
        """Show pagination info"""
        embed = discord.Embed(
            title="Pagination Info",
            description=f"Currently viewing page {self.current_page + 1} of {self.total_pages}",
            color=0x5865F2,
        )

        embed.add_field(
            name="Navigation",
            value=f"{self.emojis['first']} First page\n"
            f"{self.emojis['previous']} Previous page\n"
            f"{self.emojis['next']} Next page\n"
            f"{self.emojis['last']} Last page\n"
            f"{self.emojis['stop']} Stop pagination\n"
            f"{self.emojis['info']} Show this info",
            inline=False,
        )

        try:
            await self.ctx.send(embed=embed, delete_after=10)
        except discord.HTTPException:
            pass

    async def _cleanup(self):
        """Clean up the paginator"""
        if not self.message:
            return

        try:
            if self.delete_after:
                await self.message.delete()
            else:
                await self.message.clear_reactions()
        except discord.HTTPException:
            pass


class EmbedPaginator(Paginator):
    """
    Specialized paginator for embed content with automatic splitting
    """

    def __init__(
        self,
        ctx: commands.Context,
        *,
        title: str = "",
        description: str = "",
        color: int = 0x5865F2,
        entries: List[str],
        per_page: int = 10,
        **kwargs,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.entries = entries

        # Create pages from entries
        pages = self._create_pages(entries, per_page)

        super().__init__(ctx, pages, per_page=per_page, **kwargs)

    def _create_pages(self, entries: List[str], per_page: int) -> List[discord.Embed]:
        """Create embed pages from entries"""
        pages = []

        for i in range(0, len(entries), per_page):
            page_entries = entries[i : i + per_page]

            embed = discord.Embed(
                title=self.title, description=self.description, color=self.color
            )

            # Add entries to embed
            content = "\n".join(page_entries)
            if len(content) > 4096:
                # Split content if too long
                content = content[:4093] + "..."

            embed.add_field(
                name=f"Entries {i + 1}-{min(i + per_page, len(self.entries))}",
                value=content,
                inline=False,
            )

            pages.append(embed)

        return pages


class ListPaginator(EmbedPaginator):
    """
    Paginator for simple lists with automatic numbering
    """

    def __init__(
        self,
        ctx: commands.Context,
        items: List[str],
        *,
        title: str = "List",
        per_page: int = 10,
        numbered: bool = True,
        **kwargs,
    ):
        if numbered:
            entries = [f"{i + 1}. {item}" for i, item in enumerate(items)]
        else:
            entries = [f"• {item}" for item in items]

        super().__init__(ctx, title=title, entries=entries, per_page=per_page, **kwargs)


class FieldPaginator(Paginator):
    """
    Paginator for embeds with multiple fields
    """

    def __init__(
        self,
        ctx: commands.Context,
        *,
        title: str = "",
        description: str = "",
        color: int = 0x5865F2,
        fields: List[dict],
        per_page: int = 5,
        **kwargs,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.fields = fields

        # Create pages from fields
        pages = self._create_pages(fields, per_page)

        super().__init__(ctx, pages, per_page=per_page, **kwargs)

    def _create_pages(self, fields: List[dict], per_page: int) -> List[discord.Embed]:
        """Create embed pages from fields"""
        pages = []

        for i in range(0, len(fields), per_page):
            page_fields = fields[i : i + per_page]

            embed = discord.Embed(
                title=self.title, description=self.description, color=self.color
            )

            for field in page_fields:
                embed.add_field(
                    name=field.get("name", "Field"),
                    value=field.get("value", "No value"),
                    inline=field.get("inline", True),
                )

            pages.append(embed)

        return pages


async def paginate_text(
    ctx: commands.Context,
    text: str,
    *,
    max_length: int = 2000,
    prefix: str = "",
    suffix: str = "",
    **kwargs,
) -> Optional[discord.Message]:
    """
    Paginate long text content

    Args:
        ctx: Command context
        text: Text to paginate
        max_length: Maximum length per page
        prefix: Text to add at the beginning of each page
        suffix: Text to add at the end of each page
        **kwargs: Additional paginator options

    Returns:
        The paginator message
    """
    if len(text) <= max_length:
        return await ctx.send(f"{prefix}{text}{suffix}")

    # Split text into pages
    pages = []
    current_page = ""

    for line in text.split("\n"):
        if len(current_page) + len(line) + len(prefix) + len(suffix) + 1 > max_length:
            if current_page:
                pages.append(f"{prefix}{current_page}{suffix}")
                current_page = line
            else:
                # Line is too long, split it
                while line:
                    chunk_size = max_length - len(prefix) - len(suffix)
                    pages.append(f"{prefix}{line[:chunk_size]}{suffix}")
                    line = line[chunk_size:]
        else:
            if current_page:
                current_page += f"\n{line}"
            else:
                current_page = line

    if current_page:
        pages.append(f"{prefix}{current_page}{suffix}")

    paginator = Paginator(ctx, pages, **kwargs)
    return await paginator.start()
