import asyncio
import hashlib
import random
import sys
import time
from typing import Final, List, Dict
from urllib.parse import urlparse

import httpx
from httpx import URL
from loguru import logger

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
        """
        获取某个请求的 sign
        :param request_url: 请求 URL
        :param timestamp: 时间戳
        :param channel: android_app / alipay
        :return: sign 值
        """
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
        """签到"""
        _data = {"activityId": "600001", "token": self.token}
        _response = await self.client.post(url="/signin/doUserSignIn", data=_data)

    async def get_user_name(self):
        data = {"token": self.token}
        res_json = (await self.client.post("/user/info", data=data)).json()
        if res_json["data"]["userName"] is None:
            return "未设置昵称"
        else:
            return res_json["data"]["userName"]


async def helper(token: str, phone_brand: str):
    a = await PgAccount.create(token, phone_brand)

    # 胖乖生活 APP 签到
    username = await a.get_user_name()
    user_logger = logger.bind(username=username)
    user_logger.info(f"登录账号 {username}")
    balance_dict = await a.get_balance()
    user_logger.info(f"账户当前通用小票: {int(balance_dict['tokenCoin']) / 100}")
    user_logger.info(f"账户当前积分: {balance_dict['integral']}")
    user_logger.info(f"尝试完成 签到")
    for i in range(1,4):
        try:
            await a.is_capcha()
            break
        except ValueError:
            if i ==4:
                user_logger.error("无法绕过人机验证")
                exit(1)
            user_logger.warning(f"触发人机验证，第 {i} 次重试")
            await asyncio.sleep(random.randint(65, 125))
    await asyncio.sleep(random.random())
    await a.checkin()
    user_logger.success(f"签到成功")

    # 胖乖生活 APP 任务
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
                            exit(1)
                        user_logger.warning(f"触发人机验证，第 {i} 次重试")
                        await asyncio.sleep(random.randint(65, 125))
                await asyncio.sleep(random.randint(45, 55))
                if await a.complete_task(task["taskCode"]) is False:
                    user_logger.error(f"尝试完成第 {num} 次 {task['title']} 失败")
                    break
                user_logger.success(f"成功完成第 {num} 次 {task['title']}")
                await asyncio.sleep(random.randint(35, 95))
    user_logger.info(f"胖乖生活 APP 任务 结束")

    await asyncio.sleep(random.randint(65, 125))

    # 胖乖生活 小程序 任务
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
                            exit(1)
                        user_logger.warning(f"触发人机验证，第 {i} 次重试")
                        await asyncio.sleep(random.randint(65, 125))
                await asyncio.sleep(random.randint(45, 55))
                if await a.complete_task(task["taskCode"], channel="alipay") is False:
                    user_logger.error(f"尝试完成第 {num} 次 {task['title']} 失败")
                    break
                user_logger.success(f"成功完成第 {num} 次 {task['title']}")
                await asyncio.sleep(random.randint(35, 95))
    user_logger.info(f"胖乖生活 小程序 任务 结束")

    balance_dict = await a.get_balance()
    user_logger.success(f"{username} 积分刷取完成，当前积分: {balance_dict['integral']}")


async def main():
    try:
        accounts: List[str] = QLAPI.getEnvs({"searchValue": "PgshAccounts"})["data"][0][
            "value"
        ].split(";")
    except NameError:
        accounts: List[str] = PGSH_ACCOUNTS.split(";")
    tasks = [asyncio.create_task(helper(*account.split(":"))) for account in accounts]
    await asyncio.gather(*tasks)


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
