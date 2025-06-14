import os
import yaml
import aiohttp
import asyncio
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived

"""
Napcat自动点赞插件
支持"点赞"（默认10次）和"点赞 [次数]"（1-20次，超出按20次处理）两种格式
"""

@register(name="SendLike", description="自动点赞", version="0.1.1", author="HwlloChen")
class SendLikePlugin(BasePlugin):
    
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.config = self.load_config()
        self.onebot_api_url = self.config.get('onebot_api_url', 'http://127.0.0.1:3000')
        
    async def initialize(self):
        """异步初始化"""
        self.ap.logger.info(f"SendLike插件已加载，OneBot API地址: {self.onebot_api_url}")
    
    def load_config(self):
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        
        # 如果配置文件不存在，创建默认配置
        if not os.path.exists(config_path):
            default_config = {
                'onebot_api_url': 'http://127.0.0.1:3000'
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
            self.ap.logger.info("已创建默认配置文件 config.yaml")
            return default_config
        
        # 读取现有配置文件
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config if config else {}
        except Exception as e:
            self.ap.logger.error(f"读取配置文件失败: {e}")
            return {'onebot_api_url': 'http://127.0.0.1:3000'}
    
    async def send_like(self, user_id: str, times: int = 10):
        """发送点赞请求到OneBot API"""
        url = f"{self.onebot_api_url}/send_like"
        data = {
            "user_id": user_id,
            "times": times
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result = await response.json()
                    return result
        except asyncio.TimeoutError:
            self.ap.logger.error("点赞请求超时")
            return {"status": "failed", "message": "请求超时"}
        except Exception as e:
            self.ap.logger.error(f"点赞请求异常: {e}")
            return {"status": "failed", "message": f"请求异常: {str(e)}"}
    
    def parse_like_message(self, msg: str):
        """解析点赞消息，返回 (是否匹配, 点赞次数)"""
        msg = msg.strip()
        
        # 只处理"点赞"或"点赞 [次数]"格式
        if msg == "点赞":
            return True, 10  # 默认10次
        elif msg.startswith("点赞 "):
            try:
                times_str = msg[3:].strip()  # 去掉"点赞 "前缀
                times = int(times_str)
                # 限制最小次数为1，最大次数为20
                if times >= 1:
                    # 如果超过20次，则按20次处理
                    times = min(times, 20)
                    return True, times
                else:
                    return False, 0  # 次数小于1
            except ValueError:
                return False, 0  # 无法解析为数字
        else:
            return False, 0  # 不匹配格式
    
    def get_reply_message(self, result: dict, user_id: str, times: int):
        """根据API返回结果生成回复消息"""
        if result.get("status") == "ok":
            return f"✅ 点赞成功！已为用户 {user_id} 点赞 {times} 次"
        elif result.get("status") == "failed":
            error_msg = result.get("message", "未知错误")
            if "今日同一好友点赞数已达上限" in error_msg:
                return f"❌ 点赞失败：今日对该用户的点赞次数已达上限"
            else:
                return f"❌ 点赞失败：{error_msg}"
        else:
            return f"❓ 点赞结果未知，请检查Napcat服务状态"
    
    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def message_handler(self, ctx: EventContext):
        """统一处理私聊和群聊消息"""
        msg = ctx.event.text_message.strip()
        sender_id = str(ctx.event.sender_id)

        # 解析点赞消息
        is_match, times = self.parse_like_message(msg)

        if is_match:
            self.ap.logger.info(f"收到点赞请求，用户ID: {sender_id}, 次数: {times}")

            # 发送点赞请求
            result = await self.send_like(sender_id, times)

            # 生成回复消息
            reply_msg = self.get_reply_message(result, sender_id, times)

            # 回复消息
            ctx.add_return("reply", [reply_msg])

            # 阻止默认行为
            ctx.prevent_default()
    
    def __del__(self):
        """插件卸载时触发"""
        self.ap.logger.info("SendLike插件已卸载")