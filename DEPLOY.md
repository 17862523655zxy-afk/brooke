# 比赛部署指南

## 方案对比

| 平台 | 费用 | 难度 | 适合场景 |
|------|------|------|----------|
| **Render** (推荐) | 免费 | 极低 | 比赛 Demo，一键部署 |
| **Railway** | 免费额度 | 低 | 比赛 Demo，支持 Docker |
| **百度智能云** | 按量付费 | 中等 | 正式项目，国内访问快 |
| **阿里云 ECS** | 按量付费 | 中等 | 正式项目，完全可控 |

---

## 方案 A：Render（免费，5 分钟搞定）

1. 代码 push 到 GitHub
2. 访问 [render.com](https://render.com)，用 GitHub 登录
3. New Web Service → 选择你的仓库
4. 配置：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python3 -m src.main`
   - **Environment**: 添加 `OPENAI_API_KEY` 等环境变量
5. 自动获得 `https://xxx.onrender.com` 公网链接

## 方案 B：Railway（免费额度）

1. 代码 push 到 GitHub
2. 访问 [railway.app](https://railway.app)
3. New Project → Deploy from GitHub repo
4. 自动识别 Dockerfile，一键部署
5. 获得公网链接

## 方案 C：Docker 部署（任何云服务器通用）

```bash
# 1. 购买云服务器（百度智能云/阿里云/腾讯云）
# 2. 服务器上安装 Docker
curl -fsSL https://get.docker.com | sh

# 3. 把代码传到服务器（或用 git clone）
git clone <你的仓库地址>
cd comate-zulu-demo

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 5. 构建并启动
docker-compose up -d

# 6. 访问
# 后端: http://<服务器IP>:8080
# 前端: http://<服务器IP>:8501
```

---

## 提交给主办方需要提供的

1. **公网访问链接**（如 `https://xxx.onrender.com`）
2. **仓库地址**（GitHub/GitLab 链接）
3. **演示视频**（建议录 1-2 分钟操作视频，防止评审时服务不可用）

---

## 安全提醒

比赛提交前：
- ✅ 确认 `.env` 中的 API Key 可用（余额充足）
- ✅ 测试几个典型场景能正常跑通
- ✅ 建议录制演示视频作为备份
- ❌ 不要把真实 API Key 提交到公开仓库（用环境变量或 .gitignore）
