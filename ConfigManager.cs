using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace ZSMING
{
    public class ConfigManager
    {
        private static readonly string TokensFile = "tokens.json";
        private static readonly string WhitelistFile = "whitelist.json";

        public List<string> LoadTokens()
        {
            try
            {
                if (File.Exists(TokensFile))
                {
                    var json = File.ReadAllText(TokensFile);
                    var data = JsonSerializer.Deserialize<TokensData>(json);
                    return data?.Tokens ?? new List<string>();
                }
            }
            catch { }
            return new List<string>();
        }

        public void SaveTokens(List<string> tokens)
        {
            try
            {
                var data = new TokensData { Tokens = tokens };
                var json = JsonSerializer.Serialize(data, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(TokensFile, json);
            }
            catch { }
        }

        public HashSet<ulong> LoadWhitelist()
        {
            try
            {
                if (File.Exists(WhitelistFile))
                {
                    var json = File.ReadAllText(WhitelistFile);
                    var data = JsonSerializer.Deserialize<WhitelistData>(json);
                    return new HashSet<ulong>(data?.Whitelist ?? new List<ulong>());
                }
            }
            catch { }
            return new HashSet<ulong>();
        }

        public void SaveWhitelist(HashSet<ulong> whitelist)
        {
            try
            {
                var data = new WhitelistData { Whitelist = new List<ulong>(whitelist) };
                var json = JsonSerializer.Serialize(data, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(WhitelistFile, json);
            }
            catch { }
        }

        private class TokensData
        {
            public List<string> Tokens { get; set; }
        }

        private class WhitelistData
        {
            public List<ulong> Whitelist { get; set; }
        }
    }
}
