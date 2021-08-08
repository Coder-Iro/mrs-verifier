import pymysql

from os import environ
import redis
from flask import Flask
from flask_discord_interactions import DiscordInteractions, Response
from dotenv import load_dotenv
from requests import delete, put, patch

load_dotenv()

app = Flask(__name__)
discord = DiscordInteractions(app)
conn = pymysql.connect(host="localhost", user="root", db="mcauth", cursorclass=pymysql.cursors.DictCursor)
rd = redis.StrictRedis(host='localhost', port=6379, db=0)

MSG_MATCH = "마인크래프트 계정 {mcnick} 이/가 성공적으로 인증되었습니다."
MSG_DISMATCH = "인증번호가 일치하지 않습니다."
MSG_NOEXIST = "유효하지 않은 닉네임입니다. 인증 방법을 다시 한번 확인해주세요."
MSG_INVAILD = "유효하지 않은 인증코드입니다. 인증코드는 띄어쓰기 없이 6자리 숫자로 입력해주세요."
MSG_LIMIT = "현재 과부하로 인해 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."

SQL_INSERT = "INSERT INTO linked_account(discord,mcuuid) values (%s, %s)"
SQL_DELETE = "DELETE FROM linked_account WHERE discord=%s"

app.config["DISCORD_CLIENT_ID"] = environ["ID"]
app.config["DISCORD_PUBLIC_KEY"] = environ["KEY"]
app.config["DISCORD_CLIENT_SECRET"] = environ["SECRET"]

auth = {"Authorization": f'Bot {environ["TOKEN"]}'}

@discord.command(annotations={"code": "6자리 숫자 인증코드를 띄어쓰기 없이 입력하세요."})
def verify(ctx, code: str):
    "마인크래프트 계정을 인증합니다."

    if "867576011961139200" not in ctx.author.roles:
        return Response("이미 인증한 유저입니다. 인증된 마인크래프트 계정을 바꾸시고 싶으시면 인증 해제를 먼저 진행해주세요.", ephemeral=True)

    if len(code) != 6 or not code.isdigit():
        return Response(MSG_INVAILD, ephemeral=True)

    if rd.exists(ctx.author.display_name):
        realcode = rd.hget(ctx.author.display_name, "code").decode("UTF-8")
        uuid = rd.hget(ctx.author.display_name, "UUID").decode("UTF-8")
        if realcode == str(code):
            resp = delete(f"https://discord.com/api/guilds/330997213255827457/members/{ctx.author.id}/roles/867576011961139200", headers=auth)
            if resp.status_code == 429:
                return Response(MSG_LIMIT, ephemeral=True)
            rd.delete(ctx.author.display_name)
            conn.ping()
            with conn.cursor() as cursor:
                cursor.execute(SQL_INSERT, (int(ctx.author.id), uuid))
            conn.commit()
            return Response(MSG_MATCH.format(mcnick=ctx.author.display_name), ephemeral=True)
        else:
            return Response(MSG_DISMATCH, ephemeral=True)
    else:
        return Response(MSG_NOEXIST, ephemeral=True)


@discord.command()
def unverify(ctx):
    "마인크래프트 계정 인증을 해제합니다."

    if "867576011961139200" in ctx.author.roles:
        return Response("인증되지 않은 유저입니다. 인증된 유저만 인증을 해제할 수 있습니다.", ephemeral=True)
    conn.ping()
    with conn.cursor() as cursor:
        resp = put(f"https://discord.com/api/guilds/330997213255827457/members/{ctx.author.id}/roles/867576011961139200", headers=auth)
        if resp.status_code == 429:
                return Response(MSG_LIMIT, ephemeral=True)
        cursor.execute(SQL_DELETE, (int(ctx.author.id),))
        conn.commit()
        return Response("인증이 성공적으로 해제되었습니다.", ephemeral=True)


discord.set_route("/interactions")
discord.update_slash_commands(guild_id="330997213255827457")
