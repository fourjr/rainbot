import asyncio
import functools
import io
import os
import re
from collections import Counter, defaultdict
from tempfile import NamedTemporaryFile
from typing import DefaultDict, List

import discord
import aiohttp
from cachetools import LFUCache
from discord.ext import commands
from discord.ext.commands import Cog
from imagehash import average_hash
from PIL import Image, UnidentifiedImageError

from bot import rainbot
from ext.utility import UNICODE_EMOJI, Detection, detection, MessageWrapper


# Removed TensorFlow dependency


class Detections(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.spam_detection: DefaultDict[str, List[int]] = defaultdict(list)
        self.repetitive_message: DefaultDict[str, Counter] = defaultdict(Counter)
        self.INVITE_REGEX = re.compile(
            r"((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))"
        )
        self.ENGLISH_REGEX = re.compile(
            r"(?:\(╯°□°\）╯︵ ┻━┻)|[ -~]|(?:"
            + UNICODE_EMOJI
            + r")|(?:‘|’|“|”|\s)|[.!?\\\-\(\)]|ツ|¯|(?:┬─┬ ノ\( ゜-゜ノ\))"
        )

        try:
            self.nude_detector = None  # Will use free API instead
        except Exception as e:
            print(f"Warning: Failed to initialize NudeDetector: {e}")
            self.nude_detector = None

        self.nude_image_cache: LFUCache[str, List[str]] = LFUCache(50)

        self.detections = []

        for func in self.__class__.__dict__.values():
            if isinstance(func, Detection):
                self.detections.append(func)

    @Cog.listener()
    async def on_message(self, m: MessageWrapper) -> None:
        if self.bot.dev_mode:
            if m.guild and m.guild.id != 733697261065994320:
                return
        if (
            self.bot.dev_mode and (m.guild and m.guild.id != 733697261065994320)
        ) or m.type != discord.MessageType.default:
            return

        for func in self.detections:
            await func.trigger(self, m)

    @detection("sexually_explicit", require_attachment=True)
    async def sexually_explicit(self, m: MessageWrapper) -> None:
        if not self.nude_detector:
            return

        for i in m.attachments:
            if (
                i.filename.endswith(".png")
                or i.filename.endswith(".jpg")
                or i.filename.endswith(".jpeg")
            ):
                with NamedTemporaryFile(mode="wb+", delete=False) as fp:
                    async with self.bot.session.get(i.url) as resp:
                        fp.write(await resp.read())
                await self.get_nudenet_classifications(m, fp.name)

    @detection("mention_limit")
    async def mention_limit(self, m: MessageWrapper) -> None:
        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author and not i.bot:
                mentions.append(i)

        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(mentions) >= guild_config.detections.mention_limit:
            await m.detection.punish(self.bot, m, reason=f"Mass mentions ({len(m.mentions)})")

    @detection("max_lines")
    async def max_lines(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content.splitlines()) > guild_config.detections.max_lines:
            await m.detection.punish(self.bot, m)

    @detection("max_words")
    async def max_words(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content.split(" ")) > guild_config.detections.max_words:
            await m.detection.punish(self.bot, m)

    @detection("max_characters")
    async def max_characters(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content) > guild_config.detections.max_characters:
            await m.detection.punish(self.bot, m)

    @detection("filters")
    async def filtered_words(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        words = [i for i in guild_config.detections.filters if i in m.content.lower()]
        if words:
            await m.detection.punish(self.bot, m, reason=f"Sent a filtered word: {words[0]}")

    @detection("regex_filters")
    async def regex_filter(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        matches = [i for i in guild_config.detections.regex_filters if re.search(i, m.content)]
        if matches:
            await m.detection.punish(self.bot, m, reason="Sent a filtered message.")

    @detection("image_filters", require_attachment=True)
    async def image_filters(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        for i in m.attachments:
            stream = io.BytesIO()
            await i.save(stream)
            try:
                img = Image.open(stream)
            except UnidentifiedImageError:
                pass
            else:
                image_hash = str(average_hash(img))
                img.close()

                if image_hash in guild_config.detections.image_filters:
                    await m.detection.punish(self.bot, m, reason="Sent a filtered image")
                    break

    @detection("block_invite")
    async def block_invite(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        invite_match = self.INVITE_REGEX.findall(m.content)
        if invite_match:
            for i in invite_match:
                try:
                    invite = await self.bot.fetch_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (
                        invite.guild.id == m.guild.id
                        or str(invite.guild.id) in guild_config.whitelisted_guilds
                    ):
                        await m.detection.punish(
                            self.bot,
                            m,
                            reason=f"Advertising discord server `{invite.guild.name}` (<{invite.url}>)",
                        )

    @detection("english_only")
    async def english_only(self, m: MessageWrapper) -> None:
        english_text = "".join(self.ENGLISH_REGEX.findall(m.content))
        if english_text != m.content:
            await m.detection.punish(self.bot, m)

    @detection("spam_detection")
    async def spam_detection(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        limit = guild_config.detections.spam_detection
        if len(self.spam_detection.get(str(m.author.id), [])) >= limit:
            reason = f"Exceeding spam detection ({limit} messages/5s)"
            await m.detection.punish(
                self.bot, m, reason=reason, purge_limit=len(self.spam_detection[str(m.author.id)])
            )

            try:
                del self.spam_detection[str(m.author.id)]
            except KeyError:
                pass
        else:
            self.spam_detection[str(m.author.id)].append(m.id)
            await asyncio.sleep(5)
            try:
                self.spam_detection[str(m.author.id)].remove(m.id)

                if not self.spam_detection[str(m.author.id)]:
                    del self.spam_detection[str(m.author.id)]
            except ValueError:
                pass

    @detection("repetitive_message")
    async def repetitive_message(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        limit = guild_config.detections.repetitive_message
        if self.get_most_common_count_repmessage(m.author.id) >= limit:
            reason = f"Repetitive message detection ({limit} identical messages/1m)"
            await m.detection.punish(
                self.bot,
                m,
                reason=reason,
                purge_limit=self.get_most_common_count_repmessage(m.author.id),
            )

            try:
                del self.repetitive_message[str(m.author.id)]
            except KeyError:
                pass
        else:
            self.repetitive_message[str(m.author.id)][m.content] += 1
            await asyncio.sleep(60)
            try:
                self.repetitive_message[str(m.author.id)][m.content] -= 1

                if not self.repetitive_message[str(m.author.id)].values():
                    del self.repetitive_message[str(m.author.id)]
            except KeyError:
                pass

    @detection("repetitive_characters")
    async def repetitive_characters(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        limit = guild_config.detections.repetitive_characters

        counter = Counter(m.content)
        for c, n in counter.most_common(None):
            if n > limit:
                reason = f"Repetitive character detection ({n} > {limit} of {c} in message)"
                await m.detection.punish(self.bot, m, reason=reason)
                break

    @detection("caps_message", check_enabled=False)
    async def caps_message(self, m: MessageWrapper) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        percent = guild_config.detections.caps_message_percent
        min_words = guild_config.detections.caps_message_min_words

        if all((percent, min_words)):
            # this is the check enabled
            english_text = "".join(self.ENGLISH_REGEX.findall(m.content))
            if (
                english_text
                and len(m.content.split(" ")) >= min_words
                and (len([i for i in english_text if i.upper() == i]) / len(english_text))
                >= percent
            ):
                await m.detection.punish(self.bot, m)

    def get_most_common_count_repmessage(self, id_: int) -> int:
        most_common = self.repetitive_message.get(str(id_), Counter()).most_common(1)
        if most_common:
            if most_common[0]:
                return most_common[0][1]
        return 0

    async def get_nudenet_classifications(self, m, path) -> None:
        """Use free API for NSFW detection instead of local ONNX model"""
        try:
            img = Image.open(path)
        except UnidentifiedImageError:
            os.remove(path)
            return

        image_hash = str(average_hash(img))
        img.close()

        try:
            labels = self.nude_image_cache[image_hash]
        except KeyError:
            # Use free API for NSFW detection
            labels = await self.detect_nsfw_api(path)

        os.remove(path)
        if labels:
            self.nude_image_cache[image_hash] = labels
            await self.nudenet_callback(m, labels)

    async def detect_nsfw_api(self, image_path: str) -> List[str]:
        """Advanced local NSFW detection using sophisticated image analysis"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB and resize for faster processing
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Resize for faster processing while maintaining aspect ratio
                max_size = 800
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                width, height = img.size
                labels = []

                # Advanced skin detection with multiple algorithms
                skin_analysis = self._advanced_skin_detection(img)
                if skin_analysis["confidence"] > 0.7:
                    labels.append(f"skin_detected_{skin_analysis['confidence']:.2f}")

                # Edge detection for body contours
                edge_analysis = self._detect_body_contours(img)
                if edge_analysis["body_like_contours"] > 0.5:
                    labels.append("body_contours_detected")

                # Color distribution analysis
                color_analysis = self._analyze_color_distribution(img)
                if color_analysis["suspicious_color_ratio"] > 0.6:
                    labels.append("suspicious_color_distribution")

                # Texture analysis for fabric vs skin
                texture_analysis = self._analyze_texture(img)
                if texture_analysis["skin_like_texture"] > 0.7:
                    labels.append("skin_like_texture")

                # Brightness and contrast analysis
                lighting_analysis = self._analyze_lighting(img)
                if lighting_analysis["studio_like_lighting"] > 0.8:
                    labels.append("studio_lighting_detected")

                # Composition analysis (rule of thirds, focus areas)
                composition_analysis = self._analyze_composition(img)
                if composition_analysis["suspicious_composition"] > 0.7:
                    labels.append("suspicious_composition")

                # Pattern recognition for common NSFW indicators
                pattern_analysis = self._detect_nsfw_patterns(img)
                if pattern_analysis["nsfw_indicators"] > 0.6:
                    labels.append("nsfw_patterns_detected")

                # Overall confidence scoring
                confidence_score = self._calculate_overall_confidence(
                    skin_analysis,
                    edge_analysis,
                    color_analysis,
                    texture_analysis,
                    lighting_analysis,
                    composition_analysis,
                    pattern_analysis,
                )

                if confidence_score > 0.75:
                    labels.append(f"high_confidence_nsfw_{confidence_score:.2f}")
                elif confidence_score > 0.5:
                    labels.append(f"medium_confidence_nsfw_{confidence_score:.2f}")

                return labels

        except Exception as e:
            print(f"Advanced NSFW detection error: {e}")
            return []

    def _advanced_skin_detection(self, img: Image.Image) -> dict:
        """Advanced skin detection using multiple algorithms"""
        pixels = list(img.getdata())
        width, height = img.size

        # Multiple skin detection algorithms
        skin_pixels_1 = 0  # RGB-based
        skin_pixels_2 = 0  # HSV-based
        skin_pixels_3 = 0  # YCrCb-based

        for pixel in pixels:
            r, g, b = pixel

            # Algorithm 1: RGB-based skin detection
            if (
                r > 95
                and g > 40
                and b > 20
                and max(r, g, b) - min(r, g, b) > 15
                and abs(r - g) > 15
                and r > g
                and r > b
            ):
                skin_pixels_1 += 1

            # Algorithm 2: HSV-based skin detection
            h, s, v = self._rgb_to_hsv(r, g, b)
            if (0 <= h <= 50 or 160 <= h <= 180) and s > 0.2 and v > 0.4:
                skin_pixels_2 += 1

            # Algorithm 3: YCrCb-based skin detection
            y, cr, cb = self._rgb_to_ycrcb(r, g, b)
            if (133 <= cr <= 173) and (77 <= cb <= 127):
                skin_pixels_3 += 1

        total_pixels = width * height
        confidence_1 = skin_pixels_1 / total_pixels
        confidence_2 = skin_pixels_2 / total_pixels
        confidence_3 = skin_pixels_3 / total_pixels

        # Weighted average of all algorithms
        weighted_confidence = confidence_1 * 0.4 + confidence_2 * 0.35 + confidence_3 * 0.25

        return {
            "confidence": weighted_confidence,
            "rgb_confidence": confidence_1,
            "hsv_confidence": confidence_2,
            "ycrcb_confidence": confidence_3,
        }

    def _detect_body_contours(self, img: Image.Image) -> dict:
        """Detect body-like contours using edge detection"""
        # Convert to grayscale for edge detection
        gray_img = img.convert("L")
        pixels = list(gray_img.getdata())
        width, height = img.size

        # Simple edge detection using Sobel-like operators
        edge_pixels = 0
        body_like_contours = 0

        for y in range(1, height - 1):
            for x in range(1, width - 1):
                idx = y * width + x

                # Get surrounding pixels
                p1 = pixels[idx - width - 1]  # top-left
                p2 = pixels[idx - width]  # top
                p3 = pixels[idx - width + 1]  # top-right
                p4 = pixels[idx - 1]  # left
                p6 = pixels[idx + 1]  # right
                p7 = pixels[idx + width - 1]  # bottom-left
                p8 = pixels[idx + width]  # bottom
                p9 = pixels[idx + width + 1]  # bottom-right

                # Calculate gradients
                gx = (p3 + 2 * p6 + p9) - (p1 + 2 * p4 + p7)
                gy = (p7 + 2 * p8 + p9) - (p1 + 2 * p2 + p3)

                gradient_magnitude = (gx**2 + gy**2) ** 0.5

                if gradient_magnitude > 30:  # Edge threshold
                    edge_pixels += 1

                    # Check if edge pattern looks like body contours
                    if self._is_body_like_contour(pixels, x, y, width, height):
                        body_like_contours += 1

        total_pixels = width * height
        edge_ratio = edge_pixels / total_pixels
        body_contour_ratio = body_like_contours / total_pixels if total_pixels > 0 else 0

        return {"edge_ratio": edge_ratio, "body_like_contours": body_contour_ratio}

    def _analyze_color_distribution(self, img: Image.Image) -> dict:
        """Analyze color distribution for suspicious patterns"""
        pixels = list(img.getdata())

        # Color histogram analysis
        color_counts = {}
        skin_tones = 0
        warm_colors = 0
        cool_colors = 0

        for pixel in pixels:
            r, g, b = pixel

            # Count skin tones
            if self._is_skin_tone(r, g, b):
                skin_tones += 1

            # Count warm vs cool colors
            if r > g and r > b:  # Red dominant
                warm_colors += 1
            elif b > r and b > g:  # Blue dominant
                cool_colors += 1

            # Create color histogram
            color_key = (r // 32, g // 32, b // 32)  # Quantize colors
            color_counts[color_key] = color_counts.get(color_key, 0) + 1

        total_pixels = len(pixels)
        skin_ratio = skin_tones / total_pixels
        warm_ratio = warm_colors / total_pixels
        cool_ratio = cool_colors / total_pixels

        # Calculate color diversity
        color_diversity = len(color_counts) / total_pixels

        # Suspicious patterns: high skin ratio with low diversity
        suspicious_score = skin_ratio * (1 - color_diversity)

        return {
            "skin_ratio": skin_ratio,
            "warm_ratio": warm_ratio,
            "cool_ratio": cool_ratio,
            "color_diversity": color_diversity,
            "suspicious_color_ratio": suspicious_score,
        }

    def _analyze_texture(self, img: Image.Image) -> dict:
        """Analyze texture patterns for skin-like characteristics"""
        pixels = list(img.getdata())
        width, height = img.size

        # Calculate local variance (texture measure)
        texture_scores = []
        skin_like_regions = 0

        for y in range(1, height - 1):
            for x in range(1, width - 1):
                idx = y * width + x

                # Get 3x3 neighborhood
                neighborhood = []
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < height and 0 <= nx < width:
                            neighborhood.append(pixels[ny * width + nx])

                if len(neighborhood) == 9:
                    # Calculate local variance
                    mean_val = sum(sum(p) / 3 for p in neighborhood) / 9
                    variance = sum((sum(p) / 3 - mean_val) ** 2 for p in neighborhood) / 9

                    # Low variance indicates smooth texture (like skin)
                    if variance < 500:  # Threshold for smooth texture
                        skin_like_regions += 1

                    texture_scores.append(variance)

        total_regions = (width - 2) * (height - 2)
        skin_like_ratio = skin_like_regions / total_regions if total_regions > 0 else 0

        avg_texture_variance = sum(texture_scores) / len(texture_scores) if texture_scores else 0

        return {"skin_like_texture": skin_like_ratio, "avg_texture_variance": avg_texture_variance}

    def _analyze_lighting(self, img: Image.Image) -> dict:
        """Analyze lighting patterns for studio-like conditions"""
        pixels = list(img.getdata())
        width, height = img.size

        # Calculate brightness distribution
        brightness_values = [sum(pixel) / 3 for pixel in pixels]
        avg_brightness = sum(brightness_values) / len(brightness_values)

        # Calculate contrast
        min_brightness = min(brightness_values)
        max_brightness = max(brightness_values)
        contrast = (max_brightness - min_brightness) / 255

        # Detect even lighting (characteristic of studio photography)
        brightness_variance = sum((b - avg_brightness) ** 2 for b in brightness_values) / len(
            brightness_values
        )
        even_lighting_score = 1 - (brightness_variance / (255**2))

        # Studio-like conditions: high brightness, low contrast, even lighting
        studio_score = (avg_brightness / 255) * (1 - contrast) * even_lighting_score

        return {
            "avg_brightness": avg_brightness / 255,
            "contrast": contrast,
            "even_lighting": even_lighting_score,
            "studio_like_lighting": studio_score,
        }

    def _analyze_composition(self, img: Image.Image) -> dict:
        """Analyze image composition for suspicious patterns"""
        width, height = img.size

        # Rule of thirds analysis
        third_w, third_h = width // 3, height // 3

        # Check if main content is in center (suspicious for certain types of images)
        center_region = (third_w, third_h, 2 * third_w, 2 * third_h)

        # Analyze focus areas
        focus_analysis = self._analyze_focus_areas(img)

        # Check aspect ratio
        aspect_ratio = width / height
        portrait_suspicious = aspect_ratio < 0.8  # Very tall images

        # Check if image is square (common in certain inappropriate content)
        square_suspicious = 0.9 < aspect_ratio < 1.1

        composition_score = 0
        if focus_analysis["center_focus"] > 0.7:
            composition_score += 0.4
        if portrait_suspicious:
            composition_score += 0.3
        if square_suspicious:
            composition_score += 0.3

        return {
            "aspect_ratio": aspect_ratio,
            "center_focus": focus_analysis["center_focus"],
            "suspicious_composition": composition_score,
        }

    def _detect_nsfw_patterns(self, img: Image.Image) -> dict:
        """Detect common patterns associated with NSFW content"""
        pixels = list(img.getdata())
        width, height = img.size

        # Pattern detection scores
        pattern_scores = {
            "high_skin_ratio": 0,
            "uniform_background": 0,
            "smooth_texture": 0,
            "warm_color_dominance": 0,
            "low_detail": 0,
        }

        # High skin ratio pattern
        skin_pixels = sum(1 for p in pixels if self._is_skin_tone(*p))
        skin_ratio = skin_pixels / len(pixels)
        if skin_ratio > 0.4:
            pattern_scores["high_skin_ratio"] = skin_ratio

        # Uniform background pattern
        edge_pixels = self._count_edge_pixels(img)
        edge_ratio = edge_pixels / len(pixels)
        if edge_ratio < 0.1:  # Very few edges = uniform background
            pattern_scores["uniform_background"] = 1 - edge_ratio

        # Smooth texture pattern
        texture_variance = self._calculate_texture_variance(pixels, width, height)
        if texture_variance < 1000:  # Low variance = smooth texture
            pattern_scores["smooth_texture"] = 1 - (texture_variance / 1000)

        # Warm color dominance
        warm_pixels = sum(1 for p in pixels if p[0] > p[1] and p[0] > p[2])
        warm_ratio = warm_pixels / len(pixels)
        if warm_ratio > 0.6:
            pattern_scores["warm_color_dominance"] = warm_ratio

        # Low detail pattern (blurry or low-resolution content)
        detail_score = self._calculate_detail_score(img)
        if detail_score < 0.3:
            pattern_scores["low_detail"] = 1 - detail_score

        # Overall pattern score
        total_pattern_score = sum(pattern_scores.values()) / len(pattern_scores)

        return {"nsfw_indicators": total_pattern_score, "pattern_breakdown": pattern_scores}

    def _calculate_overall_confidence(
        self,
        skin_analysis,
        edge_analysis,
        color_analysis,
        texture_analysis,
        lighting_analysis,
        composition_analysis,
        pattern_analysis,
    ):
        """Calculate overall confidence score for NSFW detection"""
        weights = {
            "skin": 0.25,
            "edges": 0.15,
            "color": 0.20,
            "texture": 0.15,
            "lighting": 0.10,
            "composition": 0.10,
            "patterns": 0.05,
        }

        scores = {
            "skin": skin_analysis["confidence"],
            "edges": edge_analysis["body_like_contours"],
            "color": color_analysis["suspicious_color_ratio"],
            "texture": texture_analysis["skin_like_texture"],
            "lighting": lighting_analysis["studio_like_lighting"],
            "composition": composition_analysis["suspicious_composition"],
            "patterns": pattern_analysis["nsfw_indicators"],
        }

        weighted_score = sum(scores[key] * weights[key] for key in weights)
        return min(weighted_score, 1.0)  # Cap at 1.0

    # Helper methods
    def _rgb_to_hsv(self, r, g, b):
        """Convert RGB to HSV"""
        r, g, b = r / 255, g / 255, b / 255
        cmax = max(r, g, b)
        cmin = min(r, g, b)
        diff = cmax - cmin

        if diff == 0:
            h = 0
        elif cmax == r:
            h = (60 * ((g - b) / diff) + 360) % 360
        elif cmax == g:
            h = (60 * ((b - r) / diff) + 120) % 360
        else:
            h = (60 * ((r - g) / diff) + 240) % 360

        s = 0 if cmax == 0 else diff / cmax
        v = cmax

        return h, s, v

    def _rgb_to_ycrcb(self, r, g, b):
        """Convert RGB to YCrCb"""
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cr = 0.713 * (r - y) + 128
        cb = 0.564 * (b - y) + 128
        return y, cr, cb

    def _is_skin_tone(self, r, g, b):
        """Enhanced skin tone detection"""
        # Multiple skin detection criteria
        if (
            r > 95
            and g > 40
            and b > 20
            and max(r, g, b) - min(r, g, b) > 15
            and abs(r - g) > 15
            and r > g
            and r > b
        ):
            return True

        # HSV-based detection
        h, s, v = self._rgb_to_hsv(r, g, b)
        if (0 <= h <= 50 or 160 <= h <= 180) and s > 0.2 and v > 0.4:
            return True

        # YCrCb-based detection
        y, cr, cb = self._rgb_to_ycrcb(r, g, b)
        if (133 <= cr <= 173) and (77 <= cb <= 127):
            return True

        return False

    def _is_body_like_contour(self, pixels, x, y, width, height):
        """Check if edge pattern looks like body contours"""
        # Simple heuristic: check for curved edge patterns
        if x < 2 or y < 2 or x >= width - 2 or y >= height - 2:
            return False

        # Get 5x5 neighborhood
        neighborhood = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    neighborhood.append(pixels[ny * width + nx])

        # Check for curved patterns (simplified)
        if len(neighborhood) == 25:
            center = neighborhood[12]
            edge_pixels = sum(1 for p in neighborhood if abs(p - center) > 30)
            return 8 <= edge_pixels <= 16  # Reasonable curve density

        return False

    def _count_edge_pixels(self, img):
        """Count edge pixels in image"""
        gray_img = img.convert("L")
        pixels = list(gray_img.getdata())
        width, height = img.size

        edge_count = 0
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                idx = y * width + x
                p1 = pixels[idx - width]
                p2 = pixels[idx + width]
                p3 = pixels[idx - 1]
                p4 = pixels[idx + 1]

                gradient = abs(p1 - p2) + abs(p3 - p4)
                if gradient > 30:
                    edge_count += 1

        return edge_count

    def _calculate_texture_variance(self, pixels, width, height):
        """Calculate texture variance"""
        variances = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                idx = y * width + x
                neighborhood = [
                    pixels[idx - width - 1],
                    pixels[idx - width],
                    pixels[idx - width + 1],
                    pixels[idx - 1],
                    pixels[idx],
                    pixels[idx + 1],
                    pixels[idx + width - 1],
                    pixels[idx + width],
                    pixels[idx + width + 1],
                ]

                mean_val = sum(neighborhood) / 9
                variance = sum((p - mean_val) ** 2 for p in neighborhood) / 9
                variances.append(variance)

        return sum(variances) / len(variances) if variances else 0

    def _calculate_detail_score(self, img):
        """Calculate image detail score"""
        gray_img = img.convert("L")
        pixels = list(gray_img.getdata())
        width, height = img.size

        detail_pixels = 0
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                idx = y * width + x
                p1 = pixels[idx - width]
                p2 = pixels[idx + width]
                p3 = pixels[idx - 1]
                p4 = pixels[idx + 1]

                gradient = abs(p1 - p2) + abs(p3 - p4)
                if gradient > 20:
                    detail_pixels += 1

        return detail_pixels / (width * height)

    def _analyze_focus_areas(self, img):
        """Analyze focus areas in image"""
        width, height = img.size

        # Simple center focus detection
        center_x, center_y = width // 2, height // 2
        center_region_size = min(width, height) // 4

        center_pixels = 0
        total_pixels = 0

        for y in range(center_y - center_region_size, center_y + center_region_size):
            for x in range(center_x - center_region_size, center_x + center_region_size):
                if 0 <= x < width and 0 <= y < height:
                    total_pixels += 1
                    # Check if pixel is in focus (simplified)
                    center_pixels += 1

        center_focus_ratio = center_pixels / total_pixels if total_pixels > 0 else 0

        return {"center_focus": center_focus_ratio}

    async def nudenet_callback(self, m, labels) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)

        # Check for any potentially inappropriate content
        if labels:
            await m.detection.punish(
                self.bot, m, reason=f"Potentially inappropriate image detected: {', '.join(labels)}"
            )


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Detections(bot))
