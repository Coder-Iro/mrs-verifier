from flask_discord_interactions.models.component import ButtonStyles
import pymysql
import re

from os import environ
import redis
from flask import Flask
from flask_discord_interactions import DiscordInteractions, Message, Permission, ActionRow, Button, Embed, embed
from dotenv import load_dotenv
from requests import delete, put, patch

from mojang import MojangAPI
import time

load_dotenv()

app = Flask(__name__)
discord = DiscordInteractions(app)
conn = pymysql.connect(host="localhost", user="root", db="mcauth", cursorclass=pymysql.cursors.DictCursor)
rd = redis.StrictRedis(host='localhost', port=6379, db=0)

MSG_MATCH = "마인크래프트 계정 `{mcnick}` 이/가 성공적으로 인증되었습니다."
MSG_DISMATCH = "인증번호가 일치하지 않습니다."
MSG_NOEXIST = "유효하지 않은 닉네임입니다. 디스코드 닉네임을 마인크래프트 닉네임으로 올바르게 변경하였는지 다시 확인해주세요."
MSG_INVAILD = "유효하지 않은 인증코드입니다. 인증코드는 띄어쓰기 없이 6자리 숫자로 입력해주세요."
MSG_LIMIT = "현재 과부하로 인해 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."
MSG_ALREADY = "이미 인증한 유저입니다. 다른 계정으로 인증하고자 하신다면 `/unverify` 명령어로 인증을 해제하고 다시 인증해주세요."
MSG_DUPLICATE = "마인크래프트 계정 `{mcnick}` 은 이미 인증된 계정입니다. 본인이 인증한 것이 아니라면 고객센터에 문의해주세요."

MSG_DUPLICATE_BLACK = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 은/는 이미 차단되었습니다."
MSG_SUCCESS_BLACK = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 의 계정 인증이 차단되었습니다."
MSG_DELETED_BLACK = "마인크래프트 계정 `{mcnick}` (uuid: `{mcuuid}`) 의 차단이 해제되었습니다."
MSG_INVAILD_UUID = "유효하지 않은 uuid입니다. 32자리의 uuid를 대시(-)를 포함하여 정확히 입력해주세요."
MSG_NOEXIST_BLACK = "차단되지 않은 계정의 uuid입니다. 차단된 계정의 uuid를 입력해주세요."
MSG_BANNED = "마인크래프트 계정 `{mcnick}` 은/는 차단된 계정입니다. 차단된 계정으로는 인증하실 수 없습니다."

MSG_NOEXIST_NAME = "존재하지 않는 닉네임입니다. uuid를 찾고자 하는 유저의 마인크래프트 닉네임을 정확히 입력해주세요."

SQL_INSERT = "INSERT INTO linked_account(discord,mcuuid) values (%s, %s)"
SQL_DELETE = "DELETE FROM linked_account WHERE discord=%s"
SQL_CHECK = "SELECT * FROM linked_account WHERE mcuuid=%s"
SQL_GETUUID = "SELECT * FROM linked_account WHERE discord=%s"

SQL_INSERT_BLACK = "INSERT INTO blacklist(mcuuid) values (%s)"
SQL_DELETE_BLACK = "DELETE FROM blacklist WHERE mcuuid=%s"
SQL_CHECK_BLACK = "SELECT * FROM blacklist WHERE mcuuid=%s"

REGEX_CODE = re.compile(r'\d{3} ?\d{3}')
UUID_REGEX_CODE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

app.config["DISCORD_CLIENT_ID"] = environ["ID"]
app.config["DISCORD_PUBLIC_KEY"] = environ["KEY"]
app.config["DISCORD_CLIENT_SECRET"] = environ["SECRET"]

auth = {"Authorization": f'Bot {environ["TOKEN"]}'}

@discord.command(annotations={"code": "6자리 숫자 인증코드를 띄어쓰기 없이 입력하세요."})
def verify(ctx, code: str):
    "마인크래프트 계정을 인증합니다."

    if "867576011961139200" not in ctx.author.roles:
        return Message(MSG_ALREADY, ephemeral=True)

    if not REGEX_CODE.match(code):
        return Message(MSG_INVAILD, ephemeral=True)

    code = code.replace(" ","")
    if rd.exists(ctx.author.display_name):
        realcode = rd.hget(ctx.author.display_name, "code").decode("UTF-8")
        uuid = rd.hget(ctx.author.display_name, "UUID").decode("UTF-8")
        conn.ping()
        with conn.cursor() as cursor:
            if cursor.execute(SQL_CHECK, (uuid,)):
                return Message(MSG_DUPLICATE.format(mcnick=ctx.author.display_name), ephemeral=True)
            if cursor.execute(SQL_CHECK_BLACK, (uuid,)):
                return Message(MSG_BANNED.format(mcnick=ctx.author.display_name), ephemeral=True)
        if realcode == str(code):
            resp = delete(f"https://discord.com/api/guilds/330997213255827457/members/{ctx.author.id}/roles/867576011961139200", headers=auth)
            if resp.status_code == 429:
                return Message(MSG_LIMIT, ephemeral=True)
            rd.delete(ctx.author.display_name)
            conn.ping()
            with conn.cursor() as cursor:
                cursor.execute(SQL_INSERT, (int(ctx.author.id), uuid))
            conn.commit()
            return Message(MSG_MATCH.format(mcnick=ctx.author.display_name), ephemeral=True)
        else:
            return Message(MSG_DISMATCH, ephemeral=True)
    else:
        return Message(MSG_NOEXIST, ephemeral=True)

@discord.custom_handler()
def handle_unverify_yes(ctx):
    conn.ping()
    with conn.cursor() as cursor:
        resp = put(f"https://discord.com/api/guilds/330997213255827457/members/{ctx.author.id}/roles/867576011961139200", headers=auth)
        if resp.status_code == 429:
            return Message(MSG_LIMIT, ephemeral=True)
        cursor.execute(SQL_DELETE, (int(ctx.author.id),))
        conn.commit()
        return Message(
            content="계정 인증이 성공적으로 해제되었습니다.",
            components=[
                ActionRow(components=[
                    Button(
                        disabled=True,
                        style=ButtonStyles.SUCCESS,
                        custom_id=handle_unverify_yes,
                        label="예"
                    ),
                    Button(
                        disabled=True,
                        style=ButtonStyles.DANGER,
                        custom_id=handle_unverify_no,
                        label="아니오"
                    )
                ])
            ],
            ephemeral=True, update=True
        )

@discord.custom_handler()
def handle_unverify_no(ctx):
    return Message(
        content="계정 인증 해제를 취소하였습니다.",
        components=[
            ActionRow(components=[
                Button(
                    disabled=True,
                    style=ButtonStyles.SUCCESS,
                    custom_id=handle_unverify_yes,
                    label="예"
                ),
                Button(
                    disabled=True,
                    style=ButtonStyles.DANGER,
                    custom_id=handle_unverify_no,
                    label="아니오"
                )
            ])
        ],
        ephemeral=True, update=True
    )

@discord.command()
def unverify(ctx):
    "마인크래프트 계정 인증을 해제합니다."

    if "867576011961139200" in ctx.author.roles:
        return Message("인증되지 않은 유저입니다. 인증된 유저만 인증을 해제할 수 있습니다.", ephemeral=True)

    return Message(
        content="정말 계정 인증을 해제하시겠습니까?",
        components=[
            ActionRow(components=[
                Button(
                    style=ButtonStyles.SUCCESS,
                    custom_id=handle_unverify_yes,
                    label="예"
                ),
                Button(
                    style=ButtonStyles.DANGER,
                    custom_id=handle_unverify_no,
                    label="아니오"
                )
            ])
        ],
        ephemeral=True
    )

@discord.command()
def update(ctx):
    "인증된 마인크래프트 계정 정보를 갱신합니다."

    if "867576011961139200" in ctx.author.roles:
        return Message("인증되지 않은 유저입니다. 인증된 유저만 계정 정보를 갱신할 수 있습니다.", ephemeral=True)

    conn.ping()
    with conn.cursor() as cursor:
        cursor.execute(SQL_GETUUID, (int(ctx.author.id),))
        uuid = cursor.fetchone()['mcuuid']

    name = MojangAPI.get_username(uuid)
    if not name:
        return Message("계정 정보가 존재하지 않거나 Mojang API에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)

    if name == ctx.author.display_name:
        return Message("갱신할 계정 정보가 없습니다. 이미 최신 정보입니다.", ephemeral=True)
    else:
        resp = patch(f"https://discord.com/api/guilds/330997213255827457/members/{ctx.author.id}", headers=auth, json={'nick': name})
        if resp.status_code == 204:
            return Message("계정 정보를 성공적으로 갱신하였습니다.", ephemeral=True)
        else:
            return Message("계정 정보를 갱신할 수 없습니다. 여러 번 시도해도 계정 정보를 갱신할 수 없는 경우 고객센터에 문의해주세요.", ephemeral=True)

@discord.command(annotations={"uuid": "차단할 마인크래프트 계정의 uuid를 대시(-)를 포함하여 정확하게 입력하세요."}, default_permission=False, permissions=[
    Permission(role="330997746083299329")
])
def ban(ctx, uuid: str):
    "특정 유저의 계정 인증을 차단합니다."

    if not UUID_REGEX_CODE.match(uuid):
        return Message(MSG_INVAILD_UUID, ephemeral=True)

    username = MojangAPI.get_username(uuid)

    if not username:
        return Message(MSG_INVAILD_UUID, ephemeral=True)

    conn.ping()
    with conn.cursor() as cursor:
        if cursor.execute(SQL_CHECK_BLACK, (uuid,)):
            return Message(MSG_DUPLICATE_BLACK.format(mcnick=username, mcuuid=uuid), ephemeral=True)
        cursor.execute(SQL_INSERT_BLACK, (uuid,))
    conn.commit()
    return Message(MSG_SUCCESS_BLACK.format(mcnick=username, mcuuid=uuid), ephemeral=True)

@discord.command(annotations={"uuid": "차단을 해제할 마인크래프트 계정의 uuid를 대시(-)를 포함하여 정확하게 입력하세요."}, default_permission=False, permissions=[
    Permission(role="330997746083299329")
])
def unban(ctx, uuid: str):
    "특정 유저의 계정 인증 차단을 해제합니다."

    if not UUID_REGEX_CODE.match(uuid):
        return Message(MSG_INVAILD_UUID, ephemeral=True)

    username = MojangAPI.get_username(uuid)

    if not username:
        return Message(MSG_INVAILD_UUID, ephemeral=True)

    conn.ping()
    with conn.cursor() as cursor:
        if not cursor.execute(SQL_CHECK_BLACK, (uuid,)):
            return Message(MSG_NOEXIST_BLACK, ephemeral=True)
        cursor.execute(SQL_DELETE_BLACK, (uuid,))
    conn.commit()
    return Message(MSG_DELETED_BLACK.format(mcnick=username, mcuuid=uuid), ephemeral=True)

profile = discord.command_group("profile")

@profile.command(annotations={"uuid": "마인크래프트 유저의 uuid를 대시(-)를 포함하여 정확하게 입력하세요."})
def uuid(ctx, uuid: str):
    "uuid로 마인크래프트 프로필을 조회합니다."

    if not UUID_REGEX_CODE.match(uuid):
        return Message(MSG_INVAILD_UUID, ephemeral=True)
    
    profile = MojangAPI.get_profile(uuid)

    if not profile:
        return Message(MSG_INVAILD_UUID, ephemeral=True)
    
    name_history = ""
    for data in MojangAPI.get_name_history(uuid):
        if data['changed_to_at'] == 0:
            name_history = name_history + f"`{data['name']}` (계정 생성)\n"
        else:
            changed_time = time.strftime(f"%Y.%m.%d %H:%M:%S", time.localtime(data['changed_to_at'] // 1000))
            name_history = name_history + f"`{data['name']}` ({changed_time})\n"

    if profile.cape_url:
        cape_url = f"[바로가기]({profile.cape_url})"
    else:
        cape_url = "없음"

    conn.ping()
    with conn.cursor() as cursor:
        if cursor.execute(SQL_CHECK, (uuid,)):
            verify = "O"
        elif cursor.execute(SQL_CHECK_BLACK, (uuid,)):
            verify = "X (차단됨)"
        else:
            verify = "X"

    return Message(embed=Embed(
        author=embed.Author(
            name=f"{profile.name}",
            icon_url=f"https://mc-heads.net/head/{uuid}"
        ),
        thumbnail=embed.Media(
            url=f"https://mc-heads.net/body/{uuid}"
        ),
        color=15844367,
        fields=[
            embed.Field(
                name="UUID",
                value=uuid
            ),
            embed.Field(
                name="닉네임 변경 내역",
                value=name_history
            ),
            embed.Field(
                name=f"스킨 ({profile.skin_model})",
                value=f"[바로가기]({profile.skin_url})",
                inline=True
            ),
            embed.Field(
                name="망토",
                value=cape_url,
                inline=True
            ),
            embed.Field(
                name="계정 인증",
                value=verify,
                inline=True
            )
        ],
        footer=embed.Footer(
            text=time.strftime(f"%Y.%m.%d %H:%M:%S", time.localtime(profile.timestamp // 1000))
        )
    ))

@profile.command(annotations={"name": "마인크래프트 닉네임을 정확하게 입력하세요."})
def name(ctx, name: str):
    "닉네임으로 마인크래프트 프로필을 조회합니다."

    uuid = MojangAPI.get_uuid(name)

    if not uuid:
        return Message(MSG_NOEXIST_NAME, ephemeral=True)

    uuid = uuid[:8] + '-' + uuid[8:12] + '-' + uuid[12:16] + '-' + uuid[16:20] + '-' + uuid[20:]
    profile = MojangAPI.get_profile(uuid)
    
    name_history = ""
    for data in MojangAPI.get_name_history(uuid):
        if data['changed_to_at'] == 0:
            name_history = name_history + f"`{data['name']}` (계정 생성)\n"
        else:
            changed_time = time.strftime(f"%Y.%m.%d %H:%M:%S", time.localtime(data['changed_to_at'] // 1000))
            name_history = name_history + f"`{data['name']}` ({changed_time})\n"

    if profile.cape_url:
        cape_url = f"[바로가기]({profile.cape_url})"
    else:
        cape_url = "없음"

    conn.ping()
    with conn.cursor() as cursor:
        if cursor.execute(SQL_CHECK, (uuid,)):
            verify = "O"
        elif cursor.execute(SQL_CHECK_BLACK, (uuid,)):
            verify = "X (차단됨)"
        else:
            verify = "X"

    return Message(embed=Embed(
        author=embed.Author(
            name=f"{profile.name}",
            icon_url=f"https://mc-heads.net/head/{uuid}"
        ),
        thumbnail=embed.Media(
            url=f"https://mc-heads.net/body/{uuid}"
        ),
        color=15844367,
        fields=[
            embed.Field(
                name="UUID",
                value=uuid
            ),
            embed.Field(
                name="닉네임 변경 내역",
                value=name_history
            ),
            embed.Field(
                name=f"스킨 ({profile.skin_model})",
                value=f"[바로가기]({profile.skin_url})",
                inline=True
            ),
            embed.Field(
                name="망토",
                value=cape_url,
                inline=True
            ),
            embed.Field(
                name="계정 인증",
                value=verify,
                inline=True
            )
        ],
        footer=embed.Footer(
            text=time.strftime(f"%Y.%m.%d %H:%M:%S", time.localtime(profile.timestamp // 1000))
        )
    ))


discord.set_route("/interactions")
discord.update_commands(guild_id="330997213255827457")
