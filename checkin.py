import os
import json
import time
import random
import requests
from pypushdeer import PushDeer

CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"
REOPEN_URL = "https://glados.cloud/api/user/reopen"  # 新增：Restart 接口

HEADERS_BASE = {
    "origin": "https://glados.cloud",
    "referer": "https://glados.cloud/console/checkin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.cloud"}
TIMEOUT = 10


def push_deer(sckey: str, title: str, text: str):
    """推送消息到 PushDeer"""
    if sckey:
        PushDeer(pushkey=sckey).send_text(title, desp=text)


def push_serverchan(sendkey: str, title: str, content: str):
    """推送消息到 Server 酱 (Turbo 版)"""
    if not sendkey:
        return
    
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {
        "title": title,
        "desp": content
    }
    
    try:
        resp = requests.post(url, data=data, timeout=TIMEOUT)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 0:
                print("✅ Server 酱推送成功")
            else:
                print(f"⚠️ Server 酱推送失败: {result.get('message')}")
        else:
            print(f"⚠️ Server 酱推送失败: HTTP {resp.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Server 酱推送异常: {e}")


def push_all(sendkey_deer: str, sendkey_sc: str, title: str, content: str):
    """推送到所有配置的服务"""
    if sendkey_deer:
        push_deer(sendkey_deer, title, content)
    
    if sendkey_sc:
        push_serverchan(sendkey_sc, title, content)
    
    if not sendkey_deer and not sendkey_sc:
        print("⚠️ 未配置任何推送服务，请在 Secrets 中配置 SENDKEY 或 SERVERCHAN_KEY")


def safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return {}


def main():
    sendkey_deer = os.getenv("SENDKEY", "")
    sendkey_sc = os.getenv("SERVERCHAN_KEY", "")
    cookies_env = os.getenv("COOKIES", "")
    cookies = [c.strip() for c in cookies_env.split("&") if c.strip()]

    if not cookies:
        push_all(sendkey_deer, sendkey_sc, "GLaDOS 签到", "❌ 未检测到 COOKIES")
        return

    session = requests.Session()
    ok = fail = repeat = 0
    lines = []

    for idx, cookie in enumerate(cookies, 1):
        headers = dict(HEADERS_BASE)
        headers["cookie"] = cookie

        email = "unknown"
        points = "-"
        days_str = "-"
        left_days_val = 0.0

        try:
            # 1. 执行签到
            r = session.post(
                CHECKIN_URL,
                headers=headers,
                data=json.dumps(PAYLOAD),
                timeout=TIMEOUT,
            )
            j = safe_json(r)
            msg = j.get("message", "").lower()

            if "got" in msg:
                ok += 1
                points = j.get("points", "-")
                status = "✅ 成功"
            elif "repeat" in msg or "already" in msg:
                repeat += 1
                status = "🔁 已签到"
            else:
                fail += 1
                status = "❌ 失败"

            # 2. 获取状态 (包含剩余天数)
            s = session.get(STATUS_URL, headers=headers, timeout=TIMEOUT)
            sj = safe_json(s).get("data") or {}
            email = sj.get("email", email)
            
            raw_left_days = sj.get("leftDays")
            if raw_left_days is not None:
                left_days_val = float(raw_left_days)
                days_str = f"{int(left_days_val)} 天"
            else:
                left_days_val = 0.0 # 没获取到则视为 0 天

            # 3. 如果天数 <= 0，自动触发 Restart (reopen)
            if left_days_val <= 0:
                reopen_resp = session.post(
                    REOPEN_URL, 
                    headers=headers, 
                    json={}, # 根据前端 axios.post()，传空 body 即可
                    timeout=TIMEOUT
                )
                reopen_data = safe_json(reopen_resp)
                
                # 参考前端 React 的判断逻辑: if(data.data) 为成功
                if reopen_data.get("data"):
                    status += " [🔄 自动重启成功]"
                    days_str = "2 天(试用期)"
                else:
                    err_msg = reopen_data.get("message", "未知原因")
                    status += f" [⚠️ 重启失败: {err_msg}]"

        except requests.exceptions.RequestException as e:
            fail += 1
            status = f"❌ 网络异常"

        lines.append(f"{idx}. {email} | {status} | P:{points} | 剩余:{days_str}")
        time.sleep(random.uniform(1, 2))

    title = f"GLaDOS 签到完成 ✅{ok} ❌{fail} 🔁{repeat}"
    content = "\n".join(lines)

    print(content)
    push_all(sendkey_deer, sendkey_sc, title, content)


if __name__ == "__main__":
    main()
