import asyncio

import httpx
from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="amadeus_visualizer",
    description="基于ModelScope的图像生成插件",
    usage="发送 /visualize <prompt> 生成图像",
    config=Config,
)

config = get_plugin_config(Config)

visualize = on_command("visualize", aliases={"生成图像", "绘图", "generate"}, priority=5, block=True)


@visualize.handle()
async def handle_visualize(event: MessageEvent, matcher: Matcher, args: Message = CommandArg()):
    prompt = args.extract_plain_text().strip()
    if not prompt:
        await matcher.finish("请提供图像描述，例如：/visualize 一只金色的猫")

    if not config.modelscope_api_key:
        await matcher.finish("ModelScope API Key 未配置，请联系管理员")

    await matcher.send("正在生成图像，请耐心等待...")

    try:
        image_bytes = await generate_image(prompt)
        await matcher.send(MessageSegment.reply(event.message_id) + MessageSegment.image(image_bytes))
    except httpx.HTTPStatusError as e:
        logger.error(f"ModelScope API 请求失败: {e.response.status_code}")
        await matcher.send(MessageSegment.reply(event.message_id) + f"图像生成失败：API 请求错误 ({e.response.status_code})")
    except TimeoutError:
        await matcher.send(MessageSegment.reply(event.message_id) + "图像生成超时，请稍后重试")
    except Exception as e:
        logger.error(f"图像生成失败: {e}")
        await matcher.send(MessageSegment.reply(event.message_id) + f"图像生成失败：{e}")


async def generate_image(prompt: str) -> bytes:
    base_url = config.modelscope_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {config.modelscope_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        resp = await client.post(
            f"{base_url}/v1/images/generations",
            headers={**headers, "X-ModelScope-Async-Mode": "true"},
            json={"model": config.modelscope_model_id, "prompt": prompt},
        )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        logger.info(f"图像生成任务已提交: {task_id}, prompt: {prompt}")

        for _ in range(60):
            await asyncio.sleep(5)
            result = await client.get(
                f"{base_url}/v1/tasks/{task_id}",
                headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
            )
            result.raise_for_status()
            data = result.json()

            if data["task_status"] == "SUCCEED":
                image_url = data["output_images"][0]
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
                return img_resp.content
            elif data["task_status"] == "FAILED":
                raise RuntimeError("图像生成任务失败")

        raise TimeoutError("图像生成超时")

