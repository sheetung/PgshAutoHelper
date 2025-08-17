import asyncio
import hashlib
import random
import sys
import time
import os
import hmac
import base64
import urllib.parse
from typing import Final, List, Dict
from urllib.parse import urlparse

import httpx
from httpx import URL
from loguru import logger
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ==================== 通知配置 ====================
# Bark 推送配置
BARK_PUSH = os.environ.get("BARK_PUSH", "")
BARK_GROUP = "胖乖生活任务通知"
BARK_ICON = "https://www.qiekj.com/favicon.ico"  # 可替换为项目图标
BARK_SOUND = os.environ.get("BARK_SOUND", "")

# 钉钉推送配置
DINGTALK_TOKEN = os.environ.get("DD_BOT_TOKEN", "")
DINGTALK_SECRET = os.environ.get("DD_BOT_SECRET", "")

# ==================== 项目配置 ====================
PGSH_ACCOUNTS: Final[str] = ""
APP_VERSION: Final[str] = "1.82.1"
APP_SECRET: Final[str] = "nFU9pbG8YQoAe1kFh+E7eyrdlSLglwEJeA0wwHB1j5o="
ALIPAY_APP_SECRET: Final[str] = "Ew+ZSuppXZoA9YzBHgHmRvzt0Bw1CpwlQQtSl49QNhY="
TASKS: Final[List[str]] = [
    "bd28f4af-44d6-4920-8e34-51b42a07960c",
    "c48ebae8-4c11-490e-8ec0-570053dcb020",
    "90a0dceb-8b89-4c5a-b08d-60cf43b9a0c8",
    "02388d14-3ab5-43fc-b709-108b371fb6d8",
    "d798d2e3-7c16-4b5d-9e6d-4b8214ebf2e5",
    "7",
    "c6fee3bc-84ba-4090-9303-2fbf207b2bbd",
    "5",
    "2",
]

ALIPAY_TASKS: Final[List[str]] = [
    "9",
]


# ==================== 账号类 ====================
class PgAccount:
    def __init__(self, token: str, phone_brand: str):
        self.client = httpx.AsyncClient(
            base_url="https://userapi.qiekj.com",
            event_hooks={"request": [self._request_hook]},
        )
        self.token = token
        self.phone_brand = phone_brand

    @classmethod
    async def create(cls, token: str, phone_brand: str):
        self = cls(token, phone_brand)
        await self._get_acw_tc()
        return self

    def get_sign(
        self, request_url: str | URL, timestamp: str | int, channel="android_app"
    ):
        parsed_url = urlparse(str(request_url))
        path = parsed_url.path
        if channel.lower() == "android_app":
            signature_string = f"appSecret={APP_SECRET}&channel={channel}&timestamp={str(timestamp)}&token={self.token}&version={APP_VERSION}&{path}"
        elif channel.lower() == "alipay":
            signature_string = f"appSecret={ALIPAY_APP_SECRET}&channel={channel.lower()}&timestamp={str(timestamp)}&token={self.token}&{path}"
        else:
            raise ValueError(f"Unknown {channel}")
        return hashlib.sha256(signature_string.encode("utf-8")).hexdigest()

    async def get_balance(self) -> Dict:
        _data = {"token": self.token}
        response_json = (await self.client.post("/user/balance", data=_data)).json()
        return response_json["data"]

    async def _get_acw_tc(self):
        _data = {"slotKey": "android_open_screen_1_35_0", "token": self.token}
        response = await self.client.post("/slot/get", data=_data)
        return response.headers["Set-Cookie"].split(";")[0]

    async def _request_hook(self, request: httpx.Request):
        request.headers["User-Agent"] = "okhttp/4.12.0"
        request.headers["Accept-Encoding"] = "gzip"
        request.headers["Version"] = APP_VERSION
        request.headers["phoneBrand"] = self.phone_brand
        request.headers["Authorization"] = self.token
        request.headers["timestamp"] = str(int(time.time() * 1000))
        if request.extensions.get("channel") == "alipay":
            request.headers["sign"] = self.get_sign(
                request.url, request.headers["timestamp"], "alipay"
            )
            request.headers["channel"] = "alipay"
            request.headers.pop("Version")
            request.headers.pop("phoneBrand")
        else:
            request.headers["sign"] = self.get_sign(
                request.url, request.headers["timestamp"]
            )
            request.headers["channel"] = "android_app"

    async def complete_task(self, task_code: str, channel="android_app"):
        _data = {"taskCode": task_code, "token": self.token}
        _response = (
            await self.client.post(
                url="/task/completed", data=_data, extensions={"channel": channel}
            )
        ).json()
        if _response["code"] == 0 and _response["data"] == True:
            return True
        else:
            return False

    async def is_capcha(self):
        _data = {"token": self.token}
        _response = await self.client.post(url="/integralCaptcha/isCaptcha", data=_data)
        if _response is None:
            raise ValueError("触发人机验证")

    async def get_task_list(self, channel="android_app") -> List[Dict]:
        _data = {"token": self.token}
        _response = await self.client.post(
            url="task/list", data=_data, extensions={"channel": channel}
        )
        return _response.json()["data"]["items"]

    async def checkin(self):
        _data = {"activityId": "600001", "token": self.token}
        await self.client.post(url="/signin/doUserSignIn", data=_data)

    async def get_user_name(self):
        data = {"token": self.token}
        res_json = (await self.client.post("/user/info", data=data)).json()
        if res_json["data"]["userName"] is None:
            return "未设置昵称"
        else:
            return res_json["data"]["userName"]


# ==================== 任务执行 ====================
async def helper(token: str, phone_brand: str) -> Dict:
    """执行任务并返回账号结果数据"""
    result = {
        "status": "error",
        "user": "未知用户",
        "token_coin": 0.0,  # 通用小票
        "integral": 0,      # 积分
        "completed_tasks": 0,  # 完成任务总数
        "message": ""
    }

    try:
        a = await PgAccount.create(token, phone_brand)
        username = await a.get_user_name()
        result["user"] = username
        user_logger = logger.bind(username=username)
        user_logger.info(f"登录账号 {username}")

        # 获取初始资产
        balance_dict = await a.get_balance()
        initial_token_coin = int(balance_dict['tokenCoin']) / 100
        initial_integral = balance_dict['integral']
        result["token_coin"] = initial_token_coin
        result["integral"] = initial_integral

        # 签到
        user_logger.info(f"尝试完成 签到")
        for i in range(1, 4):
            try:
                await a.is_capcha()
                break
            except ValueError:
                if i == 4:
                    user_logger.error("无法绕过人机验证")
                    result["message"] = "无法绕过人机验证"
                    return result
                user_logger.warning(f"触发人机验证，第 {i} 次重试")
                await asyncio.sleep(random.randint(65, 125))
        await asyncio.sleep(random.random())
        await a.checkin()
        user_logger.success(f"签到成功")

        # 执行APP任务并计数
        completed_tasks = 0
        user_logger.info(f"开始 胖乖生活 APP 任务")
        tasks = await a.get_task_list()
        for task in tasks:
            if (
                task["taskCode"] in TASKS
                and task["completedStatus"] == 0
                and task["completedFreq"] is not None
            ):
                for num in range(1, task["dailyTaskLimit"] - task["completedFreq"]):
                    user_logger.info(f"尝试完成第 {num} 次 {task['title']}")
                    for i in range(1, 4):
                        try:
                            await a.is_capcha()
                            break
                        except ValueError:
                            if i == 4:
                                user_logger.critical("无法绕过人机验证")
                                result["message"] = "无法绕过人机验证"
                                return result
                            user_logger.warning(f"触发人机验证，第 {i} 次重试")
                            await asyncio.sleep(random.randint(65, 125))
                    await asyncio.sleep(random.randint(45, 55))
                    if await a.complete_task(task["taskCode"]):
                        user_logger.success(f"成功完成第 {num} 次 {task['title']}")
                        completed_tasks += 1
                        await asyncio.sleep(random.randint(35, 95))
                    else:
                        user_logger.error(f"尝试完成第 {num} 次 {task['title']} 失败")
                        break
        user_logger.info(f"胖乖生活 APP 任务 结束")

        # 执行小程序任务并计数
        await asyncio.sleep(random.randint(65, 125))
        user_logger.info(f"开始 胖乖生活 小程序 任务")
        tasks = await a.get_task_list(channel="alipay")
        for task in tasks:
            if (
                task["taskCode"] in ALIPAY_TASKS
                and task["completedStatus"] == 0
                and task["completedFreq"] is not None
            ):
                for num in range(1, task["dailyTaskLimit"] - task["completedFreq"]):
                    user_logger.info(f"尝试完成第 {num} 次 {task['title']}")
                    for i in range(1, 4):
                        try:
                            await a.is_capcha()
                            break
                        except ValueError:
                            if i == 4:
                                user_logger.critical("无法绕过人机验证")
                                result["message"] = "无法绕过人机验证"
                                return result
                            user_logger.warning(f"触发人机验证，第 {i} 次重试")
                            await asyncio.sleep(random.randint(65, 125))
                    await asyncio.sleep(random.randint(45, 55))
                    if await a.complete_task(task["taskCode"], channel="alipay"):
                        user_logger.success(f"成功完成第 {num} 次 {task['title']}")
                        completed_tasks += 1
                        await asyncio.sleep(random.randint(35, 95))
                    else:
                        user_logger.error(f"尝试完成第 {num} 次 {task['title']} 失败")
                        break
        user_logger.info(f"胖乖生活 小程序 任务 结束")

        # 更新最终资产和任务数
        final_balance = await a.get_balance()
        result["token_coin"] = int(final_balance['tokenCoin']) / 100
        result["integral"] = final_balance['integral']
        result["completed_tasks"] = completed_tasks
        result["status"] = "success"
        result["message"] = "任务执行完成"
        user_logger.success(f"{username} 积分刷取完成，当前积分: {result['integral']}，完成任务: {completed_tasks}个")

    except Exception as e:
        result["message"] = str(e)
        logger.error(f"{result['user']} 任务执行失败: {e}")

    return result


# ==================== 通知功能 ====================
def send_bark_notification(results: List[Dict]):
    """发送Bark通知"""
    if not BARK_PUSH:
        logger.info("未配置 Bark 推送，跳过通知")
        return

    title = "胖乖生活任务汇总"
    body_lines = []
    for i, res in enumerate(results, 1):
        if res["status"] == "success":
            line = f"账号{i}（{res['user']}）: ✅ 执行成功\n"
            line += f"通用小票: {res['token_coin']:.2f}\n"
            line += f"当前积分: {res['integral']}\n"
            line += f"完成任务: {res['completed_tasks']}个"
        else:
            line = f"账号{i}（{res['user']}）: ❌ 执行失败\n"
            line += f"原因: {res['message']}"
        body_lines.append(line)

    params = {
        "title": title,
        "body": "\n\n".join(body_lines),
        "icon": BARK_ICON,
        "sound": BARK_SOUND,
        "group": BARK_GROUP,
    }

    try:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        resp = session.post(BARK_PUSH, json=params, timeout=10)
        resp.raise_for_status()
        logger.info("✅ Bark 推送成功")
    except Exception as e:
        logger.error(f"❌ Bark 推送失败: {e}")


def send_dingtalk_notification(results: List[Dict]):
    """发送钉钉通知"""
    if not DINGTALK_TOKEN:
        logger.info("未配置 钉钉推送，跳过通知")
        return

    title = "胖乖生活任务汇总"
    text = f"# {title}\n\n"
    for i, res in enumerate(results, 1):
        if res["status"] == "success":
            text += f"### 账号{i}（{res['user']}）\n"
            text += f"- ✅ 执行状态: 成功\n"
            text += f"- 💰 通用小票: **{res['token_coin']:.2f}**\n"
            text += f"- 🎯 当前积分: **{res['integral']}**\n"
            text += f"- 📌 完成任务: **{res['completed_tasks']}** 个\n\n"
        else:
            text += f"### 账号{i}（{res['user']}）\n"
            text += f"- ❌ 执行状态: 失败\n"
            text += f"- 📝 失败原因: {res['message']}\n\n"

    data = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text}
    }

    # 生成签名
    if DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DINGTALK_SECRET.encode('utf-8')
        string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}".encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign, hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}&timestamp={timestamp}&sign={sign}"
    else:
        url = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}"

    try:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        resp = session.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=10)
        resp.raise_for_status()
        logger.info("✅ 钉钉推送成功")
    except Exception as e:
        logger.error(f"❌ 钉钉推送失败: {e}")


# ==================== 主函数 ====================
async def main():
    # 10分钟内随机延时（0-600秒）
    delay_seconds = random.uniform(0, 600)  # 生成0到600之间的随机浮点数
    minutes = int(delay_seconds // 60)
    seconds = int(delay_seconds % 60)
    logger.info(f"随机延时 {minutes}分{seconds}秒后开始执行任务...")
    await asyncio.sleep(delay_seconds)  # 异步等待延时结束
    # 收集所有账号的执行结果
    results: List[Dict] = []
    
    try:
        # 获取账号列表
        env_value = os.environ.get("PgshAccounts")
        if env_value:
            accounts: List[str] = [acc.strip() for acc in env_value.split(";") if acc.strip()]
        else:
            accounts: List[str] = [acc.strip() for acc in PGSH_ACCOUNTS.split(";") if acc.strip()]
    except Exception as e:
        logger.warning(f"获取环境变量失败: {e}，使用默认账号")
        accounts: List[str] = [acc.strip() for acc in PGSH_ACCOUNTS.split(";") if acc.strip()]
    
    # 过滤无效账号
    valid_accounts = []
    for account in accounts:
        parts = account.split(":")
        if len(parts) == 2:
            valid_accounts.append(parts)
        else:
            logger.error(f"账号格式错误: {account}，跳过该账号")

    if not valid_accounts:
        logger.error("未找到有效账号，程序退出")
        return

    # 执行所有账号任务
    tasks = [asyncio.create_task(helper(token, phone_brand)) for token, phone_brand in valid_accounts]
    results = await asyncio.gather(*tasks)

    # 发送通知
    send_bark_notification(results)
    send_dingtalk_notification(results)


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sink=sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<yellow>{extra[username]}</yellow> - "
        "<level>{message}</level>",
    )
    asyncio.run(main())