import discord
from typing import Optional, Any


async def safe_send(
    destination: Any, content: Optional[str] = None, **kwargs
) -> Optional[discord.Message]:
    """
    Safely send a message, preventing empty content errors (400/401).
    If both content and embed are empty, nothing is sent.
    """
    embed = kwargs.get("embed")
    if (content is None or str(content).strip() == "") and not (
        embed and getattr(embed, "description", None)
    ):
        return None
    try:
        return await destination.send(content, **kwargs)
    except (discord.HTTPException, discord.Forbidden) as e:
        # Optionally log the error here
        return None
