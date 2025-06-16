# PgshAutoHelper

一个用于自动化完成胖乖生活（PGSH）APP和小程序任务的Python工具。

## 功能特点

- 自动完成胖乖生活APP签到
- 自动完成胖乖生活APP日常任务
- 自动完成胖乖生活小程序任务
- 支持多账号并发运行
- 内置人机验证处理机制
- 详细的日志输出

## 使用方法
### 获取 Token 和 PhoneBrand

#### 抓包获取 Token 和 PhoneBrand
对 胖乖生活APP 进行抓包， token 一般位于请求体中。`phoneBrand` 一般位于请求头中。 

#### 网页端获取 Token
参考 https://www.zhihu.com/question/585417484 即可。`phoneBrand` 自己编或者抓包看。小米手机`PhoneBrand`为`Xiaomi`

### 部署
#### 青龙面板
在青龙面板内添加环境变量`PgshAccounts`, 格式为：`token:phoneBrand;token:phoneBrand`。  
然后设置定时执行,每日一次即可。

#### 自部署

```bash
git clone https://github.com/yourusername/PgshAutoHelper.git
cd PgshAutoHelper
```
在 `src/helper.py` 中修改 `PGSH_ACCOUNTS` 变量, 格式为：`token:phoneBrand;token:phoneBrand`。  

```bash
uv sync
uv run src/helper.py
```
定时执行即可

## 注意事项

- 不保证不黑号
- 积分及时用,攒太多容易被清空
- 建议使用定时任务每天运行一次

## 依赖项

- httpx >= 0.28.1
- loguru >= 0.7.3

## 许可证

MIT License 