import interactions

import tormysql
import re
import redis
import time, datetime

from mojang import MojangAPI
from mcstatus import JavaServer

import config

TOKEN = config.TOKEN
GUILD_ID = config.GUILD_ID
NEWBIE_ROLE_ID = config.NEWBIE_ROLE_ID
EMBED_COLOR = config.EMBED_COLOR
SQL = config.SQL
REDIS = config.REDIS

MSG_MATCH = "마인크래프트 계정 `{mcnick}` 이/가 성공적으로 인증되었습니다."
MSG_DISMATCH = "인증번호가 일치하지 않습니다."

MSG_UNVERIFY_FAIL = "입력한 문구가 올바르지 않습니다. 계정 인증 해제를 취소합니다."
MSG_UNVERIFY_SUCCESS = "계정 인증이 성공적으로 해제되었습니다."

MSG_INVAILD_UUID = "유효하지 않은 uuid입니다. 32자리의 uuid를 대시(-)를 포함하여 정확히 입력해주세요."
MSG_INVALID_NAME = "유효하지 않은 닉네임입니다. 마인크래프트 닉네임을 정확히 입력해주세요."
MSG_INVAILD_CODE = "유효하지 않은 인증코드입니다. 인증코드는 띄어쓰기 없이 6자리 숫자로 입력해주세요."

MSG_DUPLICATE = "마인크래프트 계정 `{mcnick}` 은 이미 인증된 계정입니다. 본인이 인증한 것이 아니라면 고객센터에 문의해주세요."
MSG_BANNED = "마인크래프트 계정 `{mcnick}` 은/는 차단된 계정입니다. 차단된 계정으로는 인증하실 수 없습니다."

MSG_SERVER_DOWN = "서버 정보를 불러올 수 없습니다."

SQL_CHECK_DUPLICATE = "SELECT * FROM linked_account WHERE mcuuid=%s"
SQL_CHECK_BLACK = "SELECT * FROM blacklist WHERE mcuuid=%s"
SQL_INSERT = "INSERT INTO linked_account(discord,mcuuid) values (%s, %s)"
SQL_DELETE = "DELETE FROM linked_account WHERE discord=%s"

REGEX_CODE = re.compile(r'\d{6}')
UUID_REGEX_CODE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

start_time = time.time()
pool = tormysql.ConnectionPool(**SQL)
rd = redis.StrictRedis(**REDIS)
bot = interactions.Client(token=TOKEN, intents=interactions.Intents.ALL)

def get_footer():
    return time.strftime(f"%Y.%m.%d. %H:%M:%S", time.localtime()) + " [개발 버전]"

@bot.command(
    name="verify",
    description="마인크래프트 계정을 인증합니다.",
    scope=GUILD_ID
)
async def verify(ctx: interactions.CommandContext):
    modal = interactions.Modal(
        title="MRS 마인크래프트 계정 인증",
        custom_id="modal_verify",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="마인크래프트 닉네임",
                custom_id="mcnick",
                required=True,
                min_length=3,
                max_length=16
            ),
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="인증코드 (띄어쓰기 없이 입력)",
                custom_id="code",
                required=True,
                placeholder=123456,
                min_length=6,
                max_length=6
            )
        ]
    )
    
    await ctx.popup(modal)

@bot.modal("modal_verify")
async def verify_response(ctx: interactions.CommandContext, mcnick: str, code: str):
    if not REGEX_CODE.match(code):
        return await ctx.send(MSG_INVAILD_CODE, ephemeral=True)
    
    if rd.exists(mcnick):
        realcode = rd.hget(mcnick, "code").decode("UTF-8")
        uuid = rd.hget(mcnick, "UUID").decode("UTF-8")
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                if await cur.execute(SQL_CHECK_DUPLICATE, (uuid, )):
                    return await ctx.send(MSG_DUPLICATE.format(mcnick=mcnick), ephemeral=True)
                if await cur.execute(SQL_CHECK_BLACK, (uuid, )):
                    return await ctx.send(MSG_BANNED.format(mcnick=mcnick), ephemeral=True)
        if realcode == code:
            await ctx.author.modify(nick=mcnick)
            async with await pool.Connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(SQL_INSERT, (int(ctx.author.id), uuid))
                await conn.commit()
            await ctx.send(MSG_MATCH.format(mcnick=mcnick), ephemeral=True)
        else:
            await ctx.send(MSG_DISMATCH, ephemeral=True)
    else:
        await ctx.send(MSG_INVALID_NAME, ephemeral=True)

@bot.command(
    name="unverify",
    description="마인크래프트 계정 인증을 해제합니다.",
    scope=GUILD_ID
)
async def unverify(ctx: interactions.CommandContext):
    modal = interactions.Modal(
        title="MRS 계정 인증 해제",
        custom_id="modal_unverify",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="인증을 해제하시려면 본인의 닉네임을 정확히 입력해주세요.",
                custom_id="check_msg",
                required=True,
                placeholder=ctx.author.nick
            )
        ]
    )
    
    await ctx.popup(modal)

@bot.modal("modal_unverify")
async def unverify_response(ctx: interactions.CommandContext, check_msg: str):
    if not check_msg == ctx.author.nick:
        return await ctx.send(MSG_UNVERIFY_FAIL, ephemeral=True)
    
    await ctx.author.remove_role(role=NEWBIE_ROLE_ID)
    async with await pool.Connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SQL_DELETE, (int(ctx.author.id), ))
        await conn.commit()
    await ctx.send(MSG_UNVERIFY_SUCCESS, ephemeral=True)

@bot.command(
    name="status",
    description="MRS 인증봇 현황을 확인합니다.",
    scope=GUILD_ID
)
async def status(ctx: interactions.CommandContext):
    uptime = str(datetime.timedelta(seconds=(time.time() - start_time))).split(".")[0]

    await ctx.send(embeds=interactions.Embed(
        title="MRS 인증봇 현황",
        color=EMBED_COLOR,
        fields=[
            interactions.EmbedField(
                name="인증봇 업타임",
                value=uptime
            )
        ],
        footer=interactions.EmbedFooter(
            text=get_footer()
        )
    ))

@bot.command(
    name="query",
    description="IP 주소로 마인크래프트 서버 정보를 확인합니다.",
    scope=GUILD_ID,
    options=[
        interactions.Option(
            name="ip",
            description="마인크래프트 서버의 IP 주소를 정확하게 입력해주세요.",
            type=interactions.OptionType.STRING,
            required=True
        )
    ]
)
async def query(ctx: interactions.CommandContext, ip: str = None):
    try:
        server = JavaServer.lookup(ip).status()
    except:
        return await ctx.send(MSG_SERVER_DOWN, ephemeral=True)
    
    
    await ctx.send(embeds=interactions.Embed(
        title="마인크래프트 서버 정보",
        color=EMBED_COLOR,
        fields=[
            interactions.EmbedField(
                name="서버 주소",
                value=ip
            ),
            interactions.EmbedField(
                name="MOTD",
                value=server.description
            ),
            interactions.EmbedField(
                name="버전",
                value=server.version.name,
                inline=True
            ),
            interactions.EmbedField(
                name="접속자 수",
                value=f"{server.players.online}/{server.players.max}명",
                inline=True
            ),
            interactions.EmbedField(
                name="지연 시간",
                value=f"{server.latency:.1f}ms",
                inline=True
            )
        ],
        footer=interactions.EmbedFooter(
            text=get_footer()
        )
    ))

@bot.command(
    name="profile",
    description="마인크래프트 프로필을 조회합니다.",
    scope=GUILD_ID,
    options=[
        interactions.Option(
            name="uuid",
            description="uuid로 마인크래프트 프로필을 조회합니다.",
            type=interactions.OptionType.SUB_COMMAND,
            options=[
                interactions.Option(
                    name="uuid",
                    description="마인크래프트 유저의 uuid를 대시(-)를 포함하여 정확하게 입력하세요.",
                    type=interactions.OptionType.STRING,
                    required=True,
                )
            ]
        ),
        interactions.Option(
            name="name",
            description="닉네임으로 마인크래프트 프로필을 조회합니다.",
            type=interactions.OptionType.SUB_COMMAND,
            options=[
                interactions.Option(
                    name="name",
                    description="마인크래프트 닉네임을 정확하게 입력하세요.",
                    type=interactions.OptionType.STRING,
                    required=True,
                )
            ]
        )
    ]
)
async def profile(ctx: interactions.CommandContext, sub_command: str, uuid: str = None, name: str = None):
    if sub_command == "uuid":
        profile = MojangAPI.get_profile(uuid)
        if not UUID_REGEX_CODE.match(uuid) or not profile:
            return await ctx.send(MSG_INVAILD_UUID, ephemeral=True)
    elif sub_command == "name":
        uuid = MojangAPI.get_uuid(name)
        if not uuid:
            return await ctx.send(MSG_INVALID_NAME, ephemeral=True)
        uuid = '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:]])
    
    profile = MojangAPI.get_profile(uuid)
    
    name_history = ""
    for data in MojangAPI.get_name_history(uuid):
        if data['changed_to_at'] == 0:
            changed_time = "계정 생성"
        else:
            changed_time = time.strftime(f"%Y.%m.%d. %H:%M:%S", time.localtime(data['changed_to_at'] // 1000))
        name_history = name_history + f"`{data['name']}` ({changed_time})\n"
    
    if profile.cape_url:
        cape = f"[바로가기]({profile.cape_url})"
    else:
        cape = f"없음"
    
    await ctx.send(embeds=interactions.Embed(
        author=interactions.EmbedAuthor(
            name=f"{profile.name}",
            icon_url=f"https://mc-heads.net/head/{uuid}"
        ),
        thumbnail=interactions.EmbedImageStruct(
            url=f"https://mc-heads.net/body/{uuid}"
        ),
        color=EMBED_COLOR,
        fields=[
            interactions.EmbedField(
                name="UUID",
                value=uuid
            ),
            interactions.EmbedField(
                name="닉네임 변경 내역",
                value=name_history
            ),
            interactions.EmbedField(
                name=f"스킨 ({profile.skin_model})",
                value=f"[바로가기]({profile.skin_url})",
                inline=True
            ),
            interactions.EmbedField(
                name="망토",
                value=cape,
                inline=True
            )
        ],
        footer=interactions.EmbedFooter(
            text=get_footer()
        )
    ))

bot.start()