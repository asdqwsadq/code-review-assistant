"""
Code Review Assistant MCP Server
MCP stdio protocol implementation for code review using MiMo API.
"""

import json
import os
import sys
import traceback

import httpx

# --- Configuration ---

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "tp-c6w5jsmi9x28pgwhuq8gh9bshuib12qx7f3brwc80orthn51")
MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

# --- Tool Definition ---

TOOL_REVIEW_CODE = {
    "name": "review_code",
    "description": "审查代码 - 分析代码质量，发现安全漏洞、性能问题和代码风格问题",
    "inputSchema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "待审查的代码片段"
            },
            "language": {
                "type": "string",
                "description": "编程语言 (e.g., python, javascript, go, rust)",
                "default": "python"
            },
            "focus": {
                "type": "string",
                "description": "审查重点",
                "enum": ["all", "security", "performance", "style"],
                "default": "all"
            }
        },
        "required": ["code"]
    }
}

TOOLS = [TOOL_REVIEW_CODE]


def build_prompt(code: str, language: str, focus: str) -> str:
    """Build the system and user prompt for the code review."""
    
    focus_instructions = {
        "all": "全面审查代码，覆盖安全、性能、风格和改进建议四个方面。",
        "security": "重点关注**安全漏洞**：SQL注入、XSS、命令注入、硬编码密钥、不安全的反序列化、路径遍历、权限绕过等。",
        "performance": "重点关注**性能优化**：低效算法、不必要的内存分配、冗余计算、I/O瓶颈、缓存缺失、并发问题等。",
        "style": "重点关注**代码风格**：命名规范、代码格式、可读性、设计模式、一致性等。"
    }
    
    instruction = focus_instructions.get(focus, focus_instructions["all"])
    
    system_prompt = f"""你是一个专业的代码审查助手。请按照以下JSON格式输出审查结果，不要包含其他内容。

{instruction}

输出格式（严格JSON）：
{{
  "summary": "总体评价（1-2句话）",
  "issues": [
    {{
      "type": "security" | "performance" | "style" | "improvement",
      "severity": "critical" | "major" | "minor" | "info",
      "line": 行号（如无法确定则填null）,
      "message": "问题描述（中文）",
      "suggestion": "修复建议（中文）",
      "code_example": "示例代码（可选）"
    }}
  ],
  "score": 0-100的分数
}}"""

    user_prompt = f"""请审查以下{language}代码：

```{language}
{code}
```"""

    return system_prompt, user_prompt


async def call_mimo_api(system_prompt: str, user_prompt: str) -> str:
    """Call the MiMo API for code review."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        headers = {
            "Authorization": f"Bearer {MIMO_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": MIMO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        response = await client.post(
            f"{MIMO_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def parse_review_result(content: str) -> dict:
    """Parse the LLM response into a structured review result."""
    # Try to extract JSON from the response
    content = content.strip()
    
    # Find JSON block
    if content.startswith("```"):
        lines = content.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            content = "\n".join(json_lines)
    
    # Clean up
    content = content.strip()
    
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # If parsing fails, wrap the raw response
        return {
            "summary": "代码审查完成（解析响应时出现问题）",
            "issues": [
                {
                    "type": "improvement",
                    "severity": "info",
                    "line": None,
                    "message": "原始审查结果",
                    "suggestion": content,
                }
            ],
            "score": 50,
        }


async def handle_tool_call(params: dict) -> dict:
    """Handle a tools/call request for review_code."""
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    
    if name != "review_code":
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
    
    code = arguments.get("code", "")
    language = arguments.get("language", "python")
    focus = arguments.get("focus", "all")
    
    if not code.strip():
        return {
            "content": [{"type": "text", "text": "错误：代码内容不能为空"}],
            "isError": True,
        }
    
    try:
        system_prompt, user_prompt = build_prompt(code, language, focus)
        raw_result = await call_mimo_api(system_prompt, user_prompt)
        review = parse_review_result(raw_result)
        
        return {
            "content": [{"type": "text", "text": json.dumps(review, ensure_ascii=False, indent=2)}],
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"代码审查请求失败：{str(e)}\n\n{traceback.format_exc()}"}],
            "isError": True,
        }


async def handle_message(message: dict) -> dict | None:
    """Handle a single JSON-RPC message."""
    method = message.get("method", "")
    msg_id = message.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "code-review-assistant",
                    "version": "1.0.0"
                }
            }
        }
    
    elif method == "notifications/initialized":
        return None
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": TOOLS
            }
        }
    
    elif method == "tools/call":
        result = await handle_tool_call(message.get("params", {}))
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }
