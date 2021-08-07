import discord
import asyncio
import tormysql
from discord.ext import commands

# F*ck yaml
# F*ck json
# I'm using python as config file
import config

class IroBot(commands.Bot):
    """
    IroBot (100% written by Iro)
    """

    def __init__(self, pool: tormysql.ConnectionPool, **options):
        super().__init__(**options)
        self.pool = pool
        self.working_guild: discord.Guild
        self.newbie_role: discord.Role

    async def on_ready(self):
        guild = self.get_guild(config.GUILD_ID)
        assert guild # because return value can be None
        role = guild.get_role(config.NEWBIE_ROLE_ID)
        assert role # and my linter is complaining about that

        self.working_guild = guild
        self.newbie_role = role
        print(guild)
        print(role)

    async def close(self):
        await self.pool.close()

    # 1. 서버에 들어오면 미인증 역할을 준다
    async def on_member_join(self, member: discord.Member):
        await member.add_roles(self.newbie_role)

    # 2. 미인증 유저의 챗은 모두 삭제된다
    async def on_message(self, msg: discord.Message):
        if not isinstance(msg.author, discord.Member):
            return

        if self.newbie_role in msg.author.roles:
            await msg.delete()

        # await self.process_commands(msg)

    # 3. 서버 닉네임 유지
    async def on_user_update(self, before: discord.User, after: discord.User):
        # 유저이름이 변경될 경우
        if before.name!=after.name:
            if member := self.working_guild.get_member(before.id):
                # 서버 닉네임이 설정되있지 않다면
                if not member.nick:
                    # 이전 유저이름으로 닉네임 설정
                    await member.edit(nick=before.name)

    # 4. 나간 유저 데이터 삭제
    async def on_member_leave(self, member: discord.Member):
        async with await self.pool.Connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE * FROM linked_account WHERE discord=%s", member.id)
            conn.commit()

bot = IroBot(
    pool = tormysql.ConnectionPool(**config.SQL),
    command_prefix=config.COMMAND_PREFIX,
    intents=discord.Intents.all(),
    help_command=None
)

bot.run(config.TOKEN)
