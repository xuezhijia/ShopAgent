import redis
import json
import time, datetime, traceback, sys


########## 用于与Redis缓存数据库进行交互 ##########

class RedisData:

    # 注意，这里使用“localhost”会很慢，所以用127.0.0.1
    def __init__(self):
        self.connect = redis.StrictRedis(host='127.0.0.1', port='6379', db=0, password='123456')


    def save_conversation(self, user_id: str, user_message: str, assistant_response: str):
        """保存对话到历史记录"""
        try:
            r = self.connect

            # 使用Redis列表存储对话
            key = f"conversation:{user_id}"

            # 构建对话记录
            user_record = json.dumps({
                "role": "user",
                "content": user_message,
                "timestamp": time.time()
            }, ensure_ascii=False)

            assistant_record = json.dumps({
                "role": "assistant",
                "content": assistant_response,
                "timestamp": time.time()
            }, ensure_ascii=False)

            # 使用Pipeline批量操作,提升性能
            pipe = r.pipeline()
            pipe.rpush(key, user_record)
            pipe.rpush(key, assistant_record)

            # 保持最近50条记录(裁剪列表)
            pipe.ltrim(key, -50, -1)

            # 设置过期时间(24小时)
            pipe.expire(key, 86400)

            # 执行所有操作
            pipe.execute()

        except Exception as e:
            print(f"保存对话失败: {e}")


    def get_conversation_history(self, user_id: str, max_turns: int = 10) -> list:
        """获取用户最近的对话历史"""
        try:
            r = self.connect

            # 从Redis获取对话历史
            key = f"conversation:{user_id}"

            # 获取最近N轮对话(每条对话包含user和assistant两条记录)
            start_index = -(max_turns * 2)
            history_json = r.lrange(key, start_index, -1)

            # 解析JSON
            history = []
            for item in history_json:
                try:
                    record = json.loads(item)
                    history.append(record)
                except json.JSONDecodeError:
                    continue

            return history

        except Exception as e:
            print(f"获取对话历史失败: {e}")
            return []

if __name__ == "__main__":
    redis_data = RedisData()
    redis_data.save_conversation("10025588", "我的上一个问题是什么", "上一个问题是'快递什么时候发？'")