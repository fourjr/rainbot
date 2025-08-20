"""
Helper functions and utilities
"""

import string


def apply_vars(bot, message_text, message, user_input):
    return string.Formatter().vformat(
        message_text,
        [],
        SafeFormat(
            bot=bot.user,
            guild=message.guild,
            channel=message.channel,
            author=message.author,
            user_input=user_input,
        ),
    )


class SafeString(str):
    def __getattr__(self, item):
        return SafeString("{" + item + "}")


class SafeFormat(dict):
    def __missing__(self, key):
        return SafeString("{" + key + "}")


import re
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Union, List, Any, Dict

import discord
from discord.ext import commands

from .constants import COLORS, EMOJIS


def format_duration(seconds: Union[int, float, timedelta]) -> str:
    """
    Format a duration in seconds to a human-readable string

    Args:
        seconds: Duration in seconds or timedelta object

    Returns:
        Formatted duration string (e.g., "1h 30m 45s")
    """
    if isinstance(seconds, timedelta):
        seconds = int(seconds.total_seconds())

    if seconds == 0:
        return "0 seconds"

    seconds = int(abs(seconds))

    units = [
        ("year", 31536000),
        ("month", 2592000),
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]

    parts = []
    for unit_name, unit_seconds in units:
        if seconds >= unit_seconds:
            count = seconds // unit_seconds
            seconds %= unit_seconds

            # Use short forms for common units
            short_forms = {
                "year": "y",
                "month": "mo",
                "week": "w",
                "day": "d",
                "hour": "h",
                "minute": "m",
                "second": "s",
            }

            unit_str = short_forms.get(unit_name, unit_name)
            parts.append(f"{count}{unit_str}")

            # Only show top 2 units for readability
            if len(parts) >= 2:
                break

    return " ".join(parts)


def format_timestamp(dt: datetime, style: str = "f") -> str:
    """
    Format a datetime as a Discord timestamp

    Args:
        dt: Datetime object
        style: Discord timestamp style (t, T, d, D, f, F, R)

    Returns:
        Discord timestamp string
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:{style}>"


def truncate_text(text: str, max_length: int = 2000, suffix: str = "...") -> str:
    """
    Truncate text to fit within Discord's limits

    Args:
        text: Text to truncate
        max_length: Maximum length (default: 2000 for message content)
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def get_user_avatar(user: Union[discord.User, discord.Member]) -> str:
    """
    Get user's avatar URL with fallback to default

    Args:
        user: Discord user or member

    Returns:
        Avatar URL string
    """
    if user.avatar:
        return user.avatar.url
    return user.default_avatar.url


def create_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    color: Union[int, str] = "primary",
    timestamp: bool = False,
    **kwargs,
) -> discord.Embed:
    """
    Create a standardized embed with consistent styling

    Args:
        title: Embed title
        description: Embed description
        color: Color name from COLORS dict or hex value
        timestamp: Whether to add current timestamp
        **kwargs: Additional embed parameters

    Returns:
        Configured Discord embed
    """
    # Handle color
    if isinstance(color, str):
        color = COLORS.get(color, COLORS["primary"])

    embed = discord.Embed(title=title, description=description, color=color, **kwargs)

    if timestamp:
        embed.timestamp = datetime.now(timezone.utc)

    return embed


async def safe_send(
    destination: Union[discord.abc.Messageable, commands.Context],
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    file: Optional[discord.File] = None,
    files: Optional[List[discord.File]] = None,
    delete_after: Optional[float] = None,
    **kwargs,
) -> Optional[discord.Message]:
    """
    Safely send a message with error handling

    Args:
        destination: Where to send the message
        content: Message content
        embed: Embed to send
        file: File to send
        files: Multiple files to send
        delete_after: Delete message after this many seconds
        **kwargs: Additional send parameters

    Returns:
        Sent message or None if failed
    """
    try:
        # Handle context objects
        if isinstance(destination, commands.Context):
            destination = destination.channel

        # Truncate content if too long
        if content and len(content) > 2000:
            content = truncate_text(content, 2000)

        # Truncate embed if too long
        if embed:
            if embed.description and len(embed.description) > 4096:
                embed.description = truncate_text(embed.description, 4096)

            # Check total embed length
            total_length = len(embed)
            if total_length > 6000:
                # Create a simpler embed
                embed = create_embed(
                    title="Content Too Long",
                    description="The response was too long to display. Please try a more specific query.",
                    color="warning",
                )

        return await destination.send(
            content=content,
            embed=embed,
            file=file,
            files=files,
            delete_after=delete_after,
            **kwargs,
        )

    except discord.Forbidden:
        # Try to send a simpler message
        try:
            return await destination.send(
                "I don't have permission to send that message.", delete_after=10
            )
        except discord.Forbidden:
            pass  # Can't send anything

    except discord.HTTPException as e:
        # Handle specific HTTP errors
        if e.code == 50035:  # Invalid form body
            try:
                return await destination.send(
                    "The message content was invalid. Please try again.",
                    delete_after=10,
                )
            except discord.HTTPException:
                pass

    except Exception:
        pass  # Silently fail for other errors

    return None


def parse_time(time_str: str) -> Optional[timedelta]:
    """
    Parse a time string into a timedelta

    Args:
        time_str: Time string (e.g., "1h30m", "2d", "45s")

    Returns:
        Timedelta object or None if invalid
    """
    if not time_str:
        return None

    # Regex to match time components
    pattern = r"(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?"
    match = re.match(pattern, time_str.lower().replace(" ", ""))

    if not match:
        return None

    years, months, weeks, days, hours, minutes, seconds = match.groups()

    total_seconds = 0
    if years:
        total_seconds += int(years) * 31536000  # 365 days
    if months:
        total_seconds += int(months) * 2592000  # 30 days
    if weeks:
        total_seconds += int(weeks) * 604800
    if days:
        total_seconds += int(days) * 86400
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)

    return timedelta(seconds=total_seconds) if total_seconds > 0 else None


def clean_content(content: str) -> str:
    """
    Clean message content for logging/display

    Args:
        content: Raw message content

    Returns:
        Cleaned content
    """
    # Remove mentions and replace with readable text
    content = re.sub(r"<@!?(\d+)>", r"@User(\1)", content)
    content = re.sub(r"<@&(\d+)>", r"@Role(\1)", content)
    content = re.sub(r"<#(\d+)>", r"#Channel(\1)", content)

    # Remove custom emojis
    content = re.sub(r"<a?:\w+:\d+>", "[Emoji]", content)

    # Escape markdown
    content = discord.utils.escape_markdown(content)

    return content


def get_member_status(member: discord.Member) -> str:
    """
    Get a formatted status string for a member

    Args:
        member: Discord member

    Returns:
        Status string with emoji
    """
    status_emojis = {
        discord.Status.online: "🟢",
        discord.Status.idle: "🟡",
        discord.Status.dnd: "🔴",
        discord.Status.offline: "⚫",
    }

    emoji = status_emojis.get(member.status, "⚫")
    return f"{emoji} {member.status.name.title()}"


def format_permissions(permissions: discord.Permissions) -> List[str]:
    """
    Format permissions into a readable list

    Args:
        permissions: Discord permissions object

    Returns:
        List of permission names
    """
    perm_names = []

    for perm, value in permissions:
        if value:
            # Convert snake_case to Title Case
            name = perm.replace("_", " ").title()
            perm_names.append(name)

    return sorted(perm_names)


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split a list into chunks of specified size

    Args:
        lst: List to chunk
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def get_relative_time(dt: datetime) -> str:
    """
    Get relative time string (e.g., "2 hours ago")

    Args:
        dt: Datetime to compare

    Returns:
        Relative time string
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt

    if diff.total_seconds() < 60:
        return "just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.days < 30:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.days < 365:
        months = diff.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = diff.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"


async def confirm_action(
    ctx: commands.Context, message: str, timeout: float = 30.0
) -> bool:
    """
    Ask user to confirm an action

    Args:
        ctx: Command context
        message: Confirmation message
        timeout: Timeout in seconds

    Returns:
        True if confirmed, False otherwise
    """
    embed = create_embed(
        title=f"{EMOJIS['warning']} Confirmation Required",
        description=message,
        color="warning",
    )

    msg = await safe_send(ctx, embed=embed)
    if not msg:
        return False

    # Add reactions
    try:
        await msg.add_reaction(EMOJIS["success"])
        await msg.add_reaction(EMOJIS["error"])
    except discord.HTTPException:
        return False

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and str(reaction.emoji) in [EMOJIS["success"], EMOJIS["error"]]
        )

    try:
        reaction, user = await ctx.bot.wait_for(
            "reaction_add", timeout=timeout, check=check
        )

        return str(reaction.emoji) == EMOJIS["success"]

    except asyncio.TimeoutError:
        # Remove reactions on timeout
        try:
            await msg.clear_reactions()
        except discord.HTTPException:
            pass

        return False
