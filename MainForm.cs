using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ZSMING
{
    public class MainForm : Form
    {
        private DiscordManager _discord;
        private ConfigManager _config;
        private CancellationTokenSource _spamCts;

        private Panel _sidebar;
        private Panel _mainArea;
        private Panel _header;
        private Panel _content;
        private List<Button> _navButtons = new List<Button>();
        private List<Panel> _contentPanels = new List<Panel>();
        private int _currentNavIndex = 0;

        private Label _lblConnStatus;

        private Label _statTotalTokens;
        private Label _statConnected;
        private Label _statTotalDms;
        private ListView _lvDashboardBots;

        private TextBox _txtTokenInput;
        private ListView _lvTokens;
        private Button _btnConnectAll;
        private Button _btnDisconnectAll;

        private TextBox _txtTargetId;
        private TextBox _txtSpamMessage;
        private NumericUpDown _numAmount;
        private CheckBox _chkMultiMessage;
        private Button _btnStartSpam;
        private Button _btnStopSpam;
        private ProgressBar _progressSpam;
        private Label _lblSpamStatus;

        private TextBox _txtWhitelistId;
        private ListView _lvWhitelist;

        private RichTextBox _rtbLog;

        public MainForm()
        {
            _config = new ConfigManager();
            _discord = new DiscordManager(_config);
            _discord.OnLog = OnLogCallback;
            _discord.OnBotsChanged = OnBotsChangedCallback;
            _discord.OnWhitelistChanged = OnWhitelistChangedCallback;

            SetupForm();
            CreateSidebar();
            CreateMainArea();
            NavigateTo(0);
            RefreshTokensList();
            RefreshWhitelistList();
            RefreshDashboard();

            Log("ZSMING 已初始化", "INFO");
            Log($"已載入 {_discord.GetBots().Count} 個 Token，{_discord.GetWhitelist().Count} 個白名單用戶", "INFO");
        }

        private void SetupForm()
        {
            Text = "ZSMING - Discord 大量私訊控制面板";
            Size = new Size(1200, 750);
            MinimumSize = new Size(960, 640);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Theme.Background;
            ForeColor = Theme.TextPrimary;
            Font = Theme.LabelFont;
            FormBorderStyle = FormBorderStyle.Sizable;
            DoubleBuffered = true;
            FormClosing += OnFormClosing;
        }

        private void CreateSidebar()
        {
            _sidebar = new Panel
            {
                Dock = DockStyle.Left,
                Width = 220,
                BackColor = Theme.Sidebar
            };

            var logoPanel = new Panel
            {
                Dock = DockStyle.Top,
                Height = 64,
                BackColor = Theme.Sidebar
            };

            var lblLogo = new Label
            {
                Text = "ZSMING",
                Font = new Font("Segoe UI", 18F, FontStyle.Bold),
                ForeColor = Theme.Accent,
                BackColor = Color.Transparent,
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter
            };
            logoPanel.Controls.Add(lblLogo);
            _sidebar.Controls.Add(logoPanel);

            var separator = new Panel
            {
                Dock = DockStyle.Top,
                Height = 1,
                BackColor = Theme.Border
            };
            _sidebar.Controls.Add(separator);

            var navContainer = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Theme.Sidebar,
                Padding = new Padding(0, 8, 0, 0)
            };

            string[] navItems = { "總覽", "機器人 Token", "私訊轟炸", "白名單管理", "日誌" };
            for (int i = 0; i < navItems.Length; i++)
            {
                var btn = Theme.CreateNavButton(navItems[i]);
                btn.Dock = DockStyle.Top;
                btn.Height = 46;
                btn.Tag = i;
                btn.Click += OnNavClick;
                _navButtons.Add(btn);
                navContainer.Controls.Add(btn);
            }

            _lblConnStatus = new Label
            {
                Dock = DockStyle.Bottom,
                Height = 32,
                Text = "  0 隻機器人上線",
                ForeColor = Theme.TextDim,
                Font = Theme.SmallFont,
                TextAlign = ContentAlignment.MiddleLeft,
                BackColor = Theme.Sidebar
            };

            _sidebar.Controls.Add(navContainer);
            _sidebar.Controls.Add(_lblConnStatus);
            Controls.Add(_sidebar);
        }

        private void CreateMainArea()
        {
            _mainArea = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Theme.Background
            };

            CreateHeader();
            CreateContentPanel();

            Controls.Add(_mainArea);
            _mainArea.BringToFront();
        }

        private void CreateHeader()
        {
            _header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 56,
                BackColor = Theme.Panel
            };

            var lblTitle = new Label
            {
                Text = "控制面板",
                Font = Theme.TitleFont,
                ForeColor = Theme.TextPrimary,
                BackColor = Color.Transparent,
                Dock = DockStyle.Left,
                Width = 300,
                TextAlign = ContentAlignment.MiddleLeft,
                Padding = new Padding(24, 0, 0, 0)
            };

            var lblAccent = new Label
            {
                Text = "",
                BackColor = Theme.Accent,
                Dock = DockStyle.Bottom,
                Height = 1
            };

            _header.Controls.Add(lblAccent);
            _header.Controls.Add(lblTitle);
            _mainArea.Controls.Add(_header);
        }

        private void CreateContentPanel()
        {
            _content = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Theme.Background,
                Padding = new Padding(24, 20, 24, 20)
            };

            CreateDashboardPanel();
            CreateTokensPanel();
            CreateSpamPanel();
            CreateWhitelistPanel();
            CreateLogPanel();

            foreach (var p in _contentPanels)
                _content.Controls.Add(p);

            _mainArea.Controls.Add(_content);
        }

        private void CreateDashboardPanel()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = Theme.Background, AutoScroll = true };
            _contentPanels.Add(panel);

            var lblTitle = Theme.CreateLabel("總覽", Theme.TextPrimary, Theme.TitleFont);
            lblTitle.Location = new Point(0, 0);
            panel.Controls.Add(lblTitle);

            int cardWidth = 240;
            int cardHeight = 100;
            int cardGap = 20;
            int cardY = 50;

            var card1 = CreateStatCard("總 Token 數", "0", Theme.SecondaryAccent, 0, cardY, cardWidth, cardHeight);
            _statTotalTokens = card1.Tag as Label;
            panel.Controls.Add(card1);

            var card2 = CreateStatCard("已連線機器人", "0", Theme.Success, cardWidth + cardGap, cardY, cardWidth, cardHeight);
            _statConnected = card2.Tag as Label;
            panel.Controls.Add(card2);

            var card3 = CreateStatCard("已發送私訊數", "0", Theme.Accent, (cardWidth + cardGap) * 2, cardY, cardWidth, cardHeight);
            _statTotalDms = card3.Tag as Label;
            panel.Controls.Add(card3);

            var lblBotList = Theme.CreateLabel("機器人狀態", Theme.TextSecondary, Theme.LabelFontBold);
            lblBotList.Location = new Point(0, cardY + cardHeight + 24);
            panel.Controls.Add(lblBotList);

            _lvDashboardBots = Theme.CreateListView();
            _lvDashboardBots.Location = new Point(0, cardY + cardHeight + 48);
            _lvDashboardBots.Size = new Size(740, 300);
            _lvDashboardBots.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            _lvDashboardBots.Columns.Add("機器人名稱", 180);
            _lvDashboardBots.Columns.Add("ID", 140);
            _lvDashboardBots.Columns.Add("狀態", 100);
            _lvDashboardBots.Columns.Add("已發送私訊", 100);
            panel.Controls.Add(_lvDashboardBots);
        }

        private Panel CreateStatCard(string title, string value, Color accentColor, int x, int y, int w, int h)
        {
            var card = Theme.CreateCard(w, h);
            card.Location = new Point(x, y);

            var accentBar = new Panel
            {
                Size = new Size(4, h),
                BackColor = accentColor,
                Dock = DockStyle.Left
            };

            var lblTitle = Theme.CreateLabel(title, Theme.TextSecondary, Theme.StatLabelFont);
            lblTitle.Location = new Point(16, 12);
            lblTitle.AutoSize = true;

            var lblValue = new Label
            {
                Text = value,
                Font = Theme.StatFont,
                ForeColor = Theme.TextPrimary,
                BackColor = Color.Transparent,
                Location = new Point(16, 36),
                AutoSize = true
            };

            card.Controls.Add(lblValue);
            card.Controls.Add(lblTitle);
            card.Controls.Add(accentBar);
            card.Tag = lblValue;
            return card;
        }

        private void CreateTokensPanel()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = Theme.Background, AutoScroll = true };
            _contentPanels.Add(panel);

            var lblTitle = Theme.CreateLabel("機器人 Token", Theme.TextPrimary, Theme.TitleFont);
            lblTitle.Location = new Point(0, 0);
            panel.Controls.Add(lblTitle);

            var lblDesc = Theme.CreateLabel("新增無限數量的 Discord 機器人 Token，每個 Token 獨立運作以達到最大私訊吞吐量。", Theme.TextSecondary, Theme.SmallFont);
            lblDesc.Location = new Point(0, 28);
            lblDesc.AutoSize = true;
            panel.Controls.Add(lblDesc);

            _txtTokenInput = Theme.CreateTextBox();
            _txtTokenInput.Location = new Point(0, 60);
            _txtTokenInput.Size = new Size(500, 32);
            _txtTokenInput.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            _txtTokenInput.PlaceholderText = "在此貼上機器人 Token...";
            panel.Controls.Add(_txtTokenInput);

            var btnAdd = Theme.CreateActionButton("新增 Token", Theme.Accent, Color.Black);
            btnAdd.Location = new Point(510, 60);
            btnAdd.Size = new Size(120, 32);
            btnAdd.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnAdd.Click += OnAddToken;
            panel.Controls.Add(btnAdd);

            _btnConnectAll = Theme.CreateActionButton("全部連線", Theme.Accent, Color.Black);
            _btnConnectAll.Location = new Point(0, 104);
            _btnConnectAll.Size = new Size(130, 34);
            _btnConnectAll.Click += OnConnectAll;
            panel.Controls.Add(_btnConnectAll);

            _btnDisconnectAll = Theme.CreateActionButton("全部斷線", Theme.Danger, Color.White);
            _btnDisconnectAll.Location = new Point(140, 104);
            _btnDisconnectAll.Size = new Size(140, 34);
            _btnDisconnectAll.Click += OnDisconnectAll;
            panel.Controls.Add(_btnDisconnectAll);

            var btnRemove = Theme.CreateActionButton("移除選取項目", Theme.Border, Theme.TextPrimary);
            btnRemove.Location = new Point(290, 104);
            btnRemove.Size = new Size(140, 34);
            btnRemove.Click += OnRemoveToken;
            panel.Controls.Add(btnRemove);

            _lvTokens = Theme.CreateListView();
            _lvTokens.Location = new Point(0, 152);
            _lvTokens.Size = new Size(740, 380);
            _lvTokens.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            _lvTokens.Columns.Add("機器人名稱", 160);
            _lvTokens.Columns.Add("狀態", 100);
            _lvTokens.Columns.Add("Token", 200);
            _lvTokens.Columns.Add("已發送私訊", 80);
            panel.Controls.Add(_lvTokens);
        }

        private void CreateSpamPanel()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = Theme.Background, AutoScroll = true };
            _contentPanels.Add(panel);

            var lblTitle = Theme.CreateLabel("私訊轟炸", Theme.TextPrimary, Theme.TitleFont);
            lblTitle.Location = new Point(0, 0);
            panel.Controls.Add(lblTitle);

            var lblTarget = Theme.CreateLabel("目標用戶 ID", Theme.TextSecondary, Theme.LabelFontBold);
            lblTarget.Location = new Point(0, 44);
            panel.Controls.Add(lblTarget);

            _txtTargetId = Theme.CreateTextBox();
            _txtTargetId.Location = new Point(0, 64);
            _txtTargetId.Size = new Size(360, 32);
            _txtTargetId.PlaceholderText = "輸入 Discord 用戶 ID...";
            panel.Controls.Add(_txtTargetId);

            var lblMessage = Theme.CreateLabel("訊息內容", Theme.TextSecondary, Theme.LabelFontBold);
            lblMessage.Location = new Point(0, 110);
            panel.Controls.Add(lblMessage);

            _txtSpamMessage = new TextBox
            {
                BackColor = Theme.InputBg,
                ForeColor = Theme.TextPrimary,
                Font = Theme.InputFont,
                BorderStyle = BorderStyle.FixedSingle,
                Location = new Point(0, 130),
                Size = new Size(630, 80),
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                PlaceholderText = "輸入訊息內容... 使用 | 分隔多條訊息（多訊息模式）"
            };
            _txtSpamMessage.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            panel.Controls.Add(_txtSpamMessage);

            var lblAmount = Theme.CreateLabel("發送數量（每隻機器人）", Theme.TextSecondary, Theme.LabelFontBold);
            lblAmount.Location = new Point(0, 224);
            panel.Controls.Add(lblAmount);

            _numAmount = new NumericUpDown
            {
                Location = new Point(0, 244),
                Size = new Size(120, 32),
                Minimum = 1,
                Maximum = 5000,
                Value = 100,
                BackColor = Theme.InputBg,
                ForeColor = Theme.TextPrimary,
                Font = Theme.InputFont,
                BorderStyle = BorderStyle.FixedSingle
            };
            panel.Controls.Add(_numAmount);

            _chkMultiMessage = new CheckBox
            {
                Text = "多訊息模式（用 | 分隔）",
                Location = new Point(140, 248),
                Size = new Size(260, 24),
                ForeColor = Theme.TextSecondary,
                Font = Theme.LabelFont,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.Transparent
            };
            panel.Controls.Add(_chkMultiMessage);

            _btnStartSpam = Theme.CreateActionButton("開始轟炸", Theme.Accent, Color.Black);
            _btnStartSpam.Location = new Point(0, 290);
            _btnStartSpam.Size = new Size(160, 40);
            _btnStartSpam.Click += OnStartSpam;
            panel.Controls.Add(_btnStartSpam);

            _btnStopSpam = Theme.CreateActionButton("停止", Theme.Danger, Color.White);
            _btnStopSpam.Location = new Point(170, 290);
            _btnStopSpam.Size = new Size(100, 40);
            _btnStopSpam.Enabled = false;
            _btnStopSpam.Click += OnStopSpam;
            panel.Controls.Add(_btnStopSpam);

            _progressSpam = new ProgressBar
            {
                Location = new Point(0, 346),
                Size = new Size(630, 8),
                Style = ProgressBarStyle.Continuous,
                ForeColor = Theme.Accent,
                BackColor = Theme.InputBg,
                Minimum = 0,
                Maximum = 100,
                Value = 0,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            panel.Controls.Add(_progressSpam);

            _lblSpamStatus = Theme.CreateLabel("就緒", Theme.TextSecondary, Theme.LabelFont);
            _lblSpamStatus.Location = new Point(0, 364);
            _lblSpamStatus.AutoSize = true;
            panel.Controls.Add(_lblSpamStatus);

            var lblInfo = Theme.CreateLabel("所有已連線的機器人會同時發送私訊。每隻機器人有獨立的速率限制，機器人越多 = 轟炸越快。", Theme.TextDim, Theme.SmallFont);
            lblInfo.Location = new Point(0, 396);
            lblInfo.AutoSize = true;
            panel.Controls.Add(lblInfo);
        }

        private void CreateWhitelistPanel()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = Theme.Background, AutoScroll = true };
            _contentPanels.Add(panel);

            var lblTitle = Theme.CreateLabel("白名單管理", Theme.TextPrimary, Theme.TitleFont);
            lblTitle.Location = new Point(0, 0);
            panel.Controls.Add(lblTitle);

            var lblDesc = Theme.CreateLabel("只有白名單內的 Discord 用戶可以使用機器人指令（!dm, !dmm, !dmmulti, !zsming）。", Theme.TextSecondary, Theme.SmallFont);
            lblDesc.Location = new Point(0, 28);
            lblDesc.AutoSize = true;
            panel.Controls.Add(lblDesc);

            var lblAdd = Theme.CreateLabel("以 Discord ID 新增用戶", Theme.TextSecondary, Theme.LabelFontBold);
            lblAdd.Location = new Point(0, 60);
            panel.Controls.Add(lblAdd);

            _txtWhitelistId = Theme.CreateTextBox();
            _txtWhitelistId.Location = new Point(0, 80);
            _txtWhitelistId.Size = new Size(500, 32);
            _txtWhitelistId.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            _txtWhitelistId.PlaceholderText = "輸入 Discord 用戶 ID...";
            panel.Controls.Add(_txtWhitelistId);

            var btnAdd = Theme.CreateActionButton("新增", Theme.Accent, Color.Black);
            btnAdd.Location = new Point(510, 80);
            btnAdd.Size = new Size(100, 32);
            btnAdd.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnAdd.Click += OnAddWhitelist;
            panel.Controls.Add(btnAdd);

            var btnRemove = Theme.CreateActionButton("移除選取項目", Theme.Danger, Color.White);
            btnRemove.Location = new Point(0, 124);
            btnRemove.Size = new Size(150, 34);
            btnRemove.Click += OnRemoveWhitelist;
            panel.Controls.Add(btnRemove);

            _lvWhitelist = Theme.CreateListView();
            _lvWhitelist.Location = new Point(0, 172);
            _lvWhitelist.Size = new Size(740, 360);
            _lvWhitelist.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            _lvWhitelist.Columns.Add("用戶 ID", 300);
            _lvWhitelist.Columns.Add("加入時間", 200);
            panel.Controls.Add(_lvWhitelist);
        }

        private void CreateLogPanel()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = Theme.Background, AutoScroll = true };
            _contentPanels.Add(panel);

            var lblTitle = Theme.CreateLabel("活動日誌", Theme.TextPrimary, Theme.TitleFont);
            lblTitle.Location = new Point(0, 0);
            panel.Controls.Add(lblTitle);

            var btnClear = Theme.CreateActionButton("清除日誌", Theme.Border, Theme.TextPrimary);
            btnClear.Location = new Point(640, 0);
            btnClear.Size = new Size(100, 28);
            btnClear.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnClear.Click += (s, e) => _rtbLog.Clear();
            panel.Controls.Add(btnClear);

            _rtbLog = new RichTextBox
            {
                Location = new Point(0, 40),
                Size = new Size(740, 480),
                BackColor = Color.Black,
                ForeColor = ColorTranslator.FromHtml("#0f0"),
                Font = new Font("Consolas", 9F),
                BorderStyle = BorderStyle.FixedSingle,
                ReadOnly = true,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            panel.Controls.Add(_rtbLog);
        }

        private void NavigateTo(int index)
        {
            _currentNavIndex = index;
            for (int i = 0; i < _navButtons.Count; i++)
            {
                var btn = _navButtons[i];
                if (i == index)
                {
                    btn.BackColor = Theme.Accent;
                    btn.ForeColor = Color.White;
                    btn.Font = Theme.NavFontActive;
                }
                else
                {
                    btn.BackColor = Theme.Sidebar;
                    btn.ForeColor = Theme.TextSecondary;
                    btn.Font = Theme.NavFont;
                }
            }

            for (int i = 0; i < _contentPanels.Count; i++)
            {
                _contentPanels[i].Visible = (i == index);
                if (i == index)
                    _contentPanels[i].BringToFront();
            }
        }

        private void OnNavClick(object sender, EventArgs e)
        {
            if (sender is Button btn && btn.Tag is int index)
                NavigateTo(index);
        }

        private async void OnAddToken(object sender, EventArgs e)
        {
            var token = _txtTokenInput.Text.Trim();
            if (string.IsNullOrEmpty(token))
            {
                Log("請輸入 Token", "WARN");
                return;
            }
            _discord.AddToken(token);
            _txtTokenInput.Clear();
            RefreshTokensList();
            RefreshDashboard();
        }

        private async void OnRemoveToken(object sender, EventArgs e)
        {
            if (_lvTokens.SelectedItems.Count == 0) return;
            int index = _lvTokens.SelectedItems[0].Index;
            await _discord.RemoveTokenAsync(index);
            RefreshTokensList();
            RefreshDashboard();
        }

        private async void OnConnectAll(object sender, EventArgs e)
        {
            _btnConnectAll.Enabled = false;
            await _discord.ConnectAll();
            _btnConnectAll.Enabled = true;
            RefreshTokensList();
            RefreshDashboard();
        }

        private async void OnDisconnectAll(object sender, EventArgs e)
        {
            _btnDisconnectAll.Enabled = false;
            await _discord.DisconnectAll();
            _btnDisconnectAll.Enabled = true;
            RefreshTokensList();
            RefreshDashboard();
        }

        private async void OnStartSpam(object sender, EventArgs e)
        {
            if (!ulong.TryParse(_txtTargetId.Text.Trim(), out var targetId))
            {
                Log("無效的目標用戶 ID", "ERROR");
                return;
            }

            var message = _txtSpamMessage.Text.Trim();
            if (string.IsNullOrEmpty(message))
            {
                Log("訊息內容不能為空", "ERROR");
                return;
            }

            int amount = (int)_numAmount.Value;
            bool multi = _chkMultiMessage.Checked;
            var connectedBots = _discord.GetConnectedBots();
            if (connectedBots.Count == 0)
            {
                Log("沒有已連線的機器人，請先到機器人 Token 頁面連線。", "ERROR");
                return;
            }

            _spamCts = new CancellationTokenSource();
            _btnStartSpam.Enabled = false;
            _btnStopSpam.Enabled = true;
            _progressSpam.Style = ProgressBarStyle.Marquee;
            _lblSpamStatus.Text = $"正在轟炸 {targetId}，使用 {connectedBots.Count} 隻機器人...";

            try
            {
                var sent = await _discord.SendSpam(targetId, message, amount, multi, _spamCts.Token);
                _lblSpamStatus.Text = $"完成：已發送 {sent} 條私訊";
            }
            catch (OperationCanceledException)
            {
                _lblSpamStatus.Text = "已由用戶停止轟炸";
                Log("轟炸已取消", "WARN");
            }
            catch (Exception ex)
            {
                _lblSpamStatus.Text = $"錯誤：{ex.Message}";
                Log($"轟炸錯誤：{ex.Message}", "ERROR");
            }
            finally
            {
                _progressSpam.Style = ProgressBarStyle.Continuous;
                _progressSpam.Value = 0;
                _btnStartSpam.Enabled = true;
                _btnStopSpam.Enabled = false;
                RefreshTokensList();
                RefreshDashboard();
            }
        }

        private void OnStopSpam(object sender, EventArgs e)
        {
            _spamCts?.Cancel();
            _lblSpamStatus.Text = "正在停止...";
        }

        private void OnAddWhitelist(object sender, EventArgs e)
        {
            if (!ulong.TryParse(_txtWhitelistId.Text.Trim(), out var userId))
            {
                Log("無效的用戶 ID 格式", "ERROR");
                return;
            }
            _discord.AddWhitelist(userId);
            _txtWhitelistId.Clear();
            RefreshWhitelistList();
        }

        private void OnRemoveWhitelist(object sender, EventArgs e)
        {
            if (_lvWhitelist.SelectedItems.Count == 0) return;
            var item = _lvWhitelist.SelectedItems[0];
            if (ulong.TryParse(item.SubItems[0].Text, out var userId))
            {
                _discord.RemoveWhitelist(userId);
                RefreshWhitelistList();
            }
        }

        private void RefreshTokensList()
        {
            if (InvokeRequired) { Invoke(new Action(RefreshTokensList)); return; }

            _lvTokens.Items.Clear();
            var bots = _discord.GetBots();
            foreach (var bot in bots)
            {
                var item = new ListViewItem(bot.Name);
                item.SubItems.Add(bot.IsConnected ? "線上" : "離線");
                item.SubItems.Add(Theme.MaskToken(bot.Token));
                item.SubItems.Add(bot.DmsSent.ToString());
                item.ForeColor = bot.IsConnected ? Theme.Success : Theme.TextSecondary;
                _lvTokens.Items.Add(item);
            }
        }

        private void RefreshWhitelistList()
        {
            if (InvokeRequired) { Invoke(new Action(RefreshWhitelistList)); return; }

            _lvWhitelist.Items.Clear();
            var whitelist = _discord.GetWhitelist().OrderByDescending(x => x).ToList();
            foreach (var userId in whitelist)
            {
                var item = new ListViewItem(userId.ToString());
                item.SubItems.Add(DateTime.Now.ToString("yyyy-MM-dd"));
                _lvWhitelist.Items.Add(item);
            }
        }

        private void RefreshDashboard()
        {
            if (InvokeRequired) { Invoke(new Action(RefreshDashboard)); return; }

            var bots = _discord.GetBots();
            int connected = bots.Count(b => b.IsConnected);
            int totalDms = bots.Sum(b => b.DmsSent);

            _statTotalTokens.Text = bots.Count.ToString();
            _statConnected.Text = connected.ToString();
            _statTotalDms.Text = totalDms.ToString();
            _lblConnStatus.Text = $"  {connected} 隻機器人上線";

            _lvDashboardBots.Items.Clear();
            foreach (var bot in bots)
            {
                var item = new ListViewItem(bot.Name);
                item.SubItems.Add(bot.Id.ToString());
                item.SubItems.Add(bot.IsConnected ? "線上" : "離線");
                item.SubItems.Add(bot.DmsSent.ToString());
                item.ForeColor = bot.IsConnected ? Theme.Success : Theme.TextSecondary;
                _lvDashboardBots.Items.Add(item);
            }
        }

        public void Log(string message, string level = "INFO")
        {
            if (InvokeRequired) { Invoke(new Action<string, string>(Log), message, level); return; }

            var timestamp = DateTime.Now.ToString("HH:mm:ss");
            Color color = level switch
            {
                "SUCCESS" => Theme.Success,
                "ERROR" => Theme.Danger,
                "WARN" => Theme.SecondaryAccent,
                _ => Theme.TextPrimary
            };

            _rtbLog.SelectionStart = _rtbLog.TextLength;
            _rtbLog.SelectionLength = 0;
            _rtbLog.SelectionColor = Theme.TextDim;
            _rtbLog.AppendText($"[{timestamp}] ");

            _rtbLog.SelectionColor = color;
            _rtbLog.SelectionStart = _rtbLog.TextLength;
            _rtbLog.SelectionLength = 0;
            _rtbLog.AppendText($"[{level}] {message}\n");

            _rtbLog.SelectionColor = Theme.TextPrimary;
            _rtbLog.ScrollToCaret();
        }

        private void OnLogCallback(string message, string level)
        {
            Log(message, level);
        }

        private void OnBotsChangedCallback()
        {
            RefreshTokensList();
            RefreshDashboard();
        }

        private void OnWhitelistChangedCallback()
        {
            RefreshWhitelistList();
        }

        private async void OnFormClosing(object sender, FormClosingEventArgs e)
        {
            try
            {
                await _discord.DisconnectAll();
            }
            catch { }
        }
    }
}
