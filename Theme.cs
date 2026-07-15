using System;
using System.Drawing;
using System.Windows.Forms;

namespace ZSMING
{
    public static class Theme
    {
        public static readonly Color Background = ColorTranslator.FromHtml("#0a0a0f");
        public static readonly Color Sidebar = ColorTranslator.FromHtml("#12121c");
        public static readonly Color Panel = ColorTranslator.FromHtml("#12121c");
        public static readonly Color Card = ColorTranslator.FromHtml("#1a1a25");
        public static readonly Color CardHover = ColorTranslator.FromHtml("#22222e");
        public static readonly Color Accent = ColorTranslator.FromHtml("#d4af37");
        public static readonly Color AccentHover = ColorTranslator.FromHtml("#ffffff");
        public static readonly Color AccentDark = ColorTranslator.FromHtml("#b8962e");
        public static readonly Color SecondaryAccent = ColorTranslator.FromHtml("#f4a261");
        public static readonly Color TextPrimary = ColorTranslator.FromHtml("#e0e0e0");
        public static readonly Color TextSecondary = ColorTranslator.FromHtml("#8a8a9a");
        public static readonly Color TextDim = ColorTranslator.FromHtml("#5a5a6a");
        public static readonly Color Border = ColorTranslator.FromHtml("#2a2a3a");
        public static readonly Color Success = ColorTranslator.FromHtml("#0f0");
        public static readonly Color Danger = ColorTranslator.FromHtml("#ff4d4d");
        public static readonly Color InputBg = ColorTranslator.FromHtml("#000000");
        public static readonly Color InputBorder = ColorTranslator.FromHtml("#333333");
        public static readonly Color GoldGlow = Color.FromArgb(20, 212, 175, 55);

        public static readonly Font HeaderFont = new Font("Segoe UI", 20F, FontStyle.Bold);
        public static readonly Font SubHeaderFont = new Font("Segoe UI", 9F, FontStyle.Regular);
        public static readonly Font NavFont = new Font("Segoe UI", 10.5F, FontStyle.Regular);
        public static readonly Font NavFontActive = new Font("Segoe UI", 10.5F, FontStyle.Bold);
        public static readonly Font LabelFont = new Font("Segoe UI", 9F, FontStyle.Regular);
        public static readonly Font LabelFontBold = new Font("Segoe UI", 9F, FontStyle.Bold);
        public static readonly Font ButtonFont = new Font("Segoe UI", 10F, FontStyle.Bold);
        public static readonly Font InputFont = new Font("Segoe UI", 10F, FontStyle.Regular);
        public static readonly Font SmallFont = new Font("Segoe UI", 8F, FontStyle.Regular);
        public static readonly Font StatFont = new Font("Segoe UI", 22F, FontStyle.Bold);
        public static readonly Font StatLabelFont = new Font("Segoe UI", 8.5F, FontStyle.Regular);
        public static readonly Font TitleFont = new Font("Segoe UI", 14F, FontStyle.Bold);

        public static void StyleForm(Form form)
        {
            form.BackColor = Background;
            form.ForeColor = TextPrimary;
            form.Font = LabelFont;
        }

        public static Button CreateNavButton(string text)
        {
            var btn = new Button
            {
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = Sidebar,
                ForeColor = TextSecondary,
                Font = NavFont,
                TextAlign = ContentAlignment.MiddleLeft,
                Padding = new Padding(24, 0, 0, 0),
                Cursor = Cursors.Hand,
                FlatAppearance = { BorderSize = 0 }
            };
            btn.FlatAppearance.MouseOverBackColor = Card;
            return btn;
        }

        public static Button CreateActionButton(string text, Color bg, Color fg)
        {
            var btn = new Button
            {
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = bg,
                ForeColor = fg,
                Font = ButtonFont,
                Cursor = Cursors.Hand,
                FlatAppearance = { BorderSize = 0 }
            };
            if (bg == Accent)
                btn.FlatAppearance.MouseOverBackColor = Color.White;
            else
                btn.FlatAppearance.MouseOverBackColor = AdjustColor(bg, 20);
            return btn;
        }

        public static TextBox CreateTextBox()
        {
            var txt = new TextBox
            {
                BackColor = InputBg,
                ForeColor = Color.White,
                Font = InputFont,
                BorderStyle = BorderStyle.FixedSingle,
                Padding = new Padding(8, 6, 8, 6)
            };
            return txt;
        }

        public static ListView CreateListView()
        {
            var lv = new ListView
            {
                BackColor = Card,
                ForeColor = TextPrimary,
                Font = InputFont,
                BorderStyle = BorderStyle.None,
                FullRowSelect = true,
                View = View.Details,
                GridLines = false,
                HeaderStyle = ColumnHeaderStyle.Nonclickable
            };
            return lv;
        }

        public static Label CreateLabel(string text, Color color, Font font)
        {
            return new Label
            {
                Text = text,
                ForeColor = color,
                Font = font,
                BackColor = Color.Transparent,
                AutoSize = true
            };
        }

        public static Panel CreateCard(int width, int height)
        {
            var card = new Panel
            {
                Size = new Size(width, height),
                BackColor = Card,
                BorderStyle = BorderStyle.None
            };
            var goldBar = new Panel
            {
                Size = new Size(4, height),
                BackColor = Accent,
                Dock = DockStyle.Left
            };
            card.Controls.Add(goldBar);
            return card;
        }

        public static Color AdjustColor(Color color, int amount)
        {
            int r = Math.Min(255, color.R + amount);
            int g = Math.Min(255, color.G + amount);
            int b = Math.Min(255, color.B + amount);
            return Color.FromArgb(r, g, b);
        }

        public static string MaskToken(string token)
        {
            if (string.IsNullOrEmpty(token) || token.Length < 10)
                return "***";
            return token.Substring(0, 4) + "..." + token.Substring(token.Length - 4);
        }
    }
}
