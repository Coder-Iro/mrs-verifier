import interactions

import tormysql
import re
import time, datetime

from os import environ
from dotenv import load_dotenv

from mojang import MojangAPI
from mcstatus import JavaServer


load_dotenv()

GUILD_ID = 330997213255827457
EMBED_COLOR = 15844367

SQL = {
    'host': "localhost",
    'port': 3306,
    'user': "root",
    'passwd': "",
    'db': "mcauth",
}

MSG_INVAILD_UUID = "유효하지 않은 uuid입니다. 32자리의 uuid를 대시(-)를 포함하여 정확히 입력해주세요."
MSG_INVALID_NAME = "유효하지 않은 닉네임입니다. 마인크래프트 닉네임을 정확히 입력해주세요."

UUID_REGEX_CODE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

start_time = time.time()
pool = tormysql.ConnectionPool(**SQL)
bot = interactions.Client(token=environ["TOKEN"], intents=interactions.Intents.ALL)

def get_footer():
    return time.strftime(f"%Y.%m.%d. %H:%M:%S", time.localtime()) + " [개발 버전]"

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
        return await ctx.send("서버 정보를 불러올 수 없습니다.", ephemeral=True)
    
    
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