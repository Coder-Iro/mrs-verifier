from ast import Pass
from flask_discord_interactions import User
import interactions

import tormysql
import re
import redis
import time, datetime

from mojang import MojangAPI
from mcstatus import JavaServer

import config

from abc import ABCMeta, abstractmethod

TOKEN: str = config.TOKEN
GUILD_ID: int = config.GUILD_ID
NEWBIE_ROLE_ID: int = config.NEWBIE_ROLE_ID
EMBED_COLOR: int = config.EMBED_COLOR
SQL: dict = config.SQL
REDIS: dict = config.REDIS

MSG_VERIFY_SUCCESS = "마인크래프트 계정 `{mcnick}` 이/가 성공적으로 인증되었습니다."
MSG_VERIFY_FAIL = "인증번호가 일치하지 않습니다."
MSG_VERIFY_ALREADY = "마인크래프트 계정 `{mcnick}` 은 이미 인증된 계정입니다."
MSG_VERIFY_BANNED = "마인크래프트 계정 `{mcnick}` 은/는 차단된 계정입니다. 차단된 계정으로는 인증하실 수 없습니다."

MSG_UNVERIFY_SUCCESS = "마인크래프트 계정 `{mcnick}`의 인증이 성공적으로 해제되었습니다."
MSG_UNVERIFY_CANCEL = "입력한 닉네임이 올바르지 않습니다. 계정 인증 해제를 취소합니다."
MSG_UNVERIFY_FAIL = "인증되지 않은 유저입니다. 인증된 유저만 인증을 해제할 수 있습니다."

MSG_UPDATE_SUCCESS = "계정 정보를 성공적으로 갱신하였습니다."
MSG_UPDATE_ALREADY = "계정 정보가 이미 최신이므로 갱신할 필요가 없습니다."
MSG_UPDATE_FAIL = "계정 정보가 존재하지 않거나 Mojang API에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

MSG_BAN_SUCCESS = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 의 계정 인증이 차단되었습니다."
MSG_BAN_FAIL = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 은/는 이미 차단되었습니다."

MSG_UNBAN_SUCCESS = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 의 계정 인증 차단이 해제되었습니다."
MSG_UNBAN_FAIL = "차단되지 않은 계정입니다. 차단된 계정에 대해서만 계정 인증 차단을 해제할 수 있습니다."

MSG_INVALID_UUID = "유효하지 않은 uuid입니다. 32자리의 uuid를 대시(-)를 포함하여 정확히 입력해주세요."
MSG_INVALID_NAME = "유효하지 않은 닉네임입니다. 마인크래프트 닉네임을 정확히 입력해주세요."
MSG_INVALID_CODE = "유효하지 않은 인증코드입니다. 인증코드는 띄어쓰기 없이 6자리 숫자로 입력해주세요."

MSG_SERVER_DOWN = "서버 정보를 불러올 수 없습니다."

SQL_CHECK_DUPLICATE = "SELECT * FROM linked_account WHERE mcuuid=%s"
SQL_CHECK_BLACK = "SELECT * FROM blacklist WHERE mcuuid=%s"
SQL_INSERT = "INSERT INTO linked_account(discord,mcuuid) values (%s, %s)"
SQL_INSERT_BLACK = "INSERT INTO blacklist(mcuuid) values (%s)"
SQL_DELETE = "DELETE FROM linked_account WHERE discord=%s"
SQL_DELETE_BLACK = "DELETE FROM blacklist WHERE mcuuid=%s"
SQL_GETUUID = "SELECT * FROM linked_account WHERE discord=%s"
SQL_COUNT_VERIFIED = "SELECT COUNT(*) as cnt FROM linked_account"
SQL_COUNT_BANNED = "SELECT COUNT(*) as cnt FROM blacklist"

REGEX_CODE = re.compile(r'\d{6}')
UUID_REGEX_CODE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

start_time: float = time.time()
pool = tormysql.ConnectionPool(**SQL)
rd = redis.StrictRedis(**REDIS)
bot = interactions.Client(token=TOKEN, intents=interactions.Intents.ALL)

def get_footer() -> str:
    return time.strftime(f"%Y.%m.%d. %H:%M:%S", time.localtime()) + " [MRS Verifier V2 Beta]"

def get_nickname(member: interactions.Member) -> str:
    return member.nick if member.nick else member.user.username

class VerificationError(Exception):
    pass

class ProfileError(Exception):
    pass

class BaseVerifier(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, ctx: interactions.CommandContext, *args):
        pass

    @abstractmethod
    async def _get_profile(self):
        pass

    async def _check_db(self):
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                if await cur.execute(SQL_CHECK_DUPLICATE, (self.uuid, )):
                    raise VerificationError(MSG_VERIFY_ALREADY.format(mcnick=self.mcnick))
                if await cur.execute(SQL_CHECK_BLACK, (self.uuid, )):
                    raise VerificationError(MSG_VERIFY_BANNED.format(mcnick=self.mcnick))

    @abstractmethod
    async def _apply_verify(self):
        pass

    @abstractmethod
    async def verify(self):
        pass


class Verifier(BaseVerifier):
    def __init__(self, ctx: interactions.CommandContext, mcnick: str, code: str):
        self.ctx: interactions.CommandContext = ctx
        self.mcnick: str = mcnick
        self.code: str = code

    async def _get_profile(self):
        if rd.exists(self.mcnick):
            self.realcode: str = rd.hget(self.mcnick, "code").decode("UTF-8")
            self.uuid: str = rd.hget(self.mcnick, "UUID").decode("UTF-8")
        else:
            raise VerificationError(MSG_INVALID_NAME)
    
    async def _validate_code(self):
        if not REGEX_CODE.match(self.code):
            raise VerificationError(MSG_INVALID_CODE)

    async def _verify_code(self):
        if self.realcode != self.code:
            raise VerificationError(MSG_VERIFY_FAIL)
    
    async def _apply_verify(self):
        await self.ctx.author.modify(nick=self.mcnick, guild_id=GUILD_ID)
        await self.ctx.author.remove_role(role=NEWBIE_ROLE_ID, guild_id=GUILD_ID)
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SQL_INSERT, (int(self.ctx.author.id), self.uuid))
            await conn.commit()
    
    async def verify(self):
        try:
            await self._get_profile()
            await self._validate_code()
            await self._check_db()
            await self._verify_code()
            await self._apply_verify()
        except VerificationError as e:
            return await self.ctx.send(e, ephemeral=True)
        
        return await self.ctx.send(MSG_VERIFY_SUCCESS.format(mcnick=self.mcnick), ephemeral=True)


class ForceVerifier(BaseVerifier):
    def __init__(self, ctx: interactions.CommandContext, user: interactions.Member, mcnick: str):
        self.ctx: interactions.CommandContext = ctx
        self.user: interactions.Member = user
        self.mcnick: str = mcnick

    async def _get_profile(self):
        uuid = MojangAPI.get_uuid(self.mcnick)
        if not uuid:
            raise VerificationError(MSG_INVALID_NAME)
        self.uuid: str = '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:]])
        self.mcnick: str = MojangAPI.get_username(self.uuid)
    
    async def _apply_verify(self):
        await self.user.modify(nick=self.mcnick, guild_id=GUILD_ID)
        await self.user.remove_role(role=NEWBIE_ROLE_ID, guild_id=GUILD_ID)
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SQL_INSERT, (int(self.user.id), self.uuid))
            await conn.commit()

    async def verify(self):
        try:
            await self._get_profile()
            await self._check_db()
            await self._apply_verify()
        except VerificationError as e:
            return await self.ctx.send(e, ephemeral=True)

        return await self.ctx.send(MSG_VERIFY_SUCCESS.format(mcnick=self.mcnick), ephemeral=True)

class BaseUnverifier(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, ctx: interactions.CommandContext, *args):
        pass

    @abstractmethod
    async def _get_profile(self):
        pass

    @abstractmethod
    async def _apply_unverify(self):
        pass

    @abstractmethod
    async def unverify(self):
        pass

class Unverifier(BaseUnverifier):
    def __init__(self, ctx: interactions.CommandContext, check_msg: str):
        self.ctx: interactions.CommandContext = ctx
        self.check_msg: str = check_msg
    
    async def _get_profile(self):
        self.mcnick: str = self.ctx.author.nick if self.ctx.author.nick else self.ctx.author.user.username
    
    async def _check_nick(self):
        if not self.check_msg == self.mcnick:
            raise VerificationError(MSG_UNVERIFY_CANCEL)
    
    async def _apply_unverify(self):
        await self.ctx.author.add_role(role=NEWBIE_ROLE_ID, guild_id=GUILD_ID)
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SQL_DELETE, (int(self.ctx.author.id), ))
            await conn.commit()
    
    async def unverify(self):
        try:
            await self._get_profile()
            await self._check_nick()
            await self._apply_unverify()
        except VerificationError as e:
            return await self.ctx.send(e, ephemeral=True)
        
        return await self.ctx.send(MSG_UNVERIFY_SUCCESS.format(mcnick=self.mcnick), ephemeral=True)

class ForceUnverifier(BaseUnverifier):
    def __init__(self, ctx: interactions.CommandContext, user: interactions.Member):
        self.ctx: interactions.CommandContext = ctx
        self.user: interactions.Member = user
    
    async def _get_profile(self):
        self.mcnick: str = self.user.nick if self.user.nick else self.user.user.username

    async def _apply_unverify(self):
        await self.user.add_role(role=NEWBIE_ROLE_ID, guild_id=GUILD_ID)
        async with await pool.Connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SQL_DELETE, (int(self.user.id), ))
            await conn.commit()
    
    async def unverify(self):
        try:
            await self._get_profile()
            await self._apply_unverify()
        except VerificationError as e:
            return await self.ctx.send(e, ephemeral=True)
        
        return await self.ctx.send(MSG_UNVERIFY_SUCCESS.format(mcnick=self.mcnick), ephemeral=True)

class Profile(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, ctx: interactions.CommandContext, *args):
        pass

    @abstractmethod
    async def _get_profile(self):
        pass

    async def _get_name_history(self):
        name_history = ""
        for data in MojangAPI.get_name_history(self.uuid):
            if data['changed_to_at'] == 0:
                changed_time = "계정 생성"
            else:
                changed_time = time.strftime(f"%Y.%m.%d. %H:%M:%S", time.localtime(data['changed_to_at'] // 1000))
            name_history = name_history + f"`{data['name']}` ({changed_time})\n"

        self.name_history: str = name_history

    async def _set_msg(self):
        self.skin: str = f"[바로가기]({self.profile.skin_url})"
        self.cape: str = f"[바로가기]({self.profile.cape_url})" if self.profile.cape_url else "없음"

    async def _send_profile(self):
        return await self.ctx.send(embeds=interactions.Embed(
            author=interactions.EmbedAuthor(
                name=f"{self.profile.name}",
                icon_url=f"https://mc-heads.net/head/{self.uuid}"
            ),
            thumbnail=interactions.EmbedImageStruct(
                url=f"https://mc-heads.net/body/{self.uuid}"
            ),
            color=EMBED_COLOR,
            fields=[
                interactions.EmbedField(
                    name="UUID",
                    value=self.uuid
                ),
                interactions.EmbedField(
                    name="닉네임 변경 내역",
                    value=self.name_history
                ),
                interactions.EmbedField(
                    name=f"스킨 ({self.profile.skin_model})",
                    value=self.skin,
                    inline=True
                ),
                interactions.EmbedField(
                    name="망토",
                    value=self.cape,
                    inline=True
                )
            ],
            footer=interactions.EmbedFooter(
                text=get_footer()
            )
        ))

    async def construct(self):
        try:
            await self._get_profile()
            await self._get_name_history()
            await self._set_msg()
        except ProfileError as e:
            return await self.ctx.send(e, ephemeral=True)
        
        return await self._send_profile()

class UUIDProfile(Profile):
    def __init__(self, ctx: interactions.CommandContext, uuid: str):
        self.uuid: str = uuid

    async def _get_profile(self):
        self.profile = MojangAPI.get_profile(self.uuid)
        if not UUID_REGEX_CODE.match(self.uuid) or not self.profile:
            raise ProfileError(MSG_INVALID_UUID)


class NameProfile(Profile):
    def __init__(self, ctx: interactions.CommandContext, name: str):
        self.name: str = name
        
    async def _get_profile(self):
        uuid = MojangAPI.get_uuid(self.name)
        if not uuid:
            raise ProfileError(MSG_INVALID_NAME)
        self.uuid: str = '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:]])
        self.profile = MojangAPI.get_profile(self.uuid)

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
                placeholder="000000",
                min_length=6,
                max_length=6
            )
        ]
    )
    
    await ctx.popup(modal)

@bot.modal("modal_verify")
async def verify_response(ctx: interactions.CommandContext, mcnick: str, code: str):
    verifier = Verifier(ctx, mcnick, code)
    await verifier.verify()

@bot.command(
    name="unverify",
    description="마인크래프트 계정 인증을 해제합니다.",
    scope=GUILD_ID
)
async def unverify(ctx: interactions.CommandContext):
    if NEWBIE_ROLE_ID in ctx.author.roles:
        return await ctx.send(MSG_UNVERIFY_FAIL, ephemeral=True)
    
    modal = interactions.Modal(
        title="MRS 마인크래프트 계정 인증 해제",
        custom_id="modal_unverify",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="인증을 해제하시려면 본인의 닉네임을 정확히 입력해주세요.",
                custom_id="check_msg",
                required=True,
                placeholder=ctx.author.nick if ctx.author.nick else ctx.author.user.username
            )
        ]
    )
    
    await ctx.popup(modal)

@bot.modal("modal_unverify")
async def unverify_response(ctx: interactions.CommandContext, check_msg: str):
    unverifier = Unverifier(ctx, check_msg)
    await unverifier.unverify()

@bot.command(
    name="force_verify",
    description="특정 유저의 마인크래프트 계정을 강제로 인증합니다.",
    scope=GUILD_ID,
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    options=[
        interactions.Option(
            name="user",
            description="강제로 인증할 디스코드 유저를 입력하세요.",
            type=interactions.OptionType.USER,
            required=True
        ),
        interactions.Option(
            name="mcnick",
            description="강제로 인증할 마인크래프트 계정의 닉네임을 정확하게 입력하세요.",
            type=interactions.OptionType.STRING,
            required=True
        )
    ]
)
async def force_verify(ctx: interactions.CommandContext, user: interactions.Member, mcnick: str):
    verifier = ForceVerifier(ctx, user, mcnick)
    await verifier.verify()
    
@bot.command(
    name="force_unverify",
    description="특정 유저의 마인크래프트 계정 인증을 강제로 해제합니다.",
    scope=GUILD_ID,
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    options=[
        interactions.Option(
            name="user",
            description="강제로 인증을 해제할 디스코드 유저를 입력하세요.",
            type=interactions.OptionType.USER,
            required=True
        )
    ]
)
async def force_unverify(ctx: interactions.CommandContext, user: interactions.Member):
    unverifier = ForceUnverifier(ctx, user)
    await unverifier.unverify()

@bot.command(
    name="update",
    description="인증된 마인크래프트 계정 정보를 갱신합니다.",
    scope=GUILD_ID
)
async def update(ctx: interactions.CommandContext):
    async with await pool.Connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SQL_GETUUID, (int(ctx.author.id), ))
            uuid = cur.fetchone()[1]
    
    name = MojangAPI.get_username(uuid)
    nick = ctx.author.nick if ctx.author.nick else ctx.author.user.username
    
    if not name:
        return await ctx.send(MSG_UPDATE_FAIL, ephemeral=True)
    
    if name == nick:
        return await ctx.send(MSG_UPDATE_ALREADY, ephemeral=True)
    
    await ctx.target.modify(nick=name, guild_id=GUILD_ID)
    await ctx.send(MSG_UPDATE_SUCCESS, ephemeral=True)

@bot.command(
    name="ban",
    description="특정 유저의 계정 인증을 차단합니다.",
    scope=GUILD_ID,
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    options=[
        interactions.Option(
            name="uuid",
            description="uuid로 계정 인증을 차단합니다.",
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
            description="닉네임으로 계정 인증을 차단합니다.",
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
async def ban(ctx: interactions.CommandContext, sub_command: str, uuid: str = None, name: str = None):
    if sub_command == "uuid":
        name = MojangAPI.get_username(uuid)
        if not UUID_REGEX_CODE.match(uuid) or not name:
            return await ctx.send(MSG_INVALID_UUID, ephemeral=True)
    elif sub_command == "name":
        uuid = MojangAPI.get_uuid(name)
        if not uuid:
            return await ctx.send(MSG_INVALID_NAME, ephemeral=True)
        uuid = '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:]])
        name = MojangAPI.get_username(uuid)
    
    async with await pool.Connection() as conn:
        async with conn.cursor() as cur:
            if await cur.execute(SQL_CHECK_BLACK, (uuid, )):
                return await ctx.send(MSG_BAN_FAIL.format(mcnick=name, mcuuid=uuid), ephemeral=True)
            await cur.execute(SQL_INSERT_BLACK, (uuid, ))
        await conn.commit()
    await ctx.send(MSG_BAN_SUCCESS.format(mcnick=name, mcuuid=uuid), ephemeral=True)
    

@bot.command(
    name="unban",
    description="특정 유저의 계정 인증 차단을 해제합니다.",
    scope=GUILD_ID,
    default_member_permissions=interactions.Permissions.ADMINISTRATOR,
    options=[
        interactions.Option(
            name="uuid",
            description="uuid로 계정 인증 차단을 해제합니다.",
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
            description="닉네임으로 계정 인증 차단을 해제합니다.",
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
async def unban(ctx: interactions.CommandContext, sub_command: str, uuid: str = None, name: str = None):
    if sub_command == "uuid":
        name = MojangAPI.get_username(uuid)
        if not UUID_REGEX_CODE.match(uuid) or not name:
            return await ctx.send(MSG_INVALID_UUID, ephemeral=True)
    elif sub_command == "name":
        uuid = MojangAPI.get_uuid(name)
        if not uuid:
            return await ctx.send(MSG_INVALID_NAME, ephemeral=True)
        uuid = '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:]])
        name = MojangAPI.get_username(uuid)
    
    async with await pool.Connection() as conn:
        async with conn.cursor() as cur:
            if not await cur.execute(SQL_CHECK_BLACK, (uuid, )):
                return await ctx.send(MSG_UNBAN_FAIL, ephemeral=True)
            await cur.execute(SQL_DELETE_BLACK, (uuid, ))
        await conn.commit()
    await ctx.send(MSG_UNBAN_SUCCESS.format(mcnick=name, mcuuid=uuid), ephemeral=True)

@bot.command(
    name="status",
    description="MRS 인증봇 현황을 확인합니다.",
    scope=GUILD_ID
)
async def status(ctx: interactions.CommandContext):
    uptime = str(datetime.timedelta(seconds=(time.time() - start_time))).split(".")[0]

    async with await pool.Connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SQL_COUNT_VERIFIED)
            verify_count = cur.fetchone()[0]
            await cur.execute(SQL_COUNT_BANNED)
            ban_count = cur.fetchone()[0]
    
    await ctx.send(embeds=interactions.Embed(
        title="MRS 인증봇 현황",
        color=EMBED_COLOR,
        fields=[
            interactions.EmbedField(
                name="인증됨",
                value=f"{verify_count}명",
                inline=True
            ),
            interactions.EmbedField(
                name="차단됨",
                value=f"{ban_count}명",
                inline=True
            ),
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
        profile = UUIDProfile(ctx, uuid)
    elif sub_command == "name":
        profile = NameProfile(ctx, name)
    
    await profile.construct()

bot.start()