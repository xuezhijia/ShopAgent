import logging
import os
import re
import json
import time
import gradio as gr
from redis_data import RedisData
from mysql_data import MysqlData
from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

# 本项目演示电商AI客服与客人的一系列对话，因为只演示后端功能，前端就不做复杂开发，仅用 gradio 简单演示。主要运用到的知识如下
# 1.链的运用
# 2.提示词的写法
# 3.对话的上下文记忆并使用摘要压缩，使用Redis

# 实例化缓存操作类
redis = RedisData()
# 实例化数据库操作类
mysql_data = MysqlData()
# 暂时固定账号
user_id = "10025588"

################# 基础函数 #################

# 使用通义千问模型
qwen = ChatTongyi(
    model_name="qwen-max",
    temperature=0.2,  # 控制创造性
    max_tokens=2000,  # 最大输出长度
    streaming=False,  # 关闭流式输出
    enable_search=True  # 启用联网搜索增强
)


# 带重试的模型调用 LLM
def call_qwen_with_retry(prompt, max_retries=3, retry_delay=2):
    """带错误重试的千问模型调用"""
    for attempt in range(max_retries):
        try:
            response = qwen.invoke(prompt)
            return response.content
        except Exception as e:
            print(f"模型调用失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            time.sleep(retry_delay)
    return "模型服务暂时不可用，请稍后再试......"


################# 上下文管理模块 #################

def compress_history_with_summary(history: list, max_tokens: int = 500) -> str:
    """使用LLM对历史对话进行摘要压缩"""
    if not history:
        return ""

    history_text = "\n".join([
        f"{msg['role']}: {msg['content']}"
        for msg in history
    ])

    prompt = f"""
    你是对话摘要专家，请将以下电商客服对话历史压缩成简洁摘要：

    {history_text}

    要求:
    1. 提取关键信息:订单号、问题类型、已提供的解决方案
    2. 保留客户情绪状态和紧急程度
    3. 控制在{max_tokens}字以内
    4. 使用中文，条理清晰

    摘要:
    """

    try:
        summary = call_qwen_with_retry(prompt, max_retries=2)
        return summary.strip()
    except Exception as e:
        print(f"摘要压缩失败: {e}")
        recent = history[-6:] if len(history) >= 6 else history
        return "\n".join([f"{m['role']}: {m['content']}" for m in recent])


def check_token_limit(history: list, token_threshold: int = 1000) -> bool:
    """估算历史对话的token数量,判断是否需要压缩"""
    total_chars = sum(len(msg['content']) for msg in history)
    estimated_tokens = total_chars * 0.6
    return estimated_tokens > token_threshold


################# 业务处理 #################

# 提取订单ID ERP 订单系统
def extract_order_id(text: str) -> dict:
    """使用千问模型提取订单ID"""
    prompt = f"""
    你是一个电商订单处理专家，请从以下客户反馈中提取订单ID：
    {text}

    订单ID通常是"ORD"开头的10位数字组合。如果找不到订单ID，返回"NOT_FOUND"。

    请严格按JSON格式返回结果：{{"order_id": "提取结果"}}
    """
    try:
        # 正则提取，除前缀外加10位号码
        match = re.search(r'ORD\d{10}', text)
        return {"order_id": match.group(0) if match else "NOT_FOUND"}
    except:
        # 备选方案：大模型提取
        result = call_qwen_with_retry(prompt)
        # 尝试解析JSON
        return json.loads(result.strip())


# 情感分类
def analyze_sentiment(text: str) -> dict:
    """使用千问模型进行情感分析"""
    prompt = f"""
    请分析以下客户反馈的情感倾向：
    「{text}」

    要求：
    1. 判断情感类型：POSITIVE(积极)/NEUTRAL(中性)/NEGATIVE(消极)
    2. 评估置信度(0.0-1.0)
    3. 提取3个关键短语

    返回JSON格式：
    {{
        "sentiment": "情感类型",
        "confidence": 置信度,
        "key_phrases": ["短语1", "短语2", "短语3"]
    }}
    """

    try:
        # 调用千问模型
        result = call_qwen_with_retry(prompt)
        output_parser = JsonOutputParser()
        result = output_parser.parse(result)
        return result
    except Exception as e:
        print(f"情感分析失败: {e}")
        return {
            "sentiment": "NEUTRAL",
            "confidence": 0.7,
            "key_phrases": []
        }


# 问题分类
def classify_issue(text: str) -> dict:
    """使用千问模型进行问题分类"""
    prompt = f"""
    作为电商客服专家，请对以下客户反馈进行分类：
    「{text}」

    分类选项：
    - 物流问题：配送延迟、物流损坏等
    - 产品质量：商品瑕疵、功能故障等
    - 客户服务：客服态度、响应速度等
    - 支付问题：扣款异常、退款延迟等
    - 退货退款：退货流程、退款金额等
    - 其他：无法归类的反馈

    要求：
    1. 选择最相关的1-2个分类
    2. 按相关性排序

    返回JSON格式：{{"categories": ["分类1", "分类2"]}}
    """

    try:
        # 调用千问模型
        result = call_qwen_with_retry(prompt)
        output_parser = JsonOutputParser()
        result = output_parser.parse(result)
        return result
    except Exception as e:
        print(f"问题分类失败: {e}")
        return {"categories": ["其他"]}


# 紧急状态评估
def assess_urgency(text: str) -> dict:
    """使用千问模型评估紧急程度"""
    prompt = f"""
    作为客服主管，请评估以下客户反馈的紧急程度：
    「{text}」

    评估标准：
    - HIGH(高)：包含"紧急"、"立刻"、"马上"或威胁投诉
    - MEDIUM(中)：表达强烈不满但无立即行动要求
    - LOW(低)：一般反馈或建议

    返回JSON格式：
    {{
        "urgency": "紧急级别",
        "sla_hours": 响应时限(小时),
        "reason": "评估理由"
    }}
    """

    try:
        result = call_qwen_with_retry(prompt)
        output_parser = JsonOutputParser()
        result = output_parser.parse(result)
        # 确保数值类型
        result["sla_hours"] = int(result["sla_hours"])
        return result
    except Exception as e:
        print(f"紧急度评估失败: {e}")
        return {
            "urgency": "MEDIUM",
            "sla_hours": 24,
            "reason": "评估失败"
        }


def generate_response(data: dict) -> dict:
    """使用千问模型生成定制化回复(包含上下文记忆和摘要压缩)"""

    # 1. 获取用户ID，暂时固定使用常量user_id
    # user_id = get_system_user_id()

    # 2. 获取对话历史
    conv_history = redis.get_conversation_history(user_id, max_turns=10)

    # 3. 检查是否需要摘要压缩
    needs_compression = check_token_limit(conv_history, token_threshold=1000)

    if needs_compression and len(conv_history) > 6:
        compressed_summary = compress_history_with_summary(
            conv_history[:-2],
            max_tokens=500
        )
        history_context = f"\n### 历史对话摘要:\n{compressed_summary}\n"
    elif conv_history:
        recent_history = conv_history[-6:]
        history_context = "\n### 最近对话历史:\n" + "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in recent_history
        ]) + "\n"
    else:
        history_context = "\n### 历史对话:\n无\n"

    # 4. 构建增强提示词
    """使用千问模型生成定制化回复"""
    prompt_template = """
    你是一名资深电商客服专家，请根据以下分析结果生成客户回复：

    ### 客户反馈原文：
    {feedback}

    ### 历史对话上下文：
    {history_context}
    
    ### 分析结果：
    - 订单ID：{order_id}
    - 订单状态：{order_status}
    - 情感倾向：{sentiment} (置信度：{confidence:.2f})
    - 问题类型：{categories}
    - 紧急程度：{urgency} (需在{sla_hours}小时内响应)
    {key_phrases_section}

    ### 回复要求：
    1. 结合历史对话上下文,避免重复询问已提供的信息
    2. 根据情感倾向调整语气：
       - 积极反馈：表达感谢，适当赞美
       - 消极反馈：诚恳道歉，明确解决方案
    3. 包含订单ID和问题分类
    4. 明确说明处理时限和后续步骤
    5. 长度100-150字，使用自然口语
    6. 结尾询问是否还有其他问题

    请直接输出回复内容，不需要额外说明。
    """

    # 构建关键短语部分
    key_phrases = data.get("key_phrases", [])
    if key_phrases:
        key_phrases_section = "- 关键要点：" + "，".join(key_phrases[:3])
    else:
        key_phrases_section = ""

    # 订单状态提取
    order_id = data["order_id"]
    order_status = "未找到订单信息"
    if mysql_data.get_order_exist(order_id):
        order_status = mysql_data.get_order_status(order_id)
    else:
        order_status = "未找到订单信息"

    # 填充模板
    prompt = prompt_template.format(
        feedback=data["original_feedback"],
        history_context=history_context,
        order_id=order_id,
        order_status=order_status,
        sentiment=data["sentiment"],
        confidence=data.get("confidence", 0.8),
        categories="、".join(data["categories"]),
        urgency=data["urgency"],
        sla_hours=data["sla_hours"],
        key_phrases_section=key_phrases_section
    )

    try:
        response = call_qwen_with_retry(prompt)

        # 添加紧急标识
        if data["urgency"] == "HIGH":
            response = f"[紧急] {response}"

        # 5. 保存当前对话到历史
        redis.save_conversation(
            user_id=user_id,
            user_message=data["original_feedback"],
            assistant_response=response
        )

        return {
            "final_response": response,
            "assigned_team": data["categories"][0] if data["categories"] else "General",
            "result": data
        }

    except Exception as e:
        print(f"回复生成失败: {e}")
        return {
            "final_response": "感谢您的反馈，我们的团队将尽快处理您的问题。",
            "assigned_team": "General"
        }


################# 构建LCEL处理链 #################

# 步骤1: 基础信息提取
"""
返回的数据格式：
{
  "order_id": {
    "order_id": "ORD2024071501"  # 或 "NOT_FOUND"
  },
  "original_feedback": "原始反馈文本"
}
"""
# lambda 表达式，简化形式，匿名函数的定义
# def fun(x):
#     return x
extract_chain = RunnableParallel(
    order_id=RunnableLambda(extract_order_id),
    original_feedback=lambda x: x
)

# 步骤2: 并行分析任务
# 参数：用户对应的反馈
"""
返回的数据格式：
{
  "sentiment": {
    "sentiment": "NEGATIVE",  # 情感类型
    "confidence": 0.92,       # 置信度
    "key_phrases": ["物流太慢", "承诺三天", "实际七天"]  # 关键短语
  },
  "categories": {
    "categories": ["物流问题"]  # 问题分类
  },
  "urgency": {
    "urgency": "HIGH",        # 紧急程度
    "sla_hours": 4,           # 响应时限(小时)
    "reason": "包含紧急处理要求"  # 评估理由
  }
}
"""
# 节省大模型处理的时间，使用并行处理
analysis_chain = RunnableParallel(
    # 情感分析
    sentiment=RunnableLambda(analyze_sentiment),
    # 问题分类
    categories=RunnableLambda(classify_issue),
    # 紧急程度
    urgency=RunnableLambda(assess_urgency)
)

# 步骤3: 组合完整流程
processing_chain = (
    # 订单提取，正则表达式，异常才会用大模型
        extract_chain
        |
        # 根据输入问题分类，情感分类，紧急程度
        RunnablePassthrough.assign(
            analysis=lambda x: analysis_chain.invoke(x["original_feedback"])
        )
        | {
            "original_feedback": lambda x: x["original_feedback"],
            "order_id": lambda x: x["order_id"]["order_id"],
            "sentiment": lambda x: x["analysis"]["sentiment"].get("sentiment", "NEUTRAL"),
            "confidence": lambda x: x["analysis"]["sentiment"].get("confidence", 0.8),
            "key_phrases": lambda x: x["analysis"]["sentiment"].get("key_phrases", []),
            "categories": lambda x: x["analysis"]["categories"]["categories"],
            "urgency": lambda x: x["analysis"]["urgency"]["urgency"],
            "sla_hours": lambda x: x["analysis"]["urgency"]["sla_hours"],
            "urgency_reason": lambda x: x["analysis"]["urgency"].get("reason", "")
        }
        # 生成答案
        | RunnableLambda(generate_response)
)


# 与前端交互处理LLM响应，这个版本的 gradio 较新，所以不能直接使用元祖形式
def compare(query, show_history):

    print(f"用户查询：{query}")
    print(f"历史对话：{show_history}")

    if len(query) == 0:
        return show_history + [{"role": "user", "content": ""}, {"role": "assistant", "content": ""}]
    try:
        # 显示用户查询和等待提示,"yield" 用于在 Gradio 中逐步返回结果:更新聊天历史显示问答对,并清空输入框
        yield show_history + [{"role": "user", "content": query},
                              {"role": "assistant", "content": "正在为您的问题进行反馈..."}], ""

        # 简单验证：检查是否包含 ORD 开头的订单号
        order_match = re.search(r'ORD\d{10}', query)

        # 如果没有找到订单号，从历史对话中查找，这里可以改造下，把最后一次提到的订单号融入到提示中
        if not order_match:
            has_order_in_history = False
            for msg in show_history:
                if msg['role'] == 'user':
                    if re.search(r'ORD\d{10}', msg['content'][0]['text']):
                        has_order_in_history = True
                        break

            # 如果历史对话中也没有订单号，提示用户输入
            if not has_order_in_history:
                prompt_message = "您好！为了帮您查询订单信息，请提供您的订单号（格式：ORD开头的10位数字）。您可以在留言中包含订单号，我会尽快为您处理问题。"
                yield show_history + [{"role": "user", "content": query},
                                      {"role": "assistant", "content": prompt_message}], ""
                return

        # 调用大模型LLM
        try:
            start = time.time()
            result = processing_chain.invoke(query)
            elapsed = time.time() - start
            print(f"大模型处理完成，耗时: {elapsed:.2f}秒")

            print(f"返回字典为{result}")

            # 返回结果
            yield show_history + [{"role": "user", "content": query},
                                  {"role": "assistant", "content": result["final_response"]}], ""
        except Exception as e:
            print(f"处理失败: {e}")
            logging.error(f"处理失败: {e}")
    except Exception as e:
        print(f"Error: {e}")
        logging.error(f"处理失败: {e}")
        yield show_history + [{"role": "user", "content": query},
                              {"role": "assistant", "content": "AI助手出错,请重试或者检查"}], ""


# 创建Gradio界面
with gr.Blocks(title="## XXX购物平台客服系统") as demo:
    # gr.Markdown("## XXX购物平台客服系统")

    with gr.Row():
        with gr.Column(scale=10):
            chatbot = gr.Chatbot(height=650)  # 空初始值

    with gr.Row():
        msg = gr.Textbox(label="输入", placeholder="请问您有什么需要我做的呢？")

    with gr.Row():
        examples = gr.Examples(
            examples=[
                '发什么快递呢？',
                '多久能发货呢？',
                '保质期多久呢？',
                '耗材多久换一次？',
                '我买多个可以议价吗？'
            ],
            inputs=[msg]
        )

    clear = gr.ClearButton([chatbot, msg])
    msg.submit(compare, [msg, chatbot], [chatbot, msg])

    # demo.launch()

if __name__ == "__main__":
    demo.launch(server_port=7778)