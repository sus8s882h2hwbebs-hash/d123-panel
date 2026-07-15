using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using DSharpPlus;
using DSharpPlus.Entities;
using DSharpPlus.EventArgs;

namespace ZSMING
{
    public class BotInstance
    {
        public string Token { get; set; }
        public DiscordClient Client { get; set; }
        public string Name { get; set; } = "未知";
        public ulong Id { get; set; }
        public bool IsConnected { get; set; }
        public int DmsSent { get; set; }
    }

    public class DiscordManager
    {
        private List<BotInstance> _bots = new List<BotInstance>();
        private ConfigManager _config;
        private HashSet<ulong> _whitelist;

        public Action<string, string> OnLog { get; set; }
        public Action OnBotsChanged { get; set; }
        public Action OnWhitelistChanged { get; set; }

        public DiscordManager(ConfigManager config)
        {
            _config = config;
            _whitelist = config.LoadWhitelist();
            var tokens = config.LoadTokens();
            foreach (var token in tokens)
            {
                AddToken(token);
            }
        }

        public List<BotInstance> GetBots() => _bots.ToList();

        public List<BotInstance> GetConnectedBots() => _bots.Where(b => b.IsConnected).ToList();

        public HashSet<ulong> GetWhitelist() => new HashSet<ulong>(_whitelist);

        public void AddToken(string token)
        {
            token = token.Trim();
            if (string.IsNullOrEmpty(token)) return;
            if (_bots.Any(b => b.Token == token)) return;

            var bot = new BotInstance { Token = token };
            try
            {
                var config = new DiscordConfiguration
                {
                    Token = token,
                    TokenType = TokenType.Bot,
                    Intents = DiscordIntents.All
                };
                bot.Client = new DiscordClient(config);
                bot.Client.MessageCreated += OnMessageCreated;
                bot.Client.ClientErrored += OnClientError;
            }
            catch (Exception ex)
            {
                Log($"Token 解析失敗：{ex.Message}", "ERROR");
            }
            _bots.Add(bot);
            _config.SaveTokens(_bots.Select(b => b.Token).ToList());
            OnBotsChanged?.Invoke();
        }

        public async Task RemoveTokenAsync(int index)
        {
            if (index < 0 || index >= _bots.Count) return;
            var bot = _bots[index];
            if (bot.IsConnected)
            {
                await DisconnectBot(index);
            }
            try
            {
                bot.Client?.Dispose();
            }
            catch { }
            _bots.RemoveAt(index);
            _config.SaveTokens(_bots.Select(b => b.Token).ToList());
            OnBotsChanged?.Invoke();
            Log("Token 已移除", "INFO");
        }

        public async Task ConnectBot(int index)
        {
            if (index < 0 || index >= _bots.Count) return;
            var bot = _bots[index];
            if (bot.IsConnected) return;

            try
            {
                await bot.Client.ConnectAsync();
                await Task.Delay(1500);
                bot.Name = bot.Client.CurrentUser?.Username ?? "未知";
                bot.Id = bot.Client.CurrentUser?.Id ?? 0;
                bot.IsConnected = true;
                Log($"[{bot.Name}] 已連線", "SUCCESS");
                OnBotsChanged?.Invoke();
            }
            catch (Exception ex)
            {
                bot.IsConnected = false;
                Log($"連線失敗：{ex.Message}", "ERROR");
                OnBotsChanged?.Invoke();
            }
        }

        public async Task DisconnectBot(int index)
        {
            if (index < 0 || index >= _bots.Count) return;
            var bot = _bots[index];
            if (!bot.IsConnected) return;

            try
            {
                await bot.Client.DisconnectAsync();
                bot.IsConnected = false;
                Log($"[{bot.Name}] 已斷線", "INFO");
                OnBotsChanged?.Invoke();
            }
            catch (Exception ex)
            {
                Log($"斷線錯誤：{ex.Message}", "ERROR");
            }
        }

        public async Task ConnectAll()
        {
            Log("正在連線所有機器人...", "INFO");
            for (int i = 0; i < _bots.Count; i++)
            {
                if (!_bots[i].IsConnected)
                {
                    await ConnectBot(i);
                    await Task.Delay(500);
                }
            }
            Log("所有機器人已連線", "SUCCESS");
        }

        public async Task DisconnectAll()
        {
            Log("正在斷線所有機器人...", "INFO");
            for (int i = 0; i < _bots.Count; i++)
            {
                if (_bots[i].IsConnected)
                {
                    await DisconnectBot(i);
                }
            }
            Log("所有機器人已斷線", "INFO");
        }

        public async Task<int> SendSpam(ulong targetId, string message, int amount, bool multiMessage, CancellationToken ct)
        {
            var connectedBots = GetConnectedBots();
            if (connectedBots.Count == 0)
            {
                Log("沒有已連線的機器人", "ERROR");
                return 0;
            }

            var messages = multiMessage
                ? message.Split('|').Select(m => m.Trim()).Where(m => !string.IsNullOrEmpty(m)).ToList()
                : new List<string> { message };

            if (messages.Count == 0)
            {
                Log("沒有有效的訊息", "ERROR");
                return 0;
            }

            int totalSent = 0;
            int totalFailed = 0;

            Log($"正在轟炸 {targetId}，使用 {connectedBots.Count} 隻機器人 x {amount} 輪 x {messages.Count} 條訊息", "INFO");

            var tasks = connectedBots.Select(async bot =>
            {
                string channelId = null;
                try
                {
                    using var http = new HttpClient();
                    http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bot", bot.Token);
                    var payload = $"{{\"recipient_id\":\"{targetId}\"}}";
                    var content = new StringContent(payload, Encoding.UTF8, "application/json");
                    var resp = await http.PostAsync("https://discord.com/api/v9/users/@me/channels", content);
                    if (!resp.IsSuccessStatusCode)
                    {
                        Log($"[{bot.Name}] 無法建立私訊頻道：{resp.StatusCode}", "ERROR");
                        return;
                    }
                    var json = await resp.Content.ReadAsStringAsync();
                    var idx = json.IndexOf("\"id\":\"");
                    if (idx < 0)
                    {
                        Log($"[{bot.Name}] 無法解析私訊頻道", "ERROR");
                        return;
                    }
                    var start = idx + 6;
                    var end = json.IndexOf("\"", start);
                    channelId = json.Substring(start, end - start);
                }
                catch (Exception ex)
                {
                    Log($"[{bot.Name}] 無法建立私訊頻道：{ex.Message}", "ERROR");
                    return;
                }

                for (int round = 0; round < amount; round++)
                {
                    if (ct.IsCancellationRequested) break;
                    foreach (var msg in messages)
                    {
                        if (ct.IsCancellationRequested) break;
                        try
                        {
                            using var http2 = new HttpClient();
                            http2.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bot", bot.Token);
                            var msgPayload = $"{{\"content\":{System.Text.Json.JsonSerializer.Serialize(msg)}}}";
                            var msgContent = new StringContent(msgPayload, Encoding.UTF8, "application/json");
                            var msgResp = await http2.PostAsync($"https://discord.com/api/v9/channels/{channelId}/messages", msgContent);
                            if (msgResp.IsSuccessStatusCode)
                            {
                                Interlocked.Increment(ref totalSent);
                                bot.DmsSent++;
                            }
                            else
                            {
                                Interlocked.Increment(ref totalFailed);
                                if (totalFailed < 10)
                                    Log($"[{bot.Name}] 發送錯誤：{msgResp.StatusCode}", "WARN");
                            }
                        }
                        catch (Exception ex)
                        {
                            Interlocked.Increment(ref totalFailed);
                            if (totalFailed < 10)
                                Log($"[{bot.Name}] 發送錯誤：{ex.Message}", "WARN");
                        }
                    }
                }
            }).ToArray();

            await Task.WhenAll(tasks);

            Log($"轟炸完成：已發送 {totalSent} 條，失敗 {totalFailed} 條", totalFailed > 0 ? "WARN" : "SUCCESS");
            return totalSent;
        }

        public void AddWhitelist(ulong userId)
        {
            _whitelist.Add(userId);
            _config.SaveWhitelist(_whitelist);
            OnWhitelistChanged?.Invoke();
            Log($"白名單已新增：{userId}", "INFO");
        }

        public void RemoveWhitelist(ulong userId)
        {
            _whitelist.Remove(userId);
            _config.SaveWhitelist(_whitelist);
            OnWhitelistChanged?.Invoke();
            Log($"白名單已移除：{userId}", "INFO");
        }

        private async Task OnMessageCreated(DiscordClient sender, MessageCreateEventArgs e)
        {
            if (e.Author.IsBot) return;
            var content = e.Message.Content;
            if (string.IsNullOrEmpty(content) || !content.StartsWith("!")) return;
            if (!_whitelist.Contains(e.Author.Id)) return;

            var withoutPrefix = content.Substring(1);
            var command = withoutPrefix.Split(' ')[0].ToLower();

            switch (command)
            {
                case "dm":
                    await HandleDmCommand(sender, e, withoutPrefix);
                    break;
                case "dmm":
                    await HandleDmmCommand(sender, e, withoutPrefix);
                    break;
                case "dmmulti":
                    await HandleDmMultiCommand(sender, e, withoutPrefix);
                    break;
                case "zsming":
                    await HandleHelpCommand(sender, e);
                    break;
            }
        }

        private async Task HandleDmCommand(DiscordClient sender, MessageCreateEventArgs e, string args)
        {
            var parts = args.Split(new[] { ' ' }, 3, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 3)
            {
                await e.Message.RespondAsync("用法：!dm <用戶ID> <訊息>");
                return;
            }

            if (!ulong.TryParse(parts[1], out var targetId))
            {
                await e.Message.RespondAsync("無效的用戶 ID");
                return;
            }

            var message = parts[2];
            var cts = new CancellationTokenSource();
            _ = Task.Run(async () =>
            {
                var sent = await SendSpam(targetId, message, 100, false, cts.Token);
                try { await e.Message.RespondAsync($"攻擊完成：已發送 {sent} 條私訊"); } catch { }
            });
        }

        private async Task HandleDmmCommand(DiscordClient sender, MessageCreateEventArgs e, string args)
        {
            var parts = args.Split(new[] { ' ' }, 4, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 4)
            {
                await e.Message.RespondAsync("用法：!dmm <用戶ID> <數量> <訊息>");
                return;
            }

            if (!ulong.TryParse(parts[1], out var targetId))
            {
                await e.Message.RespondAsync("無效的用戶 ID");
                return;
            }

            if (!int.TryParse(parts[2], out var amount) || amount <= 0 || amount > 5000)
            {
                await e.Message.RespondAsync("數量必須在 1-5000 之間");
                return;
            }

            var message = parts[3];
            var cts = new CancellationTokenSource();
            _ = Task.Run(async () =>
            {
                var sent = await SendSpam(targetId, message, amount, false, cts.Token);
                try { await e.Message.RespondAsync($"攻擊完成：已發送 {sent} 條私訊"); } catch { }
            });
        }

        private async Task HandleDmMultiCommand(DiscordClient sender, MessageCreateEventArgs e, string args)
        {
            var parts = args.Split(new[] { ' ' }, 3, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 3)
            {
                await e.Message.RespondAsync("用法：!dmmulti <用戶ID> <訊息1|訊息2|訊息3>");
                return;
            }

            if (!ulong.TryParse(parts[1], out var targetId))
            {
                await e.Message.RespondAsync("無效的用戶 ID");
                return;
            }

            var messages = parts[2];
            var cts = new CancellationTokenSource();
            _ = Task.Run(async () =>
            {
                var sent = await SendSpam(targetId, messages, 1, true, cts.Token);
                try { await e.Message.RespondAsync($"攻擊完成：已發送 {sent} 條私訊"); } catch { }
            });
        }

        private async Task HandleHelpCommand(DiscordClient sender, MessageCreateEventArgs e)
        {
            var help = "ZSMING 指令列表：\n" +
                       "!dm <用戶ID> <訊息> - 發送 100 條私訊到目標\n" +
                       "!dmm <用戶ID> <數量> <訊息> - 自訂數量發送私訊\n" +
                       "!dmmulti <用戶ID> <訊息1|訊息2|...> - 發送多條不同訊息\n" +
                       "!zsming - 顯示此幫助訊息";
            try { await e.Message.RespondAsync(help); } catch { }
        }

        private Task OnClientError(DiscordClient sender, ClientErrorEventArgs e)
        {
            Log($"客戶端錯誤：{e.Exception?.Message}", "ERROR");
            return Task.CompletedTask;
        }

        private void Log(string message, string level = "INFO")
        {
            OnLog?.Invoke(message, level);
        }
    }
}
