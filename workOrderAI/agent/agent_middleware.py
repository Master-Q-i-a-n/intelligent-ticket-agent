from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, wrap_model_call, after_model, before_model, after_agent, \
    before_agent
from langgraph.runtime import Runtime

from workOrderAI.agent.agent_context import record_tool_call
from workOrderAI.utils.logger_handler import logger


@before_agent
def log_before_agent(status: AgentState, runtime: Runtime):
    """agent 运行前执行此函数"""
    logger.debug(f"[before_agent] agent启动， 输入：{type(status['messages'][-1]).__name__} | {status['messages'][-1].content.strip()}， 共{len(status['messages'])}条消息")


@after_agent
def log_after_agent(status: AgentState, runtime: Runtime):
    """agent 运行后执行此函数"""
    logger.debug(f"[after_agent] agent运行结束， 输出：{type(status['messages'][-1]).__name__} | {status['messages'][-1].content.strip()}， 共{len(status['messages'])}条消息")

@before_model
def log_before_model(status: AgentState, runtime: Runtime):
    """model 运行前执行此函数"""
    logger.debug(f"[before_model] model启动， 输入：{type(status['messages'][-1]).__name__} | {status['messages'][-1].content.strip()}， 共{len(status['messages'])}条消息")


@after_model
def log_after_model(status: AgentState, runtime: Runtime):
    """model 运行后执行此函数"""
    logger.debug(f"[after_model] model运行结束， 输出：{type(status['messages'][-1]).__name__} | {status['messages'][-1].content.strip()} 共{len(status['messages'])}条消息")

@wrap_model_call
async def model_call_hook(request, handler):
    """model 调用中执行此函数"""
    logger.debug("模型调用中")
    return await handler(request)

@wrap_tool_call
async def tool_call_hook(request, handler):
    """tool 调用中执行此函数"""
    logger.debug(f"工具{request.tool_call['name']}调用中, 传入参数{request.tool_call['args']}")
    try:
        result = await handler(request)
    except Exception as exc:
        record_tool_call(request.tool_call["name"], request.tool_call["args"], f"ERROR: {exc}")
        raise
    record_tool_call(request.tool_call["name"], request.tool_call["args"], result)
    return result


def get_middleware():
    """返回本模块的所有中间件"""
    return [
        log_before_agent,
        log_after_agent,
        log_before_model,
        log_after_model,
        model_call_hook,
        tool_call_hook,
    ]
