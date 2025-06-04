import discord
from discord.ext import commands, tasks
from datetime import datetime
from pytz import timezone
from dotenv import load_dotenv
from db import (
    save_attendance, get_attendance, add_exp, get_level,
    save_wakeup, log_study_time, get_today_study_time,
    get_top_users_by_exp, get_monthly_stats, get_weekly_stats,
    get_streak_attendance, get_streak_wakeup, get_streak_study
)
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

TRACKED_VOICE_CHANNELS = ["🎥｜캠스터디"]
study_sessions = {}  # {user_id: {"start": datetime, "msg_id": int}}
RANKING_CHANNEL_ID = 1378863730741219458  # 👑｜랭킹
ranking_message_id = None

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 로 로그인 완료!")
    await setup_ranking_message()
    update_ranking.start()

async def setup_ranking_message():
    global ranking_message_id
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds and "경험치 랭킹" in (msg.embeds[0].title or ""):
            ranking_message_id = msg.id
            break
    else:
        embed = make_ranking_embed()
        msg = await channel.send(embed=embed)
        await msg.pin()
        ranking_message_id = msg.id

@tasks.loop(minutes=1)
async def update_ranking():
    now = datetime.now(timezone('Asia/Seoul'))
    if now.hour == 0 and now.minute == 0:
        channel = bot.get_channel(RANKING_CHANNEL_ID)
        if ranking_message_id:
            try:
                msg = await channel.fetch_message(ranking_message_id)
                embed = make_ranking_embed()
                await msg.edit(embed=embed)
            except Exception as e:
                print("랭킹 메시지 수정 실패:", e)

def make_ranking_embed():
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    ranking = get_top_users_by_exp()
    embed = discord.Embed(
        title="🏆 경험치 랭킹 TOP 10",
        color=discord.Color.gold()
    )
    if not ranking:
        embed.description = "아직 아무도 경험치를 쌓지 않았어요! 🌱"
    else:
        msg = ""
        for i, (name, exp) in enumerate(ranking, start=1):
            crown = "👑" if i == 1 else ""
            level = calculate_level_from_exp(exp)
            msg += f"{i}위 {crown} **{name}** - Lv.{level} / {exp} Exp\n"
        embed.description = msg
    embed.set_footer(text=today_str)
    return embed

def calculate_level_from_exp(exp):
    thresholds = [0, 30, 80, 150, 250, 400, 600]
    level = 1
    for i, threshold in enumerate(thresholds):
        if exp < threshold:
            break
        level = i + 1
    return level

# === 공부 입퇴장 메시지 edit 구조 ===

@bot.event
async def on_voice_state_update(member, before, after):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    after_channel = after.channel.name if after.channel else None
    before_channel = before.channel.name if before.channel else None
    study_channel = discord.utils.get(member.guild.text_channels, name="📕｜공부기록")
    embed_color = member.color

    # 입장
    if after_channel in TRACKED_VOICE_CHANNELS and before.channel != after_channel:
        embed = discord.Embed(
            title="🎀 공듀의 입장 🎀",
            description=(f"{member.mention} 공듀님이 도서관에 나타났어요!\n오늘도 집중모드 발동✨"),
            color=embed_color
        )
        embed.set_footer(text=today_str)
        msg = await study_channel.send(embed=embed)
        study_sessions[member.id] = {
            'start': now,
            'msg_id': msg.id
        }

    # 퇴장
    if before_channel in TRACKED_VOICE_CHANNELS and (
        after.channel is None or after_channel not in TRACKED_VOICE_CHANNELS
    ):
        session = study_sessions.pop(member.id, None)
        if session:
            end_time = datetime.now(timezone('Asia/Seoul'))
            duration = (end_time - session['start']).total_seconds() / 60
            try:
                msg = await study_channel.fetch_message(session['msg_id'])
            except Exception:
                msg = None

            if duration < 10:
                embed = discord.Embed(
                    title="⏰ 집중 실패! (10분 미만)",
                    description=(f"{member.mention} 공듀님, 10분 미만은 집중 인정 불가에요!\n다시 도전해볼까요?"),
                    color=embed_color
                )
                embed.set_footer(text=today_str)
                if msg:
                    await msg.edit(embed=embed)
                else:
                    await study_channel.send(embed=embed)
                return

            log_study_time(member.id, int(duration))
            exp = round((duration / 30) * 10)
            add_exp(member.id, exp)
            level = get_level(member.id)
            today_total = get_today_study_time(member.id)

            h = int(duration) // 60
            m = int(duration) % 60
            time_str = f"{h}시간 {m}분" if h else f"{m}분"

            embed = discord.Embed(
                title="✨ 집중 완료! 공듀 퇴장 ✨",
                description=(f"{member.mention} 공듀님 오늘도 대단해요!\n공부박스 도착🎁"),
                color=embed_color
            )
            embed.add_field(name="⏳ 공부한 시간", value=f"**{time_str}**", inline=False)
            embed.add_field(name="🌹 획득 경험치", value=f"**{exp} Exp**", inline=True)
            embed.add_field(name="👑 오늘 누적", value=f"**{today_total}분**", inline=True)
            embed.add_field(name="🏅 현재 레벨", value=f"**Lv.{level}**", inline=True)
            embed.set_footer(text=today_str)
            if msg:
                await msg.edit(embed=embed)
            else:
                await study_channel.send(embed=embed)

# ======= 아래부터 기존 명령어 커맨드들 그대로 붙여서 사용 (출석, 기상, 기록 등) =======

@bot.command(name="출석")
async def checkin(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    date_str = now.strftime("%y/%m/%d")
    hour = now.hour
    is_late = hour >= 9
    nickname = ctx.author.display_name
    embed_color = ctx.author.color

    saved = save_attendance(ctx.author.id, nickname)

    embed = discord.Embed(color=embed_color)
    if not saved:
        embed.title = "👑 출석 실패"
        embed.description = f"{ctx.author.mention} 공듀님, 오늘은 이미 출석하셨어요! 🐣"
    else:
        exp_gained = 5 if not is_late else 3
        add_exp(ctx.author.id, exp_gained)
        level = get_level(ctx.author.id)
        embed.title = "👑 출석 완료"
        if is_late:
            embed.description = f"{ctx.author.mention} 공듀님, 지각핑! 늦은만큼 더 달려보자 공듀🔥 (+{exp_gained} Exp)"
        else:
            embed.description = f"{ctx.author.mention} 공듀님, 출석 완료! 오늘도 힘내보자 공듀❤️‍🔥 (+{exp_gained} Exp)"
        embed.add_field(name="📅 날짜", value=date_str)
        embed.add_field(name="🎁 현재 레벨", value=f"Lv.{level}")

    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="기상", aliases=["굿모닝"])
async def wakeup(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    date_str = now.strftime("%y/%m/%d")
    hour = now.hour
    is_late = hour >= 9
    nickname = ctx.author.display_name
    embed_color = ctx.author.color

    saved = save_wakeup(ctx.author.id, nickname)

    embed = discord.Embed(color=embed_color)
    if not saved:
        embed.title = "☀️ 기상 실패"
        embed.description = f"{ctx.author.mention} 공듀님, 오늘은 이미 기상 인증했어요! ☀️"
    else:
        exp_gained = 5 if not is_late else 3
        add_exp(ctx.author.id, exp_gained)
        level = get_level(ctx.author.id)
        embed.title = "☀️ 기상 인증 완료"
        if is_late:
            embed.description = f"{ctx.author.mention} 공듀님, 늦잠 잤지만 인증 완료! ☁️ (+{exp_gained} Exp)"
        else:
            embed.description = f"{ctx.author.mention} 공듀님, 눈부신 아침이에요! 🌞 (+{exp_gained} Exp)"
        embed.add_field(name="📅 날짜", value=date_str)
        embed.add_field(name="🎁 현재 레벨", value=f"Lv.{level}")

    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="출석기록")
async def show_attendance(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    rows = get_attendance(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(color=embed_color)
    embed.title = "📒 출석 기록"

    if not rows:
        embed.description = f"{ctx.author.mention} 공듀님은 아직 출석 기록이 없어!🏫"
    else:
        dates = [row[0] for row in rows]
        formatted = "\n".join(f"✅ {d}" for d in dates)
        embed.description = f"{ctx.author.mention} 공듀님의 출석 기록:\n{formatted}"

    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="내정보")
async def my_info(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    nickname = ctx.author.display_name
    level = get_level(user_id)
    embed_color = ctx.author.color

    embed = discord.Embed(
        title="✨ 내 정보",
        description=f"{ctx.author.mention} 공듀님의 현재 레벨",
        color=embed_color
    )
    embed.add_field(name="👑 레벨", value=f"Lv.{level}")
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="월통계")
async def monthly_stats(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    stats = get_monthly_stats(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(
        title="📅 이번달 통계",
        color=embed_color
    )
    embed.add_field(name="출석일수", value=f"{stats['attendance']}일")
    embed.add_field(name="기상일수", value=f"{stats['wakeup']}일")
    embed.add_field(name="공부일수", value=f"{stats['study_days']}일")
    embed.add_field(name="총 공부시간", value=f"{stats['study_minutes']}분")
    embed.add_field(name="획득 Exp", value=f"{stats['exp']}Exp")
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="주통계")
async def weekly_stats(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    stats = get_weekly_stats(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(
        title="🗓️ 이번주 통계",
        color=embed_color
    )
    embed.add_field(name="출석일수", value=f"{stats['attendance']}일")
    embed.add_field(name="기상일수", value=f"{stats['wakeup']}일")
    embed.add_field(name="공부일수", value=f"{stats['study_days']}일")
    embed.add_field(name="총 공부시간", value=f"{stats['study_minutes']}분")
    embed.add_field(name="획득 Exp", value=f"{stats['exp']}Exp")
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="연속출석")
async def streak_attendance(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    streak = get_streak_attendance(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(
        title="🌱 연속 출석일수",
        description=f"{ctx.author.mention} 공듀님의 연속 출석일수는 {streak}일이에요!",
        color=embed_color
    )
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="연속기상")
async def streak_wakeup(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    streak = get_streak_wakeup(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(
        title="⏰ 연속 기상일수",
        description=f"{ctx.author.mention} 공듀님의 연속 기상일수는 {streak}일이에요!",
        color=embed_color
    )
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="연속공부")
async def streak_study(ctx):
    now = datetime.now(timezone('Asia/Seoul'))
    today_str = now.strftime("%Y년 %m월 %d일")
    user_id = ctx.author.id
    streak = get_streak_study(user_id)
    embed_color = ctx.author.color
    embed = discord.Embed(
        title="📚 연속 공부일수",
        description=f"{ctx.author.mention} 공듀님의 연속 공부일수는 {streak}일이에요!",
        color=embed_color
    )
    embed.set_footer(text=today_str)
    await ctx.send(embed=embed)

@bot.command(name="명령어")
async def command_list(ctx):
    ranking_channel_id = 1378863730741219458   # 👑｜랭킹
    attendance_channel_id = 1378862713484218489  # 🍀｜출석체크
    wakeup_channel_id = 1378862771214745690     # 🌅｜기상인증
    myinfo_channel_id = 1378952514702938182     # 🏠｜내정보

    embed_color = ctx.author.color
    embed = discord.Embed(
        title="💡 사용 가능한 명령어 모음",
        description="각 채널에서 명령어를 입력해보세요!\n아래 채널명 클릭 시 바로 이동됩니다.",
        color=embed_color
    )
    embed.add_field(
        name="👑 랭킹",
        value=(
            f"<#{ranking_channel_id}> 에서 사용\n"
            "`!랭킹` - 전체 경험치 순위 TOP 10"
        ),
        inline=False
    )
    embed.add_field(
        name="🍀 출석",
        value=(
            f"<#{attendance_channel_id}> 에서 사용\n"
            "`!출석` - 오늘 출석 체크\n"
            "`!출석기록` - 내 출석 날짜 전체 확인"
        ),
        inline=False
    )
    embed.add_field(
        name="🌅 기상",
        value=(
            f"<#{wakeup_channel_id}> 에서 사용\n"
            "`!기상` 또는 `!굿모닝` - 오늘 기상 인증"
        ),
        inline=False
    )
    embed.add_field(
        name="🏠 내 정보·통계",
        value=(
            f"<#{myinfo_channel_id}> 에서 사용\n"
            "`!내정보` - 내 레벨 및 프로필\n"
            "`!월통계` - 이번달 통계\n"
            "`!주통계` - 이번주 통계\n"
            "`!연속출석` `!연속기상` `!연속공부`"
        ),
        inline=False
    )
    embed.add_field(
        name="Voice 자동 기록",
        value=(
            "- `🎥｜캠스터디`, `독서실` 채널에 입퇴장 시 자동으로 공부시간 기록"
        ),
        inline=False
    )
    embed.set_footer(text="궁금한 점은 언제든 !명령어 로 확인해 주세요!")
    await ctx.send(embed=embed)

bot.run(TOKEN)
