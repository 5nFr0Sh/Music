import os
import re
import asyncio
import discord
from discord.ext import commands, tasks
import yt_dlp

# =========================================================================
# ⚙️ CONFIGURATION & CREDENTIALS (الإعدادات والتوكن لـ سوالف العرب)
# =========================================================================
TOKEN = "MTUyNjgwMDY2NTI1NzcwNTUyMw.GleoKk" # التوكن الخاص بك
OWNER_ID = 211773456562257930  # الآيدي الخاص بك كمالك للبوت (Mond Reef)

# مسار الـ FFmpeg للينكس (تم تعديله ليعمل تلقائياً على السيرفر)
FFMPEG_PATH = "ffmpeg"

# تعديل سطر الـ bug reports لتجنب الأخطاء مع النسخ الجديدة لـ yt-dlp
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""

# خيارات متطورة جداً لتخطى الحظر الشديد بدون كوكيز (محاكاة الموبايل)
YTDL_OPTS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    
    # 🌟 إجبار اليوتيوب على معاملتنا كجهاز آيفون أو أندرويد فقط وتجنب الويب تماماً
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android"], 
            "skip": ["dash", "hls"]
        }
    },
    # ترويسة هيدر مخصصة لمحاكاة تطبيق يوتيوب الرسمي على الموبايل
    "http_headers": {
        "User-Agent": "com.google.ios.youtube/19.17.2 (iPhone16,2; U; CPU iOS 17_5 like Mac OS X; en_US)",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
}

# خيارات تشغيل الـ FFmpeg لضمان أعلى استقرار وبث صوتي فخم نقي
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

# إعدادات البوت والبادئة (Prefix) والأذونات
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

# الألوان الفاخرة المعتمدة لسيرفر سوالف العرب
GOLD_COLOR = 0xD4AF37      # ذهبي ملكي للتشغيل الأساسي والأمور الفخمة
DARK_GOLD_COLOR = 0xA87C1E # ذهبي داكن للإضافات والانتظار
RED_COLOR = 0xE06666       # أحمر هادئ للتحذيرات والأخطاء
BLUE_COLOR = 0x4A90E2      # أزرق نقي للعمليات العادية كالوقف المؤقت والاستئناف

# =========================================================================
# 👑 SECURITY CHECKS (التحقق الأمني من المالك للأوامر الحساسة)
# =========================================================================
def is_bot_owner():
    """شرط برمجي للتأكد من أن مستخدم الأمر هو المالك فقط."""
    async def predicate(ctx: commands.Context):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

# =========================================================================
# 📂 STATE MANAGEMENT (إدارة غرف الصوت وقائمة الانتظار)
# =========================================================================
class GuildState:
    def __init__(self):
        self.queue = []
        self.current = None
        self.voice_client = None
        self.locked_channel_id = None  # لحفظ روم الحراسة 24/7
        self.text_channel = None       # لحفظ آخر قناة نصية أرسل فيها أمر لإرسال التحديثات الفخمة تلقائياً

guild_states = {}

def get_state(guild_id):
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState()
    return guild_states[guild_id]

# =========================================================================
# 🎵 MUSIC PLAYER LOGIC (منطق استخراج وتشغيل الموسيقى)
# =========================================================================
async def fetch_track(query):
    """استخراج رابط الصوت المباشر ومعلومات المقطع ذكياً لتفادي نتائج البحث الفارغة."""
    loop = asyncio.get_event_loop()
    
    # التحقق مما إذا كان المدخل رابطًا مباشرًا أم نص بحث عادي
    if not query.startswith(("http://", "https://")):
        search_query = f"ytsearch1:{query}"
    else:
        search_query = query

    try:
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(search_query, download=False)
        )
        
        if not data:
            return None
            
        # التحقق وتجاوز مشكلة القائمة الفارغة للنتائج
        if "entries" in data:
            if not data["entries"]:
                print(f"[fetch_track Warning]: No search results found for query: {query}")
                return None
            data = data["entries"][0]
        
        # استخراج غلاف الفيديو أو استخدام غلاف افتراضي فخم
        thumbnail = data.get("thumbnail") or "https://i.imgur.com/8Wp9Z0v.png"
        
        return {
            "title": data.get("title", "Unknown Title"),
            "stream_url": data.get("url"),
            "url": data.get("webpage_url") or query,
            "thumbnail": thumbnail,
            "duration": data.get("duration", 0),
            "uploader": data.get("uploader", "غير معروف")
        }
    except Exception as e:
        print(f"[fetch_track Error]: {e}")
        return None

def format_duration(seconds):
    """تحويل ثواني المقطع إلى تنسيق دقيقة:ثانية بشكل منسق."""
    if not seconds:
        return "البث المباشر 🔴"
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def play_next(guild_id):
    """تشغيل المقطع التالي من طابور الانتظار تلقائياً مع إرسال بطاقة التشغيل الفخمة."""
    state = get_state(guild_id)
    if not state.voice_client or not state.voice_client.is_connected():
        return

    if not state.queue:
        state.current = None
        return

    state.current = state.queue.pop(0)
    
    try:
        source = discord.FFmpegPCMAudio(
            state.current["stream_url"],
            executable=FFMPEG_PATH,
            **FFMPEG_OPTS
        )
        
        def after_playing(error):
            if error:
                print(f"[Playback Error]: {error}")
            play_next(guild_id)

        state.voice_client.play(source, after=after_playing)
        
        # إرسال بطاقة تشغيل تلقائية فخمة جداً في الشات الفعال
        if state.text_channel:
            embed = discord.Embed(
                title="✨ تم الانتقال للمقطع التالي تلقائياً ✨",
                description=f"👑 **[{state.current['title']}]({state.current['url']})**",
                color=GOLD_COLOR
            )
            embed.add_field(name="🎙️ القناة الصوتية", value=f"`{state.voice_client.channel.name}`", inline=True)
            embed.add_field(name="⏳ مدة المقطع", value=f"`{format_duration(state.current['duration'])}`", inline=True)
            embed.add_field(name="👤 الناشر", value=f"`{state.current['uploader']}`", inline=True)
            if state.current["thumbnail"]:
                embed.set_thumbnail(url=state.current["thumbnail"])
            embed.set_footer(text="سيرفر سوالف العرب • نبرة الفخامة والروقان 👑")
            
            # إرسال الرسالة بشكل غير متزامن داخل الكولباك
            bot.loop.create_task(state.text_channel.send(embed=embed))
        
    except Exception as e:
        print(f"[play_next Exception]: {e}")
        play_next(guild_id)

# =========================================================================
# 🛡️ 24/7 VOICE GUARD TASK (مهمة الحراسة الصوتية الفخمة)
# =========================================================================
@tasks.loop(seconds=10)
async def voice_guard():
    """مهمة تعمل كل 10 ثوانٍ للتأكد من بقاء البوت في روم الحراسة المقفل لسيرفر سوالف العرب."""
    for guild_id, state in list(guild_states.items()):
        if not state.locked_channel_id:
            continue

        guild = bot.get_guild(guild_id)
        if not guild:
            continue

        channel = guild.get_channel(state.locked_channel_id)
        if not channel:
            continue

        # إذا لم يكن متصلاً بالصوت إطلاقاً
        if not state.voice_client or not state.voice_client.is_connected():
            try:
                state.voice_client = await channel.connect()
                print(f"[Guard]: Connected to locked channel {channel.name} in {guild.name}")
            except Exception as e:
                print(f"[Guard Reconnect Failed]: {e}")
        # إذا كان متصلاً بروم أخرى، يتم سحبه ونقله فوراً للروم المقفل
        elif state.voice_client.channel.id != state.locked_channel_id:
            try:
                await state.voice_client.move_to(channel)
                print(f"[Guard]: Moved back to locked channel {channel.name}")
            except Exception as e:
                print(f"[Guard Move Failed]: {e}")

# =========================================================================
# 📅 BOT EVENTS (أحداث البوت الأساسية)
# =========================================================================
@bot.event
async def on_ready():
    # تعديل حالة البوت بشكل يليق بسيرفر سوالف العرب
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="سوالف العرب 👑"))
    print(f"==================================================")
    print(f"✅ تم تشغيل نظام الصوت الفاخر بنجاح!")
    print(f"🤖 الاسم البرمجي: {bot.user}")
    print(f"👑 المالك والمشرف المعتمد: Mond Reef")
    print(f"⚙️ حراسة الروم الصوتية 24/7 نشطة وحية الآن.")
    print(f"==================================================")
    voice_guard.start()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # فحص المنشن المباشر للبوت لقفل حراسة الغرف
    if bot.user in message.mentions:
        if message.author.id != OWNER_ID:
            embed = discord.Embed(
                title="🛡️ نظام الحماية الملكي",
                description="عذراً يا عزيزي، إعداد حراسة الغرف 24/7 متاح فقط للمالك والمسؤول الإداري الأعلى **Mond Reef**.",
                color=RED_COLOR
            )
            embed.set_footer(text="سيرفر سوالف العرب")
            await message.reply(embed=embed)
            return

        stripped = re.sub(rf"<@!?{bot.user.id}>", "", message.content).strip()
        parts = stripped.split(maxsplit=1)

        if parts and parts[0].lower() == "set":
            arg = parts[1].strip() if len(parts) > 1 else None
            await handle_set_command(message, arg)
            return

    await bot.process_commands(message)

# =========================================================================
# 🔒 BOT ADMINISTRATIVE COMMANDS (أوامر الإدارة الحصرية للمالك)
# =========================================================================
async def handle_set_command(message: discord.Message, arg: str):
    """التحكم في قفل حراسة الصوت 24/7 بروم محددة (تصميم فخم جداً)."""
    state = get_state(message.guild.id)
    state.text_channel = message.channel
    
    if not arg:
        embed = discord.Embed(
            title="⚠️ إعداد ناقص",
            description="يرجى كتابة آيدي الروم الصوتية المطلوب ربطه وحراسته بالكامل.\n\n**طريقة الاستخدام:**\n`@البوت set [آيدي الروم]`",
            color=RED_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب")
        await message.reply(embed=embed)
        return

    try:
        channel_id = int(arg)
    except ValueError:
        embed = discord.Embed(
            title="❌ تنسيق خاطئ",
            description="الآيدي الرقمي للروم يجب أن يتكون من أرقام فقط دون حروف.",
            color=RED_COLOR
        )
        await message.reply(embed=embed)
        return

    channel = message.guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        embed = discord.Embed(
            title="🔍 لم يتم العثور على الروم",
            description="تعذر إيجاد الروم الصوتية المطلوبة في السيرفر الحالي. يرجى التأكد من الآيدي وصلاحيات البوت.",
            color=RED_COLOR
        )
        await message.reply(embed=embed)
        return

    state.locked_channel_id = channel_id
    
    embed = discord.Embed(
        title="🔒 تم تفعيل الحراسة الملكية 24/7",
        description=f"تم قفل وتثبيت البوت بشكل كامل في الروم الصوتية الفاخرة:\n🏆 **{channel.name}**\n\nلن يخرج البوت من هذه الروم وسيعود إليها تلقائياً فوراً إذا تم نقله أو فصله.",
        color=GOLD_COLOR
    )
    embed.set_thumbnail(url="https://i.imgur.com/8Wp9Z0v.png") # شعار قفل الحماية الفاخر
    embed.set_footer(text="سيرفر سوالف العرب • حماية وإدارة Mond Reef 👑")
    await message.reply(embed=embed)

@bot.command(name="destroy", aliases=["اطلع", "طرد"])
@is_bot_owner()
async def destroy(ctx: commands.Context):
    """طرد البوت نهائياً وفك قفل الحراسة والـ 24/7 (تصميم فخم جداً)."""
    state = get_state(ctx.guild.id)
    state.locked_channel_id = None  # إلغاء القفل الحارس
    state.queue.clear()
    state.current = None

    if state.voice_client and state.voice_client.is_connected():
        await state.voice_client.disconnect()
        state.voice_client = None
        
        embed = discord.Embed(
            title="👋 تم تفكيك نظام الحراسة بنجاح",
            description="تم تعطيل ميزة الـ 24/7 بشكل فوري، تصفير طابور التشغيل بالكامل، ومغادرة الغرفة الصوتية بناءً على توجيهات الإدارة.",
            color=GOLD_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب • بإشراف المالك Mond Reef 👑")
        await ctx.reply(embed=embed)
    else:
        embed = discord.Embed(
            title="ℹ️ تأكيد الإجراء",
            description="البوت غير متصل حالياً بأي روم، ولكن تم تصفير وإلغاء طوابير الانتظار تماماً بنجاح.",
            color=BLUE_COLOR
        )
        await ctx.reply(embed=embed)

# =========================================================================
# 🎵 MUSIC COMMANDS (أوامر الموسيقى العامة - منسقة بتصميم فخم لجميع الأعضاء)
# =========================================================================

@bot.command(name="play", aliases=["ش", "p", "شغل"])
async def play(ctx: commands.Context, *, query: str):
    """البحث عن مقطع يوتيوب وتشغيله أو إضافته للطابور بتصميم فخم."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            title="⚠️ تنبيه أمني للروم",
            description="يجب أن تكون متصلاً بإحدى القنوات الصوتية أولاً لتتمكن من تشغيل الصوتيات والاستماع!",
            color=RED_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب • منصة روتانا الفاخرة")
        await ctx.reply(embed=embed)
        return

    user_channel = ctx.author.voice.channel
    state = get_state(ctx.guild.id)
    state.text_channel = ctx.channel # تعيين القناة الحالية لتلقي التحديثات والرسائل اللاحقة

    # الاتصال بالروم إذا لم يكن متصلاً
    if not state.voice_client or not state.voice_client.is_connected():
        try:
            state.voice_client = await user_channel.connect()
        except Exception as e:
            embed = discord.Embed(
                title="❌ فشل الاتصال",
                description=f"حدث خطأ غير متوقع أثناء محاولة الدخول للروم الصوتية:\n`{e}`",
                color=RED_COLOR
            )
            await ctx.reply(embed=embed)
            return

    # إرسال رسالة جاري البحث الفخمة المؤقتة
    wait_embed = discord.Embed(
        description="🔍 **جاري استخراج وفحص الصوت من السيرفرات الرسمية...**",
        color=DARK_GOLD_COLOR
    )
    wait_msg = await ctx.reply(embed=wait_embed)

    track = await fetch_track(query)
    
    if not track:
        embed = discord.Embed(
            title="❌ خطأ فني بالاستخراج",
            description="تعذر إيجاد الملف الصوتي المطلوب أو لم يُرجع البحث نتائج. يرجى محاولة استخدام كلمات بحثية بديلة أو وضع رابط يوتيوب مباشر (وهو الخيار الأكثر استقرارًا للـ VPS).",
            color=RED_COLOR
        )
        await wait_msg.edit(embed=embed)
        return

    # التشغيل الفوري إذا لم يكن هناك شيء يعمل بالخلفية
    if not state.voice_client.is_playing() and not state.voice_client.is_paused():
        state.current = track
        try:
            source = discord.FFmpegPCMAudio(
                track["stream_url"],
                executable=FFMPEG_PATH,
                **FFMPEG_OPTS
            )
            
            def after_playing(error):
                if error:
                    print(f"[Playback Error]: {error}")
                play_next(ctx.guild.id)

            state.voice_client.play(source, after=after_playing)
            
            # تصميم بطاقة التشغيل المباشر الفاخرة جداً
            embed = discord.Embed(
                title="✨ جاري التشغيل الآن فعلياً ✨",
                description=f"🏆 **[{track['title']}]({track['url']})**",
                color=GOLD_COLOR
            )
            embed.add_field(name="🎙️ القناة الصوتية", value=f"`{user_channel.name}`", inline=True)
            embed.add_field(name="⏳ مدة المقطع", value=f"`{format_duration(track['duration'])}`", inline=True)
            embed.add_field(name="👤 طلب بواسطة", value=ctx.author.mention, inline=True)
            embed.add_field(name="📡 الناشر الأصلي", value=f"`{track['uploader']}`", inline=False)
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.set_footer(text="سيرفر سوالف العرب • استمع بأرقى وأفخم الأوقات 👑")
            
            await wait_msg.edit(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ فشل تشغيل المسار",
                description=f"تعذر دمج وبث الصوت عبر FFmpeg:\n`{e}`",
                color=RED_COLOR
            )
            await wait_msg.edit(embed=embed)
    else:
        # إضافة للطابور إذا كان هناك مقطع يعمل بالفعل (تصميم مخصص للاستعداد)
        state.queue.append(track)
        
        embed = discord.Embed(
            title="📥 تم إضافته لانتظار سوالف العرب",
            description=f"🛡️ **[{track['title']}]({track['url']})**",
            color=DARK_GOLD_COLOR
        )
        embed.add_field(name="🔢 الترتيب الحالي في الانتظار", value=f"`{len(state.queue)}`", inline=True)
        embed.add_field(name="⏳ مدة المقطع", value=f"`{format_duration(track['duration'])}`", inline=True)
        embed.add_field(name="👤 طلب بواسطة", value=ctx.author.mention, inline=True)
        if track["thumbnail"]:
            embed.set_thumbnail(url=track["thumbnail"])
        embed.set_footer(text="سيرفر سوالف العرب • طابور الموسيقى الملكي 👑")
        
        await wait_msg.edit(embed=embed)

@bot.command(name="pause", aliases=["وقف", "stop"])
async def pause(ctx: commands.Context):
    """إيقاف تشغيل الموسيقى مؤقتاً بتصميم فخم."""
    state = get_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_playing():
        state.voice_client.pause()
        embed = discord.Embed(
            title="⏸️ تم الإيقاف المؤقت",
            description=f"تم إيقاف تشغيل المقطع الحالي مؤقتاً بواسطة {ctx.author.mention}.\nلاستئناف البث اكتب `-resume` أو `-r`.",
            color=BLUE_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب • نظام التحكم الصوتي")
        await ctx.reply(embed=embed)
    else:
        embed = discord.Embed(
            title="ℹ️ حالة النظام",
            description="لا توجد صوتيات تعمل حالياً لإيقافها مؤقتاً.",
            color=BLUE_COLOR
        )
        await ctx.reply(embed=embed)

@bot.command(name="resume", aliases=["كمل", "r"])
async def resume(ctx: commands.Context):
    """استئناف تشغيل الموسيقى المتوقفة مؤقتاً."""
    state = get_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_paused():
        state.voice_client.resume()
        embed = discord.Embed(
            title="▶️ تم استئناف البث الصوتي",
            description=f"تم إكمال تشغيل المقطع الحالي بنجاح بواسطة {ctx.author.mention}.",
            color=BLUE_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب • استماع ممتع")
        await ctx.reply(embed=embed)
    else:
        embed = discord.Embed(
            title="ℹ️ حالة النظام",
            description="المسار الصوتي مستمر في العمل بالفعل أو لا يوجد شيء قيد الانتظار حالياً.",
            color=BLUE_COLOR
        )
        await ctx.reply(embed=embed)

@bot.command(name="skip", aliases=["تخطي", "s"])
async def skip(ctx: commands.Context):
    """تخطي الأغنية الحالية والانتقال للتالية."""
    state = get_state(ctx.guild.id)
    if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
        state.voice_client.stop() # يستدعي after_playing تلقائياً لتشغيل التالي
        embed = discord.Embed(
            title="⏭️ تخطي ناجح",
            description=f"تم تخطي المقطع الصوتي الحالي بنجاح بواسطة {ctx.author.mention}.\nجاري تحضير وتجهيز المقطع التالي في الطابور...",
            color=GOLD_COLOR
        )
        embed.set_footer(text="سيرفر سوالف العرب")
        await ctx.reply(embed=embed)
    else:
        embed = discord.Embed(
            title="ℹ️ حالة النظام",
            description="لا توجد أي أغنية تعمل بالخلفية لتخطيها حالياً.",
            color=BLUE_COLOR
        )
        await ctx.reply(embed=embed)

# =========================================================================
# 🏃‍♂️ RUN THE BOT (تشغيل البوت الفعلي)
# =========================================================================
if __name__ == "__main__":
    bot.run(TOKEN)
