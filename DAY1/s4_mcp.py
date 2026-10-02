import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ALLOWED_DIR = r"C:\Users\kashish\agentic-ai\mcp_test"

server_params = StdioServerParameters(
    command="npx",
    args=[
        "-y",
        "@modelcontextprotocol/server-filesystem",
        ALLOWED_DIR
    ]
)


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("AVAILABLE TOOLS:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")

            print("\n--- CALL 1: list_directory ---")

            result1 = await session.call_tool(
                "list_directory",
                {"path": ALLOWED_DIR}
            )

            print(result1)

            print("\n--- CALL 2: read_text_file ---")

            result2 = await session.call_tool(
                "read_text_file",
                {
                    "path": f"{ALLOWED_DIR}\\test.txt"
                }
            )

            text = result2.content[0].text
            print(text)

            print("\n--- CALL 3: get_file_info ---")

            result3 = await session.call_tool(
                "get_file_info",
                {
                    "path": f"{ALLOWED_DIR}\\test.txt"
                }
            )

            print(result3)


if __name__ == "__main__":
    asyncio.run(main())
