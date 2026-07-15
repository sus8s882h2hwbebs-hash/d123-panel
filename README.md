# D123 DIGITAL PANEL

## 部署到 Railway

1. 把這個資料夾推到 GitHub repo
2. 到 [railway.app](https://railway.app) 新建專案，選擇該 repo
3. Railway 會自動偵測 `requirements.txt` + `Procfile`
4. 部署完成後會拿到 `https://你的app名.up.railway.app`
5. 用瀏覽器打開即可使用面板

## 本機執行

```bash
pip install -r requirements.txt
python d123_panel.py
```

打開 `http://localhost:5000`

## Discord Slash 指令

| 指令 | 權限 | 說明 |
|------|------|------|
| `/增加權限` | Owner | 授權用戶 |
| `/移除權限` | Owner | 移除權限 |
| `/查看權限` | Owner | 列出授權用戶 |
| `/dm` | 授權用戶 | 轟炸 100 條私訊 |
| `/dmm` | 授權用戶 | 自訂數量轟炸 |
| `/dmmulti` | 授權用戶 | 多訊息轟炸 (用 \| 分隔) |

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `PORT` | 5000 | Web server port (Railway 自動設定) |
