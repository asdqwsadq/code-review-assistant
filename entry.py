#!/usr/bin/env python3
"""
Code Review Assistant MCP stdio entry point.
Reads JSON-RPC messages from stdin and writes responses to stdout.
"""

import asyncio
import json
import sys

from server import handle_message


async def main():
    """Main loop: read JSON-RPC messages from stdin, process, write to stdout."""
    # Signal readiness
    sys.stderr.write("code-review-assistant MCP server starting...\n")
    sys.stderr.flush()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            line = line.strip()
            if not line:
                continue
            
            message = json.loads(line)
            response = await handle_message(message)
            
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON parse error: {e}\n")
            sys.stderr.flush()
        except EOFError:
            break
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()
    
    sys.stderr.write("code-review-assistant MCP server shutting down.\n")
    sys.stderr.flush()


if __name__ == "__main__":
    asyncio.run(main())
